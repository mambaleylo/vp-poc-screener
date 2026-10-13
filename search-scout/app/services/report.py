"""Тексты отчётов для Telegram (HTML) и экспорт в CSV."""

from __future__ import annotations

import csv
import html
import io
from datetime import date
from zoneinfo import ZoneInfo

from app.config import Mode, ModeUnavailableError, Settings, region_label
from app.services.ideas import (
    COMPETITION_UNKNOWN,
    missing_data,
    next_steps,
    product_idea,
    search_url,
    wordstat_url,
)
from app.services.intent import INTENT_LABELS, Intent
from app.services.scorer import CONFIDENCE_LABELS
from app.storage.repository import OpportunityView, Repository, ScanRunView
from app.topics import TopicsConfig

TELEGRAM_LIMIT = 3900  # запас до лимита 4096 символов

SOURCE_LABELS = {
    "wordstat": "Яндекс Wordstat (API)",
    "csv-demo": "CSV (тестовые данные)",
    "csv": "CSV",
    "demo-synthetic": "синтетические тестовые данные",
}

STATUS_LABELS = {
    "success": "успешно",
    "partial": "частично (были ошибки)",
    "failed": "ошибка",
    "running": "выполняется",
    "interrupted": "прервано",
}

DEMO_BANNER = "🧪 <b>ТЕСТОВЫЕ ДАННЫЕ</b> — это не рыночная статистика, а пример для проверки бота."
DISCLAIMER = (
    "<i>Рейтинг — эвристика для сортировки гипотез, а не прогноз прибыли. Спрос ≠ готовность "
    "платить. Выручку, число клиентов и конкуренцию бот не оценивает.</i>"
)


def esc(value: object) -> str:
    return html.escape(str(value), quote=False)


def fmt_int(value: int | float | None) -> str:
    if value is None:
        return "нет данных"
    return f"{int(value):,}".replace(",", " ")


def dedupe_groups(items: list[OpportunityView]) -> list[OpportunityView]:
    """Оставляет лучшую фразу из каждой группы близких формулировок."""
    seen: set[str] = set()
    result = []
    for item in items:
        if item.group_key in seen:
            continue
        seen.add(item.group_key)
        result.append(item)
    return result


def trend_text(data_used: dict) -> str:
    trend = data_used.get("trend") or {}
    status = trend.get("status")
    if status == "insufficient_history":
        return "недостаточно истории"
    if status == "low_volume":
        return "объём ниже порога — динамика не оценивается"
    if status != "ok" or trend.get("growth_ratio") is None:
        return "нет данных"
    pct = (trend["growth_ratio"] - 1) * 100
    text = f"{pct:+.0f}% ({trend.get('window')})"
    if trend.get("spike"):
        text += ", разовый всплеск"
    if trend.get("seasonal"):
        text += f", сезонное изменение (год к году {(trend['yoy_ratio'] - 1) * 100:+.0f}%)"
    elif trend.get("seasonal") is None:
        text += ", сезонность не проверена"
    return text


def sources_text(data_used: dict) -> str:
    sources = data_used.get("sources") or []
    return ", ".join(SOURCE_LABELS.get(s, s) for s in sources) or "нет данных"


def format_item(
    index: int, item: OpportunityView, topics: TopicsConfig, detailed: bool = True
) -> str:
    data = item.data_used
    topic = topics.by_key(item.topic_key) if item.topic_key else None
    try:
        intent_label = INTENT_LABELS[Intent(data.get("intent"))]
    except ValueError:
        intent_label = "не определено"
    kind = "предварительный" if item.is_preliminary else "полный"
    count = data.get("latest_count")
    count_text = (
        f"{fmt_int(count)} ({esc(data.get('latest_period'))})"
        if count is not None
        else "нет данных"
    )
    lines = [
        f"<b>{index}. {esc(item.original)}</b>" + (" 🧪" if item.is_demo else ""),
        f"• Источник: {esc(sources_text(data))}",
        f"• Регион: {esc(region_label(item.region_key))}",
        f"• Частотность: {count_text}",
        f"• Динамика: {esc(trend_text(data))}",
        f"• Коммерческое намерение: {esc(intent_label)} "
        f"({item.components['commercial']['value']:.0f}/100, по формулировке)",
        f"• Рейтинг: <b>{item.total:.0f}/100</b>, {kind}; уверенность "
        f"{CONFIDENCE_LABELS.get(item.confidence, item.confidence)}",
    ]
    if detailed:
        why = "; ".join(item.reasons) or item.status_reason
        problem_note = item.components["problem"].get("note") or ""
        steps = next_steps(data, item.is_preliminary)
        hint = topic.product_hint if topic else None
        lines += [
            f"• Почему интересна: {esc(why)}",
            f"• Возможная проблема: {esc(problem_note)}",
            f"• Возможный продукт: {esc(product_idea(data.get('intent', ''), hint))}",
            f"• Конкуренция: {COMPETITION_UNKNOWN}",
            f"• Не хватает данных: {esc(', '.join(missing_data(data)))}",
            f"• Что проверить дальше: {esc(steps[0])}",
            f'• <a href="{esc(wordstat_url(item.normalized, item.region_key))}">Wordstat</a> · '
            f'<a href="{esc(search_url(item.normalized))}">выдача Яндекса</a>',
        ]
    else:
        lines.append(f"• Статус: {esc(item.status_reason)}")
    return "\n".join(lines)


def split_messages(blocks: list[str], limit: int = TELEGRAM_LIMIT) -> list[str]:
    """Склеивает блоки в сообщения не длиннее лимита Telegram."""
    messages: list[str] = []
    current = ""
    for block in blocks:
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            messages.append(current)
        while len(block) > limit:  # на всякий случай: очень длинный блок
            messages.append(block[:limit])
            block = block[limit:]
        current = block
    if current:
        messages.append(current)
    return messages


def mode_line(mode: Mode, is_demo: bool) -> str:
    if mode == "live":
        return "Режим: Live (Яндекс Wordstat)"
    return "Режим: Demo/CSV" + (" — тестовые данные" if is_demo else " — данные из CSV")


def scan_line(run: ScanRunView | None, tz: ZoneInfo) -> str:
    if run is None:
        return "Сканирований ещё не было — запустите /scan."
    when = run.started_at.astimezone(tz)
    status = STATUS_LABELS.get(run.status, run.status)
    return f"Последнее сканирование: {when:%d.%m.%Y %H:%M} — {status}"


class ReportBuilder:
    def __init__(self, settings: Settings, repo: Repository, topics: TopicsConfig) -> None:
        self.settings = settings
        self.repo = repo
        self.topics = topics

    def _context(self) -> tuple[Mode, bool]:
        try:
            mode = self.settings.resolve_mode()
        except ModeUnavailableError:
            # Live запрошен, но не настроен: показываем только реальные данные (если есть).
            mode = "live"
        return mode, self.settings.dataset_is_demo(mode)

    def top_items(self, limit: int) -> list[OpportunityView]:
        _mode, is_demo = self._context()
        items = self.repo.list_opportunities(self.settings.region_key, is_demo, ("top",), limit * 5)
        return dedupe_groups(items)[:limit]

    def watch_items(self, limit: int) -> list[OpportunityView]:
        _mode, is_demo = self._context()
        items = self.repo.list_opportunities(
            self.settings.region_key, is_demo, ("watch",), limit * 5
        )
        return dedupe_groups(items)[:limit]

    def daily_report(self, report_date: date) -> list[str]:
        mode, is_demo = self._context()
        tz = self.settings.tz
        header = [
            f"<b>Search Scout — отчёт за {report_date:%d.%m.%Y}</b>",
            esc(mode_line(mode, is_demo)),
        ]
        if is_demo:
            header.append(DEMO_BANNER)
        header.append(f"Регион: {esc(region_label(self.settings.region_key))}")
        header.append(esc(scan_line(self.repo.last_scan_run(), tz)))
        blocks = ["\n".join(header)]

        top = self.top_items(self.settings.report_max_items)
        if top:
            blocks.append(f"<b>Лучшие возможности ({len(top)})</b>")
            blocks += [format_item(i, item, self.topics) for i, item in enumerate(top, 1)]
        else:
            blocks.append(
                "Сильных возможностей с подтверждённой динамикой пока нет. Список не заполняется "
                "искусственно: фразам нужна история спроса (бот запрашивает её постепенно)."
            )

        watch = self.watch_items(self.settings.report_watch_items)
        if watch:
            blocks.append(
                f"<b>Список наблюдения ({len(watch)})</b> — новые фразы без достаточной истории, "
                "рейтинг предварительный:"
            )
            blocks += [
                format_item(i, item, self.topics, detailed=False) for i, item in enumerate(watch, 1)
            ]
        blocks.append(DISCLAIMER)
        return split_messages(blocks)

    def top_report(self) -> list[str]:
        mode, is_demo = self._context()
        top = self.top_items(self.settings.report_max_items)
        head = f"<b>Лучшие текущие возможности</b>\n{esc(mode_line(mode, is_demo))}"
        if is_demo:
            head += "\n" + DEMO_BANNER
        if not top:
            return [
                head + "\n\nПока пусто: нет фраз с подтверждённой динамикой выше порога. "
                "Посмотрите /watchlist."
            ]
        return split_messages(
            [head] + [format_item(i, it, self.topics) for i, it in enumerate(top, 1)]
        )

    def watchlist_report(self) -> list[str]:
        mode, is_demo = self._context()
        watch = self.watch_items(20)
        head = (
            "<b>Список наблюдения</b>\nНовые фразы, по которым ещё мало истории, и разовые "
            f"всплески. Рейтинг предварительный.\n{esc(mode_line(mode, is_demo))}"
        )
        if is_demo:
            head += "\n" + DEMO_BANNER
        if not watch:
            return [head + "\n\nСписок пуст."]
        blocks = [head] + [
            format_item(i, it, self.topics, detailed=False) for i, it in enumerate(watch, 1)
        ]
        return split_messages(blocks)

    def export_csv(self) -> bytes:
        _mode, is_demo = self._context()
        items = self.repo.list_opportunities(
            self.settings.region_key, is_demo, ("top", "watch", "rejected")
        )
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=";")
        writer.writerow(
            [
                "phrase",
                "normalized",
                "is_demo",
                "topic",
                "status",
                "status_reason",
                "score",
                "is_preliminary",
                "completeness",
                "confidence",
                "trend",
                "commercial",
                "problem",
                "novelty",
                "intent",
                "latest_count",
                "latest_period",
                "trend_text",
                "sources",
                "region",
                "first_found_utc",
                "last_observed_on",
                "reasons",
            ]
        )
        for it in items:
            comp = it.components
            writer.writerow(
                [
                    it.original,
                    it.normalized,
                    int(it.is_demo),
                    it.topic_key or "",
                    it.status,
                    it.status_reason,
                    f"{it.total:.1f}",
                    int(it.is_preliminary),
                    f"{it.completeness:.2f}",
                    it.confidence,
                    "" if comp["trend"]["value"] is None else f"{comp['trend']['value']:.1f}",
                    f"{comp['commercial']['value']:.1f}",
                    f"{comp['problem']['value']:.1f}",
                    f"{comp['novelty']['value']:.1f}",
                    it.data_used.get("intent", ""),
                    ""
                    if it.data_used.get("latest_count") is None
                    else it.data_used["latest_count"],
                    it.data_used.get("latest_period") or "",
                    trend_text(it.data_used),
                    ",".join(it.data_used.get("sources") or []),
                    it.region_key,
                    it.first_found_at.isoformat(timespec="seconds"),
                    it.last_observed_on.isoformat() if it.last_observed_on else "",
                    " | ".join(it.reasons),
                ]
            )
        # BOM — чтобы Excel правильно открыл кириллицу
        return ("﻿" + buffer.getvalue()).encode("utf-8")
