"""HTTP-запросы к внешним API: лимит частоты, повторы, разбор ошибок.

Политика повторов:
  * повторяем: тайм-ауты, сетевые ошибки, HTTP 429 и 5xx;
  * пауза: экспоненциальная (1, 2, 4, 8 … с, максимум 30 с) + случайная
    добавка, чтобы параллельные запросы не повторялись синхронно;
    для 429 учитываем заголовок Retry-After;
  * не повторяем: 400 (ошибка параметров) и 401/403 (ключ/права/биллинг).
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.sources.base import (
    SourceAuthError,
    SourceError,
    SourceRequestError,
    SourceTemporaryError,
)

log = logging.getLogger(__name__)

MAX_BACKOFF_S = 30.0
Sleep = Callable[[float], Awaitable[None]]


class RateLimiter:
    """Не чаще rps запросов в секунду (минимальный интервал между стартами)."""

    def __init__(self, rps: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._interval = 1.0 / rps
        self._clock = clock
        self._next_at = 0.0
        self._lock = asyncio.Lock()

    async def wait(self, sleep: Sleep = asyncio.sleep) -> None:
        async with self._lock:
            now = self._clock()
            delay = self._next_at - now
            if delay > 0:
                await sleep(delay)
                now = self._clock()
            self._next_at = max(now, self._next_at) + self._interval


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0.0, min(float(value), 120.0))
    except ValueError:
        return None


def _short_body(response: httpx.Response) -> str:
    text = response.text.strip().replace("\n", " ")
    return text[:300]


def backoff_delay(attempt: int) -> float:
    return min(MAX_BACKOFF_S, 2.0**attempt) + random.uniform(0, 0.5)


async def post_json(
    client: httpx.AsyncClient,
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str],
    max_retries: int,
    limiter: RateLimiter,
    semaphore: asyncio.Semaphore,
    sleep: Sleep = asyncio.sleep,
    on_request: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """POST с JSON и повторами. Возвращает разобранный JSON-ответ."""
    last_error: SourceError | None = None
    for attempt in range(max_retries + 1):
        delay: float | None = None
        try:
            async with semaphore:
                await limiter.wait(sleep)
                if on_request:
                    on_request()
                response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException:
            last_error = SourceTemporaryError("тайм-аут запроса")
        except httpx.TransportError as exc:
            last_error = SourceTemporaryError(f"сетевая ошибка: {type(exc).__name__}")
        else:
            status = response.status_code
            if 200 <= status < 300:
                try:
                    data = response.json()
                except ValueError as exc:
                    raise SourceRequestError("источник вернул не JSON") from exc
                if not isinstance(data, dict):
                    raise SourceRequestError("неожиданный формат ответа")
                return data
            body = _short_body(response)
            if status == 429:
                last_error = SourceTemporaryError(f"HTTP 429: превышен лимит запросов. {body}")
                delay = _retry_after(response)
            elif status >= 500:
                last_error = SourceTemporaryError(
                    f"HTTP {status}: ошибка на стороне сервиса. {body}"
                )
            elif status in (401, 403):
                raise SourceAuthError(
                    f"HTTP {status}: доступ запрещён. Проверьте API-ключ, ID каталога, роль "
                    f"сервисного аккаунта и привязку платёжного аккаунта. Ответ: {body}"
                )
            else:
                raise SourceRequestError(f"HTTP {status}: запрос отклонён. Ответ: {body}")

        if attempt < max_retries:
            wait = delay if delay is not None else backoff_delay(attempt)
            log.warning(
                "Временная ошибка (%s), повтор %s/%s через %.1f с",
                last_error,
                attempt + 1,
                max_retries,
                wait,
            )
            await sleep(wait)
    assert last_error is not None
    raise last_error
