"""Небольшие мини-игры на бесплатные виртуальные монеты."""
from __future__ import annotations
import random
from aiogram import Router
from aiogram.types import Message
from db import DB
from utils import Cmd, parse_amount, fmt_money

router = Router(name="mini_games")

async def play(message: Message, db: DB, amount_token: str, game: str, choice: str | None = None):
    amount = parse_amount(amount_token)
    if amount is None or amount > 100000:
        await message.reply("Укажи ставку от 1 до 100 000 виртуальных монет."); return
    user = message.from_user
    if user is None or user.is_bot:
        await message.reply("Эта игра доступна только обычным аккаунтам."); return
    # Результат определяется до транзакции; списание и начисление выполняются атомарно.
    if game == "слоты":
        symbols = ["🍒", "🍋", "🔔", "⭐", "💎"]
        result = [random.choice(symbols) for _ in range(3)]
        if result[0] == result[1] == result[2]:
            multiplier = 5
        elif len(set(result)) == 2:
            multiplier = 2
        else:
            multiplier = 0
        outcome = " ".join(result)
    elif game == "кости":
        dice = [random.randint(1, 6), random.randint(1, 6)]
        multiplier = 2 if sum(dice) >= 8 else 0
        outcome = f"🎲 {dice[0]} + {dice[1]} = {sum(dice)}"
    else:
        if choice not in {"красное", "чёрное", "зелёное"}:
            await message.reply("Укажи цвет: /рулетка 100 красное (или чёрное / зелёное).")
            return
        pick = random.randint(0, 36)
        red_numbers = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
        color = "зелёное" if pick == 0 else ("красное" if pick in red_numbers else "чёрное")
        multiplier = 14 if choice == "зелёное" and color == "зелёное" else (2 if choice == color else 0)
        outcome = f"🎡 Выпало {pick} ({color}); твой выбор: {choice}"
    async with db.lock:
        await db.conn.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (user.id,))
        async with db.conn.execute("SELECT balance FROM users WHERE user_id=?", (user.id,)) as cur:
            row = await cur.fetchone()
        if row["balance"] < amount:
            await db.conn.commit()
            await message.reply(f"Не хватает монет. Баланс: {fmt_money(row['balance'])}"); return
        payout = amount * multiplier
        new_balance = min(10**15, row["balance"] - amount + payout)
        await db.conn.execute("UPDATE users SET balance=? WHERE user_id=?", (new_balance, user.id))
        await db.conn.commit()
    label = "ничья/выигрыш" if multiplier else "ставка проиграла"
    await message.reply(
        f"{'🎉' if multiplier else '🙂'} <b>{game.title()}</b>\n{outcome}\n"
        f"{label}: {fmt_money(payout if multiplier else 0)}\n"
        f"Баланс: <b>{fmt_money(new_balance)}</b>"
    )

def args_or_help(args):
    return args[0] if args else None

@router.message(Cmd("слоты", "slots"))
async def slots(message: Message, args: list[str], db: DB):
    token = args_or_help(args)
    if token is None:
        await message.reply("Формат: /слоты 100"); return
    await play(message, db, token, "слоты")

@router.message(Cmd("кости", "dice"))
async def dice(message: Message, args: list[str], db: DB):
    token = args_or_help(args)
    if token is None:
        await message.reply("Формат: /кости 100"); return
    await play(message, db, token, "кости")

@router.message(Cmd("рулетка", "roulette"))
async def roulette(message: Message, args: list[str], db: DB):
    token = args_or_help(args)
    if token is None:
        await message.reply("Формат: /рулетка 100"); return
    choice = args[1].lower() if len(args) > 1 else None
    await play(message, db, token, "рулетка", choice)
