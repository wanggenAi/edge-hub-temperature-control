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
- Rectangular pin-row modules/connectors remain table-style only for:
  `DD1, A1, XS1, XS2, XS3, XS4, XS5`
- Discrete components are standard schematic symbol primitives, not table rectangles:
  `R1, R2, R3, R4, R5, R6, C1, C2, C3, C4, SB1, SB2, HL1, VT1`
- Generated symbol primitive count: `58`
- Required discrete-symbol lint failures now include:
  `FORBIDDEN_TABLE_STYLE_FOR_DISCRETE_SYMBOL`, `REQUIRED_SYMBOL_SHAPE_MISSING`,
  `FORBIDDEN_RANDOM_SYMBOL_GEOMETRY`, `PIN_LINE_NOT_CONNECTED`, `PIN_NUMBER_MISSING`
- Rectangular module pin label policy: `inside_table_row`
- Discrete symbol pin label policy: `above_pin_line`

## Local Wire Visibility
- Minimum configured heater/power local wire length: `25.0` draw.io page units
- Measured local wire lengths:
  - `wire.local.GATE_R.R4_VT1_R5`: `265.000`
  - `wire.local.GATE_R.R4_bus`: `40.000`
  - `wire.local.GATE_R.R5_bus`: `40.000`
  - `wire.local.HEAT-.VT1_XS2`: `45.000`
- Zero-length local wire check: passed
- Local wire too short check: passed

## Reserved Regions
- Source template: `hardware/eda/functiondiagramYUANLITU.drawio`
- Generated drawing: `hardware/eda/functiondiagramYUANLITU.generated.drawio`
- Source template diff after this package step: empty
- Generated drawing: updated middle circuit only; original template remains unchanged
- Outer frame: unchanged
- List of Elements region: unchanged in layout
- Title Block region: unchanged in layout

## Validation
- `python3 -m pytest tests/test_visual_schematic_lint.py -q`: `39 passed`
- `python3 tools/visual_schematic_lint.py hardware/eda/functiondiagramYUANLITU.generated.drawio --mode generated --lock-file hardware/eda/reserved_regions.lock.json --reports-dir build/reports/generated-symbol-schematic`: `0` errors
- `python3 tools/visual_schematic_lint.py hardware/eda/functiondiagramYUANLITU.drawio --mode template --reports-dir build/reports/final-human-review-template`: `0` errors
- `python3 tools/export_artifact_lint.py --export-dir hardware/eda/exports/final --basename esp32_temperature_control_unit_electrical_schematic --label final-symbol-schematic --reports-dir build/reports/final-symbol-export`: `0` errors

## ERC Status
`ERC_UNAVAILABLE`: this is the draw.io visual engineering workflow. No KiCad schematic source is used here, so KiCad ERC is not claimed as passed.

## Human Review Checklist
- DD1 area: pin row spacing, readable labels, no text collisions.
- Reset / LED / decoupling area: R/C/SB/HL1 symbols are true schematic primitives, not table boxes.
- Sensor / UART area: connector labels readable and net labels close to stubs.
- Heater area: R4/R5 resistor symbols, VT1 NMOS symbol, visible `GATE_R`, `HEAT+`, and `HEAT-` local wires.
- Power area: XS3/A1 modules with C3/C4 capacitor symbols, readable `+12V`, `+3V3`, and `GND` labels.
- List of Elements: readable rows, correct component coverage, no table clipping.
- Title Block: document code visible, no clipping, frame alignment intact.
- Whole page: balanced white space, no overlap with right-side tables, black-white engineering style.
