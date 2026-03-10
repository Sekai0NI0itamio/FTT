from __future__ import annotations

import urllib.request
from pathlib import Path
import subprocess

from ftt.vision.base import VisionBackend


class LocalLlamaCppBackend(VisionBackend):
    def __init__(
        self,
        llama_cli_path: str,
        model_path: str,
        mmproj_path: str,
        lora_path: str,
        download: bool,
        model_url: str,
        mmproj_url: str,
    ) -> None:
        self.llama_cli_path = Path(llama_cli_path)
        self.model_path = Path(model_path)
        self.mmproj_path = Path(mmproj_path)
        self.lora_path = Path(lora_path) if lora_path else None
        self.download = download
        self.model_url = model_url
        self.mmproj_url = mmproj_url
        if self.download:
            self._ensure_model(self.model_path, self.model_url)
            self._ensure_model(self.mmproj_path, self.mmproj_url)

    def _ensure_model(self, path: Path, url: str) -> None:
        if path.exists():
            return
        if not url:
            raise FileNotFoundError(f"Missing model file {path} and no URL configured")
        path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, path)

    def transcribe(self, image_path: Path, prompt: str, max_tokens: int) -> str:
        if not self.llama_cli_path.exists():
            raise FileNotFoundError(f"llama CLI not found at {self.llama_cli_path}")
        if not self.model_path.exists():
            raise FileNotFoundError(f"Model not found at {self.model_path}")
        if not self.mmproj_path.exists():
            raise FileNotFoundError(f"MMProj not found at {self.mmproj_path}")

        cli_path = self.llama_cli_path
        result = self._run_cli(cli_path, image_path, prompt, max_tokens, include_sampling=True)
        if result.returncode == 0:
            return result.stdout.strip()

        detail = (result.stderr.strip() or result.stdout.strip() or "llama CLI failed")
        if "deprecated" in detail.lower():
            fallback = self._find_mtmd_cli(cli_path)
            if fallback:
                cli_path = fallback
                result = self._run_cli(cli_path, image_path, prompt, max_tokens, include_sampling=True)
                if result.returncode == 0:
                    return result.stdout.strip()
                detail = (result.stderr.strip() or result.stdout.strip() or detail)

        if "invalid argument: -n" in detail or "invalid argument: --temp" in detail:
            retry = self._run_cli(cli_path, image_path, prompt, max_tokens, include_sampling=False)
            if retry.returncode == 0:
                return retry.stdout.strip()
            detail = retry.stderr.strip() or retry.stdout.strip() or detail

        raise RuntimeError(detail)

    def _run_cli(
        self,
        cli_path: Path,
        image_path: Path,
        prompt: str,
        max_tokens: int,
        include_sampling: bool,
    ) -> subprocess.CompletedProcess[str]:
        cmd = self._build_cmd(cli_path, image_path, prompt, max_tokens, include_sampling=include_sampling)
        if self.lora_path:
            cmd.extend(["--lora", str(self.lora_path)])
        return subprocess.run(cmd, capture_output=True, text=True)

    def _build_cmd(
        self,
        cli_path: Path,
        image_path: Path,
        prompt: str,
        max_tokens: int,
        include_sampling: bool,
    ) -> list[str]:
        cmd = [
            str(cli_path),
            "-m",
            str(self.model_path),
            "--mmproj",
            str(self.mmproj_path),
            "--image",
            str(image_path),
            "-p",
            prompt,
        ]
        if include_sampling:
            cmd.extend(["-n", str(max_tokens), "--temp", "0"])
        return cmd

    @staticmethod
    def _find_mtmd_cli(current: Path) -> Path | None:
        candidate = current.parent / "llama-mtmd-cli"
        if candidate.exists():
            return candidate
        return None
