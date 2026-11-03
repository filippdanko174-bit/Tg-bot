"""Магазин косметических предметов за игровые монеты."""
from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from db import DB
from utils import Cmd, fmt_money

router = Router(name="shop")
ITEMS = {
    "bronze": ("🥉 Бронзовый значок", 250),
    "silver": ("🥈 Серебряный значок", 750),
    "gold": ("🥇 Золотой значок", 1500),
    "star": ("⭐ Звёздный титул", 3000),
    "crown": ("👑 Королевский титул", 5000),
}

def keyboard(uid: int):
    kb = InlineKeyboardBuilder()
    for key, (name, price) in ITEMS.items():
        kb.button(text=f"{name} — {price} 🪙", callback_data=f"shop_buy:{key}:{uid}")
    kb.button(text="🎒 Моя коллекция", callback_data=f"shop_inventory:{uid}")
    kb.adjust(1)
    return kb.as_markup()

@router.message(Cmd("магазин", "shop"))
async def open_shop(message: Message, db: DB):
    if not message.from_user:
        return
    await db.ensure_user(message.from_user.id)
    row = await db.get_user(message.from_user.id)
    lines = ["🛍 <b>МАГАЗИН МОНЕТОК</b>", f"Баланс: <b>{fmt_money(row['balance'])} 🪙</b>", ""]
    for name, price in ITEMS.values():
        lines.append(f"{name} — <b>{price} 🪙</b>")
    lines += ["", "Покупки сохраняются в коллекции навсегда. Монеты списываются только за выбранный предмет."]
    await message.answer("\n".join(lines), reply_markup=keyboard(message.from_user.id))

@router.callback_query(F.data.startswith("shop_buy:"))
async def buy_item(cb: CallbackQuery, db: DB):
    try:
        _, key, owner = cb.data.split(":")
        owner = int(owner)
    except (ValueError, AttributeError):
        await cb.answer("Некорректная покупка", show_alert=True)
        return
    if cb.from_user.id != owner:
        await cb.answer("Открой /магазин у себя.", show_alert=True)
        return
    if key not in ITEMS:
        await cb.answer("Предмет не найден.", show_alert=True)
        return
    name, price = ITEMS[key]
    async with db.lock:
        async with db.conn.execute("SELECT 1 FROM shop_inventory WHERE user_id=? AND item_id=?", (owner, key)) as cur:
            owned = await cur.fetchone()
        if owned:
            await cb.answer("Этот предмет уже есть у тебя!", show_alert=True)
            return
        async with db.conn.execute("SELECT balance FROM users WHERE user_id=?", (owner,)) as cur:
            row = await cur.fetchone()
        if not row or row["balance"] < price:
            await cb.answer(f"Не хватает {price - (row['balance'] if row else 0)} монет.", show_alert=True)
            return
        cur = await db.conn.execute("UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?", (price, owner, price))
        if cur.rowcount != 1:
            await db.conn.rollback()
            await cb.answer("Не удалось провести покупку. Попробуй ещё раз.", show_alert=True)
            return
        await db.conn.execute("INSERT INTO shop_inventory(user_id,item_id) VALUES(?,?)", (owner, key))
        await db.conn.execute("UPDATE users SET active_title=? WHERE user_id=?", (key, owner))
        await db.conn.commit()
    await cb.answer("Покупка успешна! 🎉", show_alert=True)
    if cb.message:
        await cb.message.answer(f"🎉 Куплено и надето: {name} за {price} 🪙\nПредмет в твоей коллекции. Напиши /инвентарь.")

@router.callback_query(F.data.startswith("shop_inventory:"))
async def inventory_button(cb: CallbackQuery, db: DB):
    try:
        owner = int(cb.data.split(":")[1])
    except (ValueError, AttributeError):
        await cb.answer("Ошибка", show_alert=True)
        return
    if cb.from_user.id != owner:
        await cb.answer("Это не твоя коллекция.", show_alert=True)
        return
    await cb.answer()
    if cb.message:
        await send_inventory(cb.message, owner, db)

async def send_inventory(message: Message, uid: int, db: DB):
    async with db.conn.execute("SELECT item_id FROM shop_inventory WHERE user_id=? ORDER BY bought_at", (uid,)) as cur:
        rows = await cur.fetchall()
    async with db.conn.execute("SELECT active_title FROM users WHERE user_id=?", (uid,)) as cur:
        active_row = await cur.fetchone()
    active = active_row["active_title"] if active_row else ""
    if not rows:
        await message.answer("🎒 <b>Коллекция пуста.</b>\\nЗагляни в /магазин!")
        return
    kb = InlineKeyboardBuilder()
    lines = ["🎒 <b>ТВОЯ КОЛЛЕКЦИЯ</b>", ""]
    for row in rows:
        key = row["item_id"]
        if key not in ITEMS:
            continue
        name = ITEMS[key][0]
        marker = " ✅ надет" if key == active else ""
        lines.append(f"• {name}{marker}")
        if key != active:
            kb.button(text=f"Надеть: {name}", callback_data=f"shop_equip:{key}:{uid}")
    kb.button(text="Снять титул", callback_data=f"shop_equip:none:{uid}")
    kb.adjust(1)
    await message.answer("\\n".join(lines), reply_markup=kb.as_markup())

@router.message(Cmd("инвентарь", "коллекция", "inventory"))
async def inventory_command(message: Message, db: DB):
    if message.from_user:
        await send_inventory(message, message.from_user.id, db)


@router.callback_query(F.data.startswith("shop_equip:"))
async def equip_title(cb: CallbackQuery, db: DB):
    try:
        _, key, owner_s = cb.data.split(":")
        owner = int(owner_s)
    except (ValueError, AttributeError):
        await cb.answer("Ошибка", show_alert=True)
        return
    if cb.from_user.id != owner:
        await cb.answer("Это не твоя коллекция.", show_alert=True)
        return
    if key != "none":
        if key not in ITEMS:
            await cb.answer("Такого титула нет.", show_alert=True)
            return
        async with db.conn.execute("SELECT 1 FROM shop_inventory WHERE user_id=? AND item_id=?", (owner, key)) as cur:
            owned = await cur.fetchone()
        if not owned:
            await cb.answer("Сначала купи этот титул.", show_alert=True)
            return
    async with db.lock:
        await db.conn.execute("UPDATE users SET active_title=? WHERE user_id=?", ("" if key == "none" else key, owner))
        await db.conn.commit()
    await cb.answer("Титул надет!" if key != "none" else "Титул снят!", show_alert=True)
    if cb.message:
        await send_inventory(cb.message, owner, db)
