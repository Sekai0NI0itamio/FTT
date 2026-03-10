from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TextIO

LEVELS = {"debug": 10, "info": 20, "warning": 30, "error": 40}


class FileLogger:
    def __init__(self, path: Path, level: str = "info") -> None:
        self.path = path
        self.level = LEVELS.get(level, 20)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle: TextIO = self.path.open("a", encoding="utf-8")

    def _write(self, level: str, message: str) -> None:
        if LEVELS.get(level, 20) < self.level:
            return
        timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        line = f"[{timestamp}] {level.upper()}: {message}\n"
        self._handle.write(line)
        self._handle.flush()

    def debug(self, message: str) -> None:
        self._write("debug", message)

    def info(self, message: str) -> None:
        self._write("info", message)

    def warning(self, message: str) -> None:
        self._write("warning", message)

    def error(self, message: str) -> None:
        self._write("error", message)

    def close(self) -> None:
        try:
            self._handle.close()
        except Exception:
            pass
