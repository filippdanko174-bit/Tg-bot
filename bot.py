"""Точка входа. Запуск: python bot.py"""
from __future__ import annotations

import asyncio
import logging

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllChatAdministrators,
    BotCommandScopeDefault,
    ErrorEvent,
    Message,
)

import config
import utils
from common_handlers import router as common_router
from db import DB
from eco_handlers import router as eco_router
from mod_handlers import router as mod_router
from work_handlers import router as work_router
from owner_handlers import router as owner_router
from feature_db import init_features

log = logging.getLogger("bot")


class TrackUsers(BaseMiddleware):
    """Запоминает ники и имена, чтобы команды работали по @нику."""

    async def __call__(self, handler, event: Message, data):
        db: DB = data["db"]
        try:
            for user in (event.from_user, event.reply_to_message.from_user if event.reply_to_message else None):
                if user is not None and not user.is_bot:
                    await db.upsert_user(user.id, user.username, user.full_name)
        except Exception:  # учёт пользователей не должен ломать обработку команды
            log.exception("Не удалось сохранить пользователя")
        return await handler(event, data)


async def on_error(event: ErrorEvent) -> bool:
    log.error("Ошибка при обработке обновления", exc_info=event.exception)
    return True


PUBLIC_COMMANDS = [
    BotCommand(command="work", description="Выйти на смену"),
    BotCommand(command="jobs", description="Список работ"),
    BotCommand(command="profile", description="Мой профиль"),
    BotCommand(command="balance", description="Баланс монет"),
    BotCommand(command="pay", description="Передать монеты"),
    BotCommand(command="top", description="Самые богатые"),
    BotCommand(command="quit", description="Уволиться"),
    BotCommand(command="warns", description="Сколько варнов"),
    BotCommand(command="help", description="Все команды"),
]
ADMIN_COMMANDS = PUBLIC_COMMANDS + [
    BotCommand(command="ban", description="Забанить"),
    BotCommand(command="unban", description="Разбанить"),
    BotCommand(command="kick", description="Выгнать"),
    BotCommand(command="mute", description="Замутить"),
    BotCommand(command="unmute", description="Размутить"),
    BotCommand(command="warn", description="Выдать варн"),
    BotCommand(command="unwarn", description="Снять варн"),
    BotCommand(command="del", description="Удалить сообщение"),
    BotCommand(command="purge", description="Почистить чат"),
]


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not config.BOT_TOKEN:
        raise SystemExit("Не задан BOT_TOKEN. Укажи токен от @BotFather в переменных окружения или в файле .env")
    if not config.OWNER_IDS:
        log.warning("OWNER_ID не задан: команды владельца (/выдать, /забрать) работать не будут.")

    db = DB(config.DB_PATH)
    await db.init()
    await init_features(db)

    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    me = await bot.get_me()
    utils.BOT_USERNAME = me.username or ""
    log.info("Запущен бот @%s", me.username)

    dp = Dispatcher(db=db)
    dp.message.outer_middleware(TrackUsers())
    dp.errors.register(on_error)
    dp.include_routers(owner_router, mod_router, eco_router, work_router, common_router)

    try:
        await bot.set_my_commands(PUBLIC_COMMANDS, scope=BotCommandScopeDefault())
        await bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeAllChatAdministrators())
    except Exception:
        log.exception("Не удалось выставить меню команд (не критично)")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
