"""Оригинальные шуточные команды для лички и групп."""
from __future__ import annotations

import random
from html import escape

from aiogram import Router
from aiogram.types import Message

import config
from utils import Cmd

router = Router(name="fun")

ZAVOZ = [
    "{name} зашёл в чат — даже уведомления выпрямили спины.",
    "Система зафиксировала +999 к вайбу у {name}. Сервер просит автограф.",
    "{name} написал одно сообщение, а чат уже назвал это историческим событием.",
    "Завоз подъехал: сегодня у {name} режим главного героя без рекламы.",
    "Даже Wi-Fi поймал настроение {name} и стал работать стабильнее.",
    "{name} появился в сети. У скуки закончился контракт.",
    "Чат стал на 42% веселее. Причина: обнаружен {name}.",
    "{name} нажал «отправить», и где-то заиграли воображаемые фанфары.",
    "Уровень завоза: легендарный. Побочный эффект: улыбка у случайных прохожих.",
    "{name} сегодня не опаздывает — это время пытается за ним угнаться.",
]

VIBES = [
    "режим легенды активирован",
    "спокойная уверенность, как у кота на любимом кресле",
    "энергия главного героя, но без лишней драмы",
    "вайб человека, у которого всё под контролем (почти)",
    "сегодня даже понедельник не рискнёт спорить",
    "режим «я просто зашёл, а уже навёл атмосферу»",
]

ROFL = [
    "Мой план на сегодня: сделать список дел. Первый пункт — составить список дел.",
    "Я не торможу. Я даю событию время красиво произойти.",
    "У меня стабильный интернет. Нестабильны только решения.",
    "Бот хотел пошутить, но сначала попросил обновить чувство юмора.",
    "Самое сложное в понедельнике — объяснить ему, что он уже наступил.",
    "Когда говоришь «сейчас», но даже календарь не знает, когда именно.",
    "Мой режим энергосбережения включается после фразы «надо бы заняться делами».",
    "Чат настолько тихий, что даже уведомления шепчут.",
]


def _name(message: Message) -> str:
    user = message.from_user
    return escape(user.first_name if user and user.first_name else "Легенда")


@router.message(Cmd("завоз", "завозик", "zavoz"))
async def cmd_zavoz(message: Message) -> None:
    if message.from_user is None or message.from_user.is_bot:
        return
    owner_mode = message.from_user.id in config.OWNER_IDS
    heading = "👑 <b>ЭКСКЛЮЗИВНЫЙ ЗАВОЗ ДЛЯ ВЛАДЕЛЬЦА</b>" if owner_mode else "🚚 <b>ЗАВОЗ ПОДЪЕХАЛ</b>"
    line = random.choice(ZAVOZ).format(name=_name(message))
    await message.reply(f"{heading}\n\n{line}\n\n✨ Завоз одобрен.")


@router.message(Cmd("вайб", "vibe"))
async def cmd_vibe(message: Message) -> None:
    if message.from_user is None or message.from_user.is_bot:
        return
    score = random.randint(85, 100)
    line = random.choice(VIBES)
    await message.reply(
        f"🎛 <b>Проверка вайба</b>\n"
        f"Для: {_name(message)}\n"
        f"Уровень: <b>{score}/100</b>\n"
        f"Вердикт: {line}."
    )


@router.message(Cmd("рофл", "rofl"))
async def cmd_rofl(message: Message) -> None:
    if message.from_user is None or message.from_user.is_bot:
        return
    await message.reply(f"🤣 <b>Минутка рофла</b>\n\n{random.choice(ROFL)}")
