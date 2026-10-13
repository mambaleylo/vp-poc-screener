from datetime import UTC, datetime

from app.context import make_batch_factory
from app.scheduler import DailyScheduler
from app.services.collector import ScanService
from app.services.notifier import Notifier
from app.services.report import ReportBuilder
from tests.test_collector import write_csv


def build(make_settings, repo, topics, tmp_path, now: datetime, sent: list):
    settings = make_settings(
        csv_import_path=write_csv(tmp_path), daily_time="09:00", timezone="Europe/Moscow"
    )
    repo.register_allowed_users(settings.allowed_user_ids, True, now)
    scan = ScanService(
        settings, repo, topics, batch_source_factory=make_batch_factory(settings), clock=lambda: now
    )

    async def send(chat_id: int, text: str) -> None:
        sent.append((chat_id, text))

    notifier = Notifier(
        settings, repo, ReportBuilder(settings, repo, topics), send, clock=lambda: now
    )
    return DailyScheduler(settings, repo, scan, notifier, clock=lambda: now)


async def test_catch_up_after_restart_runs_once(make_settings, repo, topics, tmp_path) -> None:
    now = datetime(2026, 10, 13, 7, 30, tzinfo=UTC)  # 10:30 по Москве — время отчёта прошло
    sent: list = []
    scheduler = build(make_settings, repo, topics, tmp_path, now, sent)
    await scheduler.catch_up()
    assert repo.last_scan_run().trigger == "scheduled"  # type: ignore[union-attr]
    messages_after_first = len(sent)
    assert messages_after_first >= 1
    # «Перезапуск»: новый планировщик в тот же день не дублирует ни скан, ни отчёт
    again = build(make_settings, repo, topics, tmp_path, now, sent)
    await again.catch_up()
    assert len(sent) == messages_after_first
    assert repo.last_scan_run().id == 1  # type: ignore[union-attr]


async def test_catch_up_before_daily_time_does_nothing(
    make_settings, repo, topics, tmp_path
) -> None:
    now = datetime(2026, 10, 13, 5, 0, tzinfo=UTC)  # 08:00 по Москве
    sent: list = []
    await build(make_settings, repo, topics, tmp_path, now, sent).catch_up()
    assert sent == [] and repo.last_scan_run() is None


async def test_job_is_scheduled_in_local_timezone(make_settings, repo, topics, tmp_path) -> None:
    now = datetime(2026, 10, 13, 5, 0, tzinfo=UTC)
    scheduler = build(make_settings, repo, topics, tmp_path, now, [])
    scheduler.start()
    try:
        next_run = scheduler.next_run_time()
        assert next_run is not None
        assert (next_run.hour, next_run.minute) == (9, 0)
        assert str(next_run.tzinfo) == "Europe/Moscow"
    finally:
        scheduler.shutdown()
