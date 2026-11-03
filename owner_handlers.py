"""Owner tools: interactive per-user editor and welcome settings."""
from __future__ import annotations

from html import escape
from aiogram import F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
from db import DB
from utils import Cmd, resolve_target, mention, fmt_money

router = Router(name="owner")
_pending: dict[int, tuple[int, str]] = {}

FIELDS = {
    "balance": ("Баланс", "целое число от 0 до 10^15"),
    "custom_nick": ("Ник", "текст до 64 символов; точка . — очистить"),
    "role": ("Роль", "текст до 64 символов; точка . — очистить"),
    "job_id": ("ID работы", "ID из jobs.py; точка . — без работы"),
    "total_shifts": ("Смены", "целое число от 0 до 10^9"),
    "total_earned": ("Всего заработано", "целое число от 0 до 10^15"),
}

def owner_ok(user) -> bool:
    return user is not None and user.id in config.OWNER_IDS

def user_keyboard(uid: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for field, (label, _) in FIELDS.items():
        kb.button(text=f"✏️ {label}", callback_data=f"u_edit:{uid}:{field}")
    kb.button(text="⚠️ Варны в этом чате", callback_data=f"u_warn:{uid}")
    kb.button(text="♻️ Сбросить профиль", callback_data=f"u_reset:{uid}")
    kb.adjust(2, 2, 2, 1, 1)
    return kb.as_markup()

async def render_user(db: DB, uid: int) -> str:
    await db.ensure_user(uid)
    row = await db.get_user(uid)
    if not row:
        return "Пользователь не найден."
    return (
        f"👤 <b>Редактор пользователя</b>\n"
        f"ID: <code>{uid}</code>\n"
        f"Имя: {escape(row['first_name'] or '—')}\n"
        f"Username: @{escape(row['username'] or '—')}\n"
        f"Ник: {escape(row['custom_nick'] or '—')}\n"
        f"Роль: {escape(row['role'] or '—')}\n"
        f"Баланс: <b>{fmt_money(row['balance'])}</b>\n"
        f"Работа: <code>{escape(row['job_id'] or 'нет')}</code>\n"
        f"Смены: {row['total_shifts']}\n"
        f"Заработано: {fmt_money(row['total_earned'])}"
    )

@router.message(Cmd("панель", "adminpanel"))
async def admin_panel(message: Message):
    if not owner_ok(message.from_user):
        return
    kb = InlineKeyboardBuilder()
    kb.button(text="👤 Редактировать пользователя", callback_data="owner_user_help")
    kb.button(text="👋 Настроить приветствие", callback_data="owner_welcome_help")
    kb.button(text="🎮 Игровые команды и правила", callback_data="owner_games_help")
    kb.adjust(1)
    await message.answer(
        "👑 <b>Панель владельца</b>\n\n"
        "Открой редактор пользователя командой <code>/юзер ID</code> "
        "или ответом на его сообщение: <code>/юзер</code>.\n"
        "Приветствие: <code>/приветствие текст</code> или <code>/приветствие выкл</code>.\n"
        "Все действия доступны только OWNER_ID.",
        reply_markup=kb.as_markup()
    )

@router.callback_query(F.data == "owner_user_help")
async def owner_user_help(cb: CallbackQuery):
    if not owner_ok(cb.from_user):
        await cb.answer("Нет доступа", show_alert=True); return
    await cb.answer()
    if cb.message:
        await cb.message.answer("Используй /юзер ID или ответь /юзер на сообщение участника.")

@router.callback_query(F.data == "owner_welcome_help")
async def owner_welcome_help(cb: CallbackQuery):
    if not owner_ok(cb.from_user):
        await cb.answer("Нет доступа", show_alert=True); return
    await cb.answer()
    if cb.message:
        await cb.message.answer("В группе: /приветствие Привет, {name}!\nОтключить: /приветствие выкл")

@router.callback_query(F.data == "owner_games_help")
async def owner_games_help(cb: CallbackQuery):
    if not owner_ok(cb.from_user):
        await cb.answer("Нет доступа", show_alert=True); return
    await cb.answer()
    if cb.message:
        await cb.message.answer("Игры используют только виртуальные монеты: /слоты сумма, /кости сумма, /рулетка сумма. Денежного вывода нет.")

@router.message(Cmd("юзер", "useredit"))
async def edit_user(message: Message, args: list[str], db: DB):
    if not owner_ok(message.from_user):
        return
    target = await resolve_target(message, args, db)
    if target is None:
        await message.reply("Укажи ID/@ник или ответь на сообщение: /юзер ID")
        return
    await message.answer(await render_user(db, target.user_id), reply_markup=user_keyboard(target.user_id))

@router.callback_query(F.data.startswith("u_edit:"))
async def edit_field(cb: CallbackQuery):
    if not owner_ok(cb.from_user):
        await cb.answer("Нет доступа", show_alert=True); return
    try:
        _, uid_s, field = cb.data.split(":")
        uid = int(uid_s)
        if field not in FIELDS: raise ValueError
    except ValueError:
        await cb.answer("Некорректное действие", show_alert=True); return
    _pending[cb.from_user.id] = (uid, field)
    await cb.answer()
    if cb.message:
        await cb.message.answer(
            f"Отправь новое значение для «{FIELDS[field][0]}» пользователя <code>{uid}</code>.\n"
            f"Формат: {FIELDS[field][1]}"
        )

@router.callback_query(F.data.startswith("u_warn:"))
async def show_warns(cb: CallbackQuery, db: DB):
    if not owner_ok(cb.from_user):
        await cb.answer("Нет доступа", show_alert=True); return
    uid = int(cb.data.split(":")[1])
    count = await db.get_warns(cb.message.chat.id, uid) if cb.message else 0
    await cb.answer(f"Варны в этом чате: {count}", show_alert=True)

@router.callback_query(F.data.startswith("u_reset:"))
async def reset_user(cb: CallbackQuery, db: DB):
    if not owner_ok(cb.from_user):
        await cb.answer("Нет доступа", show_alert=True); return
    uid = int(cb.data.split(":")[1])
    async with db.lock:
        await db.conn.execute(
            "UPDATE users SET balance=0,job_id=NULL,total_shifts=0,total_earned=0,last_work=0,custom_nick='',role='' WHERE user_id=?",
            (uid,))
        await db.conn.execute("DELETE FROM job_stats WHERE user_id=?", (uid,))
        await db.conn.commit()
    await cb.answer("Профиль сброшен", show_alert=True)
    if cb.message:
        await cb.message.answer(await render_user(db, uid), reply_markup=user_keyboard(uid))

@router.message()
async def pending_value(message: Message, db: DB):
    if not owner_ok(message.from_user) or message.from_user.id not in _pending or not message.text:
        return
    uid, field = _pending[message.from_user.id]
    value = message.text.strip()
    if field in {"balance", "total_shifts", "total_earned"}:
        if not value.isdigit():
            await message.reply("Нужно целое неотрицательное число. Попробуй ещё раз.")
            return
        number = int(value)
        maximum = 10**15 if field != "total_shifts" else 10**9
        if number > maximum:
            await message.reply("Слишком большое значение.")
            return
        async with db.lock:
            await db.conn.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
            await db.conn.execute(f"UPDATE users SET {field}=? WHERE user_id=?", (number, uid))
            await db.conn.commit()
    else:
        if field == "job_id" and value != ".":
            from jobs import JOBS_BY_ID
            if value not in JOBS_BY_ID:
                await message.reply("Такого ID нет в jobs.py. Отправь корректный ID или точку для очистки.")
                return
        value = "" if value == "." else value[:64]
        async with db.lock:
            await db.conn.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
            await db.conn.execute(f"UPDATE users SET {field}=? WHERE user_id=?", (value, uid))
            await db.conn.commit()
    _pending.pop(message.from_user.id, None)
    await message.answer("✅ Изменение сохранено.\n\n" + await render_user(db, uid), reply_markup=user_keyboard(uid))

@router.message(Cmd("приветствие", "welcome"))
async def set_welcome(message: Message, args: list[str], db: DB):
    if not owner_ok(message.from_user):
        return
    if message.chat.type not in {"group", "supergroup"}:
        await message.reply("Настраивай приветствие в нужной группе."); return
    value = " ".join(args)
    if not value:
        await message.reply("Формат: /приветствие Привет, {name}! или /приветствие выкл"); return
    if value.lower() in {"выкл", "off", "disable"}:
        value = ""
    async with db.lock:
        await db.conn.execute(
            "INSERT INTO chat_settings(chat_id,welcome_text) VALUES(?,?) "
            "ON CONFLICT(chat_id) DO UPDATE SET welcome_text=excluded.welcome_text",
            (message.chat.id, value[:1000]))
        await db.conn.commit()
    await message.reply("✅ Приветствие отключено." if not value else "✅ Приветствие сохранено.")
