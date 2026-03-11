# FTT Transformer (Electron)

## Dev Setup

1. Install dependencies:
   `npm install`
2. Run dev:
   `npm run dev`

## Export Format

The app exports a zip with:
- `project.json` (metadata, file list, stroke data)
- `regions/` (per-pen extracted regions as PNG)

Use the workflow **FTT Transformer Based Project Extraction** to process these bundles on GitHub Actions.
