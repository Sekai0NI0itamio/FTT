from __future__ import annotations

from pathlib import Path

from ftt.vision.base import VisionBackend


class OpenAIStub(VisionBackend):
    def transcribe(self, image_path: Path, prompt: str, max_tokens: int) -> str:
        raise NotImplementedError("OpenAI backend is a stub. Configure local_llama_cpp or implement API calls.")
