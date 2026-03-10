from __future__ import annotations

from pathlib import Path
from typing import List

from ftt.extractors.base import ExtractedContent, ImageRef
from ftt.logging_utils import FileLogger
from ftt.render import convert_office_to_pdf, render_pdf_pages


def _office_enabled(mode: str) -> bool:
    return mode.lower() == "true"


def extract_docx(
    path: Path,
    visual_mode: str,
    render_office_mode: str,
    render_dpi: int,
    render_max_pages: int,
    visuals_dir: Path,
    work_dir: Path,
    logger: FileLogger,
) -> ExtractedContent:
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError("python-docx is required for DOCX extraction") from exc

    content = ExtractedContent()
    document = Document(str(path))
    for paragraph in document.paragraphs:
        if paragraph.text.strip():
            content.text_parts.append(paragraph.text)

    image_count = 0
    for rel in document.part.related_parts.values():
        if not hasattr(rel, "content_type"):
            continue
        if rel.content_type.startswith("image/"):
            image_count += 1
            suffix = Path(getattr(rel, "partname", "")).suffix or ".bin"
            image_path = visuals_dir / f"docx_image_{image_count:04d}{suffix}"
            image_path.write_bytes(rel.blob)
            content.images.append(ImageRef(path=image_path, label=f"image {image_count}", source="docx"))

    if visual_mode != "embedded" and _office_enabled(render_office_mode):
        try:
            pdf_path = convert_office_to_pdf(path, work_dir, logger)
            try:
                import pdfplumber
            except ImportError as exc:
                raise RuntimeError("pdfplumber is required for DOCX rendering") from exc
            with pdfplumber.open(str(pdf_path)) as pdf:
                total_pages = len(pdf.pages)
            pages = list(range(1, min(total_pages, render_max_pages) + 1))
            logger.info(f"Rendering {len(pages)} DOCX pages for visuals")
            image_paths = render_pdf_pages(pdf_path, visuals_dir, pages, render_dpi, logger)
            for image_path in image_paths:
                page_num = int(image_path.stem.split("_")[-1])
                content.images.append(ImageRef(path=image_path, label=f"page {page_num}", source="docx"))
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"DOCX visual rendering skipped: {exc}")

    return content
