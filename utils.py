"""Общие помощники: разбор команд, времени, сумм, поиск цели команды."""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from aiogram.filters import Filter
from aiogram.types import Message

if TYPE_CHECKING:
    from db import DB

BOT_USERNAME = ""  # заполняется при старте в bot.py
ANON_ADMIN_ID = 1087968824  # «GroupAnonymousBot»: так выглядит админ, пишущий анонимно
FOREVER = 0  # «навсегда» для наказаний
MAX_AMOUNT = 10**12


# ---------- команды ----------

_NAME_RE = re.compile(r"^\w+$")


def parse_command(text: str) -> tuple[str, list[str]] | None:
    """'/бан@bot 1д спам' -> ('бан', ['1д', 'спам']). Работает с / и ! и с русскими буквами."""
    text = (text or "").strip()
    if len(text) < 2 or text[0] not in "/!":
        return None
    parts = text.split(None, 1)
    head = parts[0][1:]
    rest = parts[1].split() if len(parts) > 1 else []
    name, _, target_bot = head.partition("@")
    if target_bot and BOT_USERNAME and target_bot.lower() != BOT_USERNAME.lower():
        return None  # команда адресована другому боту
    if not _NAME_RE.match(name):
        return None
    return name.lower(), rest


class Cmd(Filter):
    """Фильтр команды. Telegram не умеет русские команды, поэтому разбираем текст сами."""

    def __init__(self, *names: str) -> None:
        self.names = {n.lower() for n in names}

    async def __call__(self, message: Message):
        parsed = parse_command(message.text or "")
        if parsed is None or parsed[0] not in self.names:
            return False
        return {"args": parsed[1]}


# ---------- время и деньги ----------

_UNITS = {
    **dict.fromkeys(("мин", "м", "min", "m"), 60),
    **dict.fromkeys(("часов", "часа", "час", "ч", "hr", "h"), 3600),
    **dict.fromkeys(("дней", "дня", "день", "дн", "д", "d"), 86400),
    **dict.fromkeys(("нед", "н", "w"), 604800),
}
_DUR_RE = re.compile(r"^(\d{1,6})([^\W\d_]+)$")
_FOREVER_WORDS = {"навсегда", "навечно", "forever", "perm"}
_MAX_TEMP = 366 * 86400  # дольше этого Telegram считает наказание вечным


def parse_duration(token: str) -> int | None:
    """'30м' -> 1800, '2ч' -> 7200, 'навсегда' -> FOREVER, не время -> None."""
    t = token.lower()
    if t in _FOREVER_WORDS:
        return FOREVER
    m = _DUR_RE.match(t)
    if not m or m.group(2) not in _UNITS:
        return None
    secs = int(m.group(1)) * _UNITS[m.group(2)]
    if secs <= 0:
        return None
    return FOREVER if secs > _MAX_TEMP else secs


def fmt_duration(seconds: int) -> str:
    seconds = int(seconds)
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if d:
        parts.append(f"{d} д")
    if h:
        parts.append(f"{h} ч")
    if m:
        parts.append(f"{m} мин")
    if not parts:
        parts.append(f"{s} сек")
    return " ".join(parts)


_AMOUNT_RE = re.compile(r"^(\d+(?:[.,]\d+)?)(кк|kk|к|k)?$")


def parse_amount(token: str) -> int | None:
    """'1000' -> 1000, '5к' -> 5000, '1.5кк' -> 1500000. Неверное или <=0 -> None."""
    m = _AMOUNT_RE.match(token.lower().replace("_", ""))
    if not m:
        return None
    try:
        num = Decimal(m.group(1).replace(",", "."))
    except InvalidOperation:
        return None
    mult = {None: 1, "к": 1000, "k": 1000, "кк": 10**6, "kk": 10**6}[m.group(2)]
    value = int(num * mult)
    if value <= 0 or value > MAX_AMOUNT:
        return None
    return value


def fmt_money(n: int) -> str:
    return f"{n:,}".replace(",", " ") + " 🪙"


# ---------- пользователи ----------

def mention(user_id: int, name: str) -> str:
    return f'<a href="tg://user?id={user_id}">{html.escape(name or str(user_id))}</a>'


def row_name(row) -> str:
    if row is None:
        return "?"
    if row["first_name"]:
        return row["first_name"]
    if row["username"]:
        return "@" + row["username"]
    return str(row["user_id"])


@dataclass
class Target:
    user_id: int
    name: str
    is_bot: bool
    rest: list[str]  # остальные аргументы команды (время, причина, сумма...)


async def resolve_target(message: Message, args: list[str], db: "DB") -> Target | None:
    """Кого касается команда: автор сообщения, на которое ответили, либо @ник / ID первым словом."""
    reply = message.reply_to_message
    if reply is not None and reply.forum_topic_created is not None:
        reply = None  # в темах форума «ответом» считается само создание темы
    if reply is not None and reply.from_user is not None:
        u = reply.from_user
        return Target(u.id, u.full_name, u.is_bot, args)
    if not args:
        return None
    first = args[0]
    if first.startswith("@") and len(first) > 1:
        row = await db.find_by_username(first)
        if row is None:
            return None
        return Target(row["user_id"], row_name(row), False, args[1:])
    if first.isdigit() and len(first) >= 5:
        uid = int(first)
        row = await db.get_user(uid)
        return Target(uid, row_name(row) if row else str(uid), False, args[1:])
    return None
