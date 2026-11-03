"""Справка и /id."""
from __future__ import annotations

from aiogram import Router
from aiogram.types import Message
from html import escape

from utils import Cmd

router = Router(name="common")

HELP = """<b>🤖 Команды бота</b>

<b>🪙 Монеты и работа</b>
/работа — выйти на смену и заработать монеты
/работы — список работ
/уволиться — уйти с работы
/профиль — твой профиль и прогресс
/баланс — посмотреть баланс
/передать [@ник] сумма — перевести монеты
/топ — рейтинг по монетам

<b>🛍 Магазин и титулы</b>
/магазин — купить предметы за монеты
/инвентарь — коллекция и выбор титула
/титул — привилегии активного титула

<b>📢 Упоминания</b>
/зов_вкл — согласиться получать упоминания
/зов_выкл — отказаться от упоминаний
/зов — позвать подписавшихся участников

<b>ℹ️ Прочее</b>
/стафф — список стаффа\n/id — твой ID и ID чата
/help — показать эту справку

Команды также доступны на английском: /work /jobs /profile /balance /pay /top /shop /inventory /title."""

@router.message(Cmd("start", "help", "помощь", "хелп", "команды"))
async def cmd_help(message: Message) -> None:
    await message.reply(HELP)


@router.message(Cmd("стафф", "staff"))
async def cmd_staff(message: Message, db: DB) -> None:
    async with db.conn.execute(
        "SELECT u.user_id, u.username, u.first_name, u.custom_nick, u.role, "
        "COALESCE(r.priority, 0) AS priority "
        "FROM users u LEFT JOIN custom_roles r ON r.name=u.role COLLATE NOCASE "
        "WHERE u.role IS NOT NULL AND u.role!='' "
        "ORDER BY priority DESC, u.role COLLATE NOCASE, u.user_id LIMIT 100"
    ) as cur:
        rows = await cur.fetchall()
    if not rows:
        await message.reply("👥 Пока в стаффе никого нет.")
        return
    lines = ["👥 <b>Стафф</b>", ""]
    for row in rows:
        name = row["custom_nick"] or row["first_name"] or (f"@{row['username']}" if row["username"] else str(row["user_id"]))
        role = row["role"]
        priority = row["priority"]
        lines.append(
            f"• <a href=\"tg://user?id={row['user_id']}\">{escape(name)}</a> — "
            f"<b>{escape(role)}</b> <i>({priority}/100)</i>"
        )
    await message.reply("\\n".join(lines))


@router.message(Cmd("id", "айди"))
async def cmd_id(message: Message) -> None:
    lines = []
    if message.from_user is not None:
        lines.append(f"🆔 Твой ID: <code>{message.from_user.id}</code>")
    reply = message.reply_to_message
    if reply is not None and reply.from_user is not None and reply.forum_topic_created is None:
        lines.append(f"🆔 ID автора сообщения: <code>{reply.from_user.id}</code>")
    lines.append(f"💬 ID чата: <code>{message.chat.id}</code>")
    await message.reply("\\n".join(lines))
