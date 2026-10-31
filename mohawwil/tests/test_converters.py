"""اختبارات سريعة للتحويلات التي لا تحتاج برامج نظام. شغّلها بـ: python -m pytest  (أو python tests/test_converters.py)"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

from converters import TOOLS, is_available, missing  # noqa: E402


def _run(key, inputs=(), text=None):
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "out"
        out.mkdir()
        res = TOOLS[key].run([Path(p) for p in inputs], out, text)
        assert res and all(p.exists() and p.stat().st_size > 0 for p in res), key
        return [p.name for p in res]


def _img(d: Path, name="a.png") -> Path:
    p = d / name
    Image.new("RGB", (64, 48), "red").save(p)
    return p


def test_images():
    with tempfile.TemporaryDirectory() as d:
        p = _img(Path(d))
        for key in ("img_png", "img_jpg", "img_webp", "img_compress", "img_resize", "img_pdf"):
            _run(key, [p])


def test_zip():
    with tempfile.TemporaryDirectory() as d:
        _run("zip", [_img(Path(d), "0_a.png"), _img(Path(d), "1_b.png")])


def test_registry_is_consistent():
    keys = [t.key for t in TOOLS.values()]
    assert len(keys) == len(set(keys))
    for t in TOOLS.values():
        assert isinstance(missing(t), list)
        assert is_available(t) == (not missing(t))


if __name__ == "__main__":
    test_images(); test_zip(); test_registry_is_consistent()
    print("✅ كل الاختبارات نجحت")
