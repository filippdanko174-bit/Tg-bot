"""Монеты: баланс, переводы, топ, а также выдача/изъятие владельцем."""
from __future__ import annotations

from html import escape

from aiogram import Router
from aiogram.types import Message

import config
from db import DB
from utils import (
    ANON_ADMIN_ID,
    Cmd,
    Target,
    fmt_money,
    mention,
    parse_amount,
    resolve_target,
    row_name,
)

router = Router(name="economy")

ANON_TEXT = "Отправь команду от своего имени (не анонимно), иначе я не пойму, кто ты."


def is_owner(message: Message) -> bool:
    return message.from_user is not None and message.from_user.id in config.OWNER_IDS


def is_real_user(message: Message) -> bool:
    u = message.from_user
    return u is not None and not u.is_bot and u.id != ANON_ADMIN_ID


# ---------- баланс / топ ----------

@router.message(Cmd("баланс", "бал", "balance", "bal"))
async def cmd_balance(message: Message, args: list[str], db: DB) -> None:
    t = await resolve_target(message, args, db)
    if t is not None:
        if t.is_bot:
            await message.reply("У ботов нет кошелька 🙂")
            return
        uid, name = t.user_id, t.name
    elif is_real_user(message):
        uid, name = message.from_user.id, message.from_user.full_name
    else:
        await message.reply(ANON_TEXT)
        return
    row = await db.get_user(uid)
    balance = row["balance"] if row else 0
    await message.reply(f"💰 Баланс {mention(uid, name)}: <b>{fmt_money(balance)}</b>")


@router.message(Cmd("топ", "top", "богачи"))
async def cmd_top(message: Message, db: DB) -> None:
    rows = await db.top(10)
    if not rows:
        await message.reply("Пока ни у кого нет монет. Начни с /работа!")
        return
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = ["🏆 <b>Самые богатые</b>", ""]
    for i, row in enumerate(rows, 1):
        async with db.conn.execute("SELECT active_title FROM users WHERE user_id=?", (row["user_id"],)) as cur:
            title_row = await cur.fetchone()
        icons = {"bronze": "🥉", "silver": "🥈", "gold": "🥇", "star": "⭐", "crown": "👑"}
        prefix = icons.get(title_row["active_title"], "") + " " if title_row else ""
        lines.append(f"{medals.get(i, f'{i}.')} {prefix}{escape(row_name(row))} — {fmt_money(row['balance'])}")
    await message.reply("\n".join(lines))


# ---------- переводы ----------

@router.message(Cmd("передать", "дать", "pay", "перевод"))
async def cmd_pay(message: Message, args: list[str], db: DB) -> None:
    if not is_real_user(message):
        await message.reply(ANON_TEXT)
        return
    usage = "Использование: ответь на сообщение командой <code>/передать 100</code> или <code>/передать @ник 100</code>."
    t = await resolve_target(message, args, db)
    if t is None or not t.rest:
        await message.reply(usage)
        return
    amount = parse_amount(t.rest[0])
    if amount is None:
        await message.reply("Сумма должна быть положительным числом (можно писать 5к = 5000).\n" + usage)
        return
    sender = message.from_user
    if t.is_bot:
        await message.reply("Ботам монеты не нужны 🙂")
        return
    if t.user_id == sender.id:
        await message.reply("Самому себе передавать нельзя.")
        return
    if not await db.transfer(sender.id, t.user_id, amount):
        row = await db.get_user(sender.id)
        have = row["balance"] if row else 0
        await message.reply(f"❌ Не хватает монет. У тебя: <b>{fmt_money(have)}</b>.")
        return
    await message.reply(
        f"💸 {mention(sender.id, sender.full_name)} передал {mention(t.user_id, t.name)} "
        f"<b>{fmt_money(amount)}</b>."
    )


# ---------- команды владельца ----------

async def owner_target(message: Message, args: list[str], db: DB) -> tuple[Target, int] | None:
    """Разбирает '/выдать [кому] сумма'. Если «кому» не указан — это сам владелец."""
    reply = message.reply_to_message
    has_reply = reply is not None and reply.from_user is not None and reply.forum_topic_created is None
    if not has_reply and len(args) == 1 and message.from_user is not None and parse_amount(args[0]) is not None:
        # «/выдать 1000» без цели: выдаём самому себе
        u = message.from_user
        t = Target(u.id, u.full_name, u.is_bot, args)
    else:
        t = await resolve_target(message, args, db)
    if t is None or not t.rest:
        await message.reply(
            "Использование: ответь на сообщение командой <code>/выдать 1000</code> "
            "или напиши <code>/выдать @ник 1000</code>."
        )
        return None
    amount = parse_amount(t.rest[0])
    if amount is None:
        await message.reply("Сумма должна быть положительным числом (можно писать 5к = 5000).")
        return None
    if t.is_bot:
        await message.reply("Ботам монеты не нужны 🙂")
        return None
    return t, amount


@router.message(Cmd("выдать", "give", "начислить"))
async def cmd_give(message: Message, args: list[str], db: DB) -> None:
    if not is_owner(message):
        await message.reply("⛔ Эта команда только для владельца бота.")
        return
    parsed = await owner_target(message, args, db)
    if parsed is None:
        return
    t, amount = parsed
    new, applied = await db.change_balance(t.user_id, amount)
    await message.reply(
        f"🏦 Владелец выдал {mention(t.user_id, t.name)} <b>{fmt_money(applied)}</b>.\n"
        f"Баланс: <b>{fmt_money(new)}</b>"
    )


@router.message(Cmd("забрать", "take", "изъять"))
async def cmd_take(message: Message, args: list[str], db: DB) -> None:
    if not is_owner(message):
        await message.reply("⛔ Эта команда только для владельца бота.")
        return
    parsed = await owner_target(message, args, db)
    if parsed is None:
        return
    t, amount = parsed
    new, applied = await db.change_balance(t.user_id, -amount)
    await message.reply(
        f"🏦 Владелец забрал у {mention(t.user_id, t.name)} <b>{fmt_money(-applied)}</b>.\n"
        f"Баланс: <b>{fmt_money(new)}</b>"
    )
