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
    BotCommandScopeChat,
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
from shop_handlers import router as shop_router
from fun_handlers import router as fun_router
from misc_handlers import router as misc_router
from ai_handlers import router as ai_router

log = logging.getLogger("bot")


class TrackUsers(BaseMiddleware):
    """Запоминает ники и имена, чтобы команды работали по @нику."""

    async def __call__(self, handler, event: Message, data):
        db: DB = data["db"]
        try:
            for user in (event.from_user, event.reply_to_message.from_user if event.reply_to_message else None):
                if user is not None and not user.is_bot:
                    await db.upsert_user(user.id, user.username, user.full_name)
        except Exception:
            log.exception("Не удалось сохранить пользователя")
        return await handler(event, data)


async def on_error(event: ErrorEvent) -> bool:
    log.error("Ошибка при обработке обновления", exc_info=event.exception)
    return True


# В Telegram меню команд поддерживает только латинские имена.
PUBLIC_COMMANDS = [
    BotCommand(command="start", description="Запустить бота"),
    BotCommand(command="help", description="Все команды и помощь"),
    BotCommand(command="ai", description="Задать вопрос ИИ"),
    BotCommand(command="aiclear", description="Очистить контекст ИИ"),
    BotCommand(command="id", description="Узнать ID пользователя и чата"),
    BotCommand(command="ping", description="Проверить связь с Telegram"),
    BotCommand(command="coin", description="Подбросить монетку"),
    BotCommand(command="dice", description="Бросить кубик"),
    BotCommand(command="number", description="Случайное число"),
    BotCommand(command="work", description="Выйти на смену и заработать"),
    BotCommand(command="jobs", description="Список работ"),
    BotCommand(command="profile", description="Мой профиль"),
    BotCommand(command="balance", description="Баланс монет"),
    BotCommand(command="pay", description="Передать монеты"),
    BotCommand(command="top", description="Рейтинг по монетам"),
    BotCommand(command="shop", description="Магазин за монеты"),
    BotCommand(command="inventory", description="Моя коллекция и титул"),
    BotCommand(command="title", description="Титулы и привилегии"),
    BotCommand(command="quit", description="Уволиться с работы"),
    BotCommand(command="staff", description="Список стаффа"),
    BotCommand(command="role", description="Посмотреть свою или чужую роль"),
    BotCommand(command="zavoz", description="Запустить мемный завоз"),
    BotCommand(command="vibe", description="Проверить свой вайб"),
    BotCommand(command="rofl", description="Случайная шутка"),
    BotCommand(command="warns", description="Количество предупреждений"),
    BotCommand(command="zov_on", description="Включить упоминания"),
    BotCommand(command="zov_off", description="Отключить упоминания"),
    BotCommand(command="zov", description="Позвать подписавшихся участников"),
]

ADMIN_COMMANDS = PUBLIC_COMMANDS + [
    BotCommand(command="ban", description="Забанить участника"),
    BotCommand(command="unban", description="Снять бан"),
    BotCommand(command="kick", description="Выгнать участника"),
    BotCommand(command="mute", description="Запретить писать"),
    BotCommand(command="unmute", description="Снять мут"),
    BotCommand(command="warn", description="Выдать предупреждение"),
    BotCommand(command="unwarn", description="Снять предупреждение"),
    BotCommand(command="del", description="Удалить сообщение"),
    BotCommand(command="purge", description="Очистить сообщения"),
    BotCommand(command="pin", description="Закрепить сообщение"),
    BotCommand(command="unpin", description="Открепить сообщение"),
]

OWNER_COMMANDS = PUBLIC_COMMANDS + [
    BotCommand(command="give", description="Выдать игровые монеты"),
    BotCommand(command="take", description="Забрать игровые монеты"),
    BotCommand(command="adminpanel", description="Панель владельца"),
    BotCommand(command="useredit", description="Редактор пользователя"),
    BotCommand(command="welcome", description="Настроить приветствие группы"),
    BotCommand(command="roles", description="Список пользовательских ролей"),
    BotCommand(command="rolecreate", description="Создать роль и приоритет 0–100"),
    BotCommand(command="roledelete", description="Удалить пользовательскую роль"),
    BotCommand(command="rolepriority", description="Изменить приоритет роли"),
    BotCommand(command="roleset", description="Назначить роль пользователю"),
    BotCommand(command="roleremove", description="Снять роль с пользователя"),
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
    try:
        me = await bot.get_me()
        utils.BOT_USERNAME = me.username or ""
        log.info("Запущен бот @%s", me.username)

        dp = Dispatcher(db=db)
        dp.message.outer_middleware(TrackUsers())
        dp.errors.register(on_error)
        dp.include_routers(
            owner_router, mod_router, eco_router, work_router,
            shop_router, common_router, fun_router, misc_router, ai_router,
        )

        try:
            await bot.set_my_commands(PUBLIC_COMMANDS, scope=BotCommandScopeDefault())
            await bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeAllChatAdministrators())
            for owner_id in config.OWNER_IDS:
                await bot.set_my_commands(OWNER_COMMANDS, scope=BotCommandScopeChat(chat_id=owner_id))
        except Exception:
            log.exception("Не удалось выставить меню команд (не критично)")

        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
