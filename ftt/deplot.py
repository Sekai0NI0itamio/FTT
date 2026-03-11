from __future__ import annotations

from pathlib import Path
import threading

from PIL import Image


# ── Model registry ──────────────────────────────────────────────────────────
# Each entry defines: architecture type, HuggingFace model id, download URL
# All models are free and open-source.
CHART_MODELS = {
    # Best accuracy — dedicated chart-to-table with data extraction task
    "unichart": {
        "model_id": "ahmed-masry/unichart-base-960",
        "arch": "unichart",
        "url": "https://huggingface.co/ahmed-masry/unichart-base-960",
        "description": "UniChart: state-of-the-art chart comprehension and data table extraction",
    },
    # Good accuracy — MatCha fine-tuned on ChartQA, ~20% better than DePlot
    "matcha": {
        "model_id": "google/matcha-chartqa",
        "arch": "pix2struct",
        "url": "https://huggingface.co/google/matcha-chartqa",
        "description": "MatCha-ChartQA: enhanced chart understanding with math reasoning pretraining",
    },
    # Lightweight fallback — original DePlot
    "deplot": {
        "model_id": "google/deplot",
        "arch": "pix2struct",
        "url": "https://huggingface.co/google/deplot",
        "description": "DePlot: plot-to-table translation (lightweight baseline)",
    },
}


class DeplotExtractor:
    """Unified chart-to-data extractor supporting multiple model backends.

    Supported model_name values:
      - "unichart"            → ahmed-masry/unichart-base-960  (best accuracy)
      - "matcha"              → google/matcha-chartqa          (good accuracy)
      - "deplot" / "google/deplot" → google/deplot             (lightweight)
      - Any HuggingFace model id   → auto-detect architecture
    """

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
            # Default to pix2struct for unknown models (backward compat)
            self.model_id = model_name
            self.arch = "pix2struct"

        self.max_tokens = max_tokens
        self.prompt = prompt
        self.cache_dir = cache_dir
        self._lock = threading.Lock()
        self._model = None
        self._processor = None

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
        assert self._model is not None
        assert self._processor is not None
        with Image.open(image_path) as img:
            img = img.convert("RGB")
            inputs = self._processor(images=img, text=self.prompt, return_tensors="pt")
            inputs = {k: v.to(self._model.device) for k, v in inputs.items()}
        with self._no_grad():
            output = self._model.generate(**inputs, max_new_tokens=self.max_tokens)
        text = self._processor.decode(output[0], skip_special_tokens=True)
        return text.replace("<0x0A>", "\n").strip()

    def _extract_unichart(self, image_path: Path) -> str:
        assert self._model is not None
        assert self._processor is not None

        # UniChart uses task-specific prompts:
        #   <extract_data_table>  → data table extraction
        #   <summarize_chart>     → chart summarization
        #   <chartqa> question    → chart question answering
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
        with self._no_grad():
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

    @staticmethod
    def _no_grad():
        try:
            import torch
        except ImportError:
            class Dummy:
                def __enter__(self):
                    return None
                def __exit__(self, exc_type, exc, tb):
                    return False
            return Dummy()
        return torch.no_grad()
