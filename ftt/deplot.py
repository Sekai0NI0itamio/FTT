from __future__ import annotations

from pathlib import Path
import threading

from PIL import Image


class DeplotExtractor:
    def __init__(self, model_name: str, max_tokens: int, prompt: str, cache_dir: str) -> None:
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.prompt = prompt
        self.cache_dir = cache_dir
        self._lock = threading.Lock()
        self._model = None
        self._processor = None

    def _ensure_loaded(self) -> None:
        if self._model is not None and self._processor is not None:
            return
        try:
            from transformers import Pix2StructForConditionalGeneration, Pix2StructProcessor
        except ImportError as exc:
            raise RuntimeError("transformers is required for DePlot extraction") from exc
        self._processor = Pix2StructProcessor.from_pretrained(self.model_name, cache_dir=self.cache_dir)
        self._model = Pix2StructForConditionalGeneration.from_pretrained(self.model_name, cache_dir=self.cache_dir)
        self._model.eval()

    def extract(self, image_path: Path) -> str:
        with self._lock:
            self._ensure_loaded()
            assert self._model is not None
            assert self._processor is not None
            with Image.open(image_path) as img:
                img = img.convert("RGB")
                inputs = self._processor(images=img, text=self.prompt, return_tensors="pt")
                inputs = {k: v.to(self._model.device) for k, v in inputs.items()}
            with self._no_grad():
                output = self._model.generate(**inputs, max_new_tokens=self.max_tokens)
            text = self._processor.decode(output[0], skip_special_tokens=True)
            return text.replace("<0x0A>", "\n").strip()

    @staticmethod
    def _no_grad():
        try:
            import torch
        except ImportError:
            class Dummy:
                def __enter__(self):
                    return None
                def __exit__(self, exc_type, exc, tb):
                    return False
            return Dummy()
        return torch.no_grad()
