# KiCad Schematic Embedding Workflow

This checkpoint switches the schematic workflow from draw.io-drawn middle circuitry to a KiCad-based middle schematic embedded into the locked BSTU draw.io frame.

## Source Of Truth

- School frame source: `hardware/eda/functiondiagramYUANLITU.drawio`
- KiCad project: `hardware/kicad_schematic/esp32_temperature_control_unit.kicad_pro`
- KiCad schematic: `hardware/kicad_schematic/esp32_temperature_control_unit.kicad_sch`
- KiCad project symbol library: `hardware/kicad_schematic/esp32_temperature_control_unit.kicad_sym`
- Final generated draw.io: `hardware/eda/functiondiagramYUANLITU.generated.drawio`

The original school frame file is not modified. The embedding script reads it, keeps the locked outer frame, element list, and title block regions, removes stale middle-circuit content from the generated copy, and inserts the KiCad SVG as the middle schematic block.

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
- `python3 -m py_compile hardware/eda/tools/embed_kicad_schematic_into_bstu_frame.py tools/export_artifact_lint.py`
- `python3 tools/export_artifact_lint.py --export-dir hardware/eda/exports/final --basename esp32_temperature_control_unit_electrical_schematic --label final-kicad-embedded --reports-dir build/reports/final-kicad-embedded-export`
- `git diff --quiet -- hardware/eda/functiondiagramYUANLITU.drawio`

Final PNG size:

- `6431 x 4654 px`

## ERC Status

KiCad ERC was run and did not pass. The report is:

`build/reports/kicad_schematic_erc.json`

Current ERC summary:

- Total violations: 186
- Errors: 85
- Warnings: 101
- Main types: `pin_not_connected`, `endpoint_off_grid`, `unconnected_wire_endpoint`, `label_dangling`, `power_pin_not_driven`, `pin_not_driven`

This means the current checkpoint verifies the KiCad source, exports, embedding, visible refs/nets, and school frame preservation, but it does not yet verify electrical connectivity by ERC. The next round should fix KiCad pin endpoint placement and grid alignment until ERC errors are eliminated.

