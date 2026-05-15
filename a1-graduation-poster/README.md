# A1 Graduation Poster Workflow

This folder holds the build workflow for the two-sided A1 landscape poster of
EdgeHub Temperature Control.

## Outputs

- `front-a1-poster.drawio`
- `back-a1-technical-sheet.drawio`
- `export/front-a1-poster.svg`
- `export/front-a1-poster.pdf`
- `export/back-a1-technical-sheet.svg`
- `export/back-a1-technical-sheet.pdf`
- `export/two-page-print.pdf`

## Current asset prep

- `scripts/render_enclosure_hero.py` renders the enclosure hero as a transparent
  PNG for the front poster.
- `scripts/generate_vector_assets.py` builds the vector-based support graphics.
- `scripts/capture_hmi_screenshots.mjs` is the screenshot workflow for the real
  HMI views.

## Asset paths

- `assets/enclosure-hero.png`
- `assets/hmi-device-detail.png`
- `assets/hmi-ai-validation.png`
- `assets/hmi-ops-console.png`
- `assets/data-hub.svg`
- `assets/hmi-layer.svg`
- `assets/ai-decision.svg`
- `assets/key-contributions.svg`

The front poster is intentionally not a giant flowchart. The back side keeps
only the formal engineering title block/table from `aa.drawio`; the rest of the
A1 page is blank.
