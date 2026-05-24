# Final Schematic Layout/Aesthetic Audit

**This is an automated engineering-layout audit, not final human approval.**

- Status: **WARN**
- Blockers: `0`
- Warnings: `1`
- JSON report: `build/reports/final_schematic_layout_audit.json`
- Evidence crop directory: `hardware/eda/exports/final/layout_audit_crops`

## Electrical Baseline

- KiCad ERC: `PASS`; violations `0`
- JLC/KiCad topology equivalence: `PASS`
- Master table lock: `PASS`; value-only changed cells `39`
- Export lint errors: `0`

## KiCad Geometry Metrics

- Symbols: `21`
- Wires: `75`
- Global labels: `57`
- Junctions: `0`
- Diagonal wires: `0`
- Zero-length wires: `0`
- Short wires: `0`
- Dangling endpoints: `0`
- Floating labels: `0`
- Wire-through-symbol-body count: `0`
- Minimum symbol spacing: `2.54` mm

## Block Review

### DD1 ESP32 core block
- Status: `PASS`
- Refs: `DD1`
- Nets: `+3V3, GND, EN, LED, BOOT, GATE, DQ, RXD0, TXD0`
- Symbol count: `1`
- Wire count near block: `11`
- Label count near block: `11`
- Local-wire continuity: `present`
- Evidence crop: `hardware/eda/exports/final/layout_audit_crops/block_dd1_esp32_core_block.png`

### RESET/EN block
- Status: `PASS`
- Refs: `R1, SB1`
- Nets: `+3V3, EN, GND`
- Symbol count: `2`
- Wire count near block: `5`
- Label count near block: `4`
- Local-wire continuity: `present`
- Evidence crop: `hardware/eda/exports/final/layout_audit_crops/block_reset_en_block.png`

### BOOT block
- Status: `PASS`
- Refs: `R6, SB2`
- Nets: `+3V3, BOOT, GND`
- Symbol count: `2`
- Wire count near block: `5`
- Label count near block: `4`
- Local-wire continuity: `present`
- Evidence crop: `hardware/eda/exports/final/layout_audit_crops/block_boot_block.png`

### LED block
- Status: `PASS`
- Refs: `R3, HL1`
- Nets: `+3V3, LED_A, LED`
- Symbol count: `2`
- Wire count near block: `5`
- Label count near block: `4`
- Local-wire continuity: `present`
- Evidence crop: `hardware/eda/exports/final/layout_audit_crops/block_led_block.png`

### DS18B20 sensor block
- Status: `PASS`
- Refs: `R2, XS1`
- Nets: `DQ, +3V3, GND`
- Symbol count: `2`
- Wire count near block: `6`
- Label count near block: `5`
- Local-wire continuity: `present`
- Evidence crop: `hardware/eda/exports/final/layout_audit_crops/block_ds18b20_sensor_block.png`

### UART/service block
- Status: `PASS`
- Refs: `XS4`
- Nets: `RXD0, TXD0, +3V3, GND`
- Symbol count: `1`
- Wire count near block: `4`
- Label count near block: `4`
- Local-wire continuity: `present`
- Evidence crop: `hardware/eda/exports/final/layout_audit_crops/block_uart_service_block.png`

### heater driver block
- Status: `PASS`
- Refs: `R4, R5, VT1, XS2, XS5`
- Nets: `GATE, GATE_R, HEAT+, HEAT-, +12V, GND`
- Symbol count: `5`
- Wire count near block: `19`
- Label count near block: `11`
- Local-wire continuity: `present`
- Evidence crop: `hardware/eda/exports/final/layout_audit_crops/block_heater_driver_block.png`

### power block
- Status: `PASS`
- Refs: `XS3, A1, C3, C4`
- Nets: `+12V, +3V3, GND`
- Symbol count: `4`
- Wire count near block: `16`
- Label count near block: `10`
- Local-wire continuity: `present`
- Evidence crop: `hardware/eda/exports/final/layout_audit_crops/block_power_block.png`

## Findings

### KICAD_PROPERTY_TEXT_NEAR_SYMBOL_BODY
- Severity: `WARNING`
- Rule: `text_symbol_spacing`
- Refs: `A1, DD1, HL1, VT1, XS1, XS4`
- Nets: ``
- Measured: `11`
- Threshold: `manual review`
- Evidence crop: `hardware/eda/exports/final/layout_audit_crops/finding_001_kicad_property_text_near_symbol_body.png`
- Explanation: The check uses conservative text bboxes because KiCad stores text anchors rather than rendered glyph extents.

## Conclusion

- PASS/WARN means the package can proceed to brief human visual approval.
- FAIL means only the listed blockers should be fixed in the next round.
- This checkpoint did not modify drawing, schematic, table, BOM, ref, net, or topology artifacts.
