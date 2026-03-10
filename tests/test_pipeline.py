from pathlib import Path

from PIL import Image

from ftt.config import load_config
from concurrent.futures import ThreadPoolExecutor

from ftt.pipeline import process_file


class DummyBackend:
    def transcribe(self, image_path: Path, prompt: str, max_tokens: int) -> str:
        return "dummy output"


def test_process_image_success(tmp_path: Path) -> None:
    img_path = tmp_path / "sample.png"
    Image.new("RGB", (10, 10), color=(255, 0, 0)).save(img_path)

    config = load_config(tmp_path / "missing.yml")
    config["logging"]["keep_visuals"] = False
    config["deplot"]["enabled"] = False
    config["ocr"]["enabled"] = False

    with ThreadPoolExecutor(max_workers=1) as pool:
        result = process_file(
            img_path,
            config,
            DummyBackend(),
            vision_pool=pool,
            output_root=tmp_path / "out",
            deplot_pool=pool,
            deplot_extractor=None,
        )

    assert result.status == "success"
    transcript = Path(result.transcript_path).read_text(encoding="utf-8")
    assert "dummy output" in transcript


def test_process_unsupported_file(tmp_path: Path) -> None:
    path = tmp_path / "file.xyz"
    path.write_text("x", encoding="utf-8")
    config = load_config(tmp_path / "missing.yml")
    config["deplot"]["enabled"] = False
    config["ocr"]["enabled"] = False

    with ThreadPoolExecutor(max_workers=1) as pool:
        result = process_file(
            path,
            config,
            DummyBackend(),
            vision_pool=pool,
            output_root=tmp_path / "out",
            deplot_pool=pool,
            deplot_extractor=None,
        )

    assert result.status == "error"
