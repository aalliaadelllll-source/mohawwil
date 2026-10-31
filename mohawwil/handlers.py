"""معالجات البوت: القوائم، استقبال الملفات، التحويل، لوحة الأدمن."""
from __future__ import annotations

import asyncio
import logging
import re
import shutil
import time
import zipfile
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, Message

import config
import db
import keyboards as kb
import texts
from converters import CATS, TOOLS, Tool, is_available, missing

router = Router()
log = logging.getLogger(__name__)
TMP = Path("tmp")
SEM = asyncio.Semaphore(config.MAX_CONCURRENT)   # يحمي السيرفر من ازدحام التحويلات
_busy: set[int] = set()                          # مستخدمون لديهم تحويل جارٍ

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff", ".tif"}
AUD_EXT = {".mp3", ".wav", ".ogg", ".oga", ".m4a", ".flac", ".aac", ".opus"}
VID_EXT = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".3gp"}


class St(StatesGroup):
    waiting = State()


# ───────────────────────────── أدوات مساعدة ─────────────────────────────
def _safe(name: str) -> str:
    return re.sub(r"[^\w.\-]", "_", Path(name).name, flags=re.UNICODE)[:80] or "file"


def detect(m: Message):
    """يرجع (النوع, file_id, الحجم, الاسم) أو None."""
    if m.photo:
        p = m.photo[-1]
        return "image", p.file_id, p.file_size or 0, f"{p.file_unique_id}.jpg"
    if m.document:
        d = m.document
        name = d.file_name or d.file_unique_id
        ext = Path(name).suffix.lower()
        if ext in IMG_EXT:
            kind = "image"
        elif ext in AUD_EXT:
            kind = "audio"
        elif ext in VID_EXT:
            kind = "video"
        elif ext == ".pdf":
            kind = "pdf"
        elif ext in (".docx", ".doc"):
            kind = "docx"
        else:
            kind = "other"
        return kind, d.file_id, d.file_size or 0, name
    if m.audio:
        a = m.audio
        return "audio", a.file_id, a.file_size or 0, a.file_name or f"{a.file_unique_id}.mp3"
    if m.voice:
        v = m.voice
        return "audio", v.file_id, v.file_size or 0, f"{v.file_unique_id}.ogg"
    if m.video:
        v = m.video
        return "video", v.file_id, v.file_size or 0, v.file_name or f"{v.file_unique_id}.mp4"
    if m.video_note:
        v = m.video_note
        return "video", v.file_id, v.file_size or 0, f"{v.file_unique_id}.mp4"
    return None


async def cleanup(state: FSMContext) -> None:
    data = await state.get_data()
    if data.get("work"):
        shutil.rmtree(data["work"], ignore_errors=True)
    await state.clear()


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n}B"


async def safe_edit(msg: Message, text: str, markup=None) -> None:
    """تعديل رسالة مع تجاهل خطأ «لم يتغير شيء»."""
    try:
        await msg.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as e:
        if "not modified" not in str(e).lower():
            log.warning("edit failed: %s", e)


async def remaining(uid: int) -> str:
    if uid in config.ADMIN_IDS:
        return "∞"
    return str(max(0, config.DAILY_LIMIT - await db.used_today(uid)))


# ───────────────────────────── الأوامر ─────────────────────────────
@router.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await cleanup(state)
    await db.add_user(m.from_user.id, m.from_user.full_name)
    await m.answer(texts.WELCOME.format(name=m.from_user.first_name), reply_markup=kb.main_menu())


@router.message(Command("help"))
async def help_cmd(m: Message):
    await m.answer(texts.HELP, reply_markup=kb.back_kb())


@router.message(Command("me"))
async def me_cmd(m: Message):
    await m.answer(await _me_text(m.from_user.id), reply_markup=kb.back_kb())


async def _me_text(uid: int) -> str:
    used = await db.used_today(uid)
    return texts.ME.format(
        used=used,
        limit="∞" if uid in config.ADMIN_IDS else config.DAILY_LIMIT,
        left=await remaining(uid),
        total=await db.user_totals(uid),
    )


@router.message(Command("cancel"))
async def cancel_cmd(m: Message, state: FSMContext):
    await cleanup(state)
    await m.answer(texts.CANCELLED, reply_markup=kb.main_menu())


@router.message(Command("admin"))
async def admin_cmd(m: Message):
    if m.from_user.id not in config.ADMIN_IDS:
        return
    s = await db.stats()
    top = "\n".join(f"• {TOOLS[t].label if t in TOOLS else t}: {n}" for t, n in s["top"]) or "—"
    off_lines = [f"• {t.label} ← ينقصها: {', '.join(missing(t))}" for t in TOOLS.values() if missing(t)]
    off = ("⚠️ <b>أدوات معطلة على هذا السيرفر:</b>\n" + "\n".join(off_lines) + "\n\n") if off_lines else ""
    await m.answer(
        "📊 <b>لوحة الإدارة</b>\n━━━━━━━━━━━━━━━━\n"
        f"👥 المستخدمون: <b>{s['users']}</b>\n"
        f"🔄 كل التحويلات: <b>{s['total']}</b>\n"
        f"📅 اليوم: <b>{s['today']}</b>\n\n"
        f"🏆 الأكثر استخداماً:\n{top}\n\n"
        f"🧩 الأدوات الجاهزة: <b>{sum(is_available(t) for t in TOOLS.values())}/{len(TOOLS)}</b>\n"
        f"{off}"
        "للإذاعة: <code>/broadcast نص الرسالة</code>"
    )


@router.message(Command("broadcast"))
async def broadcast_cmd(m: Message, command: CommandObject, bot: Bot):
    if m.from_user.id not in config.ADMIN_IDS:
        return
    if not command.args:
        await m.answer("اكتب الرسالة بعد الأمر.")
        return
    ok = bad = 0
    for uid in await db.all_user_ids():
        try:
            await bot.send_message(uid, command.args, parse_mode=None)
            ok += 1
        except Exception:
            bad += 1
        await asyncio.sleep(0.05)
    await m.answer(f"📣 أُرسلت إلى {ok} مستخدم (فشل {bad}).")


# ───────────────────────────── القوائم ─────────────────────────────
@router.callback_query(F.data == "menu")
async def cb_menu(cb: CallbackQuery, state: FSMContext):
    await cleanup(state)
    await safe_edit(cb.message, texts.MENU, kb.main_menu())
    await cb.answer()


@router.callback_query(F.data == "help")
async def cb_help(cb: CallbackQuery):
    await safe_edit(cb.message, texts.HELP, kb.back_kb())
    await cb.answer()


@router.callback_query(F.data == "me")
async def cb_me(cb: CallbackQuery):
    await safe_edit(cb.message, await _me_text(cb.from_user.id), kb.back_kb())
    await cb.answer()


@router.callback_query(F.data.startswith("cat:"))
async def cb_cat(cb: CallbackQuery):
    cat = cb.data.split(":", 1)[1]
    if cat not in CATS:
        return await cb.answer()
    await safe_edit(cb.message, texts.CAT_TITLE.format(cat=CATS[cat]), kb.cat_menu(cat))
    await cb.answer()


@router.callback_query(F.data.startswith("tool:"))
async def cb_tool(cb: CallbackQuery, state: FSMContext):
    key = cb.data.split(":", 1)[1]
    tool = TOOLS.get(key)
    if not tool or not is_available(tool):
        return await cb.answer("هذه الأداة غير متاحة على السيرفر حالياً.", show_alert=True)
    await cleanup(state)
    work = TMP / f"{cb.from_user.id}_{int(time.time())}"
    work.mkdir(parents=True, exist_ok=True)
    await state.set_state(St.waiting)
    await state.update_data(tool=key, work=str(work), files=[])
    await safe_edit(
        cb.message, texts.ASK.format(label=f"<b>{tool.label}</b>", hint=tool.hint), kb.cancel_kb()
    )
    await cb.answer()


@router.callback_query(F.data == "cancel")
async def cb_cancel(cb: CallbackQuery, state: FSMContext):
    await cleanup(state)
    await safe_edit(cb.message, texts.CANCELLED, kb.main_menu())
    await cb.answer()


@router.callback_query(St.waiting, F.data == "done")
async def cb_done(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("files"):
        return await cb.answer(texts.EMPTY_DONE, show_alert=True)
    await cb.answer()
    await run_tool(cb.message, cb.from_user.id, state, TOOLS[data["tool"]], data["files"], None)


# ───────────────────────────── استقبال المدخلات ─────────────────────────────
@router.message(St.waiting)
async def on_input(m: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    tool = TOOLS[data["tool"]]

    if tool.text:
        if not m.text:
            return await m.answer(texts.NEED_TEXT)
        if len(m.text) > 8000:
            return await m.answer(texts.TEXT_LONG)
        return await run_tool(m, m.from_user.id, state, tool, [], m.text)

    info = detect(m)
    if not info:
        return await m.answer(texts.WRONG_INPUT)
    kind, file_id, size, name = info
    if "any" not in tool.accept and kind not in tool.accept:
        need = "، ".join(texts.KIND_NAMES.get(k, k) for k in tool.accept)
        return await m.answer(texts.WRONG_KIND.format(need=need))
    if size > config.MAX_FILE_MB * 1024 * 1024:
        return await m.answer(texts.TOO_LARGE)

    files: list[str] = data.get("files", [])
    if tool.multi and len(files) >= config.MAX_MULTI:
        return await m.answer(texts.TOO_MANY, reply_markup=kb.done_kb())

    inp = Path(data["work"]) / "in"
    inp.mkdir(parents=True, exist_ok=True)
    dest = inp / f"{len(files)}_{_safe(name)}"
    try:
        await bot.download(file_id, destination=dest)
    except Exception:
        log.exception("download failed")
        return await m.answer(texts.DOWNLOAD_FAIL)
    files.append(str(dest))
    await state.update_data(files=files)

    if tool.multi:
        await m.answer(texts.GOT.format(n=len(files)), reply_markup=kb.done_kb())
    else:
        await run_tool(m, m.from_user.id, state, tool, files, None)


@router.callback_query(F.data == "done")
async def cb_done_expired(cb: CallbackQuery):
    await cb.answer(texts.EXPIRED, show_alert=True)


# ───────────────────────────── وضع الإرسال المباشر ─────────────────────────────
@router.message(F.document | F.photo | F.audio | F.voice | F.video | F.video_note)
async def on_direct_file(m: Message, state: FSMContext):
    """المستخدم أرسل ملفاً بدون اختيار قسم: نقترح عليه التحويلات المناسبة."""
    info = detect(m)
    if not info:
        return
    kind, file_id, size, name = info
    if size > config.MAX_FILE_MB * 1024 * 1024:
        return await m.answer(texts.TOO_LARGE)
    markup = kb.quick_menu(kind)
    if markup is None:
        return await m.answer(texts.QUICK_NONE, reply_markup=kb.main_menu())
    await cleanup(state)
    await state.update_data(quick=[kind, file_id, size, name])
    await m.answer(
        texts.QUICK.format(kind=texts.KIND_NAMES.get(kind, kind), size=human_size(size)),
        reply_markup=markup,
    )


@router.callback_query(F.data.startswith("q:"))
async def cb_quick(cb: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    quick = data.get("quick")
    tool = TOOLS.get(cb.data.split(":", 1)[1])
    if not quick or not tool or not is_available(tool):
        return await cb.answer(texts.EXPIRED, show_alert=True)
    await cb.answer()
    _, file_id, _, name = quick
    work = TMP / f"{cb.from_user.id}_{int(time.time())}"
    inp = work / "in"
    inp.mkdir(parents=True, exist_ok=True)
    dest = inp / f"0_{_safe(name)}"
    await state.update_data(tool=tool.key, work=str(work), files=[str(dest)], quick=None)
    try:
        await bot.download(file_id, destination=dest)
    except Exception:
        log.exception("download failed")
        await safe_edit(cb.message, texts.DOWNLOAD_FAIL, kb.again_kb())
        return await cleanup(state)
    await cb.message.delete()
    await run_tool(cb.message, cb.from_user.id, state, tool, [str(dest)], None)


@router.message(F.text & ~F.text.startswith("/"))
async def on_stray_text(m: Message):
    await m.answer(texts.HINT_MENU, reply_markup=kb.main_menu())


# ───────────────────────────── التنفيذ ─────────────────────────────
async def run_tool(
    msg: Message, uid: int, state: FSMContext, tool: Tool, files: list[str], text: str | None
) -> None:
    data = await state.get_data()
    work = Path(data["work"])

    if uid in _busy:
        await msg.answer(texts.BUSY)
        return
    if not await db.allowed(uid):
        await msg.answer(texts.LIMIT.format(n=config.DAILY_LIMIT), reply_markup=kb.back_kb())
        await cleanup(state)
        return

    _busy.add(uid)
    status = await msg.answer(texts.working(0, 0))
    out_dir = work / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    try:
        async with SEM:
            job = asyncio.create_task(
                asyncio.wait_for(
                    asyncio.to_thread(tool.run, [Path(f) for f in files], out_dir, text),
                    timeout=300,
                )
            )
            i = 0
            while not job.done():          # شريط تقدم متحرك أثناء التحويل
                await asyncio.wait({job}, timeout=2)
                if job.done():
                    break
                i += 1
                await safe_edit(status, texts.working(i, int(time.monotonic() - t0)))
            outs = job.result()
        if not outs:
            raise RuntimeError("no output")
        if len(outs) > 1:
            z = out_dir / "result.zip"
            with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
                for o in outs:
                    zf.write(o, arcname=o.name)
            outs = [z]
        result = outs[0]
        size = result.stat().st_size
        if size > config.MAX_SEND_MB * 1024 * 1024:
            await safe_edit(status, texts.TOO_BIG, kb.again_kb())
            return
        await db.bump(uid, tool.key)
        await status.delete()
        await msg.answer_document(
            FSInputFile(result),
            caption=texts.DONE.format(
                label=tool.label,
                size=human_size(size),
                secs=int(time.monotonic() - t0),
                left=await remaining(uid),
            ),
            reply_markup=kb.again_kb(),
        )
    except asyncio.TimeoutError:
        await safe_edit(status, texts.TIMEOUT, kb.again_kb())
    except Exception:
        log.exception("conversion failed: %s", tool.key)
        await safe_edit(status, texts.FAIL, kb.again_kb())
    finally:
        _busy.discard(uid)
        await cleanup(state)
