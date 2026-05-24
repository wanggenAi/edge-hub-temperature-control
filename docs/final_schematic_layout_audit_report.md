# Final Schematic Layout/Aesthetic Audit

**This is an automated engineering-layout audit, not final human approval.**

- Status: **PASS**
- Blockers: `0`
- Warnings: `0`
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
- Property text spacing status: `PASS`
- Property text spacing resolution: `FIXED_BY_TEXT_PROPERTY_MOVE`
- Property text spacing failures: `0`
- Property text spacing unresolved: `0`
- Minimum symbol spacing: `2.54` mm

## Property Text Clearance

- Body clearance threshold: `0.4` mm
- Wire clearance threshold: `0.5` mm

| Ref | Property | Text | Relation | Body clearance mm | Wire clearance mm | Status | Evidence crop |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| A1 | Reference | `A1` | inside_body | 3.1195 | 16.7519 | PASS | `hardware/eda/exports/final/layout_audit_crops/text_spacing_A1.png` |
| A1 | Value | `DC/DC 12 V to 3.3 V` | inside_body | 1.6581 | 7.7390 | PASS | `hardware/eda/exports/final/layout_audit_crops/text_spacing_A1.png` |
| DD1 | Reference | `DD1` | inside_body | 10.7395 | 18.7897 | PASS | `hardware/eda/exports/final/layout_audit_crops/text_spacing_DD1.png` |
| DD1 | Value | `ESP32-WROOM-32` | inside_body | 1.2398 | 6.6169 | PASS | `hardware/eda/exports/final/layout_audit_crops/text_spacing_DD1.png` |
| HL1 | Reference | `HL1` | outside_body | 0.6905 | 8.3808 | PASS | `hardware/eda/exports/final/layout_audit_crops/text_spacing_HL1.png` |
| HL1 | Value | `Red LED` | outside_body | 1.8495 | 5.8723 | PASS | `hardware/eda/exports/final/layout_audit_crops/text_spacing_HL1.png` |
| VT1 | Reference | `VT1` | outside_body | 0.6905 | 6.2672 | PASS | `hardware/eda/exports/final/layout_audit_crops/text_spacing_VT1.png` |
| VT1 | Value | `NMOS3400` | outside_body | 0.5191 | 2.8299 | PASS | `hardware/eda/exports/final/layout_audit_crops/text_spacing_VT1.png` |
| XS1 | Reference | `XS1` | outside_body | 0.6905 | 6.3000 | PASS | `hardware/eda/exports/final/layout_audit_crops/text_spacing_XS1.png` |
| XS1 | Value | `XH-3PA` | outside_body | 0.5795 | 4.3717 | PASS | `hardware/eda/exports/final/layout_audit_crops/text_spacing_XS1.png` |
| XS4 | Reference | `XS4` | outside_body | 0.6905 | 6.3000 | PASS | `hardware/eda/exports/final/layout_audit_crops/text_spacing_XS4.png` |
| XS4 | Value | `UART service` | outside_body | 0.5795 | 2.5696 | PASS | `hardware/eda/exports/final/layout_audit_crops/text_spacing_XS4.png` |

## Block Review

### DD1 ESP32 core block
- Status: `PASS`
- Refs: `DD1`
- Nets: `+3V3, GND, EN, LED, BOOT, GATE, DQ, RXD0, TXD0`
- Symbol count: `1`
- Wire count near block: `11`
- Label count near block: `13`
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
- Wire count near block: `6`
- Label count near block: `6`
- Local-wire continuity: `present`
- Evidence crop: `hardware/eda/exports/final/layout_audit_crops/block_led_block.png`

### DS18B20 sensor block
- Status: `PASS`
- Refs: `R2, XS1`
- Nets: `DQ, +3V3, GND`
- Symbol count: `2`
- Wire count near block: `7`
- Label count near block: `7`
- Local-wire continuity: `present`
- Evidence crop: `hardware/eda/exports/final/layout_audit_crops/block_ds18b20_sensor_block.png`

### UART/service block
- Status: `PASS`
- Refs: `XS4`
- Nets: `RXD0, TXD0, +3V3, GND`
- Symbol count: `1`
- Wire count near block: `5`
- Label count near block: `6`
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
- Label count near block: `11`
- Local-wire continuity: `present`
- Evidence crop: `hardware/eda/exports/final/layout_audit_crops/block_power_block.png`

## Findings

No blocker or warning findings were generated.
## Conclusion

- PASS/WARN means the package can proceed to brief human visual approval.
- FAIL means only the listed blockers should be fixed in the next round.
- This checkpoint verifies layout/aesthetic geometry only; it does not claim human visual approval.
