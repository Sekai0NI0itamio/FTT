from __future__ import annotations

from ftt.extractors.docx import extract_docx
from ftt.extractors.image import extract_image
from ftt.extractors.pdf import extract_pdf
from ftt.extractors.pptx import extract_pptx
from ftt.extractors.xlsx import extract_xlsx

EXTRACTOR_MAP = {
    "pdf": extract_pdf,
    "docx": extract_docx,
    "pptx": extract_pptx,
    "xlsx": extract_xlsx,
    "image": extract_image,
}
