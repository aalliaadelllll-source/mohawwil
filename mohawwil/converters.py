"""كل أدوات التحويل + سجل الأدوات (TOOLS) الذي تبني منه الواجهة أزرارها."""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

from PIL import Image, ImageOps

Image.MAX_IMAGE_PIXELS = 50_000_000  # حماية من القنابل الصورية

Runner = Callable[[list[Path], Path, "str | None"], list[Path]]


# ───────────────────────────── أدوات مساعدة ─────────────────────────────
def _has_arabic(s: str) -> bool:
    return any("\u0600" <= ch <= "\u06FF" for ch in s)


def _ffmpeg(args: list[str]) -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg غير مثبت")
    r = subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args],
        capture_output=True,
        timeout=280,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode(errors="ignore")[-300:])


_FONT_NAME: str | None = None


def _font() -> str:
    """يبحث عن خط يدعم العربية: fonts/Cairo أو Tajawal أو DejaVu ثم Arial."""
    global _FONT_NAME
    if _FONT_NAME:
        return _FONT_NAME
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    candidates = [
        Path("fonts/Cairo-Regular.ttf"),
        Path("fonts/Tajawal-Regular.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/Library/Fonts/Arial Unicode.ttf"),
    ]
    for f in candidates:
        if f.exists():
            pdfmetrics.registerFont(TTFont("AppFont", str(f)))
            _FONT_NAME = "AppFont"
            return _FONT_NAME
    _FONT_NAME = "Helvetica"
    return _FONT_NAME


# ───────────────────────────── الصور ─────────────────────────────
def img_convert(fmt: str) -> Runner:
    ext = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[fmt]

    def run(inputs, out_dir, text):
        outs = []
        for p in inputs:
            im = ImageOps.exif_transpose(Image.open(p))
            if fmt == "JPEG" and im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            o = out_dir / (p.stem + ext)
            im.save(o, fmt)
            outs.append(o)
        return outs

    return run


def img_to_pdf(inputs, out_dir, text):
    imgs = [ImageOps.exif_transpose(Image.open(p)).convert("RGB") for p in inputs]
    o = out_dir / "images.pdf"
    imgs[0].save(o, "PDF", save_all=True, append_images=imgs[1:])
    return [o]


def img_compress(inputs, out_dir, text):
    outs = []
    for p in inputs:
        im = ImageOps.exif_transpose(Image.open(p)).convert("RGB")
        o = out_dir / f"{p.stem}_compressed.jpg"
        im.save(o, "JPEG", quality=60, optimize=True)
        outs.append(o)
    return outs


def img_resize(inputs, out_dir, text):
    outs = []
    for p in inputs:
        im = ImageOps.exif_transpose(Image.open(p))
        im.thumbnail((1280, 1280))
        o = out_dir / f"{p.stem}_1280.png"
        im.save(o, "PNG", optimize=True)
        outs.append(o)
    return outs


# ───────────────────────────── PDF ─────────────────────────────
def pdf_to_images(inputs, out_dir, text):
    import fitz  # PyMuPDF

    doc = fitz.open(inputs[0])
    outs = []
    for i, page in enumerate(doc):
        if i >= 50:
            break
        o = out_dir / f"page_{i + 1:03d}.png"
        page.get_pixmap(dpi=150).save(o)
        outs.append(o)
    return outs


def pdf_merge(inputs, out_dir, text):
    from pypdf import PdfWriter

    w = PdfWriter()
    for p in inputs:
        w.append(str(p))
    o = out_dir / "merged.pdf"
    with open(o, "wb") as f:
        w.write(f)
    return [o]


def pdf_split(inputs, out_dir, text):
    from pypdf import PdfReader, PdfWriter

    r = PdfReader(inputs[0])
    if len(r.pages) > 100:
        raise RuntimeError("الملف أكثر من 100 صفحة")
    outs = []
    for i, page in enumerate(r.pages, 1):
        w = PdfWriter()
        w.add_page(page)
        o = out_dir / f"page_{i:03d}.pdf"
        with open(o, "wb") as f:
            w.write(f)
        outs.append(o)
    return outs


def pdf_compress(inputs, out_dir, text):
    import fitz

    doc = fitz.open(inputs[0])
    o = out_dir / f"{inputs[0].stem}_compressed.pdf"
    doc.save(o, garbage=4, deflate=True, clean=True)
    return [o]


def pdf_to_txt(inputs, out_dir, text):
    import fitz

    doc = fitz.open(inputs[0])
    content = "\n\n".join(page.get_text() for page in doc).strip()
    if not content:
        raise RuntimeError("لا يوجد نص (قد يكون ملفاً ممسوحاً ضوئياً)")
    o = out_dir / f"{inputs[0].stem}.txt"
    o.write_text(content, encoding="utf-8")
    return [o]


def pdf_to_docx(inputs, out_dir, text):
    from pdf2docx import Converter

    o = out_dir / f"{inputs[0].stem}.docx"
    cv = Converter(str(inputs[0]))
    try:
        cv.convert(str(o))
    finally:
        cv.close()
    return [o]


def docx_to_pdf(inputs, out_dir, text):
    exe = shutil.which("soffice") or shutil.which("libreoffice")
    if not exe:
        raise RuntimeError("LibreOffice غير مثبت")
    r = subprocess.run(
        [exe, "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(inputs[0])],
        capture_output=True,
        timeout=150,
    )
    o = out_dir / f"{inputs[0].stem}.pdf"
    if r.returncode != 0 or not o.exists():
        raise RuntimeError("فشل التحويل")
    return [o]


# ───────────────────────────── النصوص ─────────────────────────────
def text_to_pdf(inputs, out_dir, text):
    import arabic_reshaper
    from bidi.algorithm import get_display
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas

    def shape(s: str) -> str:
        return get_display(arabic_reshaper.reshape(s))

    font, size, lead = _font(), 14, 24
    W, H = A4
    m = 55
    maxw = W - 2 * m
    o = out_dir / "text.pdf"
    c = canvas.Canvas(str(o), pagesize=A4)
    c.setFont(font, size)
    y = H - m
    for para in text.splitlines():
        lines, cur = [], ""
        for w in para.split():
            t = (cur + " " + w).strip()
            if stringWidth(shape(t), font, size) <= maxw:
                cur = t
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
        for ln in lines:
            if y < m:
                c.showPage()
                c.setFont(font, size)
                y = H - m
            if _has_arabic(ln):
                c.drawRightString(W - m, y, shape(ln))
            else:
                c.drawString(m, y, ln)
            y -= lead
    c.save()
    return [o]


def text_to_docx(inputs, out_dir, text):
    from docx import Document
    from docx.oxml import OxmlElement

    doc = Document()
    for line in text.splitlines():
        p = doc.add_paragraph()
        r = p.add_run(line)
        if _has_arabic(line):
            p._p.get_or_add_pPr().append(OxmlElement("w:bidi"))
            r._r.get_or_add_rPr().append(OxmlElement("w:rtl"))
    o = out_dir / "text.docx"
    doc.save(o)
    return [o]


# ───────────────────────────── الصوت والفيديو ─────────────────────────────
def audio_convert(ext: str) -> Runner:
    codec = {
        ".mp3": ["-codec:a", "libmp3lame", "-b:a", "192k"],
        ".wav": ["-ar", "44100"],
        ".ogg": ["-c:a", "libopus", "-b:a", "96k"],
    }[ext]

    def run(inputs, out_dir, text):
        o = out_dir / (inputs[0].stem + ext)
        _ffmpeg(["-i", str(inputs[0]), "-vn", *codec, str(o)])
        return [o]

    return run


def video_to_mp3(inputs, out_dir, text):
    o = out_dir / (inputs[0].stem + ".mp3")
    _ffmpeg(["-i", str(inputs[0]), "-vn", "-codec:a", "libmp3lame", "-b:a", "192k", str(o)])
    return [o]


def video_to_gif(inputs, out_dir, text):
    o = out_dir / (inputs[0].stem + ".gif")
    _ffmpeg(
        ["-i", str(inputs[0]), "-t", "10", "-vf", "fps=12,scale=480:-1:flags=lanczos", str(o)]
    )
    return [o]


def video_compress(inputs, out_dir, text):
    o = out_dir / (inputs[0].stem + "_compressed.mp4")
    _ffmpeg(
        [
            "-i", str(inputs[0]),
            "-vcodec", "libx264", "-crf", "30", "-preset", "veryfast",
            "-acodec", "aac", "-b:a", "96k", str(o),
        ]
    )
    return [o]


# ───────────────────────────── أدوات أخرى ─────────────────────────────
def ocr_to_txt(inputs, out_dir, text):
    import pytesseract

    if not shutil.which("tesseract"):
        raise RuntimeError("Tesseract غير مثبت")
    content = pytesseract.image_to_string(Image.open(inputs[0]), lang="ara+eng").strip()
    if not content:
        raise RuntimeError("لم أجد نصاً في الصورة")
    o = out_dir / f"{inputs[0].stem}.txt"
    o.write_text(content, encoding="utf-8")
    return [o]


def make_qr(inputs, out_dir, text):
    import qrcode

    o = out_dir / "qr.png"
    qrcode.make(text).save(o)
    return [o]


def make_zip(inputs, out_dir, text):
    o = out_dir / "files.zip"
    with zipfile.ZipFile(o, "w", zipfile.ZIP_DEFLATED) as z:
        for p in inputs:
            z.write(p, arcname=p.name.split("_", 1)[-1])
    return [o]


# ───────────────────────────── السجل ─────────────────────────────
@dataclass(frozen=True)
class Tool:
    key: str
    label: str
    cat: str
    accept: tuple[str, ...]   # image / pdf / docx / audio / video / any
    run: Runner
    hint: str
    multi: bool = False        # عدة ملفات ثم زر «تم»
    text: bool = False         # يستقبل نصاً بدل ملف
    needs: tuple[str, ...] = ()  # متطلبات: "bin:ffmpeg" أو "bin:soffice|libreoffice" أو "py:fitz"


CATS = {
    "img": "🖼 الصور",
    "pdf": "📄 مستندات PDF",
    "txt": "📝 من نص إلى ملف",
    "aud": "🎙 الصوت",
    "vid": "🎬 الفيديو",
    "ocr": "🔍 استخراج النص",
    "misc": "🧰 أدوات أخرى",
}

_T = [
    # الصور
    Tool("img_png", "إلى PNG", "img", ("image",), img_convert("PNG"), "أرسل صورة أو أكثر (يفضّل كملف لتبقى الجودة)."),
    Tool("img_jpg", "إلى JPG", "img", ("image",), img_convert("JPEG"), "أرسل الصورة."),
    Tool("img_webp", "إلى WEBP", "img", ("image",), img_convert("WEBP"), "أرسل الصورة."),
    Tool("img_pdf", "صور ➜ PDF واحد", "img", ("image",), img_to_pdf, "أرسل الصور بالترتيب، ثم اضغط «تم».", multi=True),
    Tool("img_compress", "ضغط الصورة", "img", ("image",), img_compress, "أرسل الصورة لتصغير حجمها."),
    Tool("img_resize", "تصغير الأبعاد", "img", ("image",), img_resize, "أرسل الصورة وسأجعل أكبر بُعد فيها 1280 بكسل."),
    # PDF
    Tool("pdf_img", "PDF ➜ صور", "pdf", ("pdf",), pdf_to_images, "أرسل ملف PDF (حتى 50 صفحة).", needs=("py:fitz",)),
    Tool("pdf_merge", "دمج ملفات PDF", "pdf", ("pdf",), pdf_merge, "أرسل ملفات PDF بالترتيب، ثم اضغط «تم».", multi=True, needs=("py:pypdf",)),
    Tool("pdf_split", "تقسيم PDF لصفحات", "pdf", ("pdf",), pdf_split, "أرسل ملف PDF (حتى 100 صفحة).", needs=("py:pypdf",)),
    Tool("pdf_compress", "ضغط PDF", "pdf", ("pdf",), pdf_compress, "أرسل ملف PDF.", needs=("py:fitz",)),
    Tool("pdf_txt", "PDF ➜ نص TXT", "pdf", ("pdf",), pdf_to_txt, "أرسل ملف PDF.", needs=("py:fitz",)),
    Tool("pdf_docx", "PDF ➜ Word", "pdf", ("pdf",), pdf_to_docx, "أرسل ملف PDF.", needs=("py:pdf2docx",)),
    Tool("docx_pdf", "Word ➜ PDF", "pdf", ("docx",), docx_to_pdf, "أرسل ملف Word.", needs=("bin:soffice|libreoffice",)),
    # النصوص
    Tool("txt_pdf", "نص ➜ PDF (عربي)", "txt", ("text",), text_to_pdf, "اكتب أو الصق النص الآن.", text=True, needs=("py:reportlab", "py:arabic_reshaper", "py:bidi",)),
    Tool("txt_docx", "نص ➜ Word (عربي)", "txt", ("text",), text_to_docx, "اكتب أو الصق النص الآن.", text=True, needs=("py:docx",)),
    # الصوت
    Tool("aud_mp3", "إلى MP3", "aud", ("audio",), audio_convert(".mp3"), "أرسل ملفاً صوتياً أو رسالة صوتية.", needs=("bin:ffmpeg",)),
    Tool("aud_wav", "إلى WAV", "aud", ("audio",), audio_convert(".wav"), "أرسل ملفاً صوتياً أو رسالة صوتية.", needs=("bin:ffmpeg",)),
    Tool("aud_ogg", "إلى OGG", "aud", ("audio",), audio_convert(".ogg"), "أرسل ملفاً صوتياً.", needs=("bin:ffmpeg",)),
    # الفيديو
    Tool("vid_mp3", "فيديو ➜ صوت MP3", "vid", ("video",), video_to_mp3, "أرسل الفيديو.", needs=("bin:ffmpeg",)),
    Tool("vid_gif", "فيديو ➜ GIF", "vid", ("video",), video_to_gif, "أرسل فيديو (أول 10 ثوانٍ فقط).", needs=("bin:ffmpeg",)),
    Tool("vid_compress", "ضغط الفيديو", "vid", ("video",), video_compress, "أرسل الفيديو.", needs=("bin:ffmpeg",)),
    # OCR
    Tool("ocr_txt", "صورة ➜ نص (عربي/إنجليزي)", "ocr", ("image",), ocr_to_txt, "أرسل صورة فيها نص واضح، يفضّل كملف.", needs=("bin:tesseract", "py:pytesseract",)),
    # أخرى
    Tool("qr", "إنشاء QR", "misc", ("text",), make_qr, "أرسل النص أو الرابط.", text=True, needs=("py:qrcode",)),
    Tool("zip", "ضغط ملفات ZIP", "misc", ("any",), make_zip, "أرسل الملفات، ثم اضغط «تم».", multi=True),
]

TOOLS: dict[str, Tool] = {t.key: t for t in _T}


# ───────────────────────────── فحص الجاهزية ─────────────────────────────
@lru_cache(maxsize=None)
def _req_ok(req: str) -> bool:
    kind, _, spec = req.partition(":")
    if kind == "bin":
        return any(shutil.which(n) for n in spec.split("|"))
    if kind == "py":
        try:
            return importlib.util.find_spec(spec) is not None
        except (ImportError, ValueError):
            return False
    return True


def missing(tool: Tool) -> list[str]:
    """المتطلبات الناقصة على هذا السيرفر (قائمة فارغة = الأداة جاهزة)."""
    return [r.split(":", 1)[1] for r in tool.needs if not _req_ok(r)]


def is_available(tool: Tool) -> bool:
    return not missing(tool)
