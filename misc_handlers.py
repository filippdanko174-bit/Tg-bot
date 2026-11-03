"""Небольшие утилиты и мини-развлечения без лишних зависимостей."""
from __future__ import annotations

import secrets
import time

from aiogram import Bot, Router
from aiogram.types import Message

from utils import Cmd

router = Router(name="misc")


@router.message(Cmd("пинг", "ping"))
async def cmd_ping(message: Message, bot: Bot) -> None:
    started = time.perf_counter()
    try:
        await bot.get_me()
    except Exception:
        await message.reply("⚠️ Telegram API сейчас не отвечает. Попробуй чуть позже.")
        return
    latency_ms = round((time.perf_counter() - started) * 1000)
    await message.reply(f"🏓 <b>Pong!</b>\nОтвет Telegram API: <code>{latency_ms} мс</code>")


@router.message(Cmd("монетка", "coin", "орёлрешка"))
async def cmd_coin(message: Message) -> None:
    result = secrets.choice(("🦅 Орёл!", "🪙 Решка!"))
    await message.reply(f"🎯 Монетка решила: <b>{result}</b>")


@router.message(Cmd("кости", "dice"))
async def cmd_dice(message: Message, bot: Bot) -> None:
    await bot.send_dice(chat_id=message.chat.id, emoji="🎲")


@router.message(Cmd("число", "number", "рандом"))
async def cmd_number(message: Message, args: list[str]) -> None:
    if len(args) != 2:
        await message.reply("Формат: <code>/число 1 100</code> — случайное число от 1 до 100.")
        return
    try:
        low, high = (int(value) for value in args)
    except ValueError:
        await message.reply("❌ Границы должны быть целыми числами.")
        return
    if low > high:
        await message.reply("❌ Первое число должно быть меньше или равно второму.")
        return
    if low < -1_000_000 or high > 1_000_000:
        await message.reply("❌ Диапазон ограничен числами от -1 000 000 до 1 000 000.")
        return
    await message.reply(f"🎲 Случайное число: <b>{secrets.randbelow(high - low + 1) + low}</b>")
