from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

SUPPORTED_TYPES = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".pptx": "pptx",
    ".xlsx": "xlsx",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".tiff": "image",
    ".tif": "image",
    ".bmp": "image",
    ".gif": "image",
}


def discover_files(input_dir: Path) -> List[Path]:
    if not input_dir.exists():
        return []
    files: Iterable[Path] = (p for p in input_dir.iterdir() if p.is_file())
    visible = [p for p in files if not p.name.startswith(".")]
    return sorted(visible)


def detect_file_type(path: Path) -> str | None:
    return SUPPORTED_TYPES.get(path.suffix.lower())
