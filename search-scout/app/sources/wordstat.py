"""Источник Яндекс Wordstat через Yandex Cloud Search API v2.

Почему не api.wordstat.yandex.net: Wordstat API переехал в Yandex Search
API (AI Studio / Yandex Cloud). Старый адрес с OAuth-токеном, по данным
разработчиков клиентских библиотек, больше не принимает запросы. Новый API:

  POST https://searchapi.api.cloud.yandex.net/v2/wordstat/topRequests
  POST https://searchapi.api.cloud.yandex.net/v2/wordstat/dynamics
  POST https://searchapi.api.cloud.yandex.net/v2/wordstat/regions
  POST https://searchapi.api.cloud.yandex.net/v2/wordstat/getRegionsTree
  Заголовок:  Authorization: Api-Key <ключ сервисного аккаунта>
  В теле:     "folderId": "<ID каталога>"

Особенности формата (proto3 JSON):
  * числа int64 (count, totalCount) приходят СТРОКАМИ — приводим к int;
  * даты — RFC3339 ("2026-09-01T00:00:00Z");
  * перечисления — именами: PERIOD_MONTHLY, DEVICE_PHONE …;
  * регионы передаются строками.
  * topRequests считает последние 30 дней; dynamics при PERIOD_MONTHLY
    требует fromDate = первое число месяца, toDate = последний день месяца.

Подробности подключения — в README, раздел «Доступ к Wordstat API».
"""

from __future__ import annotations

import asyncio
import calendar
import logging
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from app.config import Settings
from app.sources.base import Observation, QuerySource, SourceRequestError
from app.sources.http import RateLimiter, Sleep, post_json

log = logging.getLogger(__name__)

DEVICE_ENUM = {"desktop": "DEVICE_DESKTOP", "phone": "DEVICE_PHONE", "tablet": "DEVICE_TABLET"}


def to_int(value: Any) -> int | None:
    """'1234' или 1234 → 1234; пусто/мусор → None (нет данных, а не ноль)."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def parse_api_date(value: str) -> date:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def month_range(last_full_month_end: date, months: int) -> tuple[date, date]:
    """Даты для помесячной динамики: [первое число месяца N мес. назад, конец прошлого месяца]."""
    end = last_full_month_end
    year, month = end.year, end.month - (months - 1)
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1), end


def last_full_month_end(today: date) -> date:
    return today.replace(day=1) - timedelta(days=1)


class WordstatSource(QuerySource):
    name = "wordstat"
    is_live = True

    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
        *,
        sleep: Sleep = asyncio.sleep,
        today: Callable[[], date] | None = None,
    ) -> None:
        if not settings.wordstat_configured:
            raise ValueError("Wordstat не настроен: нужны WORDSTAT_API_KEY и WORDSTAT_FOLDER_ID")
        self._settings = settings
        self._client = client or httpx.AsyncClient(timeout=settings.wordstat_timeout_s)
        self._owns_client = client is None
        self._limiter = RateLimiter(settings.wordstat_rps)
        self._semaphore = asyncio.Semaphore(settings.wordstat_concurrency)
        self._sleep = sleep
        self._today = today or (lambda: datetime.now(UTC).date())
        self._dynamics_months = settings.wordstat_dynamics_months
        self.requests_made = 0

    # ---------------- служебное ----------------

    def _count_request(self) -> None:
        self.requests_made += 1

    def _base_body(self) -> dict[str, Any]:
        body: dict[str, Any] = {"folderId": self._settings.wordstat_folder_id}
        if self._settings.wordstat_regions:
            body["regions"] = [str(r) for r in sorted(set(self._settings.wordstat_regions))]
        if self._settings.wordstat_devices:
            body["devices"] = [DEVICE_ENUM[d] for d in self._settings.wordstat_devices]
        return body

    async def _post(self, method: str, body: dict[str, Any]) -> dict[str, Any]:
        api_key = self._settings.wordstat_api_key
        assert api_key is not None
        return await post_json(
            self._client,
            f"{self._settings.wordstat_base_url.rstrip('/')}/v2/wordstat/{method}",
            body,
            headers={
                "Authorization": f"Api-Key {api_key.get_secret_value()}",
                "Content-Type": "application/json; charset=utf-8",
            },
            max_retries=self._settings.wordstat_max_retries,
            limiter=self._limiter,
            semaphore=self._semaphore,
            sleep=self._sleep,
            on_request=self._count_request,
        )

    def _observation(
        self, phrase: str, count: int | None, start: date, end: date, period: str, topic: str | None
    ) -> Observation:
        return Observation(
            phrase=phrase,
            count=count,
            period_type=period,  # type: ignore[arg-type]
            period_start=start,
            period_end=end,
            region_key=self._settings.region_key,
            devices=self._settings.devices_key,
            source=self.name,
            is_demo=False,
            topic_key=topic,
        )

    # ---------------- методы источника ----------------

    async def related(self, seed: str, topic_key: str | None) -> list[Observation]:
        body = self._base_body()
        body.update({"phrase": seed, "numPhrases": self._settings.wordstat_num_phrases})
        data = await self._post("topRequests", body)

        # API считает последние 30 дней, но точные границы окна не сообщает.
        # Записываем дату наблюдения как конец окна.
        observed = self._today()
        start = observed - timedelta(days=29)
        result = []
        total = to_int(data.get("totalCount"))
        if total is not None:
            result.append(self._observation(seed, total, start, observed, "rolling30", topic_key))
        for key in ("results", "associations"):
            for item in data.get(key) or []:
                phrase = item.get("phrase")
                if not phrase:
                    continue
                result.append(
                    self._observation(
                        phrase, to_int(item.get("count")), start, observed, "rolling30", topic_key
                    )
                )
        return result

    @property
    def supports_dynamics(self) -> bool:
        return True

    async def monthly_dynamics(self, phrase: str) -> list[Observation]:
        end = last_full_month_end(self._today())
        try:
            return await self._dynamics(phrase, end, self._dynamics_months)
        except SourceRequestError:
            # Если API не принимает длинный период, один раз пробуем 12 месяцев
            # и дальше используем его, чтобы не тратить квоту на ошибки.
            if self._dynamics_months <= 12:
                raise
            log.warning(
                "Wordstat отклонил период %s мес., переходим на 12 мес.", self._dynamics_months
            )
            self._dynamics_months = 12
            return await self._dynamics(phrase, end, 12)

    async def _dynamics(self, phrase: str, end: date, months: int) -> list[Observation]:
        start, end = month_range(end, months)
        body = self._base_body()
        body.update(
            {
                "phrase": phrase,
                "period": "PERIOD_MONTHLY",
                "fromDate": f"{start.isoformat()}T00:00:00Z",
                "toDate": f"{end.isoformat()}T00:00:00Z",
            }
        )
        data = await self._post("dynamics", body)
        result = []
        for item in data.get("results") or []:
            if not item.get("date"):
                continue
            month_start = parse_api_date(item["date"]).replace(day=1)
            month_end = month_start.replace(
                day=calendar.monthrange(month_start.year, month_start.month)[1]
            )
            if month_end > end:
                continue  # неполный месяц не используем
            result.append(
                self._observation(
                    phrase, to_int(item.get("count")), month_start, month_end, "month", None
                )
            )
        return result

    async def regions_tree(self) -> dict[str, Any]:
        """Справочник регионов (для настройки WORDSTAT_REGIONS)."""
        return await self._post("getRegionsTree", {"folderId": self._settings.wordstat_folder_id})

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
