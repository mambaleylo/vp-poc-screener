"""Сборка всех частей приложения в одном месте (используется ботом и CLI)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.config import Mode, Settings
from app.services.collector import ScanService
from app.services.report import ReportBuilder
from app.sources.base import BatchSource
from app.sources.csv_source import CsvSource
from app.sources.wordstat import WordstatSource
from app.storage.database import init_database
from app.storage.repository import Repository
from app.topics import TopicsConfig, load_topics

log = logging.getLogger(__name__)


@dataclass
class AppContext:
    settings: Settings
    repo: Repository
    topics: TopicsConfig
    scan_service: ScanService
    reports: ReportBuilder
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    scheduler: Any = None  # DailyScheduler, когда запущен бот
    _tasks: set[asyncio.Task[Any]] = field(default_factory=set)

    def spawn(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        """Фоновая задача, которую не соберёт сборщик мусора и чьи ошибки попадут в лог."""
        task = asyncio.create_task(coro)
        self._tasks.add(task)

        def _done(t: asyncio.Task[Any]) -> None:
            self._tasks.discard(t)
            if not t.cancelled() and t.exception():
                log.error("Ошибка фоновой задачи", exc_info=t.exception())

        task.add_done_callback(_done)
        return task


def make_batch_factory(settings: Settings) -> Callable[[Mode], BatchSource | None]:
    def factory(mode: Mode) -> BatchSource | None:
        path = settings.csv_file
        if path is None:
            return None
        if mode == "live" and settings.csv_is_demo:
            # Тестовые данные никогда не подмешиваются к реальным.
            return None
        return CsvSource(path, is_demo=settings.csv_is_demo, default_region=settings.region_key)

    return factory


def build_context(settings: Settings) -> AppContext:
    _, session_factory = init_database(settings.db_file)
    repo = Repository(session_factory)
    topics = load_topics(settings.topics_file)
    repo.sync_topics(topics, datetime.now(UTC))
    scan_service = ScanService(
        settings,
        repo,
        topics,
        query_source_factory=(lambda: WordstatSource(settings))
        if settings.wordstat_configured
        else None,
        batch_source_factory=make_batch_factory(settings),
    )
    return AppContext(
        settings=settings,
        repo=repo,
        topics=topics,
        scan_service=scan_service,
        reports=ReportBuilder(settings, repo, topics),
    )
