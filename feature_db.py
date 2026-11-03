"""Idempotent SQLite migrations for optional bot features."""
async def init_features(db):
    async with db.lock:
        async with db.conn.execute("PRAGMA table_info(users)") as cur:
            columns = {row["name"] for row in await cur.fetchall()}
        if "custom_nick" not in columns:
            await db.conn.execute("ALTER TABLE users ADD COLUMN custom_nick TEXT NOT NULL DEFAULT ''")
        if "role" not in columns:
            await db.conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT ''")
        if "active_title" not in columns:
            await db.conn.execute("ALTER TABLE users ADD COLUMN active_title TEXT NOT NULL DEFAULT ''")
        await db.conn.executescript("""
        CREATE TABLE IF NOT EXISTS custom_roles (
            name TEXT PRIMARY KEY COLLATE NOCASE,
            priority INTEGER NOT NULL CHECK(priority BETWEEN 0 AND 100)
        );
        CREATE TABLE IF NOT EXISTS shop_inventory (
            user_id INTEGER NOT NULL,
            item_id TEXT NOT NULL,
            bought_at REAL NOT NULL DEFAULT (strftime('%s','now')),
            PRIMARY KEY(user_id,item_id)
        );
        CREATE TABLE IF NOT EXISTS chat_settings (
            chat_id INTEGER PRIMARY KEY,
            welcome_text TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS known_chats (
            chat_id INTEGER PRIMARY KEY,
            title TEXT NOT NULL DEFAULT '',
            chat_type TEXT NOT NULL DEFAULT '',
            username TEXT NOT NULL DEFAULT '',
            last_seen REAL NOT NULL DEFAULT (strftime('%s','now'))
        );
        CREATE TABLE IF NOT EXISTS admin_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            actor_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            target_id INTEGER,
            details TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
        );
        CREATE INDEX IF NOT EXISTS idx_admin_audit_created ON admin_audit(created_at DESC);
        CREATE TABLE IF NOT EXISTS global_blocks (
            user_id INTEGER PRIMARY KEY,
            reason TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
        );
        CREATE TABLE IF NOT EXISTS mention_optins (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            PRIMARY KEY(chat_id,user_id)
        );
        """)
        await db.conn.commit()
