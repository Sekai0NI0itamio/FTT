from __future__ import annotations

from typing import Dict

from ftt.vision.base import VisionBackend
from ftt.vision.local_llama_cpp import LocalLlamaCppBackend
from ftt.vision.openai_stub import OpenAIStub
from ftt.vision.anthropic_stub import AnthropicStub
from ftt.vision.gemini_stub import GeminiStub


def build_backend(config: Dict) -> VisionBackend:
    backend = config["vision"]["backend"]
    if backend == "local_llama_cpp":
        return LocalLlamaCppBackend(
            llama_cli_path=config["vision"]["llama_cli_path"],
            model_path=config["vision"]["model_path"],
            mmproj_path=config["vision"]["mmproj_path"],
            lora_path=config["vision"]["lora_path"],
            chat_template=config["vision"]["chat_template"],
            download=config["vision"]["download"],
            model_url=config["vision"]["model_url"],
            mmproj_url=config["vision"]["mmproj_url"],
        )
    if backend == "openai":
        return OpenAIStub()
    if backend == "anthropic":
        return AnthropicStub()
    if backend == "gemini":
        return GeminiStub()
    raise ValueError(f"Unknown vision backend: {backend}")
