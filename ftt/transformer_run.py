from __future__ import annotations

import argparse
import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List

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

    files = discover_files(uploads_dir) if uploads_dir.exists() else []
    vision_backend = build_backend(config)

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

    vision_pool = ThreadPoolExecutor(max_workers=vision_workers)
    deplot_pool = ThreadPoolExecutor(max_workers=deplot_workers)
    with ThreadPoolExecutor(max_workers=file_workers) as executor:
        futures = {
            executor.submit(
                process_file,
                path,
                config,
                vision_backend,
                vision_pool,
                output_dir,
                deplot_pool,
                deplot_extractor,
            ): path
            for path in files
        }
        for future in as_completed(futures):
            result = future.result()
            results.append(result.__dict__)
    vision_pool.shutdown(wait=True)
    deplot_pool.shutdown(wait=True)

    region_items = _discover_regions(project_dir)
    region_output_dir = output_dir / "regions"
    if region_items:
        with ThreadPoolExecutor(max_workers=vision_workers) as executor:
            region_futures = {
                executor.submit(
                    _process_region,
                    region,
                    config,
                    vision_backend,
                    deplot_extractor,
                    region_output_dir / region["pen"],
                ): region
                for region in region_items
            }
            for future in as_completed(region_futures):
                results.append(future.result())

    write_summary_json(results, output_dir / "summary.json")
    write_summary_md(results, output_dir / "summary.md")
    write_combined_transcripts(results, output_dir / "all_transcripts.txt")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
