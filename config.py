"""Настройки бота. Секреты берутся из переменных окружения или файла .env."""
from __future__ import annotations

import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # на хостинге переменные обычно задаются в панели, .env не нужен
    pass


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


# Токен от @BotFather
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()

# Telegram ID владельца (можно несколько через запятую). Узнать свой ID: команда /id в боте.
OWNER_IDS: set[int] = {
    int(x) for x in os.getenv("OWNER_ID", "").replace(" ", "").split(",") if x.isdigit()
}

# Путь к файлу базы данных
DB_PATH: str = os.getenv("DB_PATH", "bot.db")

# Модерация
WARN_LIMIT: int = max(1, _int("WARN_LIMIT", 3))  # сколько варнов до авто-мута
WARN_MUTE_HOURS: int = max(1, _int("WARN_MUTE_HOURS", 24))  # на сколько часов мут за варны
DEFAULT_MUTE_MINUTES: int = max(1, _int("DEFAULT_MUTE_MINUTES", 60))  # мут без указания времени

# Работа: шанс премии за смену и её множитель
BONUS_CHANCE: float = 0.08
BONUS_MULT: float = 1.5
