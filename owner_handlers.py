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


def owner_private(message: Message) -> bool:
    return message.chat.type == "private" and owner_ok(message.from_user)


def callback_is_owner_private(cb: CallbackQuery) -> bool:
    return owner_ok(cb.from_user) and cb.message is not None and cb.message.chat.type == "private"

def user_keyboard(uid: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for field, (label, _) in FIELDS.items():
        kb.button(text=f"✏️ {label}", callback_data=f"u_edit:{uid}:{field}")
    kb.button(text="⚠️ Как проверить варны", callback_data="u_warn_help")
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

@router.message(Cmd("сетстат", "setstat"))
async def admin_panel(message: Message):
    if not owner_ok(message.from_user):
        await message.reply("⛔ Панель доступна только владельцу бота.")
        return
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Статистика", callback_data="owner_stats")
    kb.button(text="👥 Пользователи", callback_data="owner_users:0")
    kb.button(text="🏷 Роли", callback_data="owner_roles")
    kb.button(text="👤 Редактор пользователя", callback_data="owner_user_help")
    kb.button(text="👋 Приветствие", callback_data="owner_welcome_help")
    kb.button(text="🛡 Модерация", callback_data="owner_moderation_help")
    kb.button(text="🎉 Развлечения", callback_data="owner_fun_help")
    kb.button(text="🔄 Обновить панель", callback_data="owner_panel_refresh")
    kb.adjust(2, 2, 2, 2, 1)
    await message.answer(
        "👑 <b>ПАНЕЛЬ УПРАВЛЕНИЯ BYFILIPP</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Выбери раздел ниже. Кнопки доступны только владельцу.\n\n"
        "👤 Редактор профилей и подробные данные открываются в личке с ботом.\n"
        "⚙️ Команды ролей, приветствия и экономики владельца можно использовать и в группах.",
        reply_markup=kb.as_markup()
    )


def callback_is_owner(cb: CallbackQuery) -> bool:
    return owner_ok(cb.from_user) and cb.message is not None


@router.callback_query(F.data == "owner_panel_refresh")
async def owner_panel_refresh(cb: CallbackQuery):
    if not callback_is_owner(cb):
        await cb.answer("Нет доступа", show_alert=True)
        return
    await cb.answer("Панель обновлена")
    if cb.message:
        kb = InlineKeyboardBuilder()
        kb.button(text="📊 Статистика", callback_data="owner_stats")
        kb.button(text="👥 Пользователи", callback_data="owner_users:0")
        kb.button(text="🏷 Роли", callback_data="owner_roles")
        kb.button(text="👤 Редактор пользователя", callback_data="owner_user_help")
        kb.button(text="👋 Приветствие", callback_data="owner_welcome_help")
        kb.button(text="🛡 Модерация", callback_data="owner_moderation_help")
        kb.button(text="🎉 Развлечения", callback_data="owner_fun_help")
        kb.button(text="🔄 Обновить панель", callback_data="owner_panel_refresh")
        kb.adjust(2, 2, 2, 2, 1)
        await cb.message.edit_reply_markup(reply_markup=kb.as_markup())



@router.callback_query(F.data.startswith("owner_users:"))
async def owner_users(cb: CallbackQuery, db: DB):
    if not callback_is_owner_private(cb):
        await cb.answer("Открой панель в личном чате с ботом", show_alert=True)
        return
    try:
        page = max(0, int(cb.data.split(":", 1)[1]))
    except (ValueError, IndexError):
        await cb.answer("Некорректная страница", show_alert=True)
        return
    per_page = 8
    async with db.conn.execute("SELECT COUNT(*) AS n FROM users") as cur:
        total = (await cur.fetchone())["n"]
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, pages - 1)
    async with db.conn.execute(
        "SELECT user_id, username, first_name, balance, role FROM users "
        "ORDER BY user_id DESC LIMIT ? OFFSET ?", (per_page, page * per_page)
    ) as cur:
        rows = await cur.fetchall()
    lines = [f"👥 <b>ПОЛЬЗОВАТЕЛИ БОТА</b> · {total}", f"Страница {page + 1}/{pages}", ""]
    kb = InlineKeyboardBuilder()
    for row in rows:
        name = row["first_name"] or (f"@{row['username']}" if row["username"] else str(row["user_id"]))
        role = f" · {row['role']}" if row["role"] else ""
        lines.append(f"• {escape(name)} · <code>{row['user_id']}</code>{escape(role)}")
        kb.button(text=f"👤 {name[:24]}", callback_data=f"owner_user_view:{row['user_id']}")
    kb.adjust(1)
    nav = InlineKeyboardBuilder()
    if page > 0:
        nav.button(text="⬅️ Назад", callback_data=f"owner_users:{page - 1}")
    if page + 1 < pages:
        nav.button(text="Вперёд ➡️", callback_data=f"owner_users:{page + 1}")
    nav.button(text="🔄 Обновить", callback_data=f"owner_users:{page}")
    nav.button(text="🏠 В панель", callback_data="owner_panel_refresh")
    nav.adjust(2, 2)
    kb_buttons = kb.as_markup().inline_keyboard + nav.as_markup().inline_keyboard
    await cb.answer()
    if cb.message:
        await cb.message.edit_text("\\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons))


@router.callback_query(F.data.startswith("owner_user_view:"))
async def owner_user_view(cb: CallbackQuery, db: DB):
    if not callback_is_owner_private(cb):
        await cb.answer("Нет доступа", show_alert=True)
        return
    try:
        uid = int(cb.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await cb.answer("Некорректный пользователь", show_alert=True)
        return
    await cb.answer()
    if cb.message:
        kb = user_keyboard(uid)
        builder = InlineKeyboardBuilder()
        builder.button(text="⬅️ К списку", callback_data="owner_users:0")
        for row in kb.inline_keyboard:
            builder.row(*row)
        await cb.message.answer(await render_user(db, uid), reply_markup=builder.as_markup())


@router.callback_query(F.data == "owner_stats")
async def owner_stats(cb: CallbackQuery, db: DB):
    if not callback_is_owner(cb):
        await cb.answer("Нет доступа", show_alert=True)
        return
    async with db.conn.execute(
        "SELECT COUNT(*) AS users, COALESCE(SUM(balance),0) AS coins FROM users"
    ) as cur:
        totals = await cur.fetchone()
    async with db.conn.execute("SELECT COUNT(*) AS amount FROM custom_roles") as cur:
        roles = (await cur.fetchone())["amount"]
    async with db.conn.execute("SELECT COALESCE(SUM(count),0) AS amount FROM warns") as cur:
        warns = (await cur.fetchone())["amount"]
    async with db.conn.execute(
        "SELECT COUNT(*) AS amount FROM chat_settings WHERE welcome_text!=''"
    ) as cur:
        welcomes = (await cur.fetchone())["amount"]
    await cb.answer()
    if cb.message:
        await cb.message.answer(
            "📊 <b>СТАТИСТИКА БОТА</b>\n"
            f"👥 Пользователей в базе: <b>{totals['users']}</b>\n"
            f"🪙 Монет на балансах: <b>{fmt_money(totals['coins'])}</b>\n"
            f"🏷 Создано ролей: <b>{roles}</b>\n"
            f"⚠️ Активных предупреждений: <b>{warns}</b>\n"
            f"👋 Настроено приветствий: <b>{welcomes}</b>"
        )


@router.callback_query(F.data == "owner_roles")
async def owner_roles(cb: CallbackQuery, db: DB):
    if not callback_is_owner(cb):
        await cb.answer("Нет доступа", show_alert=True)
        return
    async with db.conn.execute(
        "SELECT name,priority FROM custom_roles ORDER BY priority DESC,name COLLATE NOCASE LIMIT 50"
    ) as cur:
        rows = await cur.fetchall()
    await cb.answer()
    if not cb.message:
        return
    if not rows:
        await cb.message.answer("🏷 Ролей пока нет. Создай: <code>/создатьроль Название 50</code>")
        return
    lines = ["🏷 <b>РОЛИ БОТА</b>"]
    lines.extend(f"• <b>{escape(row['name'])}</b> — приоритет {row['priority']}/100" for row in rows)
    lines.append("\nСоздать: <code>/создатьроль Название 50</code>\nНазначить: <code>/назначитьроль @ник Название</code>")
    await cb.message.answer("\n".join(lines))


@router.callback_query(F.data == "owner_user_help")
async def owner_user_help(cb: CallbackQuery):
    if not callback_is_owner(cb):
        await cb.answer("Нет доступа", show_alert=True)
        return
    await cb.answer()
    if cb.message:
        if cb.message.chat.type == "private":
            await cb.message.answer("Используй <code>/юзер ID</code> или ответь командой <code>/юзер</code> на сообщение участника.")
        else:
            await cb.message.answer("🔒 Редактор содержит личные игровые данные, поэтому открой ЛС бота и выполни <code>/юзер ID</code>.")


@router.callback_query(F.data == "owner_welcome_help")
async def owner_welcome_help(cb: CallbackQuery):
    if not callback_is_owner(cb):
        await cb.answer("Нет доступа", show_alert=True)
        return
    await cb.answer()
    if cb.message:
        if cb.message.chat.type in {"group", "supergroup"}:
            text = (
                "👋 <b>Приветствие этого чата</b>\n"
                "Установить: <code>/приветствие Привет, {name}!</code>\n"
                "Отключить: <code>/приветствие выкл</code>"
            )
        else:
            text = (
                "👋 <b>Настройка приветствия</b>\n"
                "В группе от имени владельца: <code>/приветствие Привет, {name}!</code>\n"
                "Из ЛС по ID: <code>/приветствие -1001234567890 Привет, {name}!</code>\n"
                "Отключить: <code>/приветствие -1001234567890 выкл</code>"
            )
        await cb.message.answer(text)


@router.callback_query(F.data == "owner_moderation_help")
async def owner_moderation_help(cb: CallbackQuery):
    if not callback_is_owner(cb):
        await cb.answer("Нет доступа", show_alert=True)
        return
    await cb.answer()
    if cb.message:
        await cb.message.answer(
            "🛡 <b>МОДЕРАЦИЯ</b>\n"
            "<code>/бан @ник [время] [причина]</code>\n"
            "<code>/разбан @ник</code> · <code>/кик @ник</code>\n"
            "<code>/мут @ник 10м причина</code> · <code>/размут @ник</code>\n"
            "<code>/варн @ник причина</code> · <code>/варны @ник</code>\n"
            "<code>/удалить</code> — ответом на сообщение\n"
            "<code>/чистка</code> — ответом на первое сообщение\n"
            "<code>/закрепить</code> · <code>/открепить</code>\n\n"
            "Команды модерации требуют прав администратора чата и соответствующих прав у бота."
        )


@router.callback_query(F.data == "owner_fun_help")
async def owner_fun_help(cb: CallbackQuery):
    if not callback_is_owner(cb):
        await cb.answer("Нет доступа", show_alert=True)
        return
    await cb.answer()
    if cb.message:
        await cb.message.answer(
            "🎉 <b>РАЗВЛЕЧЕНИЯ</b>\n"
            "/завоз — персональное сообщение с мемом\n"
            "/вайб — случайная оценка вайба\n"
            "/рофл — авторская шутка\n"
            "/зов_вкл и /зов_выкл — настройка добровольных упоминаний\n"
            "/зов — список тех, кто сам подписался"
        )

@router.message(Cmd("юзер", "useredit"))
async def edit_user(message: Message, args: list[str], db: DB):
    if not owner_private(message):
        return
    target = await resolve_target(message, args, db)
    if target is None:
        await message.reply("Укажи ID/@ник или ответь на сообщение: /юзер ID")
        return
    await message.answer(await render_user(db, target.user_id), reply_markup=user_keyboard(target.user_id))

@router.callback_query(F.data.startswith("u_edit:"))
async def edit_field(cb: CallbackQuery):
    if not callback_is_owner_private(cb):
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

@router.callback_query(F.data == "u_warn_help")
async def show_warns_help(cb: CallbackQuery):
    if not callback_is_owner_private(cb):
        await cb.answer("Нет доступа", show_alert=True)
        return
    await cb.answer()
    if cb.message:
        await cb.message.answer(
            "⚠️ Предупреждения считаются отдельно в каждом чате. "
            "Чтобы посмотреть их, открой нужную группу и напиши <code>/варны @ник</code>."
        )

@router.callback_query(F.data.startswith("u_reset:"))
async def confirm_reset_user(cb: CallbackQuery):
    if not callback_is_owner_private(cb):
        await cb.answer("Нет доступа", show_alert=True)
        return
    try:
        uid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer("Некорректный пользователь", show_alert=True)
        return
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да, сбросить", callback_data=f"u_reset_yes:{uid}")
    kb.button(text="↩️ Отмена", callback_data=f"u_reset_no:{uid}")
    kb.adjust(2)
    await cb.answer()
    if cb.message:
        await cb.message.answer(
            f"⚠️ <b>Подтверди сброс профиля {uid}</b>\n"
            "Баланс, работа, смены, ник и роль будут очищены. Это действие нельзя отменить.",
            reply_markup=kb.as_markup()
        )


@router.callback_query(F.data.startswith("u_reset_yes:"))
async def reset_user(cb: CallbackQuery, db: DB):
    if not callback_is_owner_private(cb):
        await cb.answer("Нет доступа", show_alert=True)
        return
    try:
        uid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer("Некорректный пользователь", show_alert=True)
        return
    async with db.lock:
        await db.conn.execute(
            "UPDATE users SET balance=0,job_id=NULL,total_shifts=0,total_earned=0,last_work=0,custom_nick='',role='',active_title='' WHERE user_id=?",
            (uid,)
        )
        await db.conn.execute("DELETE FROM job_stats WHERE user_id=?", (uid,))
        await db.conn.execute("DELETE FROM shop_inventory WHERE user_id=?", (uid,))
        await db.conn.commit()
    await cb.answer("Профиль сброшен", show_alert=True)
    if cb.message:
        await cb.message.answer(await render_user(db, uid), reply_markup=user_keyboard(uid))


@router.callback_query(F.data.startswith("u_reset_no:"))
async def cancel_reset_user(cb: CallbackQuery):
    if not callback_is_owner_private(cb):
        await cb.answer("Нет доступа", show_alert=True)
        return
    await cb.answer("Сброс отменён")
    if cb.message:
        await cb.message.answer("✅ Сброс профиля отменён.")

@router.message(lambda message: message.from_user is not None and message.from_user.id in _pending and bool(message.text))
async def pending_value(message: Message, db: DB):
    if not owner_private(message):
        return
    uid, field = _pending[message.from_user.id]
    value = message.text.strip()
    if value.lower() in {"/отмена", "/cancel", "!отмена"}:
        _pending.pop(message.from_user.id, None)
        await message.reply("✅ Редактирование отменено.")
        return
    if value.startswith("/") or value.startswith("!"):
        await message.reply("Сейчас ожидается значение поля. Чтобы выйти, отправь /отмена.")
        return
    if field.startswith("warns:"):
        try:
            chat_id = int(field.split(":", 1)[1])
            number = int(value)
            if not 0 <= number <= 1000: raise ValueError
        except ValueError:
            await message.reply("Нужно целое число от 0 до 1000. Попробуй ещё раз.")
            return
        async with db.lock:
            await db.conn.execute("INSERT INTO warns(chat_id,user_id,count) VALUES(?,?,?) ON CONFLICT(chat_id,user_id) DO UPDATE SET count=excluded.count", (chat_id, uid, number))
            await db.conn.commit()
    elif field in {"balance", "total_shifts", "total_earned"}:
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
        if field == "role" and value != ".":
            async with db.conn.execute("SELECT 1 FROM custom_roles WHERE name=? COLLATE NOCASE", (value,)) as cur:
                if await cur.fetchone() is None:
                    await message.reply("Такой роли нет. Сначала создай её командой /создатьроль Название 50 или выбери /роли.")
                    return
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



# ---------- управление пользовательскими ролями (только владелец, из любого чата) ----------

@router.message(Cmd("роли", "roles"))
async def list_roles(message: Message, db: DB):
    if not owner_ok(message.from_user):
        return
    async with db.conn.execute("SELECT name,priority FROM custom_roles ORDER BY priority DESC,name COLLATE NOCASE") as cur:
        rows = await cur.fetchall()
    if not rows:
        await message.answer("Пока ролей нет. Создай: <code>/создатьроль Название 50</code>")
        return
    lines = ["🏷 <b>Роли сервера</b> (приоритет 0–100):"]
    lines.extend(f"• <b>{escape(row['name'])}</b> — приоритет <b>{row['priority']}</b>" for row in rows)
    lines.append("\nИзменить: /приоритетроль Название 75\nУдалить: /удалитьроль Название")
    await message.answer("\n".join(lines))


@router.message(Cmd("создатьроль", "rolecreate"))
async def create_role(message: Message, args: list[str], db: DB):
    if not owner_ok(message.from_user):
        return
    if len(args) < 2:
        await message.reply("Формат: <code>/создатьроль Название 50</code>")
        return
    try:
        priority = int(args[-1])
    except ValueError:
        await message.reply("Последним аргументом укажи приоритет от 0 до 100.")
        return
    name = " ".join(args[:-1]).strip()
    if not name or len(name) > 32 or not 0 <= priority <= 100:
        await message.reply("Название — до 32 символов, приоритет — от 0 до 100.")
        return
    try:
        async with db.lock:
            await db.conn.execute("INSERT INTO custom_roles(name,priority) VALUES(?,?)", (name, priority))
            await db.conn.commit()
    except Exception:
        await message.reply("Такая роль уже существует.")
        return
    await message.answer(f"✅ Роль <b>{escape(name)}</b> создана. Приоритет: <b>{priority}</b>.")


@router.message(Cmd("удалитьроль", "roledelete"))
async def delete_role(message: Message, args: list[str], db: DB):
    if not owner_ok(message.from_user):
        return
    name = " ".join(args).strip()
    if not name:
        await message.reply("Формат: <code>/удалитьроль Название</code>")
        return
    async with db.lock:
        async with db.conn.execute("SELECT name FROM custom_roles WHERE name=? COLLATE NOCASE", (name,)) as cur:
            row = await cur.fetchone()
        if row is None:
            await message.reply("Роль не найдена. Посмотри список: /роли")
            return
        await db.conn.execute("UPDATE users SET role='' WHERE role=? COLLATE NOCASE", (row["name"],))
        await db.conn.execute("DELETE FROM custom_roles WHERE name=? COLLATE NOCASE", (row["name"],))
        await db.conn.commit()
    await message.answer(f"🗑 Роль <b>{escape(row['name'])}</b> удалена. У назначенных пользователей роль снята.")


@router.message(Cmd("приоритетроль", "rolepriority"))
async def set_role_priority(message: Message, args: list[str], db: DB):
    if not owner_ok(message.from_user):
        return
    if len(args) < 2:
        await message.reply("Формат: <code>/приоритетроль Название 75</code>")
        return
    try:
        priority = int(args[-1])
    except ValueError:
        await message.reply("Приоритет должен быть числом от 0 до 100.")
        return
    name = " ".join(args[:-1]).strip()
    if not 0 <= priority <= 100:
        await message.reply("Приоритет должен быть от 0 до 100.")
        return
    async with db.lock:
        cur = await db.conn.execute("UPDATE custom_roles SET priority=? WHERE name=? COLLATE NOCASE", (priority, name))
        await db.conn.commit()
        changed = cur.rowcount
    if not changed:
        await message.reply("Роль не найдена. Посмотри список: /роли")
        return
    await message.answer(f"✅ Приоритет роли <b>{escape(name)}</b> установлен: <b>{priority}</b>.")


@router.message(Cmd("назначитьроль", "roleset"))
async def assign_role(message: Message, args: list[str], db: DB):
    if not owner_ok(message.from_user):
        return
    target = await resolve_target(message, args, db)
    if target is None or not target.rest:
        await message.reply("Формат: ответь на сообщение <code>/назначитьроль Название</code> или напиши <code>/назначитьроль @ник Название</code>.")
        return
    role_name = " ".join(target.rest).strip()
    async with db.conn.execute("SELECT name FROM custom_roles WHERE name=? COLLATE NOCASE", (role_name,)) as cur:
        role = await cur.fetchone()
    if role is None:
        await message.reply("Роль не найдена. Посмотри /роли или создай её.")
        return
    await db.ensure_user(target.user_id)
    async with db.lock:
        await db.conn.execute("UPDATE users SET role=? WHERE user_id=?", (role["name"], target.user_id))
        await db.conn.commit()
    await message.answer(f"✅ Пользователю {mention(target.user_id, target.name)} назначена роль <b>{escape(role['name'])}</b>.")


@router.message(Cmd("снятьроль", "roleremove"))
async def remove_role(message: Message, args: list[str], db: DB):
    if not owner_ok(message.from_user):
        return
    target = await resolve_target(message, args, db)
    if target is None:
        await message.reply("Ответь на сообщение или укажи ID/@ник: /снятьроль @ник")
        return
    await db.ensure_user(target.user_id)
    async with db.lock:
        await db.conn.execute("UPDATE users SET role='' WHERE user_id=?", (target.user_id,))
        await db.conn.commit()
    await message.answer(f"✅ Роль снята с {mention(target.user_id, target.name)}.")

@router.message(Cmd("приветствие", "welcome"))
async def set_welcome(message: Message, args: list[str], db: DB):
    if not owner_ok(message.from_user):
        await message.reply("⛔ Настраивать приветствие может только владелец бота.")
        return

    if message.chat.type in {"group", "supergroup"}:
        chat_id = message.chat.id
        if not args:
            await message.reply(
                "Формат в группе: <code>/welcome Привет, {name}!</code>\n"
                "Отключить: <code>/welcome off</code>."
            )
            return
        value = " ".join(args)
    else:
        if len(args) < 2:
            await message.reply(
                "Формат в ЛС: <code>/welcome ID_ГРУППЫ Привет, {name}!</code>\n"
                "Отключить: <code>/welcome ID_ГРУППЫ off</code>."
            )
            return
        try:
            chat_id = int(args[0])
        except ValueError:
            await message.reply("Первым аргументом укажи числовой ID группы, например -1001234567890.")
            return
        value = " ".join(args[1:])

    if value.lower() in {"выкл", "off", "disable"}:
        value = ""
    async with db.lock:
        await db.conn.execute(
            "INSERT INTO chat_settings(chat_id,welcome_text) VALUES(?,?) "
            "ON CONFLICT(chat_id) DO UPDATE SET welcome_text=excluded.welcome_text",
            (chat_id, value[:1000])
        )
        await db.conn.commit()
    await message.reply("✅ Приветствие отключено." if not value else "✅ Приветствие сохранено.")


# ---------- приветствие новичков и добровольные упоминания ----------
import time
from aiogram.enums import ChatType
from aiogram.types import User

_last_call: dict[int, float] = {}

@router.message(F.new_chat_members)
async def welcome_new_members(message: Message, db: DB):
    template = await db.get_welcome(message.chat.id) if hasattr(db, "get_welcome") else ""
    if not template:
        async with db.conn.execute("SELECT welcome_text FROM chat_settings WHERE chat_id=?", (message.chat.id,)) as cur:
            row = await cur.fetchone()
        template = row["welcome_text"] if row else ""
    if not template:
        return
    for user in message.new_chat_members:
        if user.is_bot:
            continue
        safe_name = escape(user.full_name)
        text = template.replace("{name}", safe_name).replace("{username}", escape("@" + user.username if user.username else "нет")).replace("{id}", str(user.id))
        await message.answer(text[:4000])

@router.message(Cmd("зов_вкл", "zov_on"))
async def optin_zov(message: Message, db: DB):
    if message.chat.type not in {"group", "supergroup"} or message.from_user is None:
        await message.reply("Команда работает в группе."); return
    async with db.lock:
        await db.conn.execute("INSERT OR IGNORE INTO mention_optins(chat_id,user_id) VALUES(?,?)", (message.chat.id, message.from_user.id))
        await db.conn.commit()
    await message.reply("✅ Ты согласился получать упоминания по команде /зов. Отписаться: /зов_выкл")

@router.message(Cmd("зов_выкл", "zov_off"))
async def optout_zov(message: Message, db: DB):
    if message.chat.type not in {"group", "supergroup"} or message.from_user is None:
        await message.reply("Команда работает в группе."); return
    async with db.lock:
        await db.conn.execute("DELETE FROM mention_optins WHERE chat_id=? AND user_id=?", (message.chat.id, message.from_user.id))
        await db.conn.commit()
    await message.reply("Отключено: ты больше не получаешь упоминания от /зов.")

@router.message(Cmd("зов", "zov"))
async def call_opted_in(message: Message, db: DB):
    if message.chat.type not in {"group", "supergroup"}:
        await message.reply("Команда работает в группе."); return
    now = time.monotonic()
    if now - _last_call.get(message.chat.id, 0) < 60:
        await message.reply("⏳ Команду /зов можно использовать раз в минуту.")
        return
    async with db.conn.execute(
        "SELECT u.user_id,COALESCE(NULLIF(u.custom_nick,''),NULLIF(u.first_name,''),u.username,CAST(u.user_id AS TEXT)) AS display "
        "FROM mention_optins m LEFT JOIN users u ON u.user_id=m.user_id WHERE m.chat_id=? ORDER BY m.user_id LIMIT 20",
        (message.chat.id,)) as cur:
        rows = await cur.fetchall()
    if not rows:
        await message.reply("Пока никто не подписался. Участники могут написать /зов_вкл.")
        return
    _last_call[message.chat.id] = now
    mentions = [f'<a href="tg://user?id={row["user_id"]}">{escape(row["display"])}</a>' for row in rows]
    await message.answer("📢 Участники, подписавшиеся на упоминания:\n" + " · ".join(mentions))
