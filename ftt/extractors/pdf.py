from __future__ import annotations

from pathlib import Path
from typing import List

from ftt.extractors.base import ExtractedContent, ImageRef
from ftt.logging_utils import FileLogger
from ftt.render import render_pdf_pages


def _should_render_page(page, visual_mode: str, text_threshold: int) -> bool:
    if visual_mode == "full":
        return True
    if visual_mode == "embedded":
        return False
    text = page.extract_text() or ""
    has_images = len(page.images) > 0
    vector_count = len(page.rects) + len(page.curves) + len(page.lines)
    low_text = len(text.strip()) < text_threshold
    return has_images or (vector_count > 0 and low_text)


def extract_pdf(
    path: Path,
    visual_mode: str,
    render_dpi: int,
    render_max_pages: int,
    max_pages_per_file: int,
    text_threshold: int,
    visuals_dir: Path,
    logger: FileLogger,
) -> ExtractedContent:
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError("pdfplumber is required for PDF extraction") from exc

    content = ExtractedContent()
    pages_to_render: List[int] = []

    with pdfplumber.open(str(path)) as pdf:
        total_pages = len(pdf.pages)
        content.metadata["page_count"] = total_pages
        for index, page in enumerate(pdf.pages[:max_pages_per_file], start=1):
            text = page.extract_text() or ""
            if text.strip():
                content.text_parts.append(f"[Page {index}]\n{text}")
            if _should_render_page(page, visual_mode, text_threshold):
                pages_to_render.append(index)
        if total_pages > max_pages_per_file:
            logger.warning("Max pages per file reached; remaining pages skipped")

    if pages_to_render:
        pages_to_render = pages_to_render[:render_max_pages]
        logger.info(f"Rendering {len(pages_to_render)} PDF pages")
        image_paths = render_pdf_pages(path, visuals_dir, pages_to_render, render_dpi, logger)
        for image_path in image_paths:
            page_num = int(image_path.stem.split("_")[-1])
            content.images.append(ImageRef(path=image_path, label=f"page {page_num}", source="pdf"))

    return content
