"""Доступ к командам и обработчики бота (без обращения к Telegram)."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.types import Chat, Message, User

from app.bot import handlers
from app.bot.access import AccessMiddleware, is_allowed
from app.context import AppContext, make_batch_factory
from app.services.collector import ScanService
from app.services.report import ReportBuilder
from tests.conftest import FIXED_NOW
from tests.test_collector import write_csv


def tg_message(user_id: int, text: str = "/scan") -> Message:
    return Message(
        message_id=1,
        date=datetime(2026, 10, 13),
        chat=Chat(id=user_id, type="private"),
        from_user=User(id=user_id, is_bot=False, first_name="Тест"),
        text=text,
    )


def fake_message(user_id: int = 111) -> SimpleNamespace:
    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id),
        chat=SimpleNamespace(id=user_id),
        answer=AsyncMock(),
        answer_document=AsyncMock(),
    )


def test_is_allowed() -> None:
    assert is_allowed(1, {1, 2})
    assert not is_allowed(3, {1, 2})
    assert not is_allowed(None, {1})
    assert not is_allowed(1, set())  # пустой список — никого не пускаем


async def test_middleware_passes_allowed_user() -> None:
    handler = AsyncMock(return_value="ok")
    middleware = AccessMiddleware([111])
    event = tg_message(111)
    result = await middleware(handler, event, {"event_from_user": event.from_user})
    assert result == "ok"
    handler.assert_awaited_once()


async def test_middleware_blocks_stranger_and_tells_id_once_per_minute() -> None:
    handler = AsyncMock()
    clock = iter([0.0, 10.0, 100.0])
    middleware = AccessMiddleware([111], clock=lambda: next(clock))
    event = tg_message(999)
    with patch.object(Message, "answer", AsyncMock()) as answer:
        for _ in range(3):
            assert await middleware(handler, event, {"event_from_user": event.from_user}) is None
    handler.assert_not_awaited()
    assert answer.await_count == 2  # 0 с и 100 с; на 10 с — без ответа
    assert "999" in answer.await_args_list[0].args[0]


async def test_middleware_blocks_event_without_user() -> None:
    handler = AsyncMock()
    assert await AccessMiddleware([111])(handler, object(), {}) is None  # type: ignore[arg-type]
    handler.assert_not_awaited()


async def make_ctx(make_settings, repo, topics, tmp_path) -> AppContext:
    settings = make_settings(csv_import_path=write_csv(tmp_path))
    scan = ScanService(
        settings,
        repo,
        topics,
        batch_source_factory=make_batch_factory(settings),
        clock=lambda: FIXED_NOW,
    )
    return AppContext(
        settings=settings,
        repo=repo,
        topics=topics,
        scan_service=scan,
        reports=ReportBuilder(settings, repo, topics),
        clock=lambda: FIXED_NOW,
    )


async def test_scan_command_runs_in_background(make_settings, repo, topics, tmp_path) -> None:
    ctx = await make_ctx(make_settings, repo, topics, tmp_path)
    message = fake_message()
    await handlers.cmd_scan(message, ctx)  # type: ignore[arg-type]
    for task in list(ctx._tasks):
        await task
    texts = [c.args[0] for c in message.answer.await_args_list]
    assert texts[0].startswith("Запускаю сканирование")
    assert "Сканирование #1" in texts[-1]


async def test_scan_command_when_live_unavailable(make_settings, repo, topics, tmp_path) -> None:
    ctx = await make_ctx(make_settings, repo, topics, tmp_path)
    ctx.settings = make_settings(scout_mode="live")
    message = fake_message()
    await handlers.cmd_scan(message, ctx)  # type: ignore[arg-type]
    assert "Live-режим недоступен" in message.answer.await_args.args[0]
    assert not ctx._tasks


async def test_report_top_watchlist_export_status(make_settings, repo, topics, tmp_path) -> None:
    ctx = await make_ctx(make_settings, repo, topics, tmp_path)
    await ctx.scan_service.run("manual")
    for command in (
        handlers.cmd_report,
        handlers.cmd_top,
        handlers.cmd_watchlist,
        handlers.cmd_status,
        handlers.cmd_settings,
    ):
        message = fake_message()
        await command(message, ctx)  # type: ignore[arg-type]
        assert message.answer.await_count >= 1, command.__name__
    message = fake_message()
    await handlers.cmd_export(message, ctx)  # type: ignore[arg-type]
    document = message.answer_document.await_args.args[0]
    assert document.filename.endswith(".csv")


async def test_daily_on_off(make_settings, repo, topics, tmp_path) -> None:
    ctx = await make_ctx(make_settings, repo, topics, tmp_path)
    message = fake_message()
    await handlers.cmd_daily_off(message, ctx)  # type: ignore[arg-type]
    assert repo.get_user(111).daily_enabled is False  # type: ignore[union-attr]
    await handlers.cmd_daily_on(message, ctx)  # type: ignore[arg-type]
    assert repo.get_user(111).daily_enabled is True  # type: ignore[union-attr]


async def test_import_csv_via_telegram(make_settings, repo, topics, tmp_path) -> None:
    from aiogram.filters import CommandObject

    ctx = await make_ctx(make_settings, repo, topics, tmp_path)
    data = "phrase,count,period,date\nгенератор актов онлайн,300,30d,2026-10-01\n".encode()

    async def download(document, destination) -> None:
        destination.write(data)

    message = fake_message()
    message.document = SimpleNamespace(file_name="test.csv", file_size=len(data))
    message.bot = SimpleNamespace(download=download)
    await handlers.cmd_import(message, CommandObject(command="import", args=None), ctx)  # type: ignore[arg-type]
    assert "тестовые данные" in message.answer.await_args_list[0].args[0]
    phrases = [p.normalized for p in repo.phrases(is_demo=True)]
    assert phrases == ["генератор актов онлайн"]
    assert repo.phrase_count(is_demo=False) == 0

    message = fake_message()
    message.document = SimpleNamespace(file_name="photo.png", file_size=10)
    await handlers.cmd_import(message, CommandObject(command="import", args=None), ctx)  # type: ignore[arg-type]
    assert ".csv" in message.answer.await_args.args[0]
