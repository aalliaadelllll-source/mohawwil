"""إعدادات البوت — تُقرأ كلها من متغيرات البيئة (ملف .env)."""
import os

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except ValueError:
        return default


BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS: set[int] = {
    int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x.isdigit()
}
DAILY_LIMIT: int = _int("DAILY_LIMIT", 30)        # عدد التحويلات اليومية لكل مستخدم
MAX_FILE_MB: int = _int("MAX_FILE_MB", 20)        # حد تنزيل تيليجرام للبوتات = 20MB
MAX_MULTI: int = _int("MAX_MULTI", 20)            # أقصى عدد ملفات في التحويل المتعدد
MAX_CONCURRENT: int = max(1, _int("MAX_CONCURRENT", 2))  # عدد التحويلات المتزامنة (قلّله على السيرفرات الضعيفة)
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
MAX_SEND_MB: int = 50                             # حد رفع تيليجرام للبوتات = 50MB
