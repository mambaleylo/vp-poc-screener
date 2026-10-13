"""Доступ только для разрешённых Telegram user ID (ALLOWED_USER_IDS).

Middleware стоит перед всеми обработчиками: сообщения посторонних не
доходят ни до одной команды — они не могут запустить сканирование, прочитать
отчёты или выгрузить данные. Посторонний один раз в минуту получает
подсказку со своим ID (это нужно владельцу при первой настройке бота).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

log = logging.getLogger(__name__)

REPLY_INTERVAL_S = 60.0


def is_allowed(user_id: int | None, allowed: set[int]) -> bool:
    return user_id is not None and user_id in allowed


class AccessMiddleware(BaseMiddleware):
    def __init__(self, allowed_ids: list[int], clock: Callable[[], float] = time.monotonic) -> None:
        self.allowed = set(allowed_ids)
        self._clock = clock
        self._last_reply: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        user_id = getattr(user, "id", None)
        if is_allowed(user_id, self.allowed):
            return await handler(event, data)

        log.warning("Отклонён запрос от user_id=%s", user_id)
        if user_id is not None and isinstance(event, Message):
            now = self._clock()
            if now - self._last_reply.get(user_id, -REPLY_INTERVAL_S) >= REPLY_INTERVAL_S:
                self._last_reply[user_id] = now
                await event.answer(
                    "Это приватный бот.\n"
                    f"Ваш Telegram ID: {user_id}\n"
                    "Если это ваш бот, добавьте ID в ALLOWED_USER_IDS в файле .env "
                    "и перезапустите бота."
                )
        return None
