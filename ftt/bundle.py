from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List

from ftt.merger import write_combined_transcripts
from ftt.summary import write_summary_json, write_summary_md


def _load_transcripts(base_dir: Path) -> Dict[str, str]:
    transcripts = {}
    files_dir = base_dir / "files"
    if not files_dir.exists():
        return transcripts
    for file_dir in files_dir.iterdir():
        transcript = file_dir / "transcript.txt"
        if transcript.exists():
            transcripts[file_dir.name] = transcript.read_text(encoding="utf-8")
    return transcripts


def _copy_logs(output_dir: Path, input_dir: Path, suffix: str) -> None:
    files_dir = input_dir / "files"
    if not files_dir.exists():
        return
    for file_dir in files_dir.iterdir():
        logs_dir = file_dir / "logs"
        if not logs_dir.exists():
            continue
        target_logs = output_dir / "files" / file_dir.name / "logs"
        target_logs.mkdir(parents=True, exist_ok=True)
        for log_file in logs_dir.glob("*.log"):
            target = target_logs / f"{log_file.stem}-{suffix}.log"
            target.write_text(log_file.read_text(encoding="utf-8"), encoding="utf-8")


def _load_meta(base_dir: Path) -> Dict[str, str]:
    mapping = {}
    files_dir = base_dir / "files"
    if not files_dir.exists():
        return mapping
    for file_dir in files_dir.iterdir():
        meta = file_dir / "meta.json"
        if not meta.exists():
            continue
        import json

        data = json.loads(meta.read_text(encoding="utf-8"))
        if "file" in data:
            mapping[file_dir.name] = data["file"]
    return mapping


def _load_summary(base_dir: Path) -> Dict[str, Dict]:
    summary_path = base_dir / "summary.json"
    if not summary_path.exists():
        return {}
    import json

    data = json.loads(summary_path.read_text(encoding="utf-8"))
    return {item["file"]: item for item in data}


def bundle_outputs(output_dir: Path, inputs: List[Path]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    transcripts_by_task = [(_input.name, _load_transcripts(_input)) for _input in inputs]
    summaries_by_task = [(_input.name, _load_summary(_input)) for _input in inputs]
    meta_by_task = [(_input.name, _load_meta(_input)) for _input in inputs]

    all_files = set()
    for _, transcripts in transcripts_by_task:
        all_files.update(transcripts.keys())

    results = []
    for safe_name in sorted(all_files):
        combined_parts = []
        for task_name, transcripts in transcripts_by_task:
            content = transcripts.get(safe_name)
            if content:
                combined_parts.append(content.strip())
        file_dir = output_dir / "files" / safe_name
        file_dir.mkdir(parents=True, exist_ok=True)
        transcript_path = file_dir / "transcript.txt"
        transcript_path.write_text("\n\n".join(combined_parts).strip() + "\n", encoding="utf-8")

        status = "success"
        error_messages = []
        size_bytes = 0
        processing_time = 0.0
        original_name = None
        for _, meta in meta_by_task:
            if safe_name in meta:
                original_name = meta[safe_name]
                break
        if original_name is None:
            original_name = safe_name

        for _, summary in summaries_by_task:
            info = summary.get(original_name)
            if not info:
                continue
            size_bytes = info.get("size_bytes", size_bytes)
            processing_time += float(info.get("processing_time_sec", 0))
            if info.get("status") != "success":
                status = "error"
                if info.get("error"):
                    error_messages.append(str(info.get("error")))

        results.append(
            {
                "file": original_name,
                "status": status,
                "size_bytes": size_bytes,
                "processing_time_sec": processing_time,
                "transcript_path": str(transcript_path),
                "error": " | ".join(error_messages) if error_messages else None,
            }
        )

    write_summary_json(results, output_dir / "summary.json")
    write_summary_md(results, output_dir / "summary.md")
    write_combined_transcripts(results, output_dir / "all_transcripts.txt")

    for input_dir in inputs:
        suffix = input_dir.name.replace("output-", "")
        _copy_logs(output_dir, input_dir, suffix)


def main() -> int:
    parser = argparse.ArgumentParser(description="Bundle FTT outputs")
    parser.add_argument("--output", default="output", help="Bundled output directory")
    parser.add_argument("--inputs", nargs="+", required=True, help="Input output directories")
    args = parser.parse_args()

    output_dir = Path(args.output)
    inputs = [Path(p) for p in args.inputs]
    bundle_outputs(output_dir, inputs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
