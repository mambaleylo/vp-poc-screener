"""Импорт поисковых фраз и метрик из CSV.

Формат (первая строка — заголовок, порядок колонок любой):

  phrase   обязательно  поисковая фраза
  count    нет          частотность; пусто = «нет данных» (НЕ ноль)
  period   нет          month — частотность за календарный месяц,
                        30d — за 30 дней до даты date (по умолчанию)
  date     нет          для month — любая дата месяца; для 30d — дата
                        наблюдения. Форматы: 2026-09-01, 01.09.2026, 2026-09.
                        По умолчанию — сегодня.
  region   нет          ключ региона (all, 225, 149,159,225). По умолчанию —
                        регион из настроек.
  topic    нет          key тематики из config/topics.toml
  source   нет          откуда данные (например wordstat-manual)

Разделитель — запятая или точка с запятой (Excel в русской локали
сохраняет с «;»). Кодировка — UTF-8 (с BOM или без) либо Windows-1251.
Строки, начинающиеся с '#', — комментарии.

Отметка «тестовые данные» задаётся не в файле, а при импорте (is_demo):
по умолчанию любой CSV считается демо, реальные данные нужно явно
пометить флагом --real. Так тестовые данные не попадут к реальным.
"""

from __future__ import annotations

import calendar
import csv
import io
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from app.sources.base import BatchResult, BatchSource, Observation

MAX_ROWS = 200_000


def _parse_date(raw: str) -> date:
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y-%m", "%m.%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"не удалось разобрать дату «{raw}»")


def _parse_count(raw: str) -> int | None:
    raw = raw.strip().replace(" ", "").replace(" ", "")
    if raw == "" or raw.lower() in {"-", "—", "n/a", "na", "нет данных"}:
        return None
    if not re.fullmatch(r"\d+", raw):
        raise ValueError(f"частотность должна быть целым неотрицательным числом, а не «{raw}»")
    return int(raw)


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1251")


def parse_csv_text(
    text: str,
    *,
    is_demo: bool,
    default_region: str,
    default_source: str,
    today: date,
    devices: str = "all",
) -> BatchResult:
    lines = [
        line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")
    ]
    if not lines:
        return BatchResult(observations=[], errors=["файл пуст"], rows_total=0)
    delimiter = ";" if lines[0].count(";") > lines[0].count(",") else ","
    reader = csv.DictReader(io.StringIO("\n".join(lines)), delimiter=delimiter)
    fields = {(f or "").strip().lower() for f in reader.fieldnames or []}
    if "phrase" not in fields:
        return BatchResult(
            observations=[], errors=["нет обязательной колонки 'phrase' в заголовке"], rows_total=0
        )

    observations: list[Observation] = []
    errors: list[str] = []
    rows_total = 0
    for line_no, raw_row in enumerate(reader, start=2):
        rows_total += 1
        if rows_total > MAX_ROWS:
            errors.append(f"файл обрезан: больше {MAX_ROWS} строк")
            break
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw_row.items()}
        try:
            phrase = row.get("phrase", "")
            if not phrase:
                raise ValueError("пустая фраза")
            count = _parse_count(row.get("count", ""))
            period = (row.get("period") or "30d").lower()
            when = _parse_date(row["date"]) if row.get("date") else today
            if period in {"month", "m", "месяц"}:
                start = when.replace(day=1)
                end = start.replace(day=calendar.monthrange(start.year, start.month)[1])
                period_type = "month"
            elif period in {"30d", "rolling30", "30"}:
                end = when
                start = end - timedelta(days=29)
                period_type = "rolling30"
            else:
                raise ValueError(f"неизвестный period «{period}» (ожидается month или 30d)")
            observations.append(
                Observation(
                    phrase=phrase,
                    count=count,
                    period_type=period_type,
                    period_start=start,
                    period_end=end,
                    region_key=row.get("region") or default_region,
                    devices=devices,
                    source=row.get("source") or default_source,
                    is_demo=is_demo,
                    topic_key=row.get("topic") or None,
                )
            )
        except (ValueError, KeyError) as exc:
            errors.append(f"строка {line_no}: {exc}")
    return BatchResult(observations=observations, errors=errors, rows_total=rows_total)


class CsvSource(BatchSource):
    def __init__(
        self,
        path: Path,
        *,
        is_demo: bool,
        default_region: str,
        source_name: str | None = None,
        today: date | None = None,
    ) -> None:
        self.path = path
        self.is_demo = is_demo
        self.is_live = False
        self.default_region = default_region
        self.name = source_name or ("csv-demo" if is_demo else "csv")
        self._today = today

    def load(self) -> BatchResult:
        if not self.path.exists():
            return BatchResult(
                observations=[], errors=[f"файл не найден: {self.path}"], rows_total=0
            )
        return parse_csv_text(
            _decode(self.path.read_bytes()),
            is_demo=self.is_demo,
            default_region=self.default_region,
            default_source=self.name,
            today=self._today or date.today(),
        )


def parse_csv_bytes(data: bytes, **kwargs: object) -> BatchResult:
    return parse_csv_text(_decode(data), **kwargs)  # type: ignore[arg-type]
