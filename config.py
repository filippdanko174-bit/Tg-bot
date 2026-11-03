"""Настройки бота. Секреты берутся из переменных окружения или файла .env."""
from __future__ import annotations

import os
from pathlib import Path

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

# Grid API — ключ задаётся только в переменных окружения хостинга.
GRID_API_URL: str = os.getenv("GRID_API_URL", "https://keys.gridapi.ru/v1").strip()
GRID_API_KEY: str = os.getenv("GRID_API_KEY", "").strip()
GRID_MODEL: str = os.getenv("GRID_MODEL", "gpt-6.1").strip()

# База по умолчанию лежит рядом с файлами проекта, а не зависит от
# текущей рабочей папки процесса. На хостинге укажи DB_PATH на постоянный диск.
BASE_DIR = Path(__file__).resolve().parent
_db_path = Path(os.getenv("DB_PATH", str(BASE_DIR / "bot.db"))).expanduser()
if not _db_path.is_absolute():
    _db_path = BASE_DIR / _db_path
_db_path.parent.mkdir(parents=True, exist_ok=True)
DB_PATH: str = str(_db_path)

# Модерация
WARN_LIMIT: int = max(1, _int("WARN_LIMIT", 3))  # сколько варнов до авто-мута
WARN_MUTE_HOURS: int = max(1, _int("WARN_MUTE_HOURS", 24))  # на сколько часов мут за варны
DEFAULT_MUTE_MINUTES: int = max(1, _int("DEFAULT_MUTE_MINUTES", 60))  # мут без указания времени

# Работа: шанс премии за смену и её множитель
BONUS_CHANCE: float = 0.08
BONUS_MULT: float = 1.5
