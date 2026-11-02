"""Справка и /id."""
from __future__ import annotations

from aiogram import Router
from aiogram.types import Message

from utils import Cmd

router = Router(name="common")

HELP = """<b>🤖 Бот-админ чата</b>

<b>🛡 Модерация</b> (для админов; ответом на сообщение или @ник / ID)
/бан [время] [причина] — бан (без времени навсегда)
/разбан — снять бан
/кик — выгнать (можно вернуться)
/мут [время] [причина] — запретить писать (без времени 1 час)
/размут — снять мут
/варн [причина] — предупреждение (3 варна = мут на 24 ч)
/снятьварн — убрать один варн
/варны — сколько варнов
/удалить — удалить сообщение (ответом)
/чистка — удалить всё от выбранного сообщения до команды (до 100)
/закрепить и /открепить — закреп (ответом)
Время: 30м, 2ч, 1д, 1н или «навсегда».

<b>🪙 Монеты и работа</b>
/работа — выйти на смену и заработать монеты
/работы — список работ, выбрать работу
/уволиться — уйти с работы
/профиль — твой профиль и прогресс
/баланс — баланс
/передать [@ник] сумма — перевести монеты
/топ — самые богатые

<b>👑 Владелец бота</b>
/выдать [@ник] сумма — выдать монеты
/забрать [@ник] сумма — забрать монеты

<b>ℹ️ Прочее</b>
/id — твой ID и ID чата

Команды работают и латиницей: /ban /mute /warn /work /jobs /balance /pay /give."""


@router.message(Cmd("start", "help", "помощь", "хелп", "команды"))
async def cmd_help(message: Message) -> None:
    await message.reply(HELP)


@router.message(Cmd("id", "айди"))
async def cmd_id(message: Message) -> None:
    lines = []
    if message.from_user is not None:
        lines.append(f"🆔 Твой ID: <code>{message.from_user.id}</code>")
    reply = message.reply_to_message
    if reply is not None and reply.from_user is not None and reply.forum_topic_created is None:
        lines.append(f"🆔 ID автора сообщения: <code>{reply.from_user.id}</code>")
    lines.append(f"💬 ID чата: <code>{message.chat.id}</code>")
    await message.reply("\n".join(lines))
