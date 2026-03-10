from pathlib import Path

from ftt.discovery import discover_files, detect_file_type


def test_discover_files(tmp_path: Path) -> None:
    (tmp_path / "a.pdf").write_text("x")
    (tmp_path / "b.docx").write_text("x")
    (tmp_path / ".hidden").write_text("x")
    files = discover_files(tmp_path)
    assert [p.name for p in files] == ["a.pdf", "b.docx"]


def test_detect_file_type() -> None:
    assert detect_file_type(Path("test.pdf")) == "pdf"
    assert detect_file_type(Path("test.png")) == "image"
    assert detect_file_type(Path("test.unknown")) is None
