from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import threading
from typing import Dict, List

from PIL import Image


# ── Model registry ──────────────────────────────────────────────────────────
# Each entry defines: architecture, HuggingFace model id, URL, and
# human-readable strengths/weaknesses for the UI model picker.

CHART_MODELS: Dict[str, Dict] = {
    "unichart": {
        "model_id": "ahmed-masry/unichart-base-960",
        "arch": "unichart",
        "url": "https://huggingface.co/ahmed-masry/unichart-base-960",
        "label": "UniChart",
        "description": "State-of-the-art chart comprehension and data table extraction",
        "strengths": [
            "Best at extracting raw data tables from charts",
            "Handles bar charts, line charts, and pie charts well",
            "Supports chart summarization and chart QA tasks",
        ],
        "weaknesses": [
            "Slower inference due to VisionEncoderDecoder architecture",
            "Less accurate on scatter plots with dense overlapping points",
            "Struggles with 3D charts and perspective distortion",
        ],
    },
    "matcha": {
        "model_id": "google/matcha-chartqa",
        "arch": "pix2struct",
        "url": "https://huggingface.co/google/matcha-chartqa",
        "label": "MatCha-ChartQA",
        "description": "Enhanced chart understanding with math reasoning pretraining",
        "strengths": [
            "Strong at answering numeric questions about charts",
            "Good with line graphs and trend analysis",
            "Fast inference (Pix2Struct architecture)",
        ],
        "weaknesses": [
            "Outputs answers rather than full data tables",
            "Less suitable for raw data extraction tasks",
            "Can miss small annotations and legend entries",
        ],
    },
    "deplot": {
        "model_id": "google/deplot",
        "arch": "pix2struct",
        "url": "https://huggingface.co/google/deplot",
        "label": "DePlot",
        "description": "Plot-to-table translation (lightweight baseline)",
        "strengths": [
            "Lightweight and fast to load and run",
            "Decent at simple bar and line charts",
            "Good default for initial extraction attempts",
        ],
        "weaknesses": [
            "Lowest accuracy of the three models",
            "Often misreads values on complex multi-series charts",
            "Poor at stacked charts and area charts",
        ],
    },
}


def get_model_registry() -> Dict[str, Dict]:
    """Return the model registry for use by the frontend/config."""
    return CHART_MODELS


class DeplotExtractor:
    """Single-model chart-to-data extractor."""

    def __init__(self, model_name: str, max_tokens: int, prompt: str, cache_dir: str) -> None:
        resolved = CHART_MODELS.get(model_name)
        if resolved:
            self.model_id = resolved["model_id"]
            self.arch = resolved["arch"]
        elif model_name in ("google/deplot", "google/matcha-chartqa"):
            self.model_id = model_name
            self.arch = "pix2struct"
        elif "unichart" in model_name.lower():
            self.model_id = model_name
            self.arch = "unichart"
        else:
            self.model_id = model_name
            self.arch = "pix2struct"

        self.max_tokens = max_tokens
        self.prompt = prompt
        self.cache_dir = cache_dir
        self._lock = threading.Lock()
        self._model = None
        self._processor = None

    @property
    def model_key(self) -> str:
        for key, info in CHART_MODELS.items():
            if info["model_id"] == self.model_id:
                return key
        return self.model_id

    def _ensure_loaded(self) -> None:
        if self._model is not None and self._processor is not None:
            return
        if self.arch == "unichart":
            self._load_unichart()
        else:
            self._load_pix2struct()

    def _load_pix2struct(self) -> None:
        try:
            from transformers import Pix2StructForConditionalGeneration, Pix2StructProcessor
        except ImportError as exc:
            raise RuntimeError("transformers is required for chart extraction") from exc
        self._processor = Pix2StructProcessor.from_pretrained(
            self.model_id, cache_dir=self.cache_dir
        )
        self._model = Pix2StructForConditionalGeneration.from_pretrained(
            self.model_id, cache_dir=self.cache_dir
        )
        self._model.eval()

    def _load_unichart(self) -> None:
        try:
            from transformers import DonutProcessor, VisionEncoderDecoderModel
        except ImportError as exc:
            raise RuntimeError("transformers is required for chart extraction") from exc
        self._processor = DonutProcessor.from_pretrained(
            self.model_id, cache_dir=self.cache_dir
        )
        self._model = VisionEncoderDecoderModel.from_pretrained(
            self.model_id, cache_dir=self.cache_dir
        )
        self._model.eval()

    def extract(self, image_path: Path) -> str:
        with self._lock:
            self._ensure_loaded()
            assert self._model is not None
            assert self._processor is not None
            if self.arch == "unichart":
                return self._extract_unichart(image_path)
            return self._extract_pix2struct(image_path)

    def _extract_pix2struct(self, image_path: Path) -> str:
        assert self._model is not None and self._processor is not None
        with Image.open(image_path) as img:
            img = img.convert("RGB")
            inputs = self._processor(images=img, text=self.prompt, return_tensors="pt")
            inputs = {k: v.to(self._model.device) for k, v in inputs.items()}
        with _no_grad():
            output = self._model.generate(**inputs, max_new_tokens=self.max_tokens)
        text = self._processor.decode(output[0], skip_special_tokens=True)
        return text.replace("<0x0A>", "\n").strip()

    def _extract_unichart(self, image_path: Path) -> str:
        assert self._model is not None and self._processor is not None
        prompt = self.prompt
        if not prompt.startswith("<"):
            prompt = "<extract_data_table> <s_answer>"
        with Image.open(image_path) as img:
            img = img.convert("RGB")
            decoder_input_ids = self._processor.tokenizer(
                prompt, add_special_tokens=False, return_tensors="pt"
            ).input_ids
            pixel_values = self._processor(img, return_tensors="pt").pixel_values
        device = self._model.device
        with _no_grad():
            outputs = self._model.generate(
                pixel_values.to(device),
                decoder_input_ids=decoder_input_ids.to(device),
                max_length=self._model.decoder.config.max_position_embeddings,
                early_stopping=True,
                pad_token_id=self._processor.tokenizer.pad_token_id,
                eos_token_id=self._processor.tokenizer.eos_token_id,
                use_cache=True,
                num_beams=4,
                bad_words_ids=[[self._processor.tokenizer.unk_token_id]],
                return_dict_in_generate=True,
            )
        sequence = self._processor.batch_decode(outputs.sequences)[0]
        sequence = sequence.replace(
            self._processor.tokenizer.eos_token, ""
        ).replace(
            self._processor.tokenizer.pad_token, ""
        )
        if "<s_answer>" in sequence:
            sequence = sequence.split("<s_answer>")[1]
        return sequence.strip()


class MultiModelExtractor:
    """Runs multiple chart models concurrently on the same image.

    Each model extracts independently. Results are returned as a dict
    keyed by model name. This lets the pipeline compare outputs and
    pick the best extraction for each graph type.
    """

    def __init__(
        self,
        model_names: List[str],
        max_tokens: int,
        prompt: str,
        cache_dir: str,
    ) -> None:
        self._extractors: Dict[str, DeplotExtractor] = {}
        for name in model_names:
            self._extractors[name] = DeplotExtractor(
                model_name=name,
                max_tokens=max_tokens,
                prompt=prompt,
                cache_dir=cache_dir,
            )

    @property
    def model_keys(self) -> List[str]:
        return list(self._extractors.keys())

    def extract_all(self, image_path: Path) -> Dict[str, str]:
        """Run all models concurrently and return {model_key: output_text}."""
        results: Dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=len(self._extractors)) as pool:
            futures = {
                pool.submit(ext.extract, image_path): key
                for key, ext in self._extractors.items()
            }
            for future in as_completed(futures):
                key = futures[future]
                try:
                    results[key] = future.result()
                except Exception as exc:  # noqa: BLE001
                    results[key] = f"ERROR: {exc}"
        return results

    def extract(self, image_path: Path) -> str:
        """Run all models, return the best non-error result (longest output).

        Falls back to the first extractor's result if all fail.
        """
        all_results = self.extract_all(image_path)
        # Pick the longest non-error result as "best"
        valid = {k: v for k, v in all_results.items() if not v.startswith("ERROR:")}
        if valid:
            best_key = max(valid, key=lambda k: len(valid[k]))
            return f"[Model: {best_key}]\n{valid[best_key]}"
        # All errored — return first error
        first_key = next(iter(all_results))
        return all_results[first_key]


def _no_grad():
    try:
        import torch
    except ImportError:
        class _Dummy:
            def __enter__(self):
                return None
            def __exit__(self, exc_type, exc, tb):
                return False
        return _Dummy()
    return torch.no_grad()
