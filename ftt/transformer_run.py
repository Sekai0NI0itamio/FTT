from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

from ftt.config import load_config
from ftt.deplot import DeplotExtractor, MultiModelExtractor, CHART_MODELS
from ftt.discovery import discover_files
from ftt.logging_utils import FileLogger
from ftt.merger import write_combined_transcripts
from ftt.ocr import extract_text as ocr_extract, is_tesseract_available
from ftt.pipeline import process_file
from ftt.summary import write_summary_json, write_summary_md
from ftt.vision import build_backend

MODES = [
    "all",
    "discover",
    "tesseract-files",
    "python-files",
    "graph-regions",
    "tesseract-regions",
    "describe-regions",
    "bundle",
]


# ── Shared helpers ───────────────────────────────────────────────────────


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

    # Load per-region model selections if available
    graph_models_map: Dict[str, List[str]] = {}
    models_json = regions_dir / "graph" / "models.json"
    if models_json.exists():
        try:
            graph_models_map = json.loads(models_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    items: List[Dict] = []
    for pen in ("tesseract", "describe", "graph"):
        pen_dir = regions_dir / pen
        if not pen_dir.exists():
            continue
        for path in sorted(pen_dir.glob("*")):
            if path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
                continue
            region: Dict[str, Any] = {"pen": pen, "path": path}
            if pen == "graph" and path.name in graph_models_map:
                region["models"] = graph_models_map[path.name]
            items.append(region)
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


def _progress(current: int, total: int, label: str) -> None:
    """Print progress to stdout (GitHub Actions log-friendly)."""
    pct = int(current / total * 100) if total > 0 else 100
    print(f"  [{pct:3d}%] ({current}/{total}) {label}", flush=True)


def _write_results(results: List[Dict], output_dir: Path) -> None:
    """Write results.json for this mode's output."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "results.json").write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8"
    )


def _write_step_summary(title: str, results: List[Dict]) -> None:
    """Write a GitHub Actions job step summary table."""
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_file:
        return
    success = sum(1 for r in results if r.get("status") == "success")
    errors = sum(1 for r in results if r.get("status") == "error")
    lines = [
        f"### {title}",
        "",
        "| Metric | Count |",
        "|--------|-------|",
        f"| Successful | {success} |",
        f"| Errors | {errors} |",
        f"| Total | {len(results)} |",
        "",
    ]
    if errors > 0:
        lines.append("**Errors:**")
        for r in results:
            if r.get("status") == "error":
                lines.append(f"- `{r.get('file', '?')}`: {r.get('error', 'Unknown')}")
        lines.append("")
    with open(summary_file, "a") as fh:
        fh.write("\n".join(lines) + "\n")


def _set_github_output(key: str, value: str) -> None:
    """Write a key=value pair to $GITHUB_OUTPUT for job outputs."""
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as fh:
            fh.write(f"{key}={value}\n")


def _resolve_project(project_arg: str) -> Path:
    """Resolve project path, checking for zips inside directories."""
    p = Path(project_arg)
    if p.is_dir():
        zips = sorted(p.glob("*.zip"))
        if zips:
            return _load_project_dir(zips[0])
        return _load_project_dir(p)
    return _load_project_dir(p)


# ── Region processing ───────────────────────────────────────────────────


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


# ── Mode commands ────────────────────────────────────────────────────────


def cmd_discover(project_dir: Path, output_dir: Path, config: Dict) -> int:
    """Discover all items and output counts for CI job conditions."""
    uploads_dir = project_dir / "uploads"
    files = discover_files(uploads_dir) if uploads_dir.exists() else []
    status_tags = _load_status_tags(project_dir)
    regions = _discover_regions(project_dir)

    tesseract_files = [f for f in files if "tesseract" in status_tags.get(f.name, [])]
    python_files = [f for f in files if "python" in status_tags.get(f.name, [])]
    graph_regions = [r for r in regions if r["pen"] == "graph"]
    tesseract_regions = [r for r in regions if r["pen"] == "tesseract"]
    describe_regions = [r for r in regions if r["pen"] == "describe"]

    counts = {
        "tesseract_file_count": len(tesseract_files),
        "python_file_count": len(python_files),
        "graph_region_count": len(graph_regions),
        "tesseract_region_count": len(tesseract_regions),
        "describe_region_count": len(describe_regions),
    }

    print("=== Project Discovery ===")
    for key, count in counts.items():
        label = key.replace("_", " ").replace("count", "").strip().title()
        print(f"  {label}: {count}")
        _set_github_output(key, str(count))

    # Write step summary
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        lines = [
            "### Project Discovery",
            "",
            "| Extraction Job | Items |",
            "|----------------|-------|",
            f"| Tesseract Text Extraction (files) | {counts['tesseract_file_count']} |",
            f"| Python3 Extraction (files) | {counts['python_file_count']} |",
            f"| Graph Data Extraction (regions) | {counts['graph_region_count']} |",
            f"| Tesseract Region Extraction (pixel pen) | {counts['tesseract_region_count']} |",
            f"| Image Description Extraction (regions) | {counts['describe_region_count']} |",
            "",
        ]
        with open(summary_file, "a") as fh:
            fh.write("\n".join(lines) + "\n")

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "tesseract_files": [str(f) for f in tesseract_files],
        "python_files": [str(f) for f in python_files],
        "graph_regions": [{"pen": "graph", "path": str(r["path"])} for r in graph_regions],
        "tesseract_regions": [{"pen": "tesseract", "path": str(r["path"])} for r in tesseract_regions],
        "describe_regions": [{"pen": "describe", "path": str(r["path"])} for r in describe_regions],
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return 0


def cmd_tesseract_files(project_dir: Path, output_dir: Path, config: Dict) -> int:
    """OCR extraction for files tagged with tesseract in status.tag."""
    uploads_dir = project_dir / "uploads"
    files = discover_files(uploads_dir) if uploads_dir.exists() else []
    status_tags = _load_status_tags(project_dir)
    targets = [f for f in files if "tesseract" in status_tags.get(f.name, [])]

    total = len(targets)
    if total == 0:
        print("No files tagged for tesseract extraction")
        _write_results([], output_dir)
        return 0

    print(f"=== Tesseract Text Extraction: {total} files ===")

    # Config: OCR only, no vision description or chart extraction
    cfg: Dict[str, Any] = {k: (dict(v) if isinstance(v, dict) else v) for k, v in config.items()}
    cfg["processing"] = {**config["processing"], "enable_text": True, "enable_description": False, "enable_deplot": False}
    cfg["ocr"] = {**config["ocr"], "enabled": True}

    file_workers = max(1, int(config["concurrency"]["file_workers"]))
    vision_workers = max(1, int(config["concurrency"]["vision_workers"]))
    vision_pool = ThreadPoolExecutor(max_workers=vision_workers)
    deplot_pool = ThreadPoolExecutor(max_workers=1)

    results: List[Dict] = []
    completed = 0
    file_pool = ThreadPoolExecutor(max_workers=file_workers)
    futures = {}
    for path in targets:
        future = file_pool.submit(process_file, path, cfg, None, vision_pool, output_dir, deplot_pool, None)
        futures[future] = path

    for future in as_completed(futures):
        completed += 1
        path = futures[future]
        try:
            result = future.result()
            results.append(result.__dict__)
        except Exception as exc:  # noqa: BLE001
            results.append({
                "file": path.name, "status": "error", "size_bytes": 0,
                "processing_time_sec": 0, "transcript_path": None, "error": str(exc),
            })
        _progress(completed, total, path.name)

    file_pool.shutdown(wait=False)
    vision_pool.shutdown(wait=True)
    deplot_pool.shutdown(wait=True)

    _write_results(results, output_dir)
    _write_step_summary("Tesseract Text Extraction", results)
    return 0


def cmd_python_files(project_dir: Path, output_dir: Path, config: Dict) -> int:
    """Vision-based extraction for files tagged with python in status.tag."""
    uploads_dir = project_dir / "uploads"
    files = discover_files(uploads_dir) if uploads_dir.exists() else []
    status_tags = _load_status_tags(project_dir)
    targets = [f for f in files if "python" in status_tags.get(f.name, [])]

    total = len(targets)
    if total == 0:
        print("No files tagged for python extraction")
        _write_results([], output_dir)
        return 0

    print(f"=== Python3 Extraction: {total} files ===")

    # Config: vision text + description, no OCR, no chart extraction
    cfg: Dict[str, Any] = {k: (dict(v) if isinstance(v, dict) else v) for k, v in config.items()}
    cfg["processing"] = {**config["processing"], "enable_text": True, "enable_description": True, "enable_deplot": False}
    cfg["ocr"] = {**config["ocr"], "enabled": False}

    vision_backend = build_backend(config)
    file_workers = max(1, int(config["concurrency"]["file_workers"]))
    vision_workers = max(1, int(config["concurrency"]["vision_workers"]))
    vision_pool = ThreadPoolExecutor(max_workers=vision_workers)
    deplot_pool = ThreadPoolExecutor(max_workers=1)

    results: List[Dict] = []
    completed = 0
    file_pool = ThreadPoolExecutor(max_workers=file_workers)
    futures = {}
    for path in targets:
        future = file_pool.submit(process_file, path, cfg, vision_backend, vision_pool, output_dir, deplot_pool, None)
        futures[future] = path

    for future in as_completed(futures):
        completed += 1
        path = futures[future]
        try:
            result = future.result()
            results.append(result.__dict__)
        except Exception as exc:  # noqa: BLE001
            results.append({
                "file": path.name, "status": "error", "size_bytes": 0,
                "processing_time_sec": 0, "transcript_path": None, "error": str(exc),
            })
        _progress(completed, total, path.name)

    file_pool.shutdown(wait=False)
    vision_pool.shutdown(wait=True)
    deplot_pool.shutdown(wait=True)

    _write_results(results, output_dir)
    _write_step_summary("Python3 Extraction", results)
    return 0


def cmd_graph_regions(project_dir: Path, output_dir: Path, config: Dict) -> int:
    """Chart/graph data extraction for graph pen regions using multi-model concurrent extraction."""
    regions = [r for r in _discover_regions(project_dir) if r["pen"] == "graph"]
    total = len(regions)
    if total == 0:
        print("No graph regions to process")
        _write_results([], output_dir)
        return 0

    print(f"=== Graph Data Extraction: {total} regions ===")

    all_model_keys = list(CHART_MODELS.keys())
    default_models = all_model_keys

    # For graph regions that can't use deplot, fall back to vision
    vision_backend = None
    if not config["deplot"]["enabled"]:
        vision_backend = build_backend(config)

    region_output = output_dir / "regions" / "graph"
    region_output.mkdir(parents=True, exist_ok=True)
    results: List[Dict] = []

    for i, region in enumerate(regions, 1):
        path: Path = region["path"]
        start = time.time()

        if not config["deplot"]["enabled"]:
            # Fall back to vision description when deplot is disabled
            result = _process_region(region, config, vision_backend, None, region_output)
            results.append(result)
            _progress(i, total, path.name)
            continue

        # Determine which models to use for this region
        region_models = region.get("models", default_models)
        # Filter to only valid model keys
        region_models = [m for m in region_models if m in all_model_keys]
        if not region_models:
            region_models = default_models

        try:
            multi = MultiModelExtractor(
                model_names=region_models,
                max_tokens=config["deplot"]["max_tokens"],
                prompt=config["deplot"]["prompt"],
                cache_dir=config["deplot"]["cache_dir"],
            )
            all_outputs = multi.extract_all(path)

            # Write individual model outputs
            for model_key, output_text in all_outputs.items():
                model_file = region_output / f"{path.stem}_{model_key}.txt"
                model_file.write_text(output_text.strip() + "\n", encoding="utf-8")

            # Write best result as the primary transcript
            best_output = multi.extract(path)
            transcript_path = region_output / f"{path.stem}.txt"
            transcript_path.write_text(best_output.strip() + "\n", encoding="utf-8")

            results.append({
                "file": f"region:graph:{path.name}",
                "status": "success",
                "size_bytes": path.stat().st_size,
                "processing_time_sec": time.time() - start,
                "transcript_path": str(transcript_path),
                "models_used": region_models,
                "error": None,
            })
        except Exception as exc:  # noqa: BLE001
            transcript_path = region_output / f"{path.stem}.txt"
            transcript_path.write_text(f"Error processing region: {exc}\n", encoding="utf-8")
            results.append({
                "file": f"region:graph:{path.name}",
                "status": "error",
                "size_bytes": path.stat().st_size,
                "processing_time_sec": time.time() - start,
                "transcript_path": str(transcript_path),
                "models_used": region_models,
                "error": str(exc),
            })

        _progress(i, total, path.name)

    _write_results(results, output_dir)
    _write_step_summary("Graph Data Extraction", results)
    return 0


def cmd_tesseract_regions(project_dir: Path, output_dir: Path, config: Dict) -> int:
    """OCR extraction for tesseract pen (pixel pen) regions."""
    regions = [r for r in _discover_regions(project_dir) if r["pen"] == "tesseract"]
    total = len(regions)
    if total == 0:
        print("No tesseract pen regions to process")
        _write_results([], output_dir)
        return 0

    print(f"=== Tesseract Region Extraction (Pixel Pen): {total} regions ===")

    region_output = output_dir / "regions" / "tesseract"
    results: List[Dict] = []
    for i, region in enumerate(regions, 1):
        result = _process_region(region, config, None, None, region_output)
        results.append(result)
        _progress(i, total, region["path"].name)

    _write_results(results, output_dir)
    _write_step_summary("Tesseract Region Extraction (Pixel Pen)", results)
    return 0


def cmd_describe_regions(project_dir: Path, output_dir: Path, config: Dict) -> int:
    """Vision description extraction for describe pen regions."""
    regions = [r for r in _discover_regions(project_dir) if r["pen"] == "describe"]
    total = len(regions)
    if total == 0:
        print("No describe regions to process")
        _write_results([], output_dir)
        return 0

    print(f"=== Image Description Extraction: {total} regions ===")

    vision_backend = build_backend(config)
    region_output = output_dir / "regions" / "describe"
    results: List[Dict] = []
    for i, region in enumerate(regions, 1):
        result = _process_region(region, config, vision_backend, None, region_output)
        results.append(result)
        _progress(i, total, region["path"].name)

    _write_results(results, output_dir)
    _write_step_summary("Image Description Extraction", results)
    return 0


def cmd_bundle(inputs_dir: Path, output_dir: Path) -> int:
    """Merge results from all extraction jobs into final output."""
    all_results: List[Dict] = []

    for results_file in sorted(inputs_dir.rglob("results.json")):
        mode_dir = results_file.parent
        try:
            entries = json.loads(results_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for entry in entries:
            # Adjust transcript_path to point to the downloaded artifact location
            tp = entry.get("transcript_path")
            if tp:
                candidate = mode_dir / Path(tp).name
                if candidate.exists():
                    entry["transcript_path"] = str(candidate)
                else:
                    # Try to find the transcript relative to mode_dir
                    for found in mode_dir.rglob(Path(tp).name):
                        entry["transcript_path"] = str(found)
                        break
            all_results.append(entry)

    output_dir.mkdir(parents=True, exist_ok=True)
    write_summary_json(all_results, output_dir / "summary.json")
    write_summary_md(all_results, output_dir / "summary.md")
    write_combined_transcripts(all_results, output_dir / "all_transcripts.txt")

    success = sum(1 for r in all_results if r.get("status") == "success")
    errors = sum(1 for r in all_results if r.get("status") == "error")
    print(f"=== Bundle Complete ===")
    print(f"  Total items: {len(all_results)}")
    print(f"  Successful:  {success}")
    print(f"  Errors:      {errors}")

    _write_step_summary("Bundle — Final Results", all_results)
    return 0


def cmd_all(project_dir: Path, output_dir: Path, config: Dict) -> int:
    """Run all extraction modes in one process (backward-compatible)."""
    uploads_dir = project_dir / "uploads"
    status_tags = _load_status_tags(project_dir)

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
    all_futures: Dict = {}

    file_pool = ThreadPoolExecutor(max_workers=file_workers)
    for path in files:
        file_tags = status_tags.get(path.name, [])
        file_config: Dict[str, Any] = {k: (dict(v) if isinstance(v, dict) else v) for k, v in config.items()}
        if file_tags:
            file_config["processing"] = {
                **config["processing"],
                "enable_text": "tesseract" in file_tags or "python" in file_tags,
            }
            file_config["ocr"] = {**config["ocr"], "enabled": "tesseract" in file_tags}
        future = file_pool.submit(
            process_file, path, file_config, vision_backend, vision_pool,
            output_dir, deplot_pool, deplot_extractor,
        )
        all_futures[future] = ("file", path)

    region_items = _discover_regions(project_dir)
    region_output_dir = output_dir / "regions"
    region_pool = ThreadPoolExecutor(max_workers=max(2, vision_workers))
    for region in region_items:
        future = region_pool.submit(
            _process_region, region, config, vision_backend, deplot_extractor,
            region_output_dir / region["pen"],
        )
        all_futures[future] = ("region", region)

    total = len(all_futures)
    completed = 0
    for future in as_completed(all_futures):
        completed += 1
        kind, item = all_futures[future]
        name = item.name if hasattr(item, "name") else str(item)
        try:
            result = future.result()
            results.append(result.__dict__ if kind == "file" else result)
        except Exception as exc:  # noqa: BLE001
            results.append({
                "file": name, "status": "error", "size_bytes": 0,
                "processing_time_sec": 0, "transcript_path": None, "error": str(exc),
            })
        _progress(completed, total, name)

    file_pool.shutdown(wait=False)
    region_pool.shutdown(wait=False)
    vision_pool.shutdown(wait=True)
    deplot_pool.shutdown(wait=True)

    write_summary_json(results, output_dir / "summary.json")
    write_summary_md(results, output_dir / "summary.md")
    write_combined_transcripts(results, output_dir / "all_transcripts.txt")
    return 0


# ── Entry point ──────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="FTT Transformer Project runner")
    parser.add_argument("--project", required=True, help="Path to FTT Transformer export (dir or zip)")
    parser.add_argument("--config", default="ftt.yml", help="Path to config file")
    parser.add_argument("--output", default="output", help="Output directory")
    parser.add_argument(
        "--mode", default="all", choices=MODES,
        help="Extraction mode (default: all). Use 'discover' for CI job orchestration.",
    )
    parser.add_argument(
        "--inputs", default="",
        help="Inputs directory for bundle mode (contains result artifacts).",
    )
    args = parser.parse_args()

    config = load_config(Path(args.config))
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Bundle mode doesn't need a project — it merges existing results
    if args.mode == "bundle":
        inputs_dir = Path(args.inputs) if args.inputs else output_dir
        return cmd_bundle(inputs_dir, output_dir)

    project_dir = _resolve_project(args.project)

    dispatch = {
        "all": cmd_all,
        "discover": cmd_discover,
        "tesseract-files": cmd_tesseract_files,
        "python-files": cmd_python_files,
        "graph-regions": cmd_graph_regions,
        "tesseract-regions": cmd_tesseract_regions,
        "describe-regions": cmd_describe_regions,
    }

    return dispatch[args.mode](project_dir, output_dir, config)


if __name__ == "__main__":
    raise SystemExit(main())
