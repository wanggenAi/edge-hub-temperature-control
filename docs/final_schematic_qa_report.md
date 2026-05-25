# Final Schematic QA Report

This is a thesis insertion candidate package, not a final human-approved drawing.

## Final Artifacts

- Draw.io: `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.drawio`
- SVG: `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.svg`
- PDF: `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.pdf`
- PNG: `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.png`
- PNG resolution: `6431 x 4654 px`

## Automated Checks

- KiCad ERC: `PASSED`; violations `0`, errors `0`, warnings `0`
- KiCad ERC report: `build/reports/kicad_schematic_erc_layout_audit.json`
- Pytest: `33 passed in focused schematic/table/audit suite`
- Export lint errors: `0`
- Export lint report: `build/reports/final-master-table-edit-export/export_artifact_lint.json`
- Required school refs present: `True`
- Canonical nets present: `True`
- Forbidden refs/stale nets absent: `True`
- Source frame diff clean: `True`
- KiCad symbol/project diff clean: `True`
- KiCad schematic source is unchanged in this JLC-style workflow and is used only for topology verification.
- Master table lock passed: `True`
- Master table lock report: `build/reports/bstu_master_table_lock_master_table_edit.json`

## JLC-Style Schematic Block Placement

- Embed bbox: `{'x': 126.0, 'y': 543.0, 'width': 2136.4, 'height': 1200.5}`
- Main width share: `0.910`
- Main height share: `0.572`
- Gap to List of Elements: `165.78` SVG units
- Gap to Title Block: `363.92` SVG units

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
- Master geometry hash: `5e2df315aec3896a6b27fbd8e0094982b46b7f5941ad044462ae744a4b3bd71c`
- `hardware/eda/functiondiagramYUANLITU.generated.drawio`: geometry matches master `True`, value-only changed cells `38`
- `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.drawio`: geometry matches master `True`, value-only changed cells `38`

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
- `jlc_style_block`: `hardware/eda/exports/final/review_crops/jlc_style_block.png`
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
Visual Review PASS is not claimed until the review crops and final PDF/PNG are inspected by ChatGPT/user.
