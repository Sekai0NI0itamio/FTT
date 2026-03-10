from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class VisionBackend(ABC):
    @abstractmethod
    def transcribe(self, image_path: Path, prompt: str, max_tokens: int) -> str:
        raise NotImplementedError
