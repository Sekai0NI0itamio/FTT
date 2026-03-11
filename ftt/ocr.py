from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image


def extract_text(image_path: Path, lang: str) -> str:
    """Extract text from an image using the best available OCR engine.

    Priority: EasyOCR (best) > pytesseract (fallback).
    """
    if _is_easyocr_available():
        return _extract_easyocr(image_path, lang)
    if is_tesseract_available():
        return _extract_tesseract(image_path, lang)
    raise RuntimeError(
        "No OCR engine available. Install easyocr (recommended) or tesseract."
    )


# ── EasyOCR (preferred) ──────────────────────────────────────────────────

_EASYOCR_LANG_MAP = {
    "eng": "en", "fra": "fr", "deu": "de", "spa": "es", "ita": "it",
    "por": "pt", "nld": "nl", "pol": "pl", "rus": "ru", "jpn": "ja",
    "chi_sim": "ch_sim", "chi_tra": "ch_tra", "kor": "ko", "ara": "ar",
}

_easyocr_reader_cache: dict = {}


def _easyocr_lang(tesseract_lang: str) -> str:
    """Convert tesseract lang code to EasyOCR lang code."""
    return _EASYOCR_LANG_MAP.get(tesseract_lang, tesseract_lang)


def _is_easyocr_available() -> bool:
    try:
        import easyocr  # noqa: F401
        return True
    except ImportError:
        return False


def _extract_easyocr(image_path: Path, lang: str) -> str:
    import easyocr

    ocr_lang = _easyocr_lang(lang)
    cache_key = ocr_lang
    if cache_key not in _easyocr_reader_cache:
        _easyocr_reader_cache[cache_key] = easyocr.Reader(
            [ocr_lang], gpu=_has_cuda()
        )
    reader = _easyocr_reader_cache[cache_key]

    with Image.open(image_path) as img:
        img = img.convert("RGB")
        import numpy as np
        img_array = np.array(img)

    results = reader.readtext(img_array, detail=0, paragraph=True)
    return "\n".join(results).strip()


def _has_cuda() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


# ── Tesseract (fallback) ─────────────────────────────────────────────────

def _extract_tesseract(image_path: Path, lang: str) -> str:
    try:
        import pytesseract
    except ImportError as exc:
        raise RuntimeError("pytesseract is required for OCR fallback") from exc

    with Image.open(image_path) as img:
        img = img.convert("RGB")
        return pytesseract.image_to_string(img, lang=lang).strip()


def is_tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def is_ocr_available() -> bool:
    """Check if any OCR engine is available."""
    return _is_easyocr_available() or is_tesseract_available()
