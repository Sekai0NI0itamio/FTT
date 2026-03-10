from __future__ import annotations

from pathlib import Path

from PIL import Image


def extract_text(image_path: Path, lang: str) -> str:
    try:
        import pytesseract
    except ImportError as exc:
        raise RuntimeError("pytesseract is required for OCR") from exc

    with Image.open(image_path) as img:
        img = img.convert("RGB")
        return pytesseract.image_to_string(img, lang=lang).strip()
