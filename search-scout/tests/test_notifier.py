from datetime import date

from app.services.notifier import Notifier, RecipientUnavailableError
from tests.conftest import FIXED_NOW


class FakeReports:
    def daily_report(self, day: date) -> list[str]:
        return [f"отчёт {day}", "часть 2"]


class FakeSender:
    def __init__(self, fail_with: Exception | None = None) -> None:
        self.sent: list[tuple[int, str]] = []
        self.fail_with = fail_with

    async def __call__(self, chat_id: int, text: str) -> None:
        if self.fail_with:
            raise self.fail_with
        self.sent.append((chat_id, text))


def make(settings, repo, sender) -> Notifier:
    repo.register_allowed_users(settings.allowed_user_ids, True, FIXED_NOW)
    return Notifier(settings, repo, FakeReports(), sender, clock=lambda: FIXED_NOW)  # type: ignore[arg-type]


async def test_daily_report_sent_once(make_settings, repo) -> None:
    sender = FakeSender()
    notifier = make(make_settings(allowed_user_ids="111,222"), repo, sender)
    first = await notifier.send_daily(date(2026, 10, 13))
    second = await notifier.send_daily(date(2026, 10, 13))
    assert first == {"sent": 2, "skipped": 0, "failed": 0}
    assert second == {"sent": 0, "skipped": 2, "failed": 0}
    assert len(sender.sent) == 4  # 2 пользователя × 2 сообщения, без повторов
    # Новый день — новый отчёт
    assert (await notifier.send_daily(date(2026, 10, 14)))["sent"] == 2


async def test_temporary_failure_allows_retry(make_settings, repo) -> None:
    settings = make_settings()
    failing = make(settings, repo, FakeSender(RuntimeError("network")))
    assert (await failing.send_daily(date(2026, 10, 13)))["failed"] == 1
    ok_sender = FakeSender()
    retry = Notifier(settings, repo, FakeReports(), ok_sender, clock=lambda: FIXED_NOW)  # type: ignore[arg-type]
    assert (await retry.send_daily(date(2026, 10, 13)))["sent"] == 1


async def test_blocked_user_not_retried(make_settings, repo) -> None:
    settings = make_settings()
    blocked = make(settings, repo, FakeSender(RecipientUnavailableError("blocked")))
    assert (await blocked.send_daily(date(2026, 10, 13)))["failed"] == 1
    again = Notifier(settings, repo, FakeReports(), FakeSender(), clock=lambda: FIXED_NOW)  # type: ignore[arg-type]
    assert (await again.send_daily(date(2026, 10, 13)))["skipped"] == 1


async def test_disabled_daily_not_sent(make_settings, repo) -> None:
    settings = make_settings()
    sender = FakeSender()
    notifier = make(settings, repo, sender)
    repo.set_daily(111, False)
    assert await notifier.send_daily(date(2026, 10, 13)) == {"sent": 0, "skipped": 0, "failed": 0}
