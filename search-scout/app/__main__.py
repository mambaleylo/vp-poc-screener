"""Командная строка Search Scout.

python -m app                 запустить Telegram-бота (то же, что `bot`)
python -m app scan            одно сканирование в текущем режиме
python -m app import-csv FILE импорт CSV (по умолчанию как тестовые данные)
python -m app report          напечатать отчёт в терминал
python -m app export FILE     выгрузить результаты в CSV
python -m app check-wordstat  проверить доступ к Wordstat одним запросом
python -m app regions         показать ID регионов Wordstat
python -m app migrate         создать/обновить базу
"""

from __future__ import annotations

import argparse
import asyncio
import html
import logging
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from app.config import ModeUnavailableError, Settings, get_settings
from app.logging_setup import setup_logging
from app.single_instance import AlreadyRunningError, SingleInstanceLock


def _plain(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text))


def _writer_lock(settings: Settings) -> SingleInstanceLock:
    from app.main import lock_path

    lock = SingleInstanceLock(lock_path(settings))
    try:
        lock.acquire()
    except AlreadyRunningError:
        raise SystemExit(
            "Бот сейчас запущен. Используйте команды в Telegram (/scan, отправка CSV с /import) "
            "или остановите бота."
        ) from None
    return lock


def cmd_scan(settings: Settings) -> int:
    from app.context import build_context

    with _writer_lock(settings):
        ctx = build_context(settings)
        try:
            summary = asyncio.run(ctx.scan_service.run("cli"))
        except ModeUnavailableError as exc:
            print(exc)
            return 2
    print(
        f"Сканирование #{summary.run_id}: {summary.status} ({summary.mode}), {summary.duration_s} с"
    )
    for key, value in summary.stats.items():
        print(f"  {key}: {value}")
    return 0 if summary.status != "failed" else 1


def cmd_import(settings: Settings, path: Path, real: bool, source: str | None) -> int:
    from app.context import build_context
    from app.sources.csv_source import CsvSource

    with _writer_lock(settings):
        ctx = build_context(settings)
        csv_source = CsvSource(
            path, is_demo=not real, default_region=settings.region_key, source_name=source
        )
        result = csv_source.load()
        for error in result.errors[:20]:
            print(f"  ! {error}")
        if not result.observations:
            print("Нечего импортировать.")
            return 1
        summary = asyncio.run(
            ctx.scan_service.import_observations(result.observations, is_demo=not real)
        )
    kind = "реальные" if real else "ТЕСТОВЫЕ"
    print(
        f"Импортировано {len(result.observations)} из {result.rows_total} строк ({kind} данные). "
        f"Новых фраз: {summary.stats.get('new_phrases', 0)}, "
        f"в топе: {summary.stats.get('top', 0)}, "
        f"в наблюдении: {summary.stats.get('watch', 0)}"
    )
    return 0


def cmd_report(settings: Settings) -> int:
    from app.context import build_context

    ctx = build_context(settings)
    today = datetime.now(UTC).astimezone(settings.tz).date()
    for message in ctx.reports.daily_report(today):
        print(_plain(message))
        print()
    return 0


def cmd_export(settings: Settings, path: Path) -> int:
    from app.context import build_context

    ctx = build_context(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(ctx.reports.export_csv())
    print(f"Сохранено: {path}")
    return 0


def cmd_check_wordstat(settings: Settings, phrase: str) -> int:
    from app.sources.base import SourceError
    from app.sources.wordstat import WordstatSource

    if not settings.wordstat_configured:
        print("Wordstat не настроен: заполните WORDSTAT_API_KEY и WORDSTAT_FOLDER_ID в .env")
        return 2

    async def run() -> int:
        source = WordstatSource(settings)
        try:
            observations = await source.related(phrase, None)
        except SourceError as exc:
            print(f"Ошибка: {exc}")
            return 1
        finally:
            await source.aclose()
        print(f"OK: получено {len(observations)} фраз по «{phrase}» (последние 30 дней):")
        for obs in observations[:15]:
            count = "нет данных" if obs.count is None else obs.count
            print(f"  {obs.phrase} — {count}")
        return 0

    return asyncio.run(run())


def cmd_regions(settings: Settings) -> int:
    from app.sources.base import SourceError
    from app.sources.wordstat import WordstatSource

    if not settings.wordstat_configured:
        print("Wordstat не настроен. Частые ID: 225 — Россия, 149 — Беларусь, 159 — Казахстан.")
        return 2

    async def run() -> int:
        source = WordstatSource(settings)
        try:
            data = await source.regions_tree()
        except SourceError as exc:
            print(f"Ошибка: {exc}")
            return 1
        finally:
            await source.aclose()

        def walk(nodes: list[dict], depth: int) -> None:
            for node in nodes or []:
                print("  " * depth + f"{node.get('id')}: {node.get('label')}")
                if depth < 1:
                    walk(node.get("children") or [], depth + 1)

        walk(data.get("regions") or [], 0)
        return 0

    return asyncio.run(run())


def cmd_migrate(settings: Settings) -> int:
    from app.storage.database import init_database
    from app.storage.migrations import LATEST_VERSION

    init_database(settings.db_file)
    print(f"База {settings.db_file}: схема v{LATEST_VERSION}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app", description="Search Scout")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("bot", help="запустить Telegram-бота")
    sub.add_parser("scan", help="одно сканирование")
    p_import = sub.add_parser("import-csv", help="импорт CSV")
    p_import.add_argument("path", type=Path)
    p_import.add_argument("--real", action="store_true", help="данные реальные (не тестовые)")
    p_import.add_argument("--source", help="название источника, например wordstat-manual")
    sub.add_parser("report", help="напечатать отчёт")
    p_export = sub.add_parser("export", help="выгрузить CSV")
    p_export.add_argument("path", type=Path)
    p_check = sub.add_parser("check-wordstat", help="проверить доступ к Wordstat")
    p_check.add_argument("--phrase", default="конвертер pdf")
    sub.add_parser("regions", help="ID регионов Wordstat")
    sub.add_parser("migrate", help="создать/обновить базу")
    args = parser.parse_args(argv)

    try:
        settings = get_settings()
    except ValidationError as exc:
        print("Ошибка в настройках (.env):")
        for err in exc.errors():
            field = ".".join(str(x) for x in err["loc"]).upper()
            print(f"  {field}: {err['msg']}")
        return 2
    setup_logging(settings.log_level, settings.secret_values())

    command = args.command or "bot"
    if command == "bot":
        from app.main import main as run_bot_main

        try:
            run_bot_main(settings)
        except AlreadyRunningError as exc:
            print(exc)
            return 1
        except KeyboardInterrupt:
            pass
        return 0
    if command == "scan":
        return cmd_scan(settings)
    if command == "import-csv":
        return cmd_import(settings, args.path, args.real, args.source)
    if command == "report":
        return cmd_report(settings)
    if command == "export":
        return cmd_export(settings, args.path)
    if command == "check-wordstat":
        return cmd_check_wordstat(settings, args.phrase)
    if command == "regions":
        return cmd_regions(settings)
    if command == "migrate":
        return cmd_migrate(settings)
    parser.print_help()
    return 2


if __name__ == "__main__":
    logging.captureWarnings(True)
    sys.exit(main())
