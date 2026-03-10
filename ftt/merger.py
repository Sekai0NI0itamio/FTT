from __future__ import annotations

from pathlib import Path
from typing import Iterable, Dict


def write_combined_transcripts(results: Iterable[Dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for result in results:
        file_name = result.get("file")
        transcript_path = result.get("transcript_path")
        if not transcript_path:
            continue
        content = Path(transcript_path).read_text(encoding="utf-8")
        lines.append(f"File Name: {file_name}")
        lines.append("File Content:")
        lines.append(content.strip())
        lines.append("")
    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
