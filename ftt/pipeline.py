from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from ftt.discovery import detect_file_type
from ftt.extractors import EXTRACTOR_MAP
from ftt.extractors.base import ExtractedContent, ImageRef
from ftt.chart_utils import build_python_script
from ftt.deplot import DeplotExtractor
from ftt.image_utils import normalize_image
from ftt.ocr import extract_text as ocr_extract, is_tesseract_available
from ftt.logging_utils import FileLogger
from ftt.utils import safe_name


@dataclass
class FileResult:
    file: str
    status: str
    size_bytes: int
    processing_time_sec: float
    transcript_path: Optional[str]
    error: Optional[str]


def _office_mode_for(config: Dict, file_type: str) -> str:
    mode = str(config["render"]["office"]).lower()
    if mode == "auto":
        if file_type in {"pptx", "xlsx"}:
            return "true"
        return "false"
    return mode


def _call_extractor(
    file_type: str,
    path: Path,
    config: Dict,
    visuals_dir: Path,
    work_dir: Path,
    logger: FileLogger,
) -> ExtractedContent:
    visual_mode = config["visual"]["mode"]
    render_dpi = config["render"]["dpi"]
    render_max_pages = config["render"]["max_pages"]
    text_threshold = config["visual"]["text_threshold"]
    render_office_mode = _office_mode_for(config, file_type)
    max_pages_per_file = config["limits"]["max_pages_per_file"]

    extractor = EXTRACTOR_MAP[file_type]
    if file_type == "pdf":
        return extractor(
            path,
            visual_mode,
            render_dpi,
            render_max_pages,
            max_pages_per_file,
            text_threshold,
            visuals_dir,
            logger,
        )
    if file_type == "docx":
        return extractor(
            path,
            visual_mode,
            render_office_mode,
            render_dpi,
            render_max_pages,
            visuals_dir,
            work_dir,
            logger,
        )
    if file_type == "pptx":
        return extractor(
            path,
            visual_mode,
            render_office_mode,
            render_dpi,
            render_max_pages,
            visuals_dir,
            work_dir,
            logger,
        )
    if file_type == "xlsx":
        return extractor(
            path,
            visual_mode,
            render_office_mode,
            render_dpi,
            render_max_pages,
            visuals_dir,
            work_dir,
            logger,
        )
    if file_type == "image":
        return extractor(path, visuals_dir, logger)
    raise ValueError(f"Unsupported file type: {file_type}")


def _retry_transcribe(vision_backend, image_path: Path, prompt: str, max_tokens: int, retries: int) -> str:
    last_error = None
    for _ in range(retries + 1):
        try:
            return vision_backend.transcribe(image_path, prompt, max_tokens)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(1)
    raise RuntimeError(str(last_error))


def process_file(
    path: Path,
    config: Dict,
    vision_backend,
    vision_pool,
    output_root: Path,
    deplot_pool,
    deplot_extractor: DeplotExtractor | None,
) -> FileResult:
    start_time = time.time()
    file_type = detect_file_type(path)
    size_bytes = path.stat().st_size
    safe = safe_name(path)
    file_dir = output_root / "files" / safe
    visuals_dir = file_dir / "visuals"
    work_dir = file_dir / "work"
    log_path = file_dir / "logs" / "steps.log"
    logger = FileLogger(log_path, config["logging"]["level"])

    file_dir.mkdir(parents=True, exist_ok=True)
    meta_path = file_dir / "meta.json"
    if not meta_path.exists():
        import json

        meta_path.write_text(json.dumps({"file": path.name}), encoding="utf-8")

    transcript_path = file_dir / "transcript.txt"

    try:
        if file_type is None:
            raise ValueError("Unsupported file type")
        if size_bytes > config["limits"]["max_file_mb"] * 1024 * 1024:
            raise ValueError("File exceeds max size limit")

        logger.info(f"Processing {path.name} as {file_type}")
        content = _call_extractor(file_type, path, config, visuals_dir, work_dir, logger)

        text_prompt = config["vision"].get("text_prompt") or config["vision"]["prompt_template"]
        description_prompt = config["vision"].get("description_prompt") or config["vision"]["prompt_template"]
        max_tokens = config["vision"]["max_tokens"]
        retries = config["vision"].get("retries", 2)
        max_images = config["limits"]["max_images_per_file"]
        keep_visuals = config["logging"]["keep_visuals"]
        enable_text = bool(config["processing"]["enable_text"])
        enable_description = bool(config["processing"]["enable_description"])
        enable_deplot = bool(config["processing"]["enable_deplot"])
        deplot_enabled = enable_deplot and bool(config["deplot"]["enabled"]) and deplot_extractor is not None
        ocr_requested = bool(config["ocr"]["enabled"])
        ocr_enabled = ocr_requested and is_tesseract_available()
        if ocr_requested and not ocr_enabled:
            logger.warning("Tesseract not found; falling back to vision-based text extraction.")
        ocr_lang = config["ocr"]["lang"]

        visual_outputs: List[str] = []
        for index, image_ref in enumerate(content.images[:max_images], start=1):
            logger.info(f"Transcribing visual {index}/{min(len(content.images), max_images)}")
            normalized = normalize_image(image_ref.path, visuals_dir, config["visual"]["max_dim"])
            tasks = {}
            if enable_text:
                if ocr_enabled:
                    tasks["text"] = vision_pool.submit(ocr_extract, image_ref.path, ocr_lang)
                else:
                    tasks["text"] = vision_pool.submit(
                        _retry_transcribe, vision_backend, normalized, text_prompt, max_tokens, retries
                    )
            if enable_description:
                tasks["description"] = vision_pool.submit(
                    _retry_transcribe, vision_backend, normalized, description_prompt, max_tokens, retries
                )
            if deplot_enabled and deplot_pool is not None:
                tasks["deplot"] = deplot_pool.submit(deplot_extractor.extract, normalized)

            results = {}
            for name, future in tasks.items():
                try:
                    results[name] = future.result()
                except Exception as exc:  # noqa: BLE001
                    logger.error(f"{name} extraction failed: {exc}")
                    results[name] = f"ERROR: {exc}"
            sections = [f"[Visual {index} - {image_ref.label}]"]
            if enable_text:
                label = "Text (OCR)" if ocr_enabled else "Text (Vision)"
                sections.append(f"{label}:\n" + results.get("text", ""))
            if enable_description:
                sections.append("Description (Vision):\n" + results.get("description", ""))
            if "deplot" in results:
                deplot_text = results["deplot"].strip()
                if deplot_text and deplot_text.upper() != "NO_CHART":
                    sections.append("Chart Data (DePlot):\n" + deplot_text)
                    sections.append("Chart Python Script:\n" + build_python_script(deplot_text))
                else:
                    sections.append("Chart Data (DePlot): NO_CHART")
            visual_outputs.append("\n".join(sections))

        if len(content.images) > max_images:
            logger.warning("Max images per file reached; remaining images skipped")

        transcript_sections = []
        if content.text_parts and enable_text:
            transcript_sections.append("Text:\n" + "\n".join(content.text_parts))
        if visual_outputs:
            transcript_sections.append("Visuals:\n" + "\n\n".join(visual_outputs))
        if not transcript_sections:
            transcript_sections.append("No text or visuals extracted.")

        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        transcript_path.write_text("\n\n".join(transcript_sections).strip() + "\n", encoding="utf-8")

        if not keep_visuals:
            for item in visuals_dir.glob("*"):
                try:
                    item.unlink()
                except Exception:
                    pass

        status = "success"
        error = None
    except Exception as exc:  # noqa: BLE001
        logger.error(str(exc))
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        transcript_path.write_text(f"Error processing file: {exc}\n", encoding="utf-8")
        status = "error"
        error = str(exc)

    logger.close()
    elapsed = time.time() - start_time
    return FileResult(
        file=path.name,
        status=status,
        size_bytes=size_bytes,
        processing_time_sec=elapsed,
        transcript_path=str(transcript_path),
        error=error,
    )
