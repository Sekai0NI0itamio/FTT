from pathlib import Path

from ftt.config import load_config


def test_config_override(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "ftt.yml"
    cfg.write_text("inputs:\n  dir: incoming\nvision:\n  max_tokens: 123\n", encoding="utf-8")
    monkeypatch.setenv("FTT_VISION_MAX_TOKENS", "456")
    config = load_config(cfg)
    assert config["vision"]["max_tokens"] == 456
