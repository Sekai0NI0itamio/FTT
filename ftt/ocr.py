from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image


def extract_text(image_path: Path, lang: str) -> str:
    try:
        import pytesseract
    except ImportError as exc:
        raise RuntimeError("pytesseract is required for OCR") from exc
    if not is_tesseract_available():
        raise RuntimeError("tesseract is not installed or it's not in your PATH")

    with Image.open(image_path) as img:
        img = img.convert("RGB")
        return pytesseract.image_to_string(img, lang=lang).strip()


def is_tesseract_available() -> bool:
    return shutil.which("tesseract") is not None
