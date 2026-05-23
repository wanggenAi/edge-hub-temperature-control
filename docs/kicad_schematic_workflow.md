# KiCad Schematic Embedding Workflow

This checkpoint keeps the KiCad-based schematic workflow and replaces the previous label-only middle circuit with locally wired KiCad circuit blocks. KiCad owns the middle electrical schematic, while draw.io owns the BSTU school frame, right-top List of Elements, and right-bottom Title Block.

## Source Of Truth

- School frame source: `hardware/eda/functiondiagramYUANLITU.drawio`
- KiCad project: `hardware/kicad_schematic/esp32_temperature_control_unit.kicad_pro`
- KiCad schematic: `hardware/kicad_schematic/esp32_temperature_control_unit.kicad_sch`
- KiCad project symbol library: `hardware/kicad_schematic/esp32_temperature_control_unit.kicad_sym`
- Final generated draw.io: `hardware/eda/functiondiagramYUANLITU.generated.drawio`

The original school frame file is not modified. The embedding script reads it, keeps the locked outer frame, element list, and title block regions, removes stale middle-circuit content from the generated copy, and inserts the KiCad SVG as the middle schematic block.

The right-top List of Elements and right-bottom Title Block are intentionally preserved from `hardware/eda/functiondiagramYUANLITU.drawio` in this checkpoint. The current work only redraws and verifies the middle KiCad schematic block.

## Confirmed Refs And Nets

The KiCad schematic uses the confirmed thesis designators:

- `DD1`, `VT1`, `HL1`, `SB1`, `SB2`, `A1`
- `XS1`, `XS2`, `XS3`, `XS4`, `XS5`
- `R1` through `R6`
- `C1` through `C4`

The visible net labels use canonical names:

- `+3V3`, `+12V`, `GND`
- `EN`, `LED`, `LED_A`, `DQ`, `RXD0`, `TXD0`, `BOOT`
- `GATE`, `GATE_R`, `HEAT+`, `HEAT-`

Old source refs and temporary JLC net names are not used as visible KiCad schematic labels.

## Local Wiring Redraw

The middle schematic now uses project-local KiCad symbols and short, explicit wire segments to each pin endpoint. Cross-block connections use canonical global labels only after the local component pin is actually wired.

Local wired blocks:

- Decoupling: `C1`, `C2`
- Reset / EN: `R1`, `SB1`
- LED status: `R3`, `HL1`
- ESP32 controller: `DD1`
- UART service: `XS4`
- Sensor interface: `R2`, `XS1`
- Heater driver: `R4`, `R5`, `VT1`, `XS2`, `XS5`
- Power: `XS3`, `A1`, `C3`, `C4`

Project-local symbols used:

- `ESP32_Temperature_Control:R_H`
- `ESP32_Temperature_Control:C_H`
- `ESP32_Temperature_Control:SW_NO_H`
- `ESP32_Temperature_Control:LED_H`
- `ESP32_Temperature_Control:NMOS_GDS`
- `ESP32_Temperature_Control:CONN_2`
- `ESP32_Temperature_Control:CONN_3`
- `ESP32_Temperature_Control:CONN_4`
- `ESP32_Temperature_Control:ESP32-WROOM-32`
- `ESP32_Temperature_Control:DCDC_12V_3V3`

## Export Commands

KiCad CLI 9.0.2 was available at:

`/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli`

The middle schematic exports were produced with drawing sheet excluded:

```bash
kicad-cli sch export svg hardware/kicad_schematic/esp32_temperature_control_unit.kicad_sch \
  --output hardware/kicad_schematic/exports \
  --black-and-white \
  --exclude-drawing-sheet

kicad-cli sch export pdf hardware/kicad_schematic/esp32_temperature_control_unit.kicad_sch \
  --output hardware/kicad_schematic/exports/esp32_temperature_control_unit_schematic.pdf \
  --black-and-white \
  --exclude-drawing-sheet
```

Final BSTU-frame artifacts are exported through:

```bash
python3 hardware/eda/tools/embed_kicad_schematic_into_bstu_frame.py \
  --frame hardware/eda/functiondiagramYUANLITU.drawio \
  --kicad-svg hardware/kicad_schematic/exports/esp32_temperature_control_unit_schematic.svg \
  --output hardware/eda/functiondiagramYUANLITU.generated.drawio

bash hardware/eda/tools/export_final_artifacts.sh
```

## Validation

Passing checks:

- `python3 -m pytest tests/test_kicad_schematic_workflow.py -q`
- `python3 -m py_compile hardware/eda/tools/embed_kicad_schematic_into_bstu_frame.py tools/export_artifact_lint.py tests/test_kicad_schematic_workflow.py`
- `python3 tools/export_artifact_lint.py --export-dir hardware/eda/exports/final --basename esp32_temperature_control_unit_electrical_schematic --label final-kicad-embedded --reports-dir build/reports/final-kicad-local-wiring-export`
- `/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli sch erc --format json --output build/reports/kicad_schematic_erc_local_wiring.json hardware/kicad_schematic/esp32_temperature_control_unit.kicad_sch`
- `git diff --quiet -- hardware/eda/functiondiagramYUANLITU.drawio`

Final PNG size:

- `6431 x 4654 px`

## BSTU Frame Placement Polish

The current checkpoint does not change the KiCad schematic source or symbol
library. It only adjusts the KiCad SVG placement inside the generated BSTU
frame and adds export-time geometry checks.

Current draw.io embed placement:

- x: `270`
- y: `185`
- width: `2070`
- height: `1440`

Measured final SVG embed placement:

- x: `191`
- y: `178`
- width: `2070`
- height: `1440`
- main schematic width share: `83.5%`
- main schematic height share: `68.6%`
- gap to right-top List of Elements: `297.18` SVG units
- gap to right-bottom Title Block: `489.42` SVG units

The lint target requires the embedded KiCad block to use `70%` to `85%` of the
left/middle main schematic width and `45%` to `70%` of the available main
schematic height. It also requires at least `30` units clearance from the
right-top element list and at least `40` units clearance from the right-bottom
title block.

Current placement lint report:

`build/reports/final-kicad-embedded-scale-polish-export/export_artifact_lint.json`

## Generated List Of Elements Update

The original school frame source still stays locked:

`hardware/eda/functiondiagramYUANLITU.drawio`

The generated/final copies now replace only the right-top List of Elements text
content with the ESP32 temperature-control BOM. The table frame, column header
text, border geometry, title block, and outer frame remain inherited from the
school draw.io template.

The update is applied by:

```bash
python3 hardware/eda/tools/update_generated_element_list.py \
  --input hardware/eda/functiondiagramYUANLITU.generated.drawio \
  --output hardware/eda/functiondiagramYUANLITU.generated.drawio
```

`hardware/eda/tools/export_final_artifacts.sh` runs this updater before copying
and exporting the final artifacts, so regenerated final files keep the ESP32 BOM.

The generated List of Elements now contains:

- Capacitors: `C1, C4`, `C2`, `C3`
- Resistors: `R1, R5, R6`, `R2`, `R3`, `R4`
- Semiconductor Devices: `DD1`, `HL1`, `VT1`
- Switching Components: `SB1, SB2`
- Connectors: `XS1`, `XS2, XS3`, `XS4`, `XS5`
- Power Modules: `A1`

The final export lint label `final-element-list-esp32-bom` requires this ESP32
BOM text to be visible and rejects legacy template entries such as
`Microcontroller AT89C52`, `LCD1602-A`, `Crystal Oscillator`, `RV1`, `ZQ1`,
`DD2`, and `DD3`.

Current element-list update report:

`build/reports/final-element-list-esp32-bom-export/export_artifact_lint.json`

## ERC Status

KiCad ERC was run with KiCad CLI 9.0.2 and passed with zero violations.

Report:

`build/reports/kicad_schematic_erc_local_wiring.json`

Current ERC summary:

- Total violations: `0`
- Errors: `0`
- Warnings: `0`

This means the current checkpoint verifies the KiCad source, exports, embedding, visible refs/nets, school frame preservation, and KiCad electrical-rule connectivity for the locally wired middle schematic.
