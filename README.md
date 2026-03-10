# FTT (File To Text)

FTT is a GitHub Actions–only pipeline that converts files in `incoming/` to text transcripts. It extracts text from PDFs, DOCX, PPTX, and XLSX, and uses a local open-source vision LLM to describe images and charts.

## Quick Start

1. Put files into `incoming/`.
2. Commit and push.
3. In GitHub, go to Actions and run **FTT Process Files**.
4. Download the artifact from the workflow run.

## What You Get

- `output/all_transcripts.txt` with combined results.
- `output/summary.json` and `output/summary.md` with status per file.
- `output/files/<file>/transcript.txt` and logs per file.

## Configuration

See `ftt.yml` for all options. Common overrides can be set as workflow inputs or environment variables.

## Model Files

The default backend expects local GGUF vision model files. Either:
- Pre-populate `~/.cache/ftt/models` on the runner, or
- Provide `vision.model_url` and `vision.mmproj_url` in `ftt.yml` or as workflow inputs.

The current `ftt.yml` is configured for Qwen2-VL-2B (GGUF + mmproj) to work with `llama-mtmd-cli`.
Charts are additionally parsed with DePlot (`google/deplot`) when enabled.

## Documentation

Full manual: `docs/manual.md`
