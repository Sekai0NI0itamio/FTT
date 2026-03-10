import os
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

import yaml


def _expand_path(value: str) -> str:
    return str(Path(value).expanduser())


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


DEFAULT_CONFIG: Dict[str, Any] = {
    "inputs": {"dir": "incoming"},
    "outputs": {"dir": "output"},
    "vision": {
        "backend": "local_llama_cpp",
        "model_path": "~/.cache/ftt/models/llava-7b-q4.gguf",
        "mmproj_path": "~/.cache/ftt/models/llava-7b-mmproj-q4.gguf",
        "lora_path": "",
        "llama_cli_path": "vendor/llama.cpp/build/bin/llama-mtmd-cli",
        "chat_template": "vicuna",
        "max_tokens": 512,
        "retries": 2,
        "download": True,
        "model_url": "",
        "mmproj_url": "",
        "prompt_template": (
            "You are a document transcription assistant.\n"
            "Tasks:\n"
            "1) Transcribe all visible text exactly.\n"
            "2) Describe the image in detail.\n"
            "3) If this is a chart/graph, extract a Markdown table of data values "
            "including axis labels, units, and series names.\n"
            "Output with sections:\n"
            "Text:\n"
            "Description:\n"
            "Chart Data (if any):\n"
        ),
    },
    "visual": {
        "mode": "hybrid",
        "max_dim": 1024,
        "text_threshold": 200,
    },
    "render": {
        "dpi": 150,
        "max_pages": 30,
        "office": "auto",  # auto|true|false
    },
    "concurrency": {
        "file_workers": 2,
        "vision_workers": 1,
    },
    "limits": {
        "max_file_mb": 100,
        "max_pages_per_file": 200,
        "max_images_per_file": 100,
    },
    "logging": {
        "level": "info",
        "keep_visuals": True,
    },
}


_OVERRIDE_SPECS: Iterable[Tuple[str, Tuple[str, ...], str]] = [
    ("FTT_INPUTS_DIR", ("inputs", "dir"), "str"),
    ("FTT_OUTPUTS_DIR", ("outputs", "dir"), "str"),
    ("FTT_VISION_BACKEND", ("vision", "backend"), "str"),
    ("FTT_VISION_MODEL_PATH", ("vision", "model_path"), "path"),
    ("FTT_VISION_MMPROJ_PATH", ("vision", "mmproj_path"), "path"),
    ("FTT_VISION_LORA_PATH", ("vision", "lora_path"), "path"),
    ("FTT_VISION_LLAMA_CLI_PATH", ("vision", "llama_cli_path"), "path"),
    ("FTT_VISION_CHAT_TEMPLATE", ("vision", "chat_template"), "str"),
    ("FTT_VISION_MAX_TOKENS", ("vision", "max_tokens"), "int"),
    ("FTT_VISION_RETRIES", ("vision", "retries"), "int"),
    ("FTT_VISION_DOWNLOAD", ("vision", "download"), "bool"),
    ("FTT_VISION_MODEL_URL", ("vision", "model_url"), "str"),
    ("FTT_VISION_MMPROJ_URL", ("vision", "mmproj_url"), "str"),
    ("FTT_VISUAL_MODE", ("visual", "mode"), "str"),
    ("FTT_VISUAL_MAX_DIM", ("visual", "max_dim"), "int"),
    ("FTT_RENDER_DPI", ("render", "dpi"), "int"),
    ("FTT_RENDER_MAX_PAGES", ("render", "max_pages"), "int"),
    ("FTT_RENDER_OFFICE", ("render", "office"), "str"),
    ("FTT_FILE_WORKERS", ("concurrency", "file_workers"), "int"),
    ("FTT_VISION_WORKERS", ("concurrency", "vision_workers"), "int"),
    ("FTT_LIMITS_MAX_FILE_MB", ("limits", "max_file_mb"), "int"),
    ("FTT_LIMITS_MAX_PAGES_PER_FILE", ("limits", "max_pages_per_file"), "int"),
    ("FTT_LIMITS_MAX_IMAGES_PER_FILE", ("limits", "max_images_per_file"), "int"),
    ("FTT_LOG_LEVEL", ("logging", "level"), "str"),
    ("FTT_KEEP_VISUALS", ("logging", "keep_visuals"), "bool"),
]


def _set_path(config: Dict[str, Any], path: Tuple[str, ...], value: Any) -> None:
    cursor = config
    for key in path[:-1]:
        cursor = cursor.setdefault(key, {})
    cursor[path[-1]] = value


def _coerce(value: str, kind: str) -> Any:
    if kind == "int":
        return int(value)
    if kind == "bool":
        return _parse_bool(value)
    if kind == "path":
        return _expand_path(value)
    return value


def load_config(config_path: Path, env: Dict[str, str] | None = None) -> Dict[str, Any]:
    env = env or os.environ
    config: Dict[str, Any] = dict(DEFAULT_CONFIG)

    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
        if not isinstance(loaded, dict):
            raise ValueError("Config file must contain a YAML mapping")
        config = _deep_merge(config, loaded)

    for env_key, path, kind in _OVERRIDE_SPECS:
        if env_key in env and env[env_key] != "":
            _set_path(config, path, _coerce(env[env_key], kind))

    # Expand default paths
    config["vision"]["model_path"] = _expand_path(config["vision"]["model_path"])
    config["vision"]["mmproj_path"] = _expand_path(config["vision"]["mmproj_path"])
    if config["vision"].get("lora_path"):
        config["vision"]["lora_path"] = _expand_path(config["vision"]["lora_path"])
    config["vision"]["llama_cli_path"] = _expand_path(config["vision"]["llama_cli_path"])

    return config
