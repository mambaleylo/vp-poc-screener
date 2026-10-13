"""Рассылка ежедневного отчёта с защитой от повторной отправки.

Перед отправкой в таблице notifications атомарно «занимается» запись
(пользователь, тип, дата). Если запись уже есть — отчёт за эту дату уже
уходил, повторно не шлём (даже после перезапуска бота). Если отправка
не удалась из-за временной ошибки, запись удаляется и отчёт уйдёт при
следующей попытке.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime

from app.config import Settings
from app.services.report import ReportBuilder
from app.storage.repository import Repository

log = logging.getLogger(__name__)

DAILY_KIND = "daily_report"


class RecipientUnavailableError(Exception):
    """Получатель недоступен навсегда (заблокировал бота, чат удалён)."""


SendFunc = Callable[[int, str], Awaitable[None]]


class Notifier:
    def __init__(
        self,
        settings: Settings,
        repo: Repository,
        reports: ReportBuilder,
        send: SendFunc,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.settings = settings
        self.repo = repo
        self.reports = reports
        self.send = send
        self.clock = clock

    async def send_daily(self, local_day: date) -> dict[str, int]:
        stats = {"sent": 0, "skipped": 0, "failed": 0}
        users = await asyncio.to_thread(self.repo.daily_users, self.settings.allowed_user_ids)
        if not users:
            return stats
        messages = await asyncio.to_thread(self.reports.daily_report, local_day)
        key = local_day.isoformat()
        for user in users:
            reserved = await asyncio.to_thread(
                self.repo.reserve_notification, user.id, DAILY_KIND, key, self.clock()
            )
            if not reserved:
                stats["skipped"] += 1
                continue
            try:
                for text in messages:
                    await self.send(user.chat_id, text)
            except RecipientUnavailableError:
                # Запись не снимаем: повтор бессмысленен, пока пользователь не вернётся.
                log.warning("Пользователь %s недоступен, отчёт не доставлен", user.id)
                stats["failed"] += 1
            except Exception:
                log.exception("Не удалось отправить отчёт пользователю %s", user.id)
                await asyncio.to_thread(self.repo.release_notification, user.id, DAILY_KIND, key)
                stats["failed"] += 1
            else:
                stats["sent"] += 1
        log.info("Ежедневный отчёт за %s: %s", key, stats)
        return stats
