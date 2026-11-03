from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from db import DB
from feature_db import init_features
from utils import parse_amount, parse_command, parse_duration


class UtilityTests(unittest.TestCase):
    def test_command_parser(self) -> None:
        self.assertEqual(parse_command("/работа"), ("работа", []))
        self.assertEqual(parse_command("/ban@somebot 2h spam"), ("ban", ["2h", "spam"]))

    def test_amount_and_duration_parsers(self) -> None:
        self.assertEqual(parse_amount("5к"), 5000)
        self.assertEqual(parse_amount("1.5кк"), 1_500_000)
        self.assertIsNone(parse_amount("-5"))
        self.assertEqual(parse_duration("2ч"), 7200)
        self.assertIsNone(parse_duration("0м"))


class DatabaseSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = DB(str(Path(self.temp_dir.name) / "test.sqlite3"))
        await self.db.init()
        await init_features(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()
        self.temp_dir.cleanup()

    async def test_chat_directory_and_mass_grants(self) -> None:
        await self.db.upsert_user(20001, "near_cap", "Near Cap")
        await self.db.upsert_user(20002, "regular", "Regular")
        await self.db.change_balance(20001, 10**15 - 50)

        count, credited = await self.db.grant_all(100)
        self.assertEqual((count, credited), (2, 150))

        first = await self.db.get_user(20001)
        second = await self.db.get_user(20002)
        self.assertEqual(first["balance"], 10**15)
        self.assertEqual(second["balance"], 100)

        await self.db.save_chat(-1001234567890, "Test Group", "supergroup", "test_group")
        async with self.db.conn.execute(
            "SELECT title,chat_type,username FROM known_chats WHERE chat_id=?",
            (-1001234567890,),
        ) as cur:
            chat = await cur.fetchone()
        self.assertEqual(tuple(chat), ("Test Group", "supergroup", "test_group"))

        await self.db.forget_chat(-1001234567890)
        async with self.db.conn.execute(
            "SELECT 1 FROM known_chats WHERE chat_id=?", (-1001234567890,)
        ) as cur:
            self.assertIsNone(await cur.fetchone())

    async def test_transfer_rejects_recipient_overflow(self) -> None:
        await self.db.upsert_user(30001, "sender", "Sender")
        await self.db.upsert_user(30002, "recipient", "Recipient")
        await self.db.change_balance(30001, 100)
        await self.db.change_balance(30002, 10**15 - 50)

        self.assertFalse(await self.db.transfer(30001, 30002, 100))
        sender = await self.db.get_user(30001)
        recipient = await self.db.get_user(30002)
        self.assertEqual(sender["balance"], 100)
        self.assertEqual(recipient["balance"], 10**15 - 50)

        self.assertTrue(await self.db.transfer(30001, 30002, 50))
        sender = await self.db.get_user(30001)
        recipient = await self.db.get_user(30002)
        self.assertEqual(sender["balance"], 50)
        self.assertEqual(recipient["balance"], 10**15)

    async def test_migrations_and_economy(self) -> None:
        # Migrations must be safe to run more than once.
        await init_features(self.db)

        await self.db.upsert_user(10001, "first_user", "First User")
        await self.db.upsert_user(10002, "second_user", "Second User")
        await self.db.change_balance(10001, 500)

        self.assertTrue(await self.db.transfer(10001, 10002, 125))
        self.assertTrue(await self.db.hire(10001, "courier", 0))
        self.assertTrue(await self.db.do_shift(10001, "courier", 25, 1000.0, 60))

        first = await self.db.get_user(10001)
        second = await self.db.get_user(10002)
        self.assertEqual(first["balance"], 400)
        self.assertEqual(first["total_shifts"], 1)
        self.assertEqual(first["total_earned"], 25)
        self.assertEqual(second["balance"], 125)

        async with self.db.conn.execute("SELECT name FROM custom_roles") as cur:
            self.assertEqual(await cur.fetchall(), [])

        async with self.db.conn.execute(
            "INSERT INTO custom_roles(name,priority) VALUES(?,?)", ("Moderator", 80)
        ):
            pass
        async with self.db.conn.execute(
            "UPDATE users SET role=? WHERE user_id=?", ("Moderator", 10001)
        ):
            pass
        await self.db.conn.commit()

        async with self.db.conn.execute(
            "SELECT r.priority FROM users u JOIN custom_roles r "
            "ON r.name=u.role COLLATE NOCASE WHERE u.user_id=?",
            (10001,),
        ) as cur:
            role = await cur.fetchone()
        self.assertEqual(role["priority"], 80)


if __name__ == "__main__":
    unittest.main()
