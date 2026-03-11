# FTT Manual

## Overview
FTT (File To Text) runs entirely on GitHub Actions. Users commit files into `incoming/`, manually trigger a workflow, and receive transcripts, logs, and a summary as a downloadable artifact.

## How It Works
1. **Setup** job installs dependencies, builds `llama.cpp`, and restores caches.
2. **Concurrent Processing** runs three parallel jobs:
   - `text` (vision text extraction)
   - `description` (vision description)
   - `deplot` (chart data extraction)
3. **Bundling** merges outputs into a single artifact.
4. Each file is processed:
   - Text extraction from PDFs, DOCX, PPTX, XLSX.
   - Visual extraction (embedded images and/or page rendering).
   - Vision LLM transcription for image text + description.
   - DePlot chart-to-table extraction for charts (when enabled).
4. Outputs are written to `output/` and uploaded as an artifact even if some files fail.

## Folder Structure
- `incoming/`
  - Commit your input files here.
- `output/`
  - Generated at runtime.
- `ftt/`
  - Python package implementing the pipeline.
- `.github/workflows/`
  - GitHub Actions workflows.

## Triggering the Workflow
1. Go to the **Actions** tab.
2. Select **FTT Process Files**.
3. Click **Run workflow** and optionally override inputs.
4. Use `force_setup=true` to re-install dependencies and rebuild caches when needed (default skips when cached).

For Transformer exports, run **FTT Transformer Based Project Extraction** and point it at `incoming-transformer/` or a zip file.

## Local CLI
Run all tasks:
`python -m ftt.run --config ftt.yml`

Run a single mode:
`python -m ftt.run --config ftt.yml --mode text`
`python -m ftt.run --config ftt.yml --mode description`
`python -m ftt.run --config ftt.yml --mode deplot`

## Output Artifact Layout
- `output/all_transcripts.txt`
- `output/summary.json`
- `output/summary.md`
- `output/files/<safe_name>/transcript.txt`
- `output/files/<safe_name>/logs/steps.log`
- `output/files/<safe_name>/visuals/` (when `logging.keep_visuals=true`)

## Configuration
Primary configuration lives in `ftt.yml`. Common parameters:
- `visual.mode`: `embedded`, `hybrid`, `full`
- `render.dpi`: DPI for rendered pages
- `render.max_pages`: limit pages rendered per file
- `render.office`: `auto|true|false` for LibreOffice conversions (`auto` enables for PPTX/XLSX by default)
- `concurrency.file_workers` and `concurrency.vision_workers`
- `concurrency.deplot_workers`
- `vision.backend`: `local_llama_cpp` by default
- `vision.chat_template`: default `vicuna` for LLaVA v1.5 models
- `vision.text_prompt` and `vision.description_prompt`
- `deplot.enabled`, `deplot.model_name`, `deplot.prompt`
- `processing.enable_text`, `processing.enable_description`, `processing.enable_deplot`
- `ocr.enabled`, `ocr.lang`

## Chart Extraction (DePlot)
When `deplot.enabled=true`, each visual is sent to DePlot to extract chart data. The output is stored in the transcript as a chart table and a small Python script snippet for quick parsing.

Workflow inputs can override common parameters. Environment variables begin with `FTT_` (see `ftt/config.py`).

## Changing the LLM Backend
The default backend uses `llama.cpp` with a LLaVA-family model. The workflow prefers `llama-mtmd-cli` (the replacement for `llama-llava-cli`) when available.
To switch:
- Update `vision.backend` in `ftt.yml`.
- For API providers, implement the stub modules in `ftt/vision/` and add secrets in GitHub.

For the local backend, either pre-cache the model files or set `vision.model_url` and `vision.mmproj_url` so the workflow downloads them.
Recommended GGUF vision models that work with `llama-mtmd-cli` include Qwen2-VL and Gemma 3 from `ggml-org` on Hugging Face.

## Troubleshooting
- **LibreOffice conversion fails**: ensure `libreoffice` is installed in the workflow runner.
- **Missing model files**: set `vision.model_url` and `vision.mmproj_url` to valid URLs or pre-cache the files.
- **Out of memory / timeouts**: reduce `render.max_pages`, lower `visual.max_dim`, and keep `vision_workers=1`.
- **Artifacts missing**: the workflow uploads artifacts even on partial failure; check the workflow logs for errors.
