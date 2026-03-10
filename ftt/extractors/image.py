from __future__ import annotations

import shutil
from pathlib import Path

from ftt.extractors.base import ExtractedContent, ImageRef
from ftt.logging_utils import FileLogger


def extract_image(path: Path, visuals_dir: Path, logger: FileLogger) -> ExtractedContent:
    visuals_dir.mkdir(parents=True, exist_ok=True)
    target = visuals_dir / path.name
    if path.resolve() != target.resolve():
        shutil.copy2(path, target)
    logger.info("Prepared image for vision transcription")
    content = ExtractedContent()
    content.images.append(ImageRef(path=target, label="image", source="image"))
    return content
