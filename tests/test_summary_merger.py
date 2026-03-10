from pathlib import Path

from ftt.summary import write_summary_json, write_summary_md
from ftt.merger import write_combined_transcripts


def test_summary_and_merger(tmp_path: Path) -> None:
    results = [
        {
            "file": "a.pdf",
            "status": "success",
            "size_bytes": 10,
            "processing_time_sec": 1.2,
            "transcript_path": str(tmp_path / "a.txt"),
            "error": None,
        }
    ]
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    write_summary_json(results, tmp_path / "summary.json")
    write_summary_md(results, tmp_path / "summary.md")
    write_combined_transcripts(results, tmp_path / "all.txt")

    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "summary.md").exists()
    combined = (tmp_path / "all.txt").read_text(encoding="utf-8")
    assert "File Name: a.pdf" in combined
