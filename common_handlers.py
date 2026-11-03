"""Справка и /id."""
from __future__ import annotations

from aiogram import Router
from aiogram.types import Message

from db import DB
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
/роль [@ник] — посмотреть роль и её приоритет

<b>📢 Упоминания</b>
/зов_вкл — согласиться получать упоминания
/зов_выкл — отказаться от упоминаний
/зов — позвать подписавшихся участников

<b>🎉 Развлечения</b>
/завоз — получить персональный мемный завоз
/вайб — шуточная проверка вайба
/рофл — случайная авторская шутка

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
    await message.reply("\n".join(lines))



@router.message(Cmd("роль", "role"))
async def cmd_role(message: Message, args: list[str], db: DB) -> None:
    """Показывает роль автора или указанного участника."""
    if not args and message.reply_to_message and message.reply_to_message.from_user:
        target_user = message.reply_to_message.from_user
        user_id, display_name = target_user.id, target_user.full_name
    elif not args:
        if message.from_user is None:
            await message.reply("Не удалось определить пользователя.")
            return
        user_id, display_name = message.from_user.id, message.from_user.full_name
    else:
        from utils import resolve_target
        target = await resolve_target(message, args, db)
        if target is None or target.rest:
            await message.reply("Формат: <code>/роль</code> — твоя роль; <code>/роль @ник</code> — роль участника; либо ответь на его сообщение командой /роль.")
            return
        user_id, display_name = target.user_id, target.name

    row = await db.get_user(user_id)
    role_name = row["role"] if row and row["role"] else ""
    if not role_name:
        await message.reply(f"👤 {escape(display_name)}\n🏷 Роль: <b>не назначена</b>")
        return
    async with db.conn.execute(
        "SELECT priority FROM custom_roles WHERE name=? COLLATE NOCASE", (role_name,)
    ) as cur:
        role_row = await cur.fetchone()
    priority = role_row["priority"] if role_row else 0
    await message.reply(
        f"👤 {escape(display_name)}\n"
        f"🏷 Роль: <b>{escape(role_name)}</b>\n"
        f"⭐ Приоритет: <b>{priority}/100</b>"
    )

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
