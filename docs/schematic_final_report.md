# ESP32 Temperature Control Unit Schematic Final Report

## Scope
This report covers the current `hardware/eda` draw.io-based schematic workflow. The editable source template is `hardware/eda/functiondiagramYUANLITU.drawio`; the generated middle-circuit drawing is `hardware/eda/functiondiagramYUANLITU.generated.drawio`.

This round did not use KiCad and did not perform KiCad ERC.

## Final Artifacts
- Editable final draw.io: `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.drawio`
- Final SVG: `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.svg`
- Final PDF: `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.pdf`
- Final PNG: `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.png`

## Source Files
- Template source: `hardware/eda/functiondiagramYUANLITU.drawio`
- Generated source: `hardware/eda/functiondiagramYUANLITU.generated.drawio`
- Schematic model: `hardware/eda/schematic_model.yaml`
- Style rules: `hardware/eda/style_rules_from_drawio.yaml`
- Ref mapping: `hardware/eda/ref_mapping.yaml`
- Reserved-region lock: `hardware/eda/reserved_regions.lock.json`
- Final export script: `hardware/eda/tools/export_final_artifacts.sh`
- Preview export script: `hardware/eda/tools/export_preview_artifacts.sh`
- Visual lint: `tools/visual_schematic_lint.py`
- Export lint: `tools/export_artifact_lint.py`

## What Changed
- Corrected the locked Title Block document code from `BSTU.241297.005 Э3` to `BSTU.241297.006 Э3`.
- Updated only the Title Block value hash in `hardware/eda/reserved_regions.lock.json`.
- Regenerated `hardware/eda/functiondiagramYUANLITU.generated.drawio`.
- Regenerated preview exports.
- Added final export script and final artifact outputs.
- Tightened export lint so the SVG must contain `BSTU.241297.006`.

No middle schematic layout, component, ref mapping, or net topology change was made during the final export stage.

## Reserved Regions
- `outer_frame`
  - bbox: `x=79.74 y=7.74 w=3211.2 h=2322.83 right=3290.94 bottom=2330.57`
  - cell count: `1`
  - status: unchanged
- `element_list`
  - bbox: `x=2558.18 y=10.43 w=730.0 h=1260.0 right=3288.18 bottom=1270.43`
  - cell count: `1`
  - status: unchanged
- `title_block`
  - bbox: `x=2555.18 y=2107.42 w=733.786 h=221.0 right=3288.966 bottom=2328.42`
  - cell count: `39`
  - style hash: unchanged
  - geometry hash: unchanged
  - value hash: changed intentionally for document code `.006`

## Document Code Scan
- Template draw.io:
  - `BSTU.241297.005`: `0`
  - `BSTU.241297.006`: `1`
- Generated draw.io:
  - `BSTU.241297.005`: `0`
  - `BSTU.241297.006`: `1`
- Final SVG:
  - `BSTU.241297.005`: `0`
  - `BSTU.241297.006`: `1`

## Export Measurements
- Final SVG
  - Size: `1494779` bytes
  - viewBox: `-0.5 -0.5 3293 2333`
- Final PDF
  - Size: `63457` bytes
  - Page count: `1`
- Final PNG
  - Size: `988536` bytes
  - Dimensions: `6586 x 4666 px`
  - Colored pixel ratio: `0.0`
  - Selection-like pixels: `0`

## Validation Results
- `python3 tools/visual_schematic_lint.py hardware/eda/functiondiagramYUANLITU.drawio --mode template --reports-dir build/reports/template-title-code`
  - Result: passed, `0` errors
- `node --check hardware/eda/render_esp32_drawio.js`
  - Result: passed
- `node hardware/eda/render_esp32_drawio.js --write-output --layout-refinement`
  - Result: passed
- `python3 tools/visual_schematic_lint.py hardware/eda/functiondiagramYUANLITU.generated.drawio --mode generated --reports-dir build/reports/generated-final-export`
  - Result: passed, `0` errors
- `bash -n hardware/eda/tools/export_final_artifacts.sh hardware/eda/tools/export_preview_artifacts.sh`
  - Result: passed
- `bash hardware/eda/tools/export_final_artifacts.sh`
  - Result: passed
- `python3 tools/export_artifact_lint.py --export-dir hardware/eda/exports/final --basename esp32_temperature_control_unit_electrical_schematic --label final --reports-dir build/reports/export-final`
  - Result: passed, `0` errors
- `python3 tools/export_artifact_lint.py --reports-dir build/reports/export-preview-regression`
  - Result: passed, `0` errors
- `python3 -m pytest tests/test_visual_schematic_lint.py -q`
  - Result: `31 passed`
- `python3 -m py_compile tools/export_artifact_lint.py tools/visual_schematic_lint.py`
  - Result: passed

## ERC Status
`ERC_UNAVAILABLE`: no KiCad schematic source is used in the current `hardware/eda` draw.io workflow. This report verifies draw.io geometry, locked regions, text, export artifacts, and visual structure; it does not claim KiCad electrical ERC passed.

## Remaining Risks
- Human visual review is still recommended before inserting the final PDF/PNG into thesis material.
- The current workflow validates the generated draw.io and exported artifacts, but it is not a substitute for a SPICE/KiCad electrical-rule check.
