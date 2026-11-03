"""Работа с базой данных SQLite (через aiosqlite)."""
from __future__ import annotations

import asyncio

import aiosqlite

MAX_BALANCE = 10**15

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER PRIMARY KEY,
    username      TEXT,
    first_name    TEXT    NOT NULL DEFAULT '',
    balance       INTEGER NOT NULL DEFAULT 0,
    job_id        TEXT,
    total_shifts  INTEGER NOT NULL DEFAULT 0,
    total_earned  INTEGER NOT NULL DEFAULT 0,
    last_work     REAL    NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

CREATE TABLE IF NOT EXISTS job_stats (
    user_id INTEGER NOT NULL,
    job_id  TEXT    NOT NULL,
    shifts  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, job_id)
);

CREATE TABLE IF NOT EXISTS warns (
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    count   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (chat_id, user_id)
);
"""


class DB:
    def __init__(self, path: str) -> None:
        self.path = path
        self.conn: aiosqlite.Connection | None = None
        self.lock = asyncio.Lock()  # все записи идут по очереди, так нет гонок
        self._seen: dict[int, tuple[str | None, str]] = {}

    async def init(self) -> None:
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA journal_mode=WAL")
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()

    async def close(self) -> None:
        if self.conn is not None:
            # Сбрасываем WAL в основной файл перед штатным завершением процесса.
            await self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            await self.conn.close()

    # ---------- пользователи ----------

    async def upsert_user(self, user_id: int, username: str | None, name: str) -> None:
        """Запоминаем ник и имя (нужно, чтобы находить людей по @username)."""
        username = username.lower() if username else None
        key = (username, name)
        if self._seen.get(user_id) == key:
            return
        async with self.lock:
            await self.conn.execute(
                "INSERT INTO users(user_id, username, first_name) VALUES(?,?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, "
                "first_name=excluded.first_name",
                (user_id, username, name),
            )
            if username:
                await self.conn.execute(
                    "UPDATE users SET username=NULL WHERE username=? AND user_id!=?",
                    (username, user_id),
                )
            await self.conn.commit()
        self._seen[user_id] = key

    async def ensure_user(self, user_id: int) -> None:
        async with self.lock:
            await self.conn.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (user_id,))
            await self.conn.commit()

    async def get_user(self, user_id: int):
        async with self.conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)) as cur:
            return await cur.fetchone()

    async def find_by_username(self, username: str):
        async with self.conn.execute(
            "SELECT * FROM users WHERE username=?", (username.lstrip("@").lower(),)
        ) as cur:
            return await cur.fetchone()

    # ---------- монеты ----------

    async def change_balance(self, user_id: int, delta: int) -> tuple[int, int]:
        """Меняет баланс (не уходит ниже 0). Возвращает (новый баланс, реально изменено)."""
        async with self.lock:
            await self.conn.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (user_id,))
            async with self.conn.execute(
                "SELECT balance FROM users WHERE user_id=?", (user_id,)
            ) as cur:
                old = (await cur.fetchone())["balance"]
            new = min(max(old + delta, 0), MAX_BALANCE)
            await self.conn.execute("UPDATE users SET balance=? WHERE user_id=?", (new, user_id))
            await self.conn.commit()
            return new, new - old

    async def transfer(self, from_id: int, to_id: int, amount: int) -> bool:
        async with self.lock:
            await self.conn.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (to_id,))
            cur = await self.conn.execute(
                "UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?",
                (amount, from_id, amount),
            )
            if cur.rowcount != 1:
                await self.conn.rollback()
                return False
            await self.conn.execute(
                "UPDATE users SET balance=MIN(balance+?, ?) WHERE user_id=?",
                (amount, MAX_BALANCE, to_id),
            )
            await self.conn.commit()
            return True

    async def top(self, limit: int = 10):
        async with self.conn.execute(
            "SELECT user_id, username, first_name, balance FROM users "
            "WHERE balance>0 ORDER BY balance DESC LIMIT ?",
            (limit,),
        ) as cur:
            return await cur.fetchall()

    # ---------- работа ----------

    async def hire(self, user_id: int, job_id: str, req_shifts: int) -> bool:
        """Устраивает на работу, только если отработано достаточно смен."""
        async with self.lock:
            await self.conn.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (user_id,))
            cur = await self.conn.execute(
                "UPDATE users SET job_id=? WHERE user_id=? AND total_shifts>=?",
                (job_id, user_id, req_shifts),
            )
            await self.conn.commit()
            return cur.rowcount == 1

    async def quit_job(self, user_id: int) -> bool:
        async with self.lock:
            cur = await self.conn.execute(
                "UPDATE users SET job_id=NULL WHERE user_id=? AND job_id IS NOT NULL", (user_id,)
            )
            await self.conn.commit()
            return cur.rowcount == 1

    async def do_shift(self, user_id: int, job_id: str, pay: int, now: float, cooldown_s: int) -> bool:
        """Засчитывает смену. Кулдаун проверяется прямо в запросе, обойти его спамом нельзя."""
        async with self.lock:
            cur = await self.conn.execute(
                "UPDATE users SET balance=MIN(balance+?, ?), total_earned=total_earned+?, "
                "total_shifts=total_shifts+1, last_work=? "
                "WHERE user_id=? AND job_id=? AND last_work<=?",
                (pay, MAX_BALANCE, pay, now, user_id, job_id, now - cooldown_s),
            )
            if cur.rowcount != 1:
                await self.conn.rollback()
                return False
            await self.conn.execute(
                "INSERT INTO job_stats(user_id, job_id, shifts) VALUES(?,?,1) "
                "ON CONFLICT(user_id, job_id) DO UPDATE SET shifts=shifts+1",
                (user_id, job_id),
            )
            await self.conn.commit()
            return True

    async def job_shifts(self, user_id: int, job_id: str) -> int:
        async with self.conn.execute(
            "SELECT shifts FROM job_stats WHERE user_id=? AND job_id=?", (user_id, job_id)
        ) as cur:
            row = await cur.fetchone()
        return row["shifts"] if row else 0

    # ---------- варны ----------

    async def add_warn(self, chat_id: int, user_id: int) -> int:
        async with self.lock:
            await self.conn.execute(
                "INSERT INTO warns(chat_id, user_id, count) VALUES(?,?,1) "
                "ON CONFLICT(chat_id, user_id) DO UPDATE SET count=count+1",
                (chat_id, user_id),
            )
            await self.conn.commit()
        return await self.get_warns(chat_id, user_id)

    async def remove_warn(self, chat_id: int, user_id: int) -> int:
        async with self.lock:
            await self.conn.execute(
                "UPDATE warns SET count=MAX(count-1, 0) WHERE chat_id=? AND user_id=?",
                (chat_id, user_id),
            )
            await self.conn.commit()
        return await self.get_warns(chat_id, user_id)

    async def reset_warns(self, chat_id: int, user_id: int) -> None:
        async with self.lock:
            await self.conn.execute(
                "DELETE FROM warns WHERE chat_id=? AND user_id=?", (chat_id, user_id)
            )
            await self.conn.commit()

    async def get_warns(self, chat_id: int, user_id: int) -> int:
        async with self.conn.execute(
            "SELECT count FROM warns WHERE chat_id=? AND user_id=?", (chat_id, user_id)
        ) as cur:
            row = await cur.fetchone()
        return row["count"] if row else 0
