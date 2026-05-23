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
- KiCad ERC report: `build/reports/kicad_schematic_erc_final_candidate.json`
- Pytest: `13 passed in 1.06s`
- Export lint errors: `0`
- Export lint report: `build/reports/final-thesis-candidate-export/export_artifact_lint.json`
- Required school refs present: `True`
- Canonical nets present: `True`
- Forbidden refs/stale nets absent: `True`
- Source frame diff clean: `True`
- KiCad source/symbol/project diff clean: `True`

## KiCad Block Placement

- Embed bbox: `{'x': 191.0, 'y': 178.0, 'width': 2070.0, 'height': 1440.0}`
- Main width share: `0.835`
- Main height share: `0.686`
- Gap to List of Elements: `297.18` SVG units
- Gap to Title Block: `489.42` SVG units

## List Of Elements

- ESP32 BOM text present: `True`
- Required BOM groups: Capacitors, Resistors, Semiconductor Devices, Switching Components, Connectors, Power Modules

## Title Block

- ESP32 title block text present: `True`
- Legacy template title text absent: `True`

## Review Crops

- `overview`: `hardware/eda/exports/final/review_crops/overview.png`
- `kicad_block`: `hardware/eda/exports/final/review_crops/kicad_block.png`
- `element_list`: `hardware/eda/exports/final/review_crops/element_list.png`
- `title_block`: `hardware/eda/exports/final/review_crops/title_block.png`
- `heater_power_area`: `hardware/eda/exports/final/review_crops/heater_power_area.png`
- `dd1_area`: `hardware/eda/exports/final/review_crops/dd1_area.png`

## Conclusion

No automated blocker is recorded in this QA package if all booleans above are `True`, export lint reports `0`, and ERC is `PASSED`.
The user still needs to visually inspect the review crops and final PDF/PNG before thesis insertion.
