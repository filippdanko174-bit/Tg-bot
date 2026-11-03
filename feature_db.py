"""Idempotent SQLite migrations for optional bot features."""
async def init_features(db):
    async with db.lock:
        async with db.conn.execute("PRAGMA table_info(users)") as cur:
            columns = {row["name"] for row in await cur.fetchall()}
        if "custom_nick" not in columns:
            await db.conn.execute("ALTER TABLE users ADD COLUMN custom_nick TEXT NOT NULL DEFAULT ''")
        if "role" not in columns:
            await db.conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT ''")
        await db.conn.executescript("""
        CREATE TABLE IF NOT EXISTS chat_settings (
            chat_id INTEGER PRIMARY KEY,
            welcome_text TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS mention_optins (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            PRIMARY KEY(chat_id,user_id)
        );
        """)
        await db.conn.commit()
