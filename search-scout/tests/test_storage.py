from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import inspect

from app.services.normalizer import prepare
from app.sources.base import Observation
from app.storage.database import create_db_engine, init_database
from app.storage.migrations import LATEST_VERSION, current_version, migrate
from app.storage.models import Base, UTCDateTime
from app.storage.repository import (
    PreparedObservation,
    Repository,
    ScanAlreadyRunningError,
    ScoredItem,
)
from tests.conftest import FIXED_NOW


def obs(
    phrase: str,
    count: int | None,
    *,
    demo: bool = True,
    start: date = date(2026, 9, 1),
    period: str = "month",
    source: str = "test",
) -> PreparedObservation:
    end = date(2026, 9, 30) if period == "month" else start
    return PreparedObservation(
        phrase=prepare(phrase),  # type: ignore[arg-type]
        topic_key="invoices_acts",
        observation=Observation(
            phrase=phrase,
            count=count,
            period_type=period,
            period_start=start,  # type: ignore[arg-type]
            period_end=end,
            region_key="all",
            devices="all",
            source=source,
            is_demo=demo,
        ),
    )


def test_migrations_match_models(tmp_path: Path) -> None:
    engine = create_db_engine(tmp_path / "m.sqlite3")
    assert current_version(engine) == 0
    assert migrate(engine) == LATEST_VERSION
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == set(Base.metadata.tables)
    for name, table in Base.metadata.tables.items():
        db_columns = {c["name"] for c in inspector.get_columns(name)}
        assert db_columns == {c.name for c in table.columns}, name
    # Повторный запуск ничего не делает
    assert migrate(engine) == LATEST_VERSION


def test_reopen_existing_database(tmp_path: Path) -> None:
    path = tmp_path / "x.sqlite3"
    _, sf = init_database(path)
    repo = Repository(sf)
    repo.ensure_user(1, 1, True, FIXED_NOW)
    _, sf2 = init_database(path)
    assert Repository(sf2).get_user(1) is not None


def test_utc_datetime_roundtrip_and_naive_rejected() -> None:
    column = UTCDateTime()
    moscow = datetime(2026, 10, 13, 15, 0, tzinfo=ZoneInfo("Europe/Moscow"))
    stored = column.process_bind_param(moscow, None)
    assert stored == datetime(2026, 10, 13, 12, 0)
    assert column.process_result_value(stored, None) == moscow
    with pytest.raises(ValueError):
        column.process_bind_param(datetime(2026, 1, 1), None)


def test_store_observations_deduplicates(repo: Repository) -> None:
    stats = repo.store_observations(
        [
            obs("Генератор счетов", 100),
            obs("генератор  счетов", 100),
            obs("генератор счетов!", 100),
        ],
        FIXED_NOW,
    )
    assert stats["new_phrases"] == 1
    phrases = repo.phrases(is_demo=True)
    assert len(phrases) == 1
    assert phrases[0].original == "Генератор счетов"
    assert phrases[0].topic_key == "invoices_acts"


def test_snapshot_upsert_updates_value_without_duplicates(repo: Repository) -> None:
    repo.store_observations([obs("генератор счетов", 100)], FIXED_NOW)
    repo.store_observations([obs("генератор счетов", 150)], FIXED_NOW + timedelta(days=1))
    pid = repo.phrases(True)[0].id
    series = repo.series([pid], "all", "all", date(2026, 10, 13))[pid]
    assert series.monthly == [(date(2026, 9, 1), 150)]


def test_demo_and_real_never_mixed(repo: Repository) -> None:
    repo.store_observations([obs("генератор счетов", 100, demo=True)], FIXED_NOW)
    repo.store_observations([obs("генератор счетов", 7, demo=False)], FIXED_NOW)
    assert len(repo.phrases(is_demo=True)) == 1
    assert len(repo.phrases(is_demo=False)) == 1
    real_id = repo.phrases(False)[0].id
    assert repo.series([real_id], "all", "all", date(2026, 10, 13))[real_id].monthly[0][1] == 7


def test_series_skips_incomplete_month_and_none(repo: Repository) -> None:
    repo.store_observations(
        [
            obs("генератор счетов", 100),
            PreparedObservation(
                phrase=prepare("генератор счетов"),  # type: ignore[arg-type]
                topic_key=None,
                observation=Observation(
                    phrase="генератор счетов",
                    count=999,
                    period_type="month",
                    period_start=date(2026, 10, 1),
                    period_end=date(2026, 10, 31),
                    region_key="all",
                    devices="all",
                    source="test",
                    is_demo=True,
                ),
            ),
            obs("генератор счетов", None, period="rolling30", start=date(2026, 10, 1)),
        ],
        FIXED_NOW,
    )
    pid = repo.phrases(True)[0].id
    series = repo.series([pid], "all", "all", date(2026, 10, 13))[pid]
    assert series.monthly == [(date(2026, 9, 1), 100)]  # октябрь ещё не закончился
    assert series.rolling == []  # None — «нет данных», а не ноль
    assert series.rolling_without_count == 1


def test_scan_run_lock_and_stale_recovery(repo: Repository) -> None:
    run_id = repo.start_scan_run("manual", "demo", FIXED_NOW, stale_minutes=120)
    with pytest.raises(ScanAlreadyRunningError):
        repo.start_scan_run("manual", "demo", FIXED_NOW, stale_minutes=120)
    # Зависший запуск (старше порога) перестаёт блокировать
    later = FIXED_NOW + timedelta(hours=3)
    second = repo.start_scan_run("manual", "demo", later, stale_minutes=120)
    assert second != run_id
    repo.finish_scan_run(second, "success", {"top": 1}, None, later)
    last = repo.last_scan_run()
    assert last is not None and last.status == "success" and last.stats == {"top": 1}


def test_scheduled_scan_done_on_respects_timezone(repo: Repository) -> None:
    tz = ZoneInfo("Europe/Moscow")
    # 22:30 UTC 12.10 = 01:30 13.10 по Москве
    started = datetime(2026, 10, 12, 22, 30, tzinfo=UTC)
    run_id = repo.start_scan_run("scheduled", "demo", started, 120)
    repo.finish_scan_run(run_id, "success", {}, None, started)
    assert repo.scheduled_scan_done_on(date(2026, 10, 13), tz)
    assert not repo.scheduled_scan_done_on(date(2026, 10, 12), tz)


def test_notification_reserved_once(repo: Repository) -> None:
    repo.ensure_user(5, 5, True, FIXED_NOW)
    assert repo.reserve_notification(5, "daily_report", "2026-10-13", FIXED_NOW) is True
    assert repo.reserve_notification(5, "daily_report", "2026-10-13", FIXED_NOW) is False
    repo.release_notification(5, "daily_report", "2026-10-13")
    assert repo.reserve_notification(5, "daily_report", "2026-10-13", FIXED_NOW) is True


def test_daily_users_only_allowed(repo: Repository) -> None:
    repo.register_allowed_users([1, 2], True, FIXED_NOW)
    repo.ensure_user(3, 3, True, FIXED_NOW)  # уже не в списке разрешённых
    repo.set_daily(2, False)
    assert [u.id for u in repo.daily_users([1, 2])] == [1]


def test_scores_and_opportunities(repo: Repository) -> None:
    repo.store_observations([obs("генератор счетов", 100)], FIXED_NOW)
    pid = repo.phrases(True)[0].id
    item = ScoredItem(
        phrase_id=pid,
        total=70.0,
        is_preliminary=False,
        completeness=1.0,
        confidence="high",
        components={"trend": {"value": 80}},
        reasons=["тест"],
        data_used={"intent": "tool"},
        status="top",
        status_reason="тест",
        last_observed_on=date(2026, 9, 30),
    )
    repo.save_scores(None, "all", [item], FIXED_NOW)
    repo.save_scores(None, "all", [item], FIXED_NOW + timedelta(days=1))  # обновление, не дубль
    items = repo.list_opportunities("all", True, ("top",))
    assert len(items) == 1 and items[0].total == 70.0
    assert items[0].first_found_at == FIXED_NOW
    assert repo.list_opportunities("all", False, ("top",)) == []
    assert repo.prune_scores(FIXED_NOW + timedelta(days=400)) == 1  # старая, но не текущая


def test_seed_rotation(repo: Repository) -> None:
    seeds = repo.pick_seeds(3)
    assert len(seeds) == 3
    for seed in seeds:
        repo.mark_seed_scanned(seed.id, FIXED_NOW, 10)
    next_seeds = repo.pick_seeds(3)
    assert not {s.id for s in seeds} & {s.id for s in next_seeds}
    assert repo.add_expansion_seeds([("invoices_acts", "новый сид")], FIXED_NOW) == 1
    assert repo.add_expansion_seeds([("invoices_acts", "новый сид")], FIXED_NOW) == 0
