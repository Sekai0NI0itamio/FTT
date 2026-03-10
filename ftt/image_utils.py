from __future__ import annotations

from pathlib import Path

from PIL import Image


def normalize_image(image_path: Path, output_dir: Path, max_dim: int) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(image_path) as img:
        img = img.convert("RGB")
        width, height = img.size
        if max_dim <= 0:
            return _copy_as_png(img, output_dir, image_path.stem)
        scale = min(max_dim / max(width, height), 1.0)
        if scale < 1.0:
            new_size = (int(width * scale), int(height * scale))
            img = img.resize(new_size, Image.LANCZOS)
        return _copy_as_png(img, output_dir, f"{image_path.stem}_norm")


def _copy_as_png(img: Image.Image, output_dir: Path, name: str) -> Path:
    output_path = output_dir / f"{name}.png"
    img.save(output_path)
    return output_path
