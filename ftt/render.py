from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterable, List

from pdf2image import convert_from_path

from ftt.logging_utils import FileLogger


def convert_office_to_pdf(input_path: Path, output_dir: Path, logger: FileLogger) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Converting to PDF via LibreOffice: {input_path.name}")
    cmd = [
        "libreoffice",
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(output_dir),
        str(input_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"LibreOffice conversion failed: {result.stderr.strip()}")
        raise RuntimeError("LibreOffice conversion failed")

    pdf_path = output_dir / f"{input_path.stem}.pdf"
    if not pdf_path.exists():
        logger.error("LibreOffice did not produce expected PDF")
        raise FileNotFoundError("Converted PDF not found")
    return pdf_path


def render_pdf_pages(
    pdf_path: Path,
    output_dir: Path,
    pages: Iterable[int],
    dpi: int,
    logger: FileLogger,
) -> List[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    image_paths: List[Path] = []
    for page_num in pages:
        logger.debug(f"Rendering page {page_num} from {pdf_path.name}")
        images = convert_from_path(
            str(pdf_path),
            dpi=dpi,
            first_page=page_num,
            last_page=page_num,
        )
        if not images:
            continue
        image = images[0]
        image_path = output_dir / f"page_{page_num:04d}.png"
        image.save(image_path)
        image_paths.append(image_path)
    return image_paths
