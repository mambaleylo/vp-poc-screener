"""Общие фикстуры. Все данные в тестах — СИНТЕТИЧЕСКИЕ (тестовые), не рыночные."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.config import PROJECT_ROOT, Settings
from app.storage.database import init_database
from app.storage.repository import Repository
from app.topics import TopicsConfig, load_topics

FIXED_NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Переменные окружения разработчика не должны влиять на тесты."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


@pytest.fixture
def make_settings(tmp_path: Path) -> Callable[..., Settings]:
    def factory(**overrides: object) -> Settings:
        values: dict[str, object] = {
            "database_path": tmp_path / "test.sqlite3",
            "csv_import_path": None,
            "allowed_user_ids": "111",
            "scout_mode": "auto",
        }
        values.update(overrides)
        return Settings(_env_file=None, **values)  # type: ignore[call-arg]

    return factory


@pytest.fixture
def settings(make_settings: Callable[..., Settings]) -> Settings:
    return make_settings()


@pytest.fixture(scope="session")
def topics() -> TopicsConfig:
    return load_topics(PROJECT_ROOT / "config" / "topics.toml")


@pytest.fixture
def repo(topics: TopicsConfig) -> Repository:
    _, session_factory = init_database(":memory:")
    repository = Repository(session_factory)
    repository.sync_topics(topics, FIXED_NOW)
    return repository


def monthly(start: date, values: list[int]) -> list[tuple[date, int]]:
    """Синтетический помесячный ряд, начиная с месяца start."""
    result = []
    year, month = start.year, start.month
    for value in values:
        result.append((date(year, month, 1), value))
        month += 1
        if month > 12:
            month, year = 1, year + 1
    return result
