# Final Schematic QA Report

This is a thesis insertion candidate package, not a final human-approved drawing.

## Final Artifacts

- Draw.io: `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.drawio`
- SVG: `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.svg`
- PDF: `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.pdf`
- PNG: `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.png`
- PNG resolution: `6433 x 4654 px`

## Automated Checks

- KiCad ERC: `PASSED`; violations `0`, errors `0`, warnings `0`
- KiCad ERC report: `build/reports/kicad_schematic_erc_visual_repair_round2.json`
- Pytest: `33 passed in focused schematic/table/audit suite`
- Export lint errors: `0`
- Export lint report: `build/reports/final-visual-repair-round2-export/export_artifact_lint.json`
- Required school refs present: `True`
- Canonical nets present: `True`
- Forbidden refs/stale nets absent: `True`
- Source frame diff clean: `True`
- KiCad symbol/project diff clean: `True`
- KiCad schematic source may change only for reviewed layout, wire-route, net-label, and property-text coordinates.
- Master table lock passed: `True`
- Master table lock report: `build/reports/bstu_master_table_lock_visual_repair_round2.json`

## KiCad Block Placement

- Embed bbox: `{'x': 191.0, 'y': 178.0, 'width': 2070.0, 'height': 1440.0}`
- Main width share: `0.835`
- Main height share: `0.686`
- Gap to List of Elements: `297.18` SVG units
- Gap to Title Block: `489.42` SVG units

## List Of Elements

- ESP32 BOM text present: `True`
- Master table body source: `hardware/eda/functiondiagramYUANLITU.drawio`
- Generated/final rule: text value replacement only; table geometry, line widths, rows, columns, font/alignment metadata, and cell IDs stay locked to the master.
- BOM readability note: the master table has a fixed row count, so several ESP32 BOM items are merged into existing rows instead of adding new rows.
- Required BOM groups: Capacitors, Resistors, Semiconductor Devices, Switching Components, Connectors, Power Modules

## Master Table Lock

- Status: `PASS`
- Errors: `0`
- Master cell count: `101`
- Master geometry hash: `34ef44b8ced36aa76933db11fa585bb5d57ca868ab93e5d2f95193670983edf0`
- `hardware/eda/functiondiagramYUANLITU.generated.drawio`: geometry matches master `True`, value-only changed cells `39`
- `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.drawio`: geometry matches master `True`, value-only changed cells `39`

The review crops include `element_list_full`, `element_list_top`,
`element_list_middle`, and `element_list_bottom` so reviewers can inspect
whether the merged BOM text remains readable under the locked master table.

## Title Block

- ESP32 title block text present: `True`
- Legacy template title text absent: `True`
- Title block body source: `hardware/eda/functiondiagramYUANLITU.drawio`
- Generated/final rule: text value replacement only.

## Review Crops

- `overview`: `hardware/eda/exports/final/review_crops/overview.png`
- `kicad_block`: `hardware/eda/exports/final/review_crops/kicad_block.png`
- `dd1_area`: `hardware/eda/exports/final/review_crops/dd1_area.png`
- `reset_boot_led_area`: `hardware/eda/exports/final/review_crops/reset_boot_led_area.png`
- `sensor_uart_area`: `hardware/eda/exports/final/review_crops/sensor_uart_area.png`
- `heater_power_area`: `hardware/eda/exports/final/review_crops/heater_power_area.png`
- `power_area`: `hardware/eda/exports/final/review_crops/power_area.png`
- `element_list_full`: `hardware/eda/exports/final/review_crops/element_list_full.png`
- `element_list_top`: `hardware/eda/exports/final/review_crops/element_list_top.png`
- `element_list_middle`: `hardware/eda/exports/final/review_crops/element_list_middle.png`
- `element_list_bottom`: `hardware/eda/exports/final/review_crops/element_list_bottom.png`
- `title_block_full`: `hardware/eda/exports/final/review_crops/title_block_full.png`

## Conclusion

No automated blocker is recorded in this QA package if all booleans above are `True`, export lint reports `0`, and ERC is `PASSED`.
The user still needs to visually inspect the review crops and final PDF/PNG before thesis insertion.
