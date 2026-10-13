"""Конвейер сканирования на синтетических данных (тестовые CSV и поддельный источник)."""

from datetime import date, timedelta
from pathlib import Path

import pytest

from app.config import ModeUnavailableError
from app.context import make_batch_factory
from app.services.collector import ScanService, prepare_observations
from app.sources.base import Observation, QuerySource, SourceAuthError, SourceTemporaryError
from app.storage.repository import Repository
from tests.conftest import FIXED_NOW


class FakeSource(QuerySource):
    """Поддельный live-источник с заранее заданными (синтетическими) ответами."""

    name = "wordstat"
    is_live = True

    def __init__(self, fail: dict[str, Exception] | None = None) -> None:
        self.fail = fail or {}
        self.related_calls: list[str] = []
        self.dynamics_calls: list[str] = []
        self.requests_made = 0

    def _obs(self, phrase, count, start, end, period, topic=None):
        return Observation(phrase, count, period, start, end, "all", "all", self.name, False, topic)

    async def related(self, seed, topic_key):
        self.related_calls.append(seed)
        self.requests_made += 1
        if seed in self.fail:
            raise self.fail[seed]
        day = date(2026, 10, 13)
        start = day - timedelta(days=29)
        return [
            self._obs(seed, 500, start, day, "rolling30", topic_key),
            self._obs(f"{seed} онлайн", 300, start, day, "rolling30", topic_key),
            self._obs("рецепт борща", 9999, start, day, "rolling30", topic_key),
        ]

    @property
    def supports_dynamics(self):
        return True

    async def monthly_dynamics(self, phrase):
        self.dynamics_calls.append(phrase)
        self.requests_made += 1
        result = []
        for i in range(12):
            month = date(2025, 10, 1).replace(year=2025 + (9 + i) // 12, month=(9 + i) % 12 + 1)
            end = (month.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
            result.append(self._obs(phrase, 100 + 30 * i, month, end, "month"))
        return result


def make_service(settings, repo, topics, source=None):
    return ScanService(
        settings,
        repo,
        topics,
        query_source_factory=(lambda: source) if source else None,
        batch_source_factory=make_batch_factory(settings),
        clock=lambda: FIXED_NOW,
    )


def write_csv(tmp_path: Path) -> Path:
    path = tmp_path / "test_data.csv"
    lines = ["# ТЕСТОВЫЕ СИНТЕТИЧЕСКИЕ ДАННЫЕ", "phrase,count,period,date"]
    for i in range(8):
        lines.append(f"генератор счетов для ип,{100 + 40 * i},month,2026-{2 + i:02d}-01")
    lines.append("новый конвертер pdf онлайн,200,30d,2026-10-01")
    lines.append("рецепт борща,5000,30d,2026-10-01")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def test_prepare_observations_filters_irrelevant(topics) -> None:
    day = date(2026, 10, 1)
    items = [
        Observation("Конвертер PDF", 1, "rolling30", day, day, "all", "all", "t", True),
        Observation(
            "скачать фотошоп торрент аналог", 1, "rolling30", day, day, "all", "all", "t", True
        ),
        Observation("рецепт борща", 1, "rolling30", day, day, "all", "all", "t", True),
        Observation("  ", 1, "rolling30", day, day, "all", "all", "t", True),
    ]
    prepared, rejected = prepare_observations(items, topics)
    assert [p.phrase.normalized for p in prepared] == ["конвертер pdf"]
    assert rejected == {"стоп-слово": 1, "вне тематик": 1, "пустая фраза": 1}


async def test_demo_scan_end_to_end(make_settings, repo: Repository, topics, tmp_path) -> None:
    settings = make_settings(csv_import_path=write_csv(tmp_path), csv_is_demo=True)
    service = make_service(settings, repo, topics)
    summary = await service.run("manual")
    assert summary.mode == "demo" and summary.status == "success"
    assert summary.stats["filtered"] == {"вне тематик": 1}
    top = repo.list_opportunities("all", True, ("top",))
    watch = repo.list_opportunities("all", True, ("watch",))
    assert [o.normalized for o in top] == ["генератор счетов для ип"]
    assert top[0].is_preliminary is False and top[0].is_demo is True
    assert [o.normalized for o in watch] == ["новый конвертер pdf онлайн"]
    assert watch[0].is_preliminary is True
    # Повторное сканирование не создаёт дублей
    await service.run("manual")
    assert repo.phrase_count(True) == 2


async def test_live_scan_with_fake_source(make_settings, repo, topics) -> None:
    settings = make_settings(
        wordstat_api_key="k",
        wordstat_folder_id="f",
        wordstat_max_requests_per_scan=6,
        wordstat_dynamics_per_scan=2,
    )
    source = FakeSource()
    summary = await make_service(settings, repo, topics, source).run("manual")
    assert summary.mode == "live" and summary.status == "success"
    assert len(source.related_calls) == 4  # 6 - 2 на динамику
    assert len(source.dynamics_calls) <= 2
    assert summary.stats["filtered"]["вне тематик"] == 4  # «рецепт борща» из каждого ответа
    assert repo.phrase_count(is_demo=False) > 0
    assert repo.phrase_count(is_demo=True) == 0
    # Фразы с динамикой получают полный рейтинг
    scored = repo.list_opportunities("all", False, ("top", "watch", "rejected"))
    with_history = [o for o in scored if o.data_used["monthly_points"] == 12]
    assert with_history and all(not o.is_preliminary for o in with_history)


async def test_live_scan_partial_on_temporary_errors(make_settings, repo, topics) -> None:
    settings = make_settings(
        wordstat_api_key="k",
        wordstat_folder_id="f",
        wordstat_max_requests_per_scan=4,
        wordstat_dynamics_per_scan=0,
    )
    first_seed = repo.pick_seeds(1)[0].phrase
    source = FakeSource(fail={first_seed: SourceTemporaryError("HTTP 503")})
    summary = await make_service(settings, repo, topics, source).run("manual")
    assert summary.status == "partial"
    assert summary.stats["seeds_failed"] == 1
    assert any("503" in e for e in summary.errors)


async def test_live_scan_auth_error_fails_run(make_settings, repo, topics) -> None:
    settings = make_settings(
        wordstat_api_key="k",
        wordstat_folder_id="f",
        wordstat_max_requests_per_scan=3,
        wordstat_dynamics_per_scan=0,
    )
    seeds = [s.phrase for s in repo.pick_seeds(3)]
    source = FakeSource(fail={s: SourceAuthError("HTTP 403") for s in seeds})
    summary = await make_service(settings, repo, topics, source).run("manual")
    assert summary.status == "failed"
    last = repo.last_scan_run()
    assert last is not None and last.status == "failed" and "403" in (last.error or "")


async def test_live_mode_without_keys_is_refused(make_settings, repo, topics) -> None:
    service = make_service(make_settings(scout_mode="live"), repo, topics)
    with pytest.raises(ModeUnavailableError):
        await service.run("manual")
    assert repo.last_scan_run() is None


async def test_demo_csv_not_imported_in_live_mode(make_settings, repo, topics, tmp_path) -> None:
    settings = make_settings(
        wordstat_api_key="k",
        wordstat_folder_id="f",
        csv_import_path=write_csv(tmp_path),
        csv_is_demo=True,
        wordstat_max_requests_per_scan=2,
        wordstat_dynamics_per_scan=0,
    )
    await make_service(settings, repo, topics, FakeSource()).run("manual")
    assert repo.phrase_count(is_demo=True) == 0


async def test_concurrent_scan_rejected(make_settings, repo, topics, tmp_path) -> None:
    import asyncio

    from app.storage.repository import ScanAlreadyRunningError

    settings = make_settings(csv_import_path=write_csv(tmp_path))
    service = make_service(settings, repo, topics)
    first = asyncio.create_task(service.run("manual"))
    await asyncio.sleep(0)
    with pytest.raises(ScanAlreadyRunningError):
        await service.run("manual")
    await first
