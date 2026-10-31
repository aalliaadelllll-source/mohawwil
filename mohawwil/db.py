"""قاعدة بيانات SQLite خفيفة: المستخدمون، الاستخدام اليومي، إحصائيات الأدوات."""
import os
from datetime import date

import aiosqlite

import config

DB_PATH = "data/bot.db"


def _today() -> str:
    return date.today().isoformat()


async def init() -> None:
    os.makedirs("data", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as d:
        await d.executescript(
            """
            CREATE TABLE IF NOT EXISTS users(
                id INTEGER PRIMARY KEY, name TEXT, joined TEXT);
            CREATE TABLE IF NOT EXISTS usage(
                user_id INTEGER, day TEXT, n INTEGER,
                PRIMARY KEY(user_id, day));
            CREATE TABLE IF NOT EXISTS tools(
                tool TEXT PRIMARY KEY, n INTEGER);
            """
        )
        await d.commit()


async def add_user(uid: int, name: str) -> None:
    async with aiosqlite.connect(DB_PATH) as d:
        await d.execute(
            "INSERT OR IGNORE INTO users(id, name, joined) VALUES(?,?,?)",
            (uid, name, _today()),
        )
        await d.commit()


async def used_today(uid: int) -> int:
    async with aiosqlite.connect(DB_PATH) as d:
        cur = await d.execute(
            "SELECT n FROM usage WHERE user_id=? AND day=?", (uid, _today())
        )
        row = await cur.fetchone()
        return row[0] if row else 0


async def allowed(uid: int) -> bool:
    if uid in config.ADMIN_IDS:
        return True
    return await used_today(uid) < config.DAILY_LIMIT


async def bump(uid: int, tool: str) -> None:
    async with aiosqlite.connect(DB_PATH) as d:
        await d.execute(
            "INSERT INTO usage(user_id, day, n) VALUES(?,?,1) "
            "ON CONFLICT(user_id, day) DO UPDATE SET n = n + 1",
            (uid, _today()),
        )
        await d.execute(
            "INSERT INTO tools(tool, n) VALUES(?,1) "
            "ON CONFLICT(tool) DO UPDATE SET n = n + 1",
            (tool,),
        )
        await d.commit()


async def stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as d:
        users = (await (await d.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
        total = (await (await d.execute("SELECT COALESCE(SUM(n),0) FROM tools")).fetchone())[0]
        today = (
            await (
                await d.execute(
                    "SELECT COALESCE(SUM(n),0) FROM usage WHERE day=?", (_today(),)
                )
            ).fetchone()
        )[0]
        top = await (
            await d.execute("SELECT tool, n FROM tools ORDER BY n DESC LIMIT 5")
        ).fetchall()
    return {"users": users, "total": total, "today": today, "top": top}


async def all_user_ids() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as d:
        rows = await (await d.execute("SELECT id FROM users")).fetchall()
    return [r[0] for r in rows]


async def user_totals(uid: int) -> int:
    """إجمالي تحويلات المستخدم منذ البداية."""
    async with aiosqlite.connect(DB_PATH) as d:
        cur = await d.execute("SELECT COALESCE(SUM(n),0) FROM usage WHERE user_id=?", (uid,))
        return (await cur.fetchone())[0]
