"""فاحص الجاهزية: شغّله قبل البوت لتعرف أي التحويلات ستعمل على هذا السيرفر.

    python check.py
"""
import config
from converters import CATS, TOOLS, is_available, missing

print("═" * 44)
print(" فحص جاهزية بوت مُحَوِّل")
print("═" * 44)
print(f"BOT_TOKEN : {'✅ موجود' if config.BOT_TOKEN else '❌ غير موجود'}")
print(f"ADMIN_IDS : {sorted(config.ADMIN_IDS) or 'لا يوجد'}")
print(f"الحد اليومي: {config.DAILY_LIMIT} | المتزامن: {config.MAX_CONCURRENT}\n")

ok = 0
for key, cat in CATS.items():
    print(cat)
    for t in TOOLS.values():
        if t.cat != key:
            continue
        miss = missing(t)
        ok += not miss
        print(f"   {'✅' if not miss else '❌'} {t.label}" + (f"  ← ينقصها: {', '.join(miss)}" if miss else ""))
print(f"\nالأدوات الجاهزة: {ok}/{len(TOOLS)}")
if ok < len(TOOLS):
    print("ملاحظة: الأدوات الناقصة تُخفى تلقائياً من أزرار البوت ولا تسبب أي خطأ.")
