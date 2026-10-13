"""Отчёты на синтетических данных."""

import csv
import io
from datetime import date, timedelta
from pathlib import Path

from app.context import make_batch_factory
from app.services.collector import ScanService
from app.services.report import ReportBuilder, dedupe_groups, split_messages, trend_text
from tests.conftest import FIXED_NOW
from tests.test_collector import write_csv


async def scanned_builder(make_settings, repo, topics, tmp_path: Path, **kw) -> ReportBuilder:
    settings = make_settings(csv_import_path=write_csv(tmp_path), **kw)
    service = ScanService(
        settings,
        repo,
        topics,
        batch_source_factory=make_batch_factory(settings),
        clock=lambda: FIXED_NOW,
    )
    await service.run("manual")
    return ReportBuilder(settings, repo, topics)


async def test_daily_report_content(make_settings, repo, topics, tmp_path) -> None:
    builder = await scanned_builder(make_settings, repo, topics, tmp_path)
    text = "\n".join(builder.daily_report(date(2026, 10, 13)))
    assert "Search Scout — отчёт за 13.10.2026" in text
    assert "ТЕСТОВЫЕ ДАННЫЕ" in text  # демо-данные явно помечены
    assert "генератор счетов для ип" in text
    assert "Конкуренция: не исследована" in text
    assert "Что проверить дальше" in text
    assert "wordstat.yandex.ru" in text
    assert "Список наблюдения" in text
    assert "недостаточно истории" in text  # для новой фразы рост не выдуман
    assert "прогноз прибыли" in text


async def test_report_without_good_results_is_not_padded(
    make_settings, repo, topics, tmp_path
) -> None:
    builder = await scanned_builder(make_settings, repo, topics, tmp_path, top_min_score=99)
    text = "\n".join(builder.daily_report(date(2026, 10, 13)))
    assert "Сильных возможностей с подтверждённой динамикой пока нет" in text


async def test_live_report_does_not_show_demo_data(make_settings, repo, topics, tmp_path) -> None:
    await scanned_builder(make_settings, repo, topics, tmp_path)
    live = ReportBuilder(make_settings(wordstat_api_key="k", wordstat_folder_id="f"), repo, topics)
    text = "\n".join(live.daily_report(date(2026, 10, 13)))
    assert "генератор счетов" not in text
    assert "ТЕСТОВЫЕ" not in text


async def test_export_csv(make_settings, repo, topics, tmp_path) -> None:
    builder = await scanned_builder(make_settings, repo, topics, tmp_path)
    data = builder.export_csv()
    assert data.startswith("﻿".encode())
    rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig")), delimiter=";"))
    assert {r["phrase"] for r in rows} == {"генератор счетов для ип", "новый конвертер pdf онлайн"}
    new = next(r for r in rows if r["phrase"].startswith("новый"))
    assert new["trend"] == "" and new["is_preliminary"] == "1"  # пусто, а не выдуманное число


def test_trend_text_variants() -> None:
    assert trend_text({"trend": {"status": "insufficient_history"}}) == "недостаточно истории"
    assert trend_text({}) == "нет данных"
    text = trend_text(
        {"trend": {"status": "ok", "growth_ratio": 1.5, "window": "3 vs 3", "seasonal": None}}
    )
    assert text.startswith("+50%") and "сезонность не проверена" in text


def test_split_messages_respects_limit() -> None:
    blocks = ["a" * 1500, "b" * 1500, "c" * 1500, "d" * 5000]
    messages = split_messages(blocks, limit=3900)
    assert all(len(m) <= 3900 for m in messages)
    assert "".join(messages).count("d") == 5000


def test_dedupe_groups() -> None:
    from types import SimpleNamespace

    items = [
        SimpleNamespace(group_key="a"),
        SimpleNamespace(group_key="a"),
        SimpleNamespace(group_key="b"),
    ]
    assert len(dedupe_groups(items)) == 2  # type: ignore[arg-type]


def test_report_dates_are_local(make_settings) -> None:
    from app.services.report import scan_line
    from app.storage.repository import ScanRunView

    run = ScanRunView(
        1, "manual", "demo", "success", FIXED_NOW - timedelta(hours=11), None, {}, None
    )
    settings = make_settings(timezone="Asia/Almaty")
    assert "13.10.2026 06:00" in scan_line(run, settings.tz)
