"""Команды Telegram-бота.

Обработчики не выполняют произвольный код, SQL или команды из сообщений:
каждая команда вызывает заранее определённую операцию. Доступ проверяется
middleware (access.py) до того, как сообщение попадёт сюда.
"""

from __future__ import annotations

import asyncio
import io
import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import BotCommand, BufferedInputFile, Message

from app.config import ModeUnavailableError, region_label
from app.context import AppContext
from app.services.collector import ScanSummary
from app.services.report import STATUS_LABELS, esc, mode_line, scan_line, split_messages
from app.sources.csv_source import parse_csv_bytes
from app.storage.repository import ScanAlreadyRunningError

log = logging.getLogger(__name__)
router = Router(name="search_scout")

MAX_CSV_BYTES = 5 * 1024 * 1024

COMMANDS = [
    BotCommand(command="report", description="Последний отчёт"),
    BotCommand(command="top", description="Лучшие текущие возможности"),
    BotCommand(command="watchlist", description="Новые фразы под наблюдением"),
    BotCommand(command="scan", description="Запустить сканирование"),
    BotCommand(command="status", description="Состояние и источники"),
    BotCommand(command="settings", description="Текущие настройки"),
    BotCommand(command="daily_on", description="Включить ежедневный отчёт"),
    BotCommand(command="daily_off", description="Выключить ежедневный отчёт"),
    BotCommand(command="export", description="Выгрузка результатов в CSV"),
    BotCommand(command="help", description="Справка"),
]

HELP_TEXT = """<b>Search Scout</b> ищет в поисковом спросе гипотезы для микросервисов, ботов и SaaS.

<b>Команды</b>
/report — отчёт по последнему сканированию
/top — лучшие возможности с подтверждённой динамикой
/watchlist — новые фразы без истории (наблюдение)
/scan — запустить сканирование сейчас
/status — режим, последний запуск, источники
/settings — текущие настройки
/daily_on, /daily_off — ежедневный отчёт
/export — все результаты в CSV
/help — эта справка

<b>Импорт CSV</b>: отправьте файл .csv с подписью <code>/import</code> (данные будут помечены \
как тестовые) или <code>/import real</code> (реальные данные, например ручная выгрузка).

<i>Бот не выдумывает статистику: если данных нет, он так и пишет. Рейтинг — эвристика, \
а не прогноз прибыли.</i>"""


RUN_MODE_LABELS = {
    "live": "Режим: Live (Яндекс Wordstat)",
    "demo": "Режим: Demo/CSV — тестовые данные",
    "csv": "Импорт реальных данных из CSV",
}


async def answer_all(message: Message, texts: list[str]) -> None:
    for text in texts:
        await message.answer(text, disable_web_page_preview=True)


async def touch_user(message: Message, ctx: AppContext) -> None:
    if message.from_user is None:
        return
    await asyncio.to_thread(
        ctx.repo.ensure_user,
        message.from_user.id,
        message.chat.id,
        ctx.settings.daily_default_enabled,
        ctx.clock(),
    )


def format_summary(summary: ScanSummary) -> str:
    st = summary.stats
    lines = [
        f"<b>Сканирование #{summary.run_id}</b>: "
        f"{esc(STATUS_LABELS.get(summary.status, summary.status))}"
        f" за {summary.duration_s:.0f} с",
        esc(RUN_MODE_LABELS.get(summary.mode, summary.mode)),
    ]
    if "seeds_requested" in st:
        lines.append(
            f"Запросов к источнику по сидам: {st.get('seeds_requested', 0)} "
            f"(ошибок: {st.get('seeds_failed', 0)}), динамика: {st.get('dynamics_requested', 0)}"
        )
    lines.append(
        f"Наблюдений: {st.get('observations', 0)}, по тематикам: {st.get('relevant', 0)}, "
        f"новых фраз: {st.get('new_phrases', 0)}"
    )
    if st.get("filtered"):
        filtered = ", ".join(f"{k} — {v}" for k, v in st["filtered"].items())
        lines.append(f"Отброшено: {esc(filtered)}")
    lines.append(
        f"Оценено: {st.get('scored', 0)} → топ: {st.get('top', 0)}, наблюдение: "
        f"{st.get('watch', 0)}, отклонено: {st.get('rejected', 0)}"
    )
    if summary.errors:
        lines.append("Ошибки: " + esc("; ".join(summary.errors[:3])))
    lines.append("Отчёт: /report · топ: /top · наблюдение: /watchlist")
    return "\n".join(lines)


# ------------------------------------------------------------------ команды


@router.message(CommandStart())
async def cmd_start(message: Message, ctx: AppContext) -> None:
    await touch_user(message, ctx)
    await message.answer(HELP_TEXT)


@router.message(Command("help"))
async def cmd_help(message: Message, ctx: AppContext) -> None:
    await message.answer(HELP_TEXT)


@router.message(Command("scan"))
async def cmd_scan(message: Message, ctx: AppContext) -> None:
    if ctx.scan_service.is_running:
        await message.answer("Сканирование уже идёт — дождитесь результата.")
        return
    try:
        mode = ctx.settings.resolve_mode()
    except ModeUnavailableError as exc:
        await message.answer(esc(str(exc)))
        return
    await message.answer(
        f"Запускаю сканирование ({esc(mode_line(mode, ctx.settings.dataset_is_demo(mode)))}). "
        "Пришлю итог, когда закончу."
    )

    async def run() -> None:
        try:
            summary = await ctx.scan_service.run("manual")
        except ScanAlreadyRunningError:
            await message.answer("Сканирование уже идёт — дождитесь результата.")
            return
        except ModeUnavailableError as exc:
            await message.answer(esc(str(exc)))
            return
        await message.answer(format_summary(summary))

    ctx.spawn(run())


@router.message(Command("report"))
async def cmd_report(message: Message, ctx: AppContext) -> None:
    today = ctx.clock().astimezone(ctx.settings.tz).date()
    await answer_all(message, await asyncio.to_thread(ctx.reports.daily_report, today))


@router.message(Command("top"))
async def cmd_top(message: Message, ctx: AppContext) -> None:
    await answer_all(message, await asyncio.to_thread(ctx.reports.top_report))


@router.message(Command("watchlist"))
async def cmd_watchlist(message: Message, ctx: AppContext) -> None:
    await answer_all(message, await asyncio.to_thread(ctx.reports.watchlist_report))


@router.message(Command("daily_on"))
async def cmd_daily_on(message: Message, ctx: AppContext) -> None:
    await touch_user(message, ctx)
    await asyncio.to_thread(ctx.repo.set_daily, message.from_user.id, True)  # type: ignore[union-attr]
    await message.answer(
        f"Ежедневный отчёт включён: каждый день в {ctx.settings.daily_time} "
        f"({esc(ctx.settings.timezone)})."
    )


@router.message(Command("daily_off"))
async def cmd_daily_off(message: Message, ctx: AppContext) -> None:
    await touch_user(message, ctx)
    await asyncio.to_thread(ctx.repo.set_daily, message.from_user.id, False)  # type: ignore[union-attr]
    await message.answer("Ежедневный отчёт выключен. Включить снова: /daily_on")


@router.message(Command("settings"))
async def cmd_settings(message: Message, ctx: AppContext) -> None:
    s = ctx.settings
    user = await asyncio.to_thread(ctx.repo.get_user, message.from_user.id)  # type: ignore[union-attr]
    w = s.weights
    text = "\n".join(
        [
            "<b>Настройки</b> (меняются в файле .env, затем перезапуск)",
            f"Режим: {esc(s.scout_mode)} (SCOUT_MODE)",
            f"Регион: {esc(region_label(s.region_key))} (WORDSTAT_REGIONS={esc(s.region_key)})",
            f"Устройства: {esc(s.devices_key)}",
            f"Ежедневный отчёт: {s.daily_time} {esc(s.timezone)}; у вас "
            f"{'включён' if user and user.daily_enabled else 'выключен'}",
            f"Лимит запросов к Wordstat за скан: {s.wordstat_max_requests_per_scan} "
            f"(из них динамика: {s.wordstat_dynamics_per_scan}), {s.wordstat_rps} запр./с",
            f"Веса рейтинга: динамика {w['trend']:.2f}, намерение {w['commercial']:.2f}, "
            f"проблема {w['problem']:.2f}, новизна {w['novelty']:.2f}",
            f"Порог топа: {s.top_min_score:.0f}; "
            f"мин. объём для динамики: {s.min_monthly_volume}/мес.",
            f"Тематик: {len(ctx.topics.topics)} (файл {esc(s.topics_path)})",
            f"CSV: {esc(s.csv_import_path or 'не задан')} "
            f"({'тестовые' if s.csv_is_demo else 'реальные'})",
        ]
    )
    await message.answer(text)


@router.message(Command("status"))
async def cmd_status(message: Message, ctx: AppContext) -> None:
    s = ctx.settings
    try:
        mode = s.resolve_mode()
        is_demo = s.dataset_is_demo(mode)
        mode_text = mode_line(mode, is_demo)
    except ModeUnavailableError as exc:
        mode_text, is_demo = str(exc), False
    run = await asyncio.to_thread(ctx.repo.last_scan_run)
    counts = await asyncio.to_thread(ctx.repo.opportunity_counts, s.region_key, is_demo)
    phrases = await asyncio.to_thread(ctx.repo.phrase_count, is_demo)
    seeds = await asyncio.to_thread(ctx.repo.seed_stats)
    next_run = ctx.scheduler.next_run_time() if ctx.scheduler else None
    lines = [
        "<b>Статус</b>",
        esc(mode_text),
        "Wordstat: "
        + ("настроен" if s.wordstat_configured else "не настроен (нет ключа или ID каталога)"),
        f"CSV: {esc(s.csv_file) if s.csv_file else 'не задан'}"
        + (
            " (найден)"
            if s.csv_file and s.csv_file.exists()
            else " (файла нет)"
            if s.csv_file
            else ""
        ),
        esc(scan_line(run, s.tz)),
    ]
    if run and run.error:
        lines.append(f"Ошибка последнего запуска: {esc(run.error[:300])}")
    if ctx.scan_service.is_running:
        lines.append("Сейчас выполняется сканирование.")
    lines += [
        f"Фраз в базе: {phrases}; топ: {counts.get('top', 0)}, "
        f"наблюдение: {counts.get('watch', 0)}, "
        f"отклонено: {counts.get('rejected', 0)}",
        f"Сиды: {seeds['total']} (ещё не опрошены: {seeds['never_scanned']}, "
        f"из расширения: {seeds['expansion']})",
        "Следующий ежедневный запуск: "
        + (f"{next_run.astimezone(s.tz):%d.%m.%Y %H:%M}" if next_run else "не запланирован"),
    ]
    await message.answer("\n".join(lines))


@router.message(Command("export"))
async def cmd_export(message: Message, ctx: AppContext) -> None:
    data = await asyncio.to_thread(ctx.reports.export_csv)
    stamp = ctx.clock().astimezone(ctx.settings.tz).strftime("%Y%m%d_%H%M")
    await message.answer_document(
        BufferedInputFile(data, filename=f"search_scout_{stamp}.csv"),
        caption="Все оценённые фразы (топ, наблюдение, отклонённые). Разделитель — «;».",
    )


@router.message(Command("import"), F.document)
async def cmd_import(message: Message, command: CommandObject, ctx: AppContext) -> None:
    document = message.document
    assert document is not None
    if not (document.file_name or "").lower().endswith(".csv"):
        await message.answer("Нужен файл с расширением .csv")
        return
    if document.file_size and document.file_size > MAX_CSV_BYTES:
        await message.answer("Файл больше 5 МБ — импортируйте его командой в терминале.")
        return
    is_demo = (command.args or "").strip().lower() != "real"
    buffer = io.BytesIO()
    await message.bot.download(document, destination=buffer)  # type: ignore[union-attr]
    result = await asyncio.to_thread(
        parse_csv_bytes,
        buffer.getvalue(),
        is_demo=is_demo,
        default_region=ctx.settings.region_key,
        default_source="csv-demo" if is_demo else "csv",
        today=ctx.clock().date(),
    )
    if not result.observations:
        await message.answer("Не удалось импортировать: " + esc("; ".join(result.errors[:5])))
        return
    try:
        summary = await ctx.scan_service.import_observations(result.observations, is_demo=is_demo)
    except ScanAlreadyRunningError:
        await message.answer("Сейчас идёт сканирование — пришлите файл чуть позже.")
        return
    lines = [
        f"Импортировано строк: {len(result.observations)} из {result.rows_total} "
        f"({'тестовые данные' if is_demo else 'реальные данные'}).",
    ]
    if result.errors:
        lines.append("Пропущено: " + esc("; ".join(result.errors[:5])))
    note = ""
    try:
        if ctx.settings.dataset_is_demo(ctx.settings.resolve_mode()) != is_demo:
            note = (
                "Внимание: текущий режим показывает другой набор данных, поэтому эти фразы "
                "не появятся в /top, пока режим не совпадёт (см. /settings)."
            )
    except ModeUnavailableError:
        pass
    lines.append(format_summary(summary))
    if note:
        lines.append(note)
    await answer_all(message, split_messages(lines))


@router.message(F.document)
async def on_document(message: Message) -> None:
    await message.answer(
        "Чтобы импортировать CSV, отправьте файл с подписью /import или /import real"
    )


@router.message()
async def on_unknown(message: Message) -> None:
    await message.answer("Не знаю такой команды. Список команд: /help")
