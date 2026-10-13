"""Импорт CSV. Все строки — синтетические тестовые данные."""

from datetime import date
from pathlib import Path

from app.config import PROJECT_ROOT
from app.sources.csv_source import CsvSource, parse_csv_bytes, parse_csv_text

TODAY = date(2026, 10, 13)


def parse(text: str, **kw):
    params = {
        "is_demo": True,
        "default_region": "all",
        "default_source": "csv-demo",
        "today": TODAY,
    }
    params.update(kw)
    return parse_csv_text(text, **params)


def test_basic_rows_and_periods() -> None:
    result = parse(
        "phrase,count,period,date,topic\n"
        "генератор счетов,120,month,2026-09-15,invoices_acts\n"
        "конвертер pdf,300,30d,2026-10-01,\n"
    )
    assert result.errors == []
    month, rolling = result.observations
    assert month.period_type == "month"
    assert (month.period_start, month.period_end) == (date(2026, 9, 1), date(2026, 9, 30))
    assert month.topic_key == "invoices_acts"
    assert rolling.period_type == "rolling30"
    assert rolling.period_end == date(2026, 10, 1)
    assert (rolling.period_end - rolling.period_start).days == 29
    assert all(o.is_demo for o in result.observations)


def test_empty_count_is_no_data_not_zero() -> None:
    result = parse("phrase,count\nаналог crm,\n")
    assert result.observations[0].count is None


def test_defaults_semicolon_comments_and_spaces_in_numbers() -> None:
    result = parse("# тестовый файл\nphrase;count\nсчет онлайн;1 200\n", default_region="225")
    obs = result.observations[0]
    assert obs.count == 1200
    assert obs.region_key == "225"
    assert obs.period_type == "rolling30" and obs.period_end == TODAY


def test_bad_rows_are_reported_with_line_numbers() -> None:
    result = parse(
        "phrase,count,period,date\nок,10,month,2026-09\n,5\nx,abc\ny,5,week\nz,5,month,31.31.2026\n"
    )
    assert len(result.observations) == 1
    assert len(result.errors) == 4
    assert result.errors[0].startswith("строка 3")


def test_missing_phrase_column() -> None:
    result = parse("query,count\nа,1\n")
    assert result.observations == []
    assert "phrase" in result.errors[0]


def test_cp1251_and_bom() -> None:
    text = "phrase,count\nсчет онлайн,5\n"
    for data in (text.encode("cp1251"), ("﻿" + text).encode("utf-8")):
        result = parse_csv_bytes(
            data, is_demo=False, default_region="all", default_source="csv", today=TODAY
        )
        assert result.observations[0].phrase == "счет онлайн"
        assert result.observations[0].is_demo is False


def test_csv_source_file(tmp_path: Path) -> None:
    path = tmp_path / "data.csv"
    path.write_text("phrase,count\nсчет онлайн,5\n", encoding="utf-8")
    result = CsvSource(path, is_demo=True, default_region="all", today=TODAY).load()
    assert result.observations[0].source == "csv-demo"
    missing = CsvSource(tmp_path / "nope.csv", is_demo=True, default_region="all").load()
    assert "не найден" in missing.errors[0]


def test_bundled_demo_file_is_valid_and_marked_as_test() -> None:
    path = PROJECT_ROOT / "data" / "demo_keywords.csv"
    assert "ТЕСТОВЫЕ" in path.read_text(encoding="utf-8").splitlines()[0]
    result = CsvSource(path, is_demo=True, default_region="all", today=TODAY).load()
    assert result.errors == []
    assert len(result.observations) > 100
