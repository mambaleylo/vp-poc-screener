"""Ежедневное сканирование и отчёт по расписанию.

Почему так устроено. APScheduler хранит задания в памяти, и после
перезапуска они теряются. Поэтому:
  * расписание не хранится, а заново строится при каждом старте из
    настроек (DAILY_TIME, TIMEZONE) — терять нечего;
  * пропущенный запуск восстанавливается: при старте catch_up() проверяет,
    прошло ли сегодня время отчёта и было ли сегодня плановое сканирование
    (это записано в базе). Если нет — выполняет его сразу;
  * повторной отправки нет: каждая доставка отмечается в notifications.

Отдельный системный cron не нужен: бот всё равно должен работать
постоянно, чтобы отвечать на команды.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import ModeUnavailableError, Settings
from app.services.collector import ScanService
from app.services.notifier import Notifier
from app.storage.repository import Repository, ScanAlreadyRunningError

log = logging.getLogger(__name__)

JOB_ID = "daily_scan_report"


class DailyScheduler:
    def __init__(
        self,
        settings: Settings,
        repo: Repository,
        scan_service: ScanService,
        notifier: Notifier,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.settings = settings
        self.repo = repo
        self.scan_service = scan_service
        self.notifier = notifier
        self.clock = clock
        self._lock = asyncio.Lock()
        self._scheduler: AsyncIOScheduler | None = None

    def start(self) -> None:
        tz = self.settings.tz
        daily = self.settings.daily_time_value
        self._scheduler = AsyncIOScheduler(timezone=tz)
        self._scheduler.add_job(
            self.run_daily,
            CronTrigger(hour=daily.hour, minute=daily.minute, timezone=tz),
            id=JOB_ID,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
            replace_existing=True,
        )
        self._scheduler.start()
        log.info(
            "Ежедневный отчёт: %s (%s), следующий запуск %s",
            self.settings.daily_time,
            self.settings.timezone,
            self.next_run_time(),
        )

    def shutdown(self) -> None:
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def next_run_time(self) -> datetime | None:
        if not self._scheduler:
            return None
        job = self._scheduler.get_job(JOB_ID)
        return job.next_run_time if job else None

    async def run_daily(self) -> None:
        """Плановое сканирование (если сегодня ещё не было) + рассылка отчёта."""
        async with self._lock:
            tz = self.settings.tz
            local_day = self.clock().astimezone(tz).date()
            done = await asyncio.to_thread(self.repo.scheduled_scan_done_on, local_day, tz)
            if not done:
                try:
                    await self.scan_service.run("scheduled")
                except ScanAlreadyRunningError:
                    log.info("Идёт ручное сканирование — дождёмся его и отправим отчёт")
                    await self.scan_service.wait_idle()
                except ModeUnavailableError as exc:
                    log.error("Плановое сканирование не выполнено: %s", exc)
            await self.notifier.send_daily(local_day)

    async def catch_up(self) -> None:
        """Выполняет сегодняшний запуск, если бот был выключен в его время."""
        now_local = self.clock().astimezone(self.settings.tz)
        if now_local.time() >= self.settings.daily_time_value:
            log.info("Проверка пропущенного ежедневного запуска за %s", now_local.date())
            try:
                await self.run_daily()
            except Exception:
                log.exception("Ошибка при восстановлении пропущенного запуска")
