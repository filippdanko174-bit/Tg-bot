"""Модерация: бан, мут, кик, варны, чистка, закреп."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import escape

from aiogram import Bot, Router
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ChatPermissions, Message

import config
from db import DB
from utils import (
    ANON_ADMIN_ID,
    FOREVER,
    Cmd,
    Target,
    fmt_duration,
    mention,
    parse_duration,
    resolve_target,
)

router = Router(name="moderation")

GROUPS = {"group", "supergroup"}
NEED_TARGET = (
    "Укажи пользователя: ответь командой на его сообщение или напиши @ник / ID "
    "(по @нику я нахожу тех, кто хоть раз писал в чате)."
)


async def audit_admin(db: DB, message: Message, action: str, target_id: int | None = None, details: str = "") -> None:
    if message.from_user is None:
        return
    async with db.lock:
        await db.conn.execute(
            "INSERT INTO admin_audit(chat_id,actor_id,action,target_id,details) VALUES(?,?,?,?,?)",
            (message.chat.id, message.from_user.id, action, target_id, details[:500]),
        )
        await db.conn.commit()


# ---------- проверки и общие функции ----------

async def is_chat_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except TelegramAPIError:
        return False
    return member.status in (ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR)


async def is_moderator(message: Message, bot: Bot) -> bool:
    if message.sender_chat is not None and message.sender_chat.id == message.chat.id:
        return True  # админ, пишущий анонимно от имени группы
    user = message.from_user
    if user is None:
        return False
    if user.id in config.OWNER_IDS:
        return True
    return await is_chat_admin(bot, message.chat.id, user.id)


async def guard(message: Message, bot: Bot) -> bool:
    """Команда только для админов в группе."""
    if message.chat.type not in GROUPS:
        await message.reply("Эта команда работает только в группе.")
        return False
    if not await is_moderator(message, bot):
        await message.reply("⛔ Эта команда только для админов чата.")
        return False
    return True


async def prepare(
    message: Message, bot: Bot, db: DB, args: list[str], *, protect: bool = True
) -> Target | None:
    """Проверяет права и находит цель. protect=True — нельзя трогать админов."""
    if not await guard(message, bot):
        return None
    target = await resolve_target(message, args, db)
    if target is None:
        await message.reply(NEED_TARGET)
        return None
    if target.user_id == bot.id:
        await message.reply("Себя я наказывать не буду 🙂")
        return None
    if message.from_user is not None and target.user_id == message.from_user.id:
        await message.reply("Себя трогать нельзя 🙂")
        return None
    if protect and (
        target.user_id == ANON_ADMIN_ID
        or target.user_id in config.OWNER_IDS
        or await is_chat_admin(bot, message.chat.id, target.user_id)
    ):
        await message.reply("🛡 Нельзя применять это к админам чата и владельцу бота.")
        return None
    return target


def fail_text(e: TelegramAPIError) -> str:
    text = getattr(e, "message", str(e))
    low = text.lower()
    if "not enough rights" in low or "need administrator" in low or "rights" in low:
        return "❌ Не получилось: у бота не хватает прав. Сделай его админом с правом банить и ограничивать."
    if "can't remove chat owner" in low or "administrator" in low:
        return "❌ Не получилось: нельзя применить это к администратору чата."
    if "method is available only for supergroups" in low:
        return "❌ Не получилось: для этого нужна супергруппа (в обычной группе не работает)."
    return f"❌ Ошибка Telegram: {escape(text)}"


def split_duration(rest: list[str], default: int) -> tuple[int, str]:
    """['1д', 'спам', 'ссылки'] -> (86400, 'спам ссылки'). Без времени берём default."""
    if rest:
        d = parse_duration(rest[0])
        if d is not None:
            return d, " ".join(rest[1:])
    return default, " ".join(rest)


def until_dt(seconds: int) -> datetime | None:
    return None if seconds == FOREVER else datetime.now(timezone.utc) + timedelta(seconds=seconds)


def dur_text(seconds: int) -> str:
    return "навсегда" if seconds == FOREVER else f"на {fmt_duration(seconds)}"


def reason_text(reason: str) -> str:
    return f"\n📝 Причина: {escape(reason)}" if reason else ""


def muted_permissions() -> ChatPermissions:
    return ChatPermissions(
        can_send_messages=False,
        can_send_audios=False,
        can_send_documents=False,
        can_send_photos=False,
        can_send_videos=False,
        can_send_video_notes=False,
        can_send_voice_notes=False,
        can_send_polls=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False,
    )


async def open_permissions(bot: Bot, chat_id: int) -> ChatPermissions:
    """Права, которые возвращаем при размуте: стандартные права чата (или обычные, если они пустые)."""
    try:
        chat = await bot.get_chat(chat_id)
        base = getattr(chat, "permissions", None)
        if base is not None:
            # Сохраняем именно права по умолчанию чата, даже если отправка сообщений отключена.
            return base
    except TelegramAPIError:
        pass
    return ChatPermissions(
        can_send_messages=True,
        can_send_audios=True,
        can_send_documents=True,
        can_send_photos=True,
        can_send_videos=True,
        can_send_video_notes=True,
        can_send_voice_notes=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_invite_users=True,
    )


# ---------- бан / разбан / кик ----------

@router.message(Cmd("бан", "ban"))
async def cmd_ban(message: Message, args: list[str], bot: Bot, db: DB) -> None:
    t = await prepare(message, bot, db, args)
    if t is None:
        return
    seconds, reason = split_duration(t.rest, FOREVER)
    try:
        await bot.ban_chat_member(message.chat.id, t.user_id, until_date=until_dt(seconds))
    except TelegramAPIError as e:
        await message.reply(fail_text(e))
        return
    await audit_admin(db, message, "ban", t.user_id, reason)
    await message.reply(f"🔨 {mention(t.user_id, t.name)} забанен {dur_text(seconds)}.{reason_text(reason)}")


@router.message(Cmd("разбан", "unban"))
async def cmd_unban(message: Message, args: list[str], bot: Bot, db: DB) -> None:
    t = await prepare(message, bot, db, args, protect=False)
    if t is None:
        return
    try:
        await bot.unban_chat_member(message.chat.id, t.user_id, only_if_banned=True)
    except TelegramAPIError as e:
        await message.reply(fail_text(e))
        return
    await audit_admin(db, message, "unban", t.user_id)
    await message.reply(f"✅ {mention(t.user_id, t.name)} разбанен.")


@router.message(Cmd("кик", "kick"))
async def cmd_kick(message: Message, args: list[str], bot: Bot, db: DB) -> None:
    t = await prepare(message, bot, db, args)
    if t is None:
        return
    reason = " ".join(t.rest)
    try:
        await bot.ban_chat_member(message.chat.id, t.user_id)
        await bot.unban_chat_member(message.chat.id, t.user_id, only_if_banned=True)
    except TelegramAPIError as e:
        await message.reply(fail_text(e))
        return
    await audit_admin(db, message, "kick", t.user_id, reason)
    await message.reply(f"👢 {mention(t.user_id, t.name)} выгнан из чата.{reason_text(reason)}")


# ---------- мут / размут ----------

@router.message(Cmd("мут", "mute"))
async def cmd_mute(message: Message, args: list[str], bot: Bot, db: DB) -> None:
    t = await prepare(message, bot, db, args)
    if t is None:
        return
    seconds, reason = split_duration(t.rest, config.DEFAULT_MUTE_MINUTES * 60)
    try:
        await bot.restrict_chat_member(
            message.chat.id, t.user_id, permissions=muted_permissions(), until_date=until_dt(seconds)
        )
    except TelegramAPIError as e:
        await message.reply(fail_text(e))
        return
    await audit_admin(db, message, "mute", t.user_id, reason)
    await message.reply(f"🔇 {mention(t.user_id, t.name)} в муте {dur_text(seconds)}.{reason_text(reason)}")


@router.message(Cmd("размут", "unmute"))
async def cmd_unmute(message: Message, args: list[str], bot: Bot, db: DB) -> None:
    t = await prepare(message, bot, db, args, protect=False)
    if t is None:
        return
    try:
        perms = await open_permissions(bot, message.chat.id)
        await bot.restrict_chat_member(message.chat.id, t.user_id, permissions=perms)
    except TelegramAPIError as e:
        await message.reply(fail_text(e))
        return
    await audit_admin(db, message, "unmute", t.user_id)
    await message.reply(f"🔊 {mention(t.user_id, t.name)} размучен.")


# ---------- варны ----------

@router.message(Cmd("варн", "warn", "пред"))
async def cmd_warn(message: Message, args: list[str], bot: Bot, db: DB) -> None:
    t = await prepare(message, bot, db, args)
    if t is None:
        return
    reason = " ".join(t.rest)
    chat_id = message.chat.id
    count = await db.add_warn(chat_id, t.user_id)
    await audit_admin(db, message, "warn", t.user_id, reason)
    who = mention(t.user_id, t.name)
    if count < config.WARN_LIMIT:
        await message.reply(
            f"⚠️ {who} получил предупреждение: <b>{count}/{config.WARN_LIMIT}</b>.{reason_text(reason)}"
        )
        return
    seconds = config.WARN_MUTE_HOURS * 3600
    try:
        await bot.restrict_chat_member(
            chat_id, t.user_id, permissions=muted_permissions(), until_date=until_dt(seconds)
        )
    except TelegramAPIError as e:
        await message.reply(
            f"⚠️ {who} набрал {count}/{config.WARN_LIMIT} варнов, но мут не получился.\n{fail_text(e)}"
        )
        return
    await db.reset_warns(chat_id, t.user_id)
    await message.reply(
        f"🔇 {who} набрал {config.WARN_LIMIT}/{config.WARN_LIMIT} варнов и отправлен в мут "
        f"{dur_text(seconds)}. Варны обнулены.{reason_text(reason)}"
    )


@router.message(Cmd("снятьварн", "унварн", "unwarn"))
async def cmd_unwarn(message: Message, args: list[str], bot: Bot, db: DB) -> None:
    t = await prepare(message, bot, db, args, protect=False)
    if t is None:
        return
    count = await db.remove_warn(message.chat.id, t.user_id)
    await audit_admin(db, message, "unwarn", t.user_id)
    await message.reply(
        f"✅ С {mention(t.user_id, t.name)} снят варн. Сейчас: <b>{count}/{config.WARN_LIMIT}</b>."
    )


@router.message(Cmd("варны", "warns"))
async def cmd_warns(message: Message, args: list[str], db: DB) -> None:
    if message.chat.type not in GROUPS:
        await message.reply("Эта команда работает только в группе.")
        return
    t = await resolve_target(message, args, db)
    if t is not None:
        uid, name = t.user_id, t.name
    elif message.from_user is not None:
        uid, name = message.from_user.id, message.from_user.full_name
    else:
        return
    count = await db.get_warns(message.chat.id, uid)
    await message.reply(f"⚠️ Варны {mention(uid, name)}: <b>{count}/{config.WARN_LIMIT}</b>.")


# ---------- удаление сообщений ----------

@router.message(Cmd("удалить", "del", "удал"))
async def cmd_delete(message: Message, bot: Bot, db: DB) -> None:
    if not await guard(message, bot):
        return
    reply = message.reply_to_message
    if reply is None or reply.forum_topic_created is not None:
        await message.reply("Ответь этой командой на сообщение, которое нужно удалить.")
        return
    try:
        await reply.delete()
        await audit_admin(db, message, "delete", reply.from_user.id if reply.from_user else None)
    except TelegramAPIError as e:
        await message.reply(fail_text(e))
        return
    try:
        await message.delete()
    except TelegramAPIError:
        pass


@router.message(Cmd("чистка", "purge", "очистить"))
async def cmd_purge(message: Message, bot: Bot, db: DB) -> None:
    if not await guard(message, bot):
        return
    reply = message.reply_to_message
    if reply is None or reply.forum_topic_created is not None:
        await message.reply("Ответь командой на сообщение, начиная с которого нужно удалить всё до команды (максимум 100).")
        return
    start, end = reply.message_id, message.message_id
    if end - start + 1 > 100:
        start = end - 99
    try:
        message_ids = list(range(start, end + 1))
        delete_many = getattr(bot, "delete_messages", None)
        if delete_many is not None:
            await delete_many(message.chat.id, message_ids)
        else:
            # Совместимость со старыми версиями aiogram без deleteMessages.
            for message_id in message_ids:
                try:
                    await bot.delete_message(message.chat.id, message_id)
                except TelegramAPIError:
                    continue
    except TelegramAPIError as e:
        await message.reply(fail_text(e))
        return
    await audit_admin(db, message, "purge", None, f"Удалено до {end-start+1} сообщений")
    await message.answer(f"🧹 Удалено сообщений: до {end - start + 1}.")


# ---------- закреп ----------

@router.message(Cmd("закрепить", "закреп", "pin"))
async def cmd_pin(message: Message, bot: Bot, db: DB) -> None:
    if not await guard(message, bot):
        return
    reply = message.reply_to_message
    if reply is None or reply.forum_topic_created is not None:
        await message.reply("Ответь командой на сообщение, которое нужно закрепить.")
        return
    try:
        await bot.pin_chat_message(message.chat.id, reply.message_id, disable_notification=True)
        await audit_admin(db, message, "pin", reply.from_user.id if reply.from_user else None)
    except TelegramAPIError as e:
        await message.reply(fail_text(e))
        return
    await message.reply("📌 Сообщение закреплено.")


@router.message(Cmd("открепить", "unpin"))
async def cmd_unpin(message: Message, bot: Bot, db: DB) -> None:
    if not await guard(message, bot):
        return
    reply = message.reply_to_message
    try:
        if reply is not None and reply.forum_topic_created is None:
            await bot.unpin_chat_message(message.chat.id, message_id=reply.message_id)
        else:
            await bot.unpin_chat_message(message.chat.id)
    except TelegramAPIError as e:
        await message.reply(fail_text(e))
        return
    await audit_admin(db, message, "unpin")
    await message.reply("📌 Сообщение откреплено.")
