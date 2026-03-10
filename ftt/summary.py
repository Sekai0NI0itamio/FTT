from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List, Dict


def build_summary(results: Iterable[Dict]) -> List[Dict]:
    return list(results)


def write_summary_json(results: Iterable[Dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(list(results), handle, indent=2)


def write_summary_md(results: Iterable[Dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(results)
    headers = ["file", "status", "size_bytes", "processing_time_sec", "error"]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        values = [
            str(row.get("file")),
            str(row.get("status")),
            str(row.get("size_bytes")),
            f"{row.get('processing_time_sec', 0):.2f}",
            str(row.get("error") or ""),
        ]
        lines.append("| " + " | ".join(values) + " |")
    with path.open("w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
