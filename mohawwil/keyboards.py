"""لوحات الأزرار — تعرض فقط الأدوات الجاهزة على هذا السيرفر."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from converters import CATS, TOOLS, is_available


def main_menu() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for key, label in CATS.items():
        if any(t.cat == key and is_available(t) for t in TOOLS.values()):
            b.button(text=label, callback_data=f"cat:{key}")
    b.adjust(2)
    b.row(
        InlineKeyboardButton(text="📊 حسابي", callback_data="me"),
        InlineKeyboardButton(text="ℹ️ المساعدة", callback_data="help"),
    )
    return b.as_markup()


def cat_menu(cat: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for t in TOOLS.values():
        if t.cat == cat and is_available(t):
            b.button(text=t.label, callback_data=f"tool:{t.key}")
    b.adjust(2)
    b.row(InlineKeyboardButton(text="🔙 رجوع", callback_data="menu"))
    return b.as_markup()


def quick_menu(kind: str) -> InlineKeyboardMarkup | None:
    """اقتراحات فورية لملف أُرسل مباشرة (أدوات الملف الواحد فقط)."""
    tools = [
        t for t in TOOLS.values()
        if kind in t.accept and not t.multi and not t.text and is_available(t)
    ]
    if not tools:
        return None
    b = InlineKeyboardBuilder()
    for t in tools:
        b.button(text=t.label, callback_data=f"q:{t.key}")
    b.adjust(2)
    b.row(InlineKeyboardButton(text="🛑 إلغاء", callback_data="cancel"))
    return b.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🛑 إلغاء", callback_data="cancel")
    return b.as_markup()


def done_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ تم — ابدأ التحويل", callback_data="done")
    b.button(text="🛑 إلغاء", callback_data="cancel")
    b.adjust(1)
    return b.as_markup()


def again_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🔄 تحويل آخر", callback_data="menu")
    return b.as_markup()


def back_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🔙 القائمة", callback_data="menu")
    return b.as_markup()
