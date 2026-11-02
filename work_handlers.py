"""Работа: список работ, трудоустройство после N смен, выход на смену."""
from __future__ import annotations

import math
import random
import time
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
from db import DB
from jobs import JOBS, JOBS_BY_ID
from utils import ANON_ADMIN_ID, Cmd, fmt_duration, fmt_money, mention, resolve_target, row_name

router = Router(name="work")

ANON_TEXT = "Отправь команду от своего имени (не анонимно), иначе я не пойму, кто ты."


def is_real_user(message: Message) -> bool:
    u = message.from_user
    return u is not None and not u.is_bot and u.id != ANON_ADMIN_ID


def jobs_text(row) -> str:
    total = row["total_shifts"]
    current = row["job_id"]
    lines = ["💼 <b>Работы</b>", f"Отработано смен: <b>{total}</b>", ""]
    for j in JOBS:
        if j.id == current:
            mark = "👉"
        elif total >= j.req_shifts:
            mark = "✅"
        else:
            mark = "🔒"
        line = f"{mark} {j.emoji} <b>{j.name}</b>: {j.min_pay}–{j.max_pay} 🪙 за смену, отдых {j.cooldown_min} мин"
        if total < j.req_shifts:
            line += f"\n      нужно смен: {j.req_shifts} (осталось {j.req_shifts - total})"
        lines.append(line)
    lines += [
        "",
        "Чтобы устроиться на работу получше, отработай нужное число смен командой /работа.",
        "Доступные работы — кнопками ниже 👇",
    ]
    return "\n".join(lines)


def jobs_kb(row, user_id: int) -> InlineKeyboardMarkup | None:
    kb = InlineKeyboardBuilder()
    count = 0
    for j in JOBS:
        if j.id != row["job_id"] and row["total_shifts"] >= j.req_shifts:
            kb.button(text=f"{j.emoji} {j.name}", callback_data=f"hire:{user_id}:{j.id}")
            count += 1
    if count == 0:
        return None
    kb.adjust(2)
    return kb.as_markup()


async def show_jobs(message: Message, db: DB, user_id: int, intro: str = "") -> None:
    row = await db.get_user(user_id)
    await message.reply(intro + jobs_text(row), reply_markup=jobs_kb(row, user_id))


# ---------- /работа ----------

@router.message(Cmd("работа", "work", "смена"))
async def cmd_work(message: Message, db: DB) -> None:
    if not is_real_user(message):
        await message.reply(ANON_TEXT)
        return
    user = message.from_user
    await db.ensure_user(user.id)
    row = await db.get_user(user.id)
    job = JOBS_BY_ID.get(row["job_id"]) if row["job_id"] else None
    if job is None:
        await show_jobs(message, db, user.id, "У тебя пока нет работы. Выбери из доступных:\n\n")
        return

    now = time.time()
    cooldown = job.cooldown_min * 60
    left = row["last_work"] + cooldown - now
    if left > 0:
        await message.reply(
            f"⏳ Ты ещё отдыхаешь после смены. Следующая через <b>{fmt_duration(math.ceil(left))}</b>."
        )
        return

    pay = random.randint(job.min_pay, job.max_pay)
    bonus = random.random() < config.BONUS_CHANCE
    if bonus:
        pay = int(pay * config.BONUS_MULT)
    if not await db.do_shift(user.id, job.id, pay, now, cooldown):
        await message.reply("⏳ Смена уже засчитана, подожди немного.")
        return

    row = await db.get_user(user.id)
    lines = [
        f"{job.emoji} <b>{job.name}</b>: смена отработана!",
        random.choice(job.flavors),
        "",
        f"💵 +{fmt_money(pay)}" + (" (🎉 премия!)" if bonus else ""),
        f"💰 Баланс: <b>{fmt_money(row['balance'])}</b>",
        f"📅 Смен всего: <b>{row['total_shifts']}</b>",
    ]
    unlocked = [j for j in JOBS if j.req_shifts == row["total_shifts"] and j.req_shifts > 0]
    for j in unlocked:
        lines.append(f"\n🔓 Открылась работа: {j.emoji} <b>{j.name}</b> ({j.min_pay}–{j.max_pay} 🪙). Выбрать: /работы")
    await message.reply("\n".join(lines))


# ---------- /работы, /уволиться ----------

@router.message(Cmd("работы", "jobs", "вакансии"))
async def cmd_jobs(message: Message, db: DB) -> None:
    if not is_real_user(message):
        await message.reply(ANON_TEXT)
        return
    await db.ensure_user(message.from_user.id)
    await show_jobs(message, db, message.from_user.id)


@router.message(Cmd("уволиться", "quit", "увольнение"))
async def cmd_quit(message: Message, db: DB) -> None:
    if not is_real_user(message):
        await message.reply(ANON_TEXT)
        return
    if await db.quit_job(message.from_user.id):
        await message.reply("📝 Ты уволился. Смены сохранены, выбрать новую работу можно в /работы.")
    else:
        await message.reply("Ты и так нигде не работаешь. Выбрать работу: /работы")


# ---------- кнопка «устроиться» ----------

@router.callback_query(F.data.startswith("hire:"))
async def cb_hire(cb: CallbackQuery, db: DB) -> None:
    try:
        _, uid_s, job_id = (cb.data or "").split(":", 2)
        owner_id = int(uid_s)
    except ValueError:
        await cb.answer()
        return
    if cb.from_user.id != owner_id:
        await cb.answer("Это меню открыл другой человек. Вызови своё командой /работы", show_alert=True)
        return
    job = JOBS_BY_ID.get(job_id)
    if job is None:
        await cb.answer("Такой работы нет", show_alert=True)
        return
    if not await db.hire(owner_id, job.id, job.req_shifts):
        row = await db.get_user(owner_id)
        have = row["total_shifts"] if row else 0
        await cb.answer(f"Нужно отработать смен: {job.req_shifts} (у тебя {have})", show_alert=True)
        return
    text = (
        f"✅ Ты устроился: {job.emoji} <b>{job.name}</b>\n"
        f"Зарплата: {job.min_pay}–{job.max_pay} 🪙 за смену, отдых {job.cooldown_min} мин.\n"
        f"Выходи на смену: /работа"
    )
    if isinstance(cb.message, Message):
        try:
            await cb.message.edit_text(text, reply_markup=None)
        except TelegramBadRequest:
            pass
    await cb.answer("Ты устроился!")


# ---------- /профиль ----------

@router.message(Cmd("профиль", "profile", "проф", "я"))
async def cmd_profile(message: Message, args: list[str], db: DB) -> None:
    t = await resolve_target(message, args, db)
    if t is not None:
        if t.is_bot:
            await message.reply("У ботов нет профиля 🙂")
            return
        uid, name = t.user_id, t.name
    elif is_real_user(message):
        uid, name = message.from_user.id, message.from_user.full_name
    else:
        await message.reply(ANON_TEXT)
        return

    await db.ensure_user(uid)
    row = await db.get_user(uid)
    job = JOBS_BY_ID.get(row["job_id"]) if row["job_id"] else None
    total = row["total_shifts"]
    lines = [
        f"👤 <b>{escape(name)}</b>",
        f"💰 Баланс: <b>{fmt_money(row['balance'])}</b>",
        f"📈 Заработано за всё время: {fmt_money(row['total_earned'])}",
    ]
    if job:
        on_job = await db.job_shifts(uid, job.id)
        lines.append(f"💼 Работа: {job.emoji} <b>{job.name}</b> (смен здесь: {on_job})")
        left = row["last_work"] + job.cooldown_min * 60 - time.time()
        if left > 0:
            lines.append(f"⏳ Следующая смена через {fmt_duration(math.ceil(left))}")
        else:
            lines.append("✅ Можно выходить на смену: /работа")
    else:
        lines.append("💼 Работа: нет (выбрать: /работы)")
    lines.append(f"📅 Смен отработано всего: <b>{total}</b>")
    nxt = next((j for j in JOBS if j.req_shifts > total), None)
    if nxt:
        lines.append(f"🎯 Следующая работа: {nxt.emoji} {nxt.name} — ещё {nxt.req_shifts - total} смен")
    await message.reply("\n".join(lines))
