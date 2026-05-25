# AI Handoff

## Current Commit
728b4a46

## Current Branch
main

## Project Goal
This project is `edge-hub-temperature-control`, used for graduation thesis and defense materials. The active schematic workflow is exact JLC symbol fidelity inside the locked BSTU draw.io frame: middle-circuit component symbols must be cloned from `hardware/eda/jlc_schematic_original.svg`, while the BSTU draw.io frame owns the outer frame, right-top List of Elements, and right-bottom Title Block.

## Workflow Status
- Current checkpoint: `Exact JLC Symbol Fidelity`.
- Previous approximate JLC-style/layout pass was not enough; user clarified the middle circuit must reuse exact JLC original symbol groups, not redraw approximations.
- This round deep-clones every component symbol group from the JLC source SVG and only applies translate placement, regenerated orthogonal wires, and school/canonical ref/net text.
- Right-top List of Elements and right-bottom Title Block remain locked to the mother draw.io geometry/style/content.
- Visual Review Result is still `PENDING_REVIEW` until Web ChatGPT/user inspects the regenerated screenshot pack.

## Automated Check Result
- JLC/KiCad topology equivalence: `PASS` (`build/reports/jlc_kicad_netlist_equivalence_exact_symbol.json`).
- Master table lock: `PASS` (`build/reports/bstu_master_table_lock_exact_symbol.json`).
- Export lint: `PASS`, `0` errors (`build/reports/final-exact-symbol-export/export_artifact_lint.json`).
- JLC exact-symbol layout audit: `PASS`, `0` blockers, `0` warnings (`build/reports/jlc_style_layout_audit_exact_symbol.json`).
- Exact symbol fidelity: `PASS`, 21/21 symbol groups, 0 missing, 0 geometry/stroke/path-count mismatches.
- Pytest: `23 passed` for BOM, table lock, JLC-style layout, and JLC/KiCad equivalence tests.
- PNG size: `6431 x 4654 px`.
- Visual Review Pack manifest: regenerated at `hardware/eda/exports/final/review_crops/manifest.json`.
- Protected-file diff guards: `PASS` for JLC source SVG/PDF/netlist/BOM, KiCad schematic/symbol/project, ref mapping, schematic model, and net equivalence rules.

## Visual Review Result
`PENDING_REVIEW`

## Human Approval Status
`NOT_APPROVED_YET`

## Final Artifacts
- Final draw.io: `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.drawio`
- Final SVG: `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.svg`
- Final PDF: `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.pdf`
- Final PNG: `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.png`

## Visual Review Pack
- Final PNG: `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.png`
- Final PDF: `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.pdf`
- Visual review index: `docs/final_visual_review_index.md`
- Manifest: `hardware/eda/exports/final/review_crops/manifest.json`
- Overview: `hardware/eda/exports/final/review_crops/overview.png`
- JLC-style block: `hardware/eda/exports/final/review_crops/jlc_style_block.png`
- DD1 area: `hardware/eda/exports/final/review_crops/dd1_area.png`
- Reset/boot/LED area: `hardware/eda/exports/final/review_crops/reset_boot_led_area.png`
- Sensor/UART area: `hardware/eda/exports/final/review_crops/sensor_uart_area.png`
- Heater/power area: `hardware/eda/exports/final/review_crops/heater_power_area.png`
- Power area: `hardware/eda/exports/final/review_crops/power_area.png`
- Right-top List of Elements full: `hardware/eda/exports/final/review_crops/element_list_full.png`
- Right-top List of Elements top: `hardware/eda/exports/final/review_crops/element_list_top.png`
- Right-top List of Elements middle: `hardware/eda/exports/final/review_crops/element_list_middle.png`
- Right-top List of Elements bottom: `hardware/eda/exports/final/review_crops/element_list_bottom.png`
- Right-bottom Title Block: `hardware/eda/exports/final/review_crops/title_block_full.png`

## What Changed This Round
- `hardware/eda/tools/create_jlc_style_schematic_drawio.py` now assigns anonymous source symbols by exact JLC source bbox to avoid swapping visually similar connector/switch symbols.
- Each generated component symbol has `data-role="jlc_symbol_exact_clone"` and metadata records exact fidelity: source/final element counts, tag counts, path counts, geometry hash, stroke/style hash, allowed transform, and verdict.
- `hardware/eda/tools/audit_jlc_style_layout.py` now fails on exact symbol fidelity violations such as geometry changes, path-count changes, stroke/style changes, missing groups, or internal element-count changes.
- `tests/test_jlc_style_schematic_layout.py` now asserts exact-symbol metadata and 21/21 PASS fidelity entries.
- Sensor/UART, heater, and power review crop boxes were tightened to match their names and reviewer purpose.
- Final draw.io/SVG/PDF/PNG and visual review crops were regenerated.

## Strict No-Change Statement
This round did not modify:
- `hardware/eda/functiondiagramYUANLITU.drawio`
- `hardware/eda/jlc_schematic_original.svg`
- `hardware/eda/jlc_schematic_original.pdf`
- `hardware/eda/jlc_netlist_altium.tel`
- `hardware/eda/jlc_schematic_bom.csv`
- `hardware/kicad_schematic/esp32_temperature_control_unit.kicad_sch`
- `hardware/kicad_schematic/esp32_temperature_control_unit.kicad_sym`
- `hardware/kicad_schematic/esp32_temperature_control_unit.kicad_pro`
- `hardware/eda/ref_mapping.yaml`
- `hardware/eda/schematic_model.yaml`
- `hardware/eda/net_equivalence_rules.yaml`
- topology, confirmed refs, canonical net names, BOM quantities, mother table geometry, title block geometry, or document code.

## Reviewer Instruction
Upload the Visual Review Pack screenshots to Web ChatGPT reviewer. Ask specifically whether this exact-symbol checkpoint satisfies the user's requirement that all middle-circuit symbols are directly reused from JLC original SVG, and whether the sensor/UART, heater, and power crops now show the intended modules clearly. Do not claim Visual Review PASS until reviewer inspects the new images.
