"""Общий интерфейс источников данных.

Источник возвращает наблюдения (Observation): «фраза X имела частотность N
за период P в регионе R по данным источника S». Источник ничего не знает о
базе, рейтинге и Telegram — поэтому новые источники (подсказки, каталоги,
обсуждения) подключаются, не трогая остальной код.

Два вида источников:
  QuerySource — отвечает на запросы по фразе (Wordstat): похожие запросы,
                опционально помесячная динамика.
  BatchSource — отдаёт готовый набор данных целиком (CSV-файл).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Literal

PeriodType = Literal["month", "rolling30"]


@dataclass(frozen=True)
class Observation:
    phrase: str  # исходная формулировка
    count: int | None  # None — источник не дал значения
    period_type: PeriodType
    period_start: date
    period_end: date
    region_key: str
    devices: str
    source: str
    is_demo: bool
    topic_key: str | None = None  # тематика сида, из которого получена фраза


class SourceError(Exception):
    """Ошибка источника. retryable=True — временная (сеть, 429, 5xx)."""

    retryable = False


class SourceTemporaryError(SourceError):
    retryable = True


class SourceAuthError(SourceError):
    """Неверный ключ, нет прав или не подключён биллинг — повтор не поможет."""


class SourceRequestError(SourceError):
    """Источник отклонил параметры запроса (HTTP 400 и т. п.)."""


class QuerySource(ABC):
    name: str
    is_live: bool

    @abstractmethod
    async def related(self, seed: str, topic_key: str | None) -> list[Observation]:
        """Сам сид и похожие на него запросы с частотностью."""

    @property
    def supports_dynamics(self) -> bool:
        return False

    async def monthly_dynamics(self, phrase: str) -> list[Observation]:
        raise NotImplementedError

    async def aclose(self) -> None:  # noqa: B027 — по умолчанию закрывать нечего
        pass


class BatchSource(ABC):
    name: str
    is_live: bool

    @abstractmethod
    def load(self) -> BatchResult:
        """Читает весь набор данных."""


@dataclass
class BatchResult:
    observations: list[Observation]
    errors: list[str]
    rows_total: int
