# ESP32 Schematic Visual Review Package

## Final Artifacts
- Final draw.io: `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.drawio`
- Final SVG: `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.svg`
- Final PDF: `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.pdf`
- Final PNG: `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.png`
- PNG resolution: `6586 x 4666 px`

## Review Crops
- `hardware/eda/exports/final/review_crops/overview.png`
- `hardware/eda/exports/final/review_crops/dd1_area.png`
- `hardware/eda/exports/final/review_crops/reset_led_decoupling_area.png`
- `hardware/eda/exports/final/review_crops/sensor_uart_area.png`
- `hardware/eda/exports/final/review_crops/heater_area.png`
- `hardware/eda/exports/final/review_crops/power_area.png`
- `hardware/eda/exports/final/review_crops/title_block_area.png`
- `hardware/eda/exports/final/review_crops/element_list_area.png`
- Manifest: `hardware/eda/exports/final/review_crops/manifest.json`

## Component Set
The generated schematic contains the confirmed 21 components:

`DD1, R1, SB1, R3, HL1, C1, C2, R2, XS1, XS4, R6, SB2, R4, R5, VT1, XS2, XS5, A1, XS3, C3, C4`

## Style Lock
- Generated component body width: `210` draw.io page units
- Component body style: `shape=table`
- Required style metadata: `data-style-lock="reference_table_component"`
- Pin label policy: `inside_table_row`
- Component table divider role: `component_table_line`

## Local Wire Visibility
- Minimum configured heater/power local wire length: `25.0` draw.io page units
- Measured local wire lengths:
  - `wire.local.GATE_R.R4_VT1_R5`: `265.000`
  - `wire.local.GATE_R.R4_bus`: `40.000`
  - `wire.local.GATE_R.R5_bus`: `40.000`
  - `wire.local.HEAT-.VT1_XS2`: `25.000`
- Zero-length local wire check: passed
- Local wire too short check: passed

## Reserved Regions
- Source template: `hardware/eda/functiondiagramYUANLITU.drawio`
- Generated drawing: `hardware/eda/functiondiagramYUANLITU.generated.drawio`
- Source template diff after this package step: empty
- Generated drawing diff after this package step: empty
- Outer frame: unchanged
- List of Elements region: unchanged in layout
- Title Block region: unchanged in layout

## Validation
- `python3 -m pytest tests/test_visual_schematic_lint.py -q`: `37 passed`
- `python3 tools/visual_schematic_lint.py hardware/eda/functiondiagramYUANLITU.generated.drawio --mode generated --reports-dir build/reports/final-human-review-generated`: `0` errors
- `python3 tools/visual_schematic_lint.py hardware/eda/functiondiagramYUANLITU.drawio --mode template --reports-dir build/reports/final-human-review-template`: `0` errors
- `python3 tools/export_artifact_lint.py --export-dir hardware/eda/exports/final --basename esp32_temperature_control_unit_electrical_schematic --label final --reports-dir build/reports/final-human-review-export`: `0` errors

## ERC Status
`ERC_UNAVAILABLE`: this is the draw.io visual engineering workflow. No KiCad schematic source is used here, so KiCad ERC is not claimed as passed.

## Human Review Checklist
- DD1 area: pin row spacing, readable labels, no text collisions.
- Reset / LED / decoupling area: clear left-side grouping and no wire/text crowding.
- Sensor / UART area: connector labels readable and net labels close to stubs.
- Heater area: R4/R5/VT1/XS2/XS5 separation, visible `GATE_R`, `HEAT+`, and `HEAT-` local wires.
- Power area: XS3/A1/C3/C4 separation, readable `+12V`, `+3V3`, and `GND` labels.
- List of Elements: readable rows, correct component coverage, no table clipping.
- Title Block: document code visible, no clipping, frame alignment intact.
- Whole page: balanced white space, no overlap with right-side tables, black-white engineering style.
