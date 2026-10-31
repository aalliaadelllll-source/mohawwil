"""نقطة تشغيل البوت."""
import asyncio
import logging
import re
import shutil
import time
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

import config
import db
from converters import TOOLS, is_available, missing
from handlers import TMP, router

TOKEN_RE = re.compile(r"^\d{6,12}:[A-Za-z0-9_-]{30,}$")


async def janitor() -> None:
    """يحذف المجلدات المؤقتة العالقة التي مضى عليها أكثر من ساعة."""
    while True:
        await asyncio.sleep(1800)
        if TMP.exists():
            for d in TMP.iterdir():
                if d.is_dir() and time.time() - d.stat().st_mtime > 3600:
                    shutil.rmtree(d, ignore_errors=True)


def report_tools() -> None:
    ready = [t for t in TOOLS.values() if is_available(t)]
    logging.info("الأدوات الجاهزة: %d/%d", len(ready), len(TOOLS))
    for t in TOOLS.values():
        if not is_available(t):
            logging.warning("أداة معطلة «%s» — ينقصها: %s", t.label, ", ".join(missing(t)))


async def main() -> None:
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if not config.BOT_TOKEN:
        raise SystemExit("❌ ضع BOT_TOKEN في متغيرات البيئة أو ملف .env (انسخ .env.example إلى .env)")
    if not TOKEN_RE.match(config.BOT_TOKEN):
        raise SystemExit("❌ شكل BOT_TOKEN غير صحيح. انسخه كاملاً من @BotFather (مثال: 123456:ABC...)")

    TMP.mkdir(exist_ok=True)
    shutil.rmtree(TMP, ignore_errors=True)   # تنظيف بقايا التشغيل السابق
    TMP.mkdir(exist_ok=True)
    await db.init()
    report_tools()

    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="🚀 القائمة الرئيسية"),
            BotCommand(command="me", description="📊 استخدامي اليوم"),
            BotCommand(command="help", description="ℹ️ المساعدة"),
            BotCommand(command="cancel", description="🛑 إلغاء العملية"),
        ]
    )
    cleaner = asyncio.create_task(janitor())
    me = await bot.get_me()
    logging.info("✅ البوت يعمل: @%s", me.username)
    try:
        await dp.start_polling(bot, drop_pending_updates=True)
    finally:
        cleaner.cancel()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit) as e:
        if isinstance(e, SystemExit) and e.code:
            print(e.code)
