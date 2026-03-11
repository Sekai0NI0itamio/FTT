from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

from ftt.config import load_config
from ftt.deplot import DeplotExtractor
from ftt.discovery import discover_files
from ftt.logging_utils import FileLogger
from ftt.merger import write_combined_transcripts
from ftt.ocr import extract_text as ocr_extract, is_tesseract_available
from ftt.pipeline import process_file
from ftt.summary import write_summary_json, write_summary_md
from ftt.vision import build_backend


def _safe_name(name: str) -> str:
    return name.replace("/", "_").replace(" ", "_")


def _load_project_dir(project_path: Path) -> Path:
    if project_path.is_dir():
        return project_path
    if project_path.suffix.lower() == ".zip":
        tmp = Path(tempfile.mkdtemp(prefix="ftt-project-"))
        shutil.unpack_archive(str(project_path), tmp)
        return tmp
    raise ValueError("Project must be a directory or zip")


def _discover_regions(project_dir: Path) -> List[Dict]:
    regions_dir = project_dir / "regions"
    if not regions_dir.exists():
        return []
    items: List[Dict] = []
    for pen in ("tesseract", "describe", "graph"):
        pen_dir = regions_dir / pen
        if not pen_dir.exists():
            continue
        for path in sorted(pen_dir.glob("*")):
            if path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
                continue
            items.append({"pen": pen, "path": path})
    return items


def _load_status_tags(project_dir: Path) -> Dict[str, List[str]]:
    """Parse status.tag to learn which extraction methods to use for each file."""
    status_path = project_dir / "status.tag"
    tags: Dict[str, List[str]] = {}
    if not status_path.exists():
        return tags
    for line in status_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        name, _, raw_tags = line.partition(":")
        file_tags = [t.strip() for t in raw_tags.split(",") if t.strip() and t.strip() != "none"]
        tags[name.strip()] = file_tags
    return tags


def _load_project_json(project_dir: Path) -> Optional[Dict]:
    path = project_dir / "project.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _process_region(
    region: Dict,
    config: Dict,
    vision_backend,
    deplot_extractor: DeplotExtractor | None,
    output_dir: Path,
) -> Dict:
    pen = region["pen"]
    path: Path = region["path"]
    logger = FileLogger(output_dir / "logs" / f"{_safe_name(path.name)}.log", config["logging"]["level"])
    start = time.time()
    try:
        text_prompt = config["vision"].get("text_prompt") or config["vision"]["prompt_template"]
        description_prompt = config["vision"].get("description_prompt") or config["vision"]["prompt_template"]
        max_tokens = config["vision"]["max_tokens"]
        retries = config["vision"].get("retries", 2)

        def retry_call(prompt: str) -> str:
            last_error: Exception | None = None
            for _ in range(retries + 1):
                try:
                    return vision_backend.transcribe(path, prompt, max_tokens)
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
            raise RuntimeError(str(last_error))

        if pen == "tesseract":
            if is_tesseract_available():
                output = ocr_extract(path, config["ocr"]["lang"])
            else:
                output = retry_call(text_prompt)
        elif pen == "describe":
            output = retry_call(description_prompt)
        else:
            if deplot_extractor is None:
                output = retry_call(description_prompt)
            else:
                output = deplot_extractor.extract(path)

        output_dir.mkdir(parents=True, exist_ok=True)
        transcript_path = output_dir / f"{path.stem}.txt"
        transcript_path.write_text(output.strip() + "\n", encoding="utf-8")
        status = "success"
        error = None
    except Exception as exc:  # noqa: BLE001
        transcript_path = output_dir / f"{path.stem}.txt"
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        transcript_path.write_text(f"Error processing region: {exc}\n", encoding="utf-8")
        status = "error"
        error = str(exc)
    finally:
        logger.close()

    return {
        "file": f"region:{pen}:{path.name}",
        "status": status,
        "size_bytes": path.stat().st_size,
        "processing_time_sec": time.time() - start,
        "transcript_path": str(transcript_path),
        "error": error,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="FTT Transformer Project runner")
    parser.add_argument("--project", required=True, help="Path to FTT Transformer export (dir or zip)")
    parser.add_argument("--config", default="ftt.yml", help="Path to config file")
    parser.add_argument("--output", default="output", help="Output directory")
    args = parser.parse_args()

    config = load_config(Path(args.config))
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    project_dir = _load_project_dir(Path(args.project))
    uploads_dir = project_dir / "uploads"

    # Load project metadata for status tags
    status_tags = _load_status_tags(project_dir)
    project_json = _load_project_json(project_dir)

    files = discover_files(uploads_dir) if uploads_dir.exists() else []
    vision_backend = build_backend(config)

    # Scale workers for maximum parallelism
    vision_workers = max(1, int(config["concurrency"]["vision_workers"]))
    file_workers = max(1, int(config["concurrency"]["file_workers"]))
    deplot_workers = max(1, int(config["concurrency"].get("deplot_workers", 1)))

    deplot_extractor = None
    if config["deplot"]["enabled"]:
        deplot_extractor = DeplotExtractor(
            model_name=config["deplot"]["model_name"],
            max_tokens=config["deplot"]["max_tokens"],
            prompt=config["deplot"]["prompt"],
            cache_dir=config["deplot"]["cache_dir"],
        )

    results: List[Dict] = []

    # ── Phase 1: files + regions — all submitted concurrently ──
    # Use shared pools so vision and deplot resources are shared
    # across both file processing and region processing.
    vision_pool = ThreadPoolExecutor(max_workers=vision_workers)
    deplot_pool = ThreadPoolExecutor(max_workers=deplot_workers)

    all_futures: Dict = {}

    # Submit file processing (each file runs extraction + vision internally)
    file_pool = ThreadPoolExecutor(max_workers=file_workers)
    for path in files:
        file_tags = status_tags.get(path.name, [])
        # Apply per-file overrides from status.tag if present
        file_config = dict(config)
        if file_tags:
            processing = dict(config["processing"])
            ocr_cfg = dict(config["ocr"])
            # Enable/disable based on tags
            processing["enable_text"] = "tesseract" in file_tags or "python" in file_tags
            ocr_cfg["enabled"] = "tesseract" in file_tags
            file_config = {**config, "processing": processing, "ocr": ocr_cfg}

        future = file_pool.submit(
            process_file,
            path,
            file_config,
            vision_backend,
            vision_pool,
            output_dir,
            deplot_pool,
            deplot_extractor,
        )
        all_futures[future] = ("file", path)

    # Submit region processing concurrently alongside file processing
    region_items = _discover_regions(project_dir)
    region_output_dir = output_dir / "regions"
    region_pool = ThreadPoolExecutor(max_workers=max(2, vision_workers))

    for region in region_items:
        future = region_pool.submit(
            _process_region,
            region,
            config,
            vision_backend,
            deplot_extractor,
            region_output_dir / region["pen"],
        )
        all_futures[future] = ("region", region)

    # ── Collect all results ──
    for future in as_completed(all_futures):
        kind, _item = all_futures[future]
        try:
            result = future.result()
            if kind == "file":
                results.append(result.__dict__)
            else:
                results.append(result)
        except Exception as exc:  # noqa: BLE001
            name = _item.name if hasattr(_item, "name") else str(_item)
            results.append({
                "file": name,
                "status": "error",
                "size_bytes": 0,
                "processing_time_sec": 0,
                "transcript_path": None,
                "error": str(exc),
            })

    # Shutdown all pools
    file_pool.shutdown(wait=False)
    region_pool.shutdown(wait=False)
    vision_pool.shutdown(wait=True)
    deplot_pool.shutdown(wait=True)

    # ── Write combined outputs ──
    write_summary_json(results, output_dir / "summary.json")
    write_summary_md(results, output_dir / "summary.md")
    write_combined_transcripts(results, output_dir / "all_transcripts.txt")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
