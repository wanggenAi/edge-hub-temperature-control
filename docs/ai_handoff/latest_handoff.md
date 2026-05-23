# AI Handoff

## Current Commit
65c0afb

## Current Branch
main

## Project Goal
This project is `edge-hub-temperature-control`, used for graduation thesis and defense materials. The current engineering focus is reproducible draw.io schematic generation, confirmed reference-designator mapping, and thesis-quality technical drawing output.

## Reviewer Input Used
Firefox ChatGPT rejected the previous visual direction because discrete components were rendered as table-like pin modules. The new instruction is explicit:

- `DD1`, `A1`, and `XS1` through `XS5` may remain rectangular pin-row modules/connectors.
- `R1` through `R6` must be resistor symbols.
- `C1` through `C4` must be capacitor symbols.
- `SB1` and `SB2` must be switch/button symbols.
- `HL1` must be an LED symbol.
- `VT1` must be an NMOS/MOSFET symbol.
- If a pin line is drawn, it must connect to a wire, net label, junction, or terminal.

## What Was Done In This Round
- Reworked `hardware/eda/render_esp32_drawio.js` so discrete components render as standard schematic symbol primitives instead of `shape=table` rectangles.
- Kept rectangular pin-row style only for module/connector components:
  `DD1, A1, XS1, XS2, XS3, XS4, XS5`.
- Added generated `symbol_primitive` mxCells with role metadata and symbol type metadata for resistor, capacitor, switch, LED, and NMOS symbols.
- Added pin-line connectivity validation so rendered pin lines cannot silently float.
- Added lint failures for the exact bad direction:
  - `FORBIDDEN_TABLE_STYLE_FOR_DISCRETE_SYMBOL`
  - `REQUIRED_SYMBOL_SHAPE_MISSING`
  - `FORBIDDEN_RANDOM_SYMBOL_GEOMETRY`
  - `PIN_LINE_NOT_CONNECTED`
  - `PIN_NUMBER_MISSING`
- Updated tests so:
  - discrete table-style components fail;
  - missing discrete symbol primitives fail;
  - good generated schematic passes.
- Regenerated final draw.io/SVG/PDF/PNG artifacts and review crops.
- Did not modify `hardware/eda/functiondiagramYUANLITU.drawio`.

## Files Changed
- `hardware/eda/render_esp32_drawio.js`
- `tools/visual_schematic_lint.py`
- `tests/test_visual_schematic_lint.py`
- `hardware/eda/style_rules_from_drawio.yaml`
- `hardware/eda/functiondiagramYUANLITU.generated.drawio`
- `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.drawio`
- `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.svg`
- `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.pdf`
- `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.png`
- `hardware/eda/exports/final/review_crops/*.png`
- `docs/schematic_visual_review_report.md`
- `docs/ai_handoff/latest_handoff.md`

## Final Artifacts
- Editable final draw.io: `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.drawio`
- Final SVG: `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.svg`
- Final PDF: `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.pdf`
- Final PNG: `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.png`
- Review report: `docs/schematic_visual_review_report.md`
- Review crop manifest: `hardware/eda/exports/final/review_crops/manifest.json`

## Symbol Rendering Summary
- Table-style component bodies:
  `DD1, A1, XS1, XS2, XS3, XS4, XS5`
- Standard schematic symbol component bodies:
  `R1, R2, R3, R4, R5, R6, C1, C2, C3, C4, SB1, SB2, HL1, VT1`
- Generated symbol primitive count: `58`
- PNG dimensions: `6586 x 4666 px`
- PNG colored ratio: `0.0`
- PNG selection-like pixels: `0`

## Validation Performed
- `python3 -m pytest tests/test_visual_schematic_lint.py -q`
  - Result: `39 passed`
- `python3 tools/visual_schematic_lint.py hardware/eda/functiondiagramYUANLITU.generated.drawio --mode generated --lock-file hardware/eda/reserved_regions.lock.json --reports-dir build/reports/generated-symbol-schematic`
  - Result: passed, `0` errors
- `python3 tools/export_artifact_lint.py --export-dir hardware/eda/exports/final --basename esp32_temperature_control_unit_electrical_schematic --label final-symbol-schematic --reports-dir build/reports/final-symbol-export`
  - Result: passed, `0` errors
- `bash hardware/eda/tools/export_final_artifacts.sh`
  - Result: passed
- `python3 hardware/eda/tools/create_visual_review_crops.py`
  - Result: passed

## Topology / Ref / Net Status
- Component set: unchanged, 21 components.
- Refs: unchanged.
- Canonical net names: unchanged.
- Electrical topology: intended unchanged; this remains a draw.io visual engineering workflow, not KiCad ERC.
- Original source template `hardware/eda/functiondiagramYUANLITU.drawio`: unchanged.

## ERC Status
`ERC_UNAVAILABLE`: no KiCad schematic source is used in the current `hardware/eda` draw.io workflow. Electrical ERC is not claimed as passed.

## Current Repository State Notes
- The working tree still contains unrelated uncommitted changes from other project areas; they were intentionally not staged for this schematic round.
- `build/reports/*` is generated locally but ignored by `.gitignore`; report paths are listed for local inspection.

## Open Questions For ChatGPT
1. Are the resistor/capacitor/switch/LED/NMOS symbol primitives now acceptable as schematic symbols instead of table rectangles?
2. Should VT1 be redrawn with a more detailed MOSFET symbol, or is the current NMOS primitive acceptable for the thesis drawing?
3. Should local visible wires be added for more nets, or is the current net-label-heavy engineering style acceptable?

## Suggested Next Step
Ask ChatGPT/reviewer to inspect the updated PDF/PNG and identify concrete visual defects only. Do not return to the table-rectangle style for discrete components.
