from __future__ import annotations

from pathlib import Path

from ftt.vision.base import VisionBackend


class AnthropicStub(VisionBackend):
    def transcribe(self, image_path: Path, prompt: str, max_tokens: int) -> str:
        raise NotImplementedError("Anthropic backend is a stub. Configure local_llama_cpp or implement API calls.")
