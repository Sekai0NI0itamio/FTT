from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


@dataclass
class ImageRef:
    path: Path
    label: str
    source: str


@dataclass
class ExtractedContent:
    text_parts: List[str] = field(default_factory=list)
    images: List[ImageRef] = field(default_factory=list)
    metadata: Dict[str, object] = field(default_factory=dict)
