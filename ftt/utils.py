from __future__ import annotations

import re
from pathlib import Path


def safe_name(path: Path) -> str:
    name = path.name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    return name.strip("_") or "file"
