from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from ftt.config import load_config
from ftt.discovery import discover_files
from ftt.merger import write_combined_transcripts
from ftt.deplot import DeplotExtractor
from ftt.pipeline import process_file
from ftt.summary import write_summary_json, write_summary_md
from ftt.vision import build_backend


def main() -> int:
    parser = argparse.ArgumentParser(description="FTT (File To Text) runner")
    parser.add_argument("--config", default="ftt.yml", help="Path to config file")
    parser.add_argument("--inputs", default="", help="Override inputs directory")
    parser.add_argument("--outputs", default="", help="Override outputs directory")
    parser.add_argument(
        "--mode",
        default="all",
        choices=["all", "text", "description", "deplot"],
        help="Extraction mode for visuals",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    config = load_config(config_path)

    if args.inputs:
        config["inputs"]["dir"] = args.inputs
    if args.outputs:
        config["outputs"]["dir"] = args.outputs

    if args.mode != "all":
        config["processing"]["enable_text"] = args.mode == "text"
        config["processing"]["enable_description"] = args.mode == "description"
        config["processing"]["enable_deplot"] = args.mode == "deplot"

    input_dir = Path(config["inputs"]["dir"])
    output_dir = Path(config["outputs"]["dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    files = discover_files(input_dir)
    if not files:
        write_summary_json([], output_dir / "summary.json")
        write_summary_md([], output_dir / "summary.md")
        (output_dir / "all_transcripts.txt").write_text("", encoding="utf-8")
        return 0

    vision_backend = build_backend(config)

    vision_workers = max(1, int(config["concurrency"]["vision_workers"]))
    file_workers = max(1, int(config["concurrency"]["file_workers"]))
    deplot_workers = max(1, int(config["concurrency"].get("deplot_workers", 1)))
    vision_pool = ThreadPoolExecutor(max_workers=vision_workers)
    deplot_pool = ThreadPoolExecutor(max_workers=deplot_workers)

    deplot_extractor = None
    if config["deplot"]["enabled"] and config["processing"]["enable_deplot"]:
        deplot_extractor = DeplotExtractor(
            model_name=config["deplot"]["model_name"],
            max_tokens=config["deplot"]["max_tokens"],
            prompt=config["deplot"]["prompt"],
            cache_dir=config["deplot"]["cache_dir"],
        )

    results = []
    with ThreadPoolExecutor(max_workers=file_workers) as executor:
        futures = {
            executor.submit(
                process_file, path, config, vision_backend, vision_pool, output_dir, deplot_pool, deplot_extractor
            ): path
            for path in files
        }
        for future in as_completed(futures):
            result = future.result()
            results.append(result)

    vision_pool.shutdown(wait=True)
    deplot_pool.shutdown(wait=True)

    result_dicts = [result.__dict__ for result in results]
    write_summary_json(result_dicts, output_dir / "summary.json")
    write_summary_md(result_dicts, output_dir / "summary.md")
    write_combined_transcripts(result_dicts, output_dir / "all_transcripts.txt")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
