"""Интеграция с Grid API: /ai и обращение к боту в чате."""
from __future__ import annotations

import asyncio
import logging
import re
from collections import defaultdict
from typing import Any

import aiohttp
from aiogram import Bot, Router, F
from aiogram.filters import Command
from aiogram.types import Message

import config

router = Router(name="ai")
log = logging.getLogger("ai")
API_URL = config.GRID_API_URL.rstrip("/") + "/chat/completions"
_histories: dict[tuple[int, int], list[dict[str, str]]] = defaultdict(list)
_locks: dict[tuple[int, int], asyncio.Lock] = {}
MAX_HISTORY = 12
MAX_PROMPT = 4000
SYSTEM_PROMPT = (
    "Ты дружелюбный помощник в Telegram-чате. Отвечай по-русски, "
    "если пользователь пишет по-русски. Будь полезным, ясным и кратким."
)

_bot_identity: tuple[int, str] | None = None
_bot_identity_lock = asyncio.Lock()


async def _get_bot_identity(bot: Bot) -> tuple[int, str]:
    """Запрашивает профиль бота один раз, а не на каждое обычное сообщение."""
    global _bot_identity
    if _bot_identity is None:
        async with _bot_identity_lock:
            if _bot_identity is None:
                me = await bot.get_me()
                _bot_identity = (me.id, me.username or "")
    return _bot_identity



def _history_key(message: Message) -> tuple[int, int]:
    return (message.chat.id, message.from_user.id if message.from_user else message.chat.id)


def _extract_text(message: Message, bot_username: str = "") -> str:
    text = (message.text or message.caption or "").strip()
    if text.startswith("/"):
        parts = text.split(maxsplit=1)
        text = parts[1] if len(parts) > 1 else ""
    if bot_username:
        text = re.sub(rf"@{re.escape(bot_username)}\b", "", text, flags=re.IGNORECASE)
    return text.strip()


async def _ask_grid(prompt: str, history: list[dict[str, str]]) -> str:
    if not config.GRID_API_KEY:
        raise RuntimeError("GRID_API_KEY не задан в переменных окружения")
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history, {"role": "user", "content": prompt}]
    headers = {"Authorization": f"Bearer {config.GRID_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": config.GRID_MODEL, "messages": messages, "temperature": 0.7}
    timeout = aiohttp.ClientTimeout(total=60, connect=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(API_URL, headers=headers, json=payload) as response:
            if response.status >= 400:
                body = (await response.text())[:500]
                log.warning("Grid API вернул HTTP %s: %s", response.status, body)
                if response.status in (401, 403):
                    raise RuntimeError("Grid API не принял ключ. Проверь GRID_API_KEY.")
                if response.status == 429:
                    raise RuntimeError("Лимит Grid API исчерпан. Попробуй позже.")
                raise RuntimeError(f"Grid API временно недоступен (HTTP {response.status}).")
            data: dict[str, Any] = await response.json()
    try:
        answer = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("Grid API вернул ответ в неожиданном формате.")
    if isinstance(answer, list):
        answer = "".join(part.get("text", "") for part in answer if isinstance(part, dict))
    answer = str(answer).strip()
    if not answer:
        raise RuntimeError("Grid API вернул пустой ответ.")
    return answer[:12000]


async def _handle_ai(message: Message, prompt: str, bot: Bot) -> None:
    if not prompt:
        await message.reply("Напиши вопрос после команды: <code>/ai привет!</code>", parse_mode="HTML")
        return
    if len(prompt) > MAX_PROMPT:
        await message.reply(f"Сообщение слишком длинное. Максимум {MAX_PROMPT} символов.", parse_mode=None)
        return
    key = _history_key(message)
    lock = _locks.setdefault(key, asyncio.Lock())
    status = await message.reply("🤖 Думаю…", parse_mode=None)
    async with lock:
        history = _histories[key]
        try:
            answer = await _ask_grid(prompt, history[-MAX_HISTORY:])
        except (aiohttp.ClientError, asyncio.TimeoutError):
            log.exception("Ошибка соединения с Grid API")
            await status.edit_text("Не удалось связаться с Grid API. Попробуй немного позже.", parse_mode=None)
            return
        except RuntimeError as exc:
            await status.edit_text(str(exc), parse_mode=None)
            return
        history.extend([{"role": "user", "content": prompt}, {"role": "assistant", "content": answer}])
        del history[:-MAX_HISTORY]
    chunks = [answer[i:i + 4000] for i in range(0, len(answer), 4000)]
    await status.edit_text(chunks[0], parse_mode=None)
    for chunk in chunks[1:]:
        await message.answer(chunk, parse_mode=None)


@router.message(Command("ai"))
async def cmd_ai(message: Message, bot: Bot) -> None:
    await _handle_ai(message, _extract_text(message), bot)


@router.message(F.text & ~F.text.startswith("/"))
async def chat_with_ai(message: Message, bot: Bot) -> None:
    if not message.from_user or message.from_user.is_bot:
        return
    bot_id, username = await _get_bot_identity(bot)
    is_reply_to_bot = bool(
        message.reply_to_message
        and message.reply_to_message.from_user
        and message.reply_to_message.from_user.id == bot_id
    )
    is_mention = bool(username and re.search(rf"@{re.escape(username)}\b", message.text or "", re.IGNORECASE))
    if not (is_reply_to_bot or is_mention):
        return
    await _handle_ai(message, _extract_text(message, username), bot)


@router.message(Command("aiclear"))
async def cmd_ai_clear(message: Message) -> None:
    _histories.pop(_history_key(message), None)
    await message.reply("🧹 Контекст нашего диалога очищен.", parse_mode=None)
