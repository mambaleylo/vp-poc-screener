"""Проверка настоящего Wordstat API. По умолчанию НЕ запускается.

Запуск (тратит 1–2 запроса квоты):
    SCOUT_LIVE_TESTS=1 pytest -m live
Ключи берутся из .env.
"""

import os

import pytest

from app.config import Settings
from app.sources.wordstat import WordstatSource

pytestmark = pytest.mark.live


@pytest.fixture
def live_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    if os.environ.get("SCOUT_LIVE_TESTS") != "1":
        pytest.skip("SCOUT_LIVE_TESTS=1 не задан")
    settings = Settings()
    if not settings.wordstat_configured:
        pytest.skip("WORDSTAT_API_KEY / WORDSTAT_FOLDER_ID не заданы в .env")
    return settings


async def test_top_requests_live(live_settings: Settings) -> None:
    source = WordstatSource(live_settings)
    try:
        observations = await source.related("конвертер pdf", None)
    finally:
        await source.aclose()
    assert observations, "API вернул пустой ответ"
    assert all(o.count is None or o.count >= 0 for o in observations)
