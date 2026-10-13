"""Запуск Telegram-бота."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from app.bot.access import AccessMiddleware
from app.bot.handlers import COMMANDS, router
from app.config import Settings
from app.context import build_context
from app.scheduler import DailyScheduler
from app.services.notifier import Notifier, RecipientUnavailableError
from app.single_instance import SingleInstanceLock

log = logging.getLogger(__name__)


def lock_path(settings: Settings):
    return settings.db_file.with_suffix(".lock")


async def run_bot(settings: Settings) -> None:
    if settings.telegram_bot_token is None:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN не задан. Создайте бота у @BotFather и впишите токен в .env "
            "(см. README)."
        )
    if not settings.allowed_user_ids:
        log.warning(
            "ALLOWED_USER_IDS пуст — бот никому не будет отвечать. Напишите боту, он сообщит "
            "ваш ID; впишите его в .env и перезапустите."
        )

    instance_lock = SingleInstanceLock(lock_path(settings))
    instance_lock.acquire()
    try:
        ctx = build_context(settings)
        now = ctx.clock()
        interrupted = ctx.repo.interrupt_running_runs(now)
        if interrupted:
            log.warning(
                "Найдено %s незавершённых сканирований — отмечены как прерванные", interrupted
            )
        ctx.repo.register_allowed_users(
            settings.allowed_user_ids, settings.daily_default_enabled, now
        )

        session = (
            AiohttpSession(api=TelegramAPIServer.from_base(settings.telegram_api_base))
            if settings.telegram_api_base
            else None
        )
        bot = Bot(
            token=settings.telegram_bot_token.get_secret_value(),
            session=session,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
        )

        async def send(chat_id: int, text: str) -> None:
            try:
                await bot.send_message(chat_id, text)
            except TelegramForbiddenError as exc:
                raise RecipientUnavailableError(str(exc)) from exc
            except TelegramBadRequest as exc:
                if "chat not found" in str(exc).lower():
                    raise RecipientUnavailableError(str(exc)) from exc
                raise

        notifier = Notifier(settings, ctx.repo, ctx.reports, send)
        scheduler = DailyScheduler(settings, ctx.repo, ctx.scan_service, notifier)
        ctx.scheduler = scheduler

        dp = Dispatcher()
        dp["ctx"] = ctx
        access = AccessMiddleware(settings.allowed_user_ids)
        dp.message.outer_middleware(access)
        dp.callback_query.outer_middleware(access)
        dp.include_router(router)

        try:
            # Если раньше был настроен webhook, polling работать не будет.
            await bot.delete_webhook(drop_pending_updates=False)
            await bot.set_my_commands(COMMANDS)
            me = await bot.get_me()
            log.info("Бот @%s запущен. Режим: %s", me.username, settings.scout_mode)
            scheduler.start()
            ctx.spawn(scheduler.catch_up())
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
        finally:
            scheduler.shutdown()
            await bot.session.close()
    finally:
        instance_lock.release()


def main(settings: Settings) -> None:
    asyncio.run(run_bot(settings))
