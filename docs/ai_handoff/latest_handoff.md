# AI Handoff

## Current Commit
10c2ef4d

## Current Branch
main

## Project Goal
This project is `edge-hub-temperature-control`, used for graduation thesis and defense materials. The active schematic workflow is KiCad-based: KiCad owns the middle electrical schematic, while draw.io owns the BSTU school frame, right-top List of Elements, and right-bottom Title Block.

## Workflow State
- Current round target: correct the previous generated-table rebuild direction.
- New hard rule from user: the master draw.io table geometry, line widths, row/column structure, fonts, alignment, and outer frame are the only accepted standard.
- Generated/final draw.io files may replace table text values only.
- This round does not change KiCad schematic topology, KiCad source files, KiCad exports, original school frame, refs, nets, or confirmed netlist equivalence.

## What Was Done In This Round
- Removed the separate generated-table geometry rule path:
  - deleted `hardware/eda/table_geometry_rules.yaml`
  - deleted `hardware/eda/tools/rebuild_generated_tables.py`
  - deleted `tests/test_bstu_table_geometry.py`
  - deleted `docs/bstu_table_geometry_report.md`
- Added master table lock validation:
  - `hardware/eda/tools/validate_generated_tables_match_master.py`
  - `tests/test_bstu_master_table_lock.py`
  - `docs/bstu_master_table_lock_report.md`
- Updated generated text updaters so they replace only existing master cell `value` text and preserve the table body.
- Updated the embed script to preserve all master List of Elements cells, including edge cells without normal bounding boxes.
- Updated final export and export lint to validate generated/final table objects against the master draw.io table objects.
- Regenerated final draw.io/SVG/PDF/PNG artifacts.
- Updated workflow documentation to replace the old “table rebuild” wording with “master table lock / text-only replacement”.

## Master Table Lock Result
PASS.

Master source:
- `hardware/eda/functiondiagramYUANLITU.drawio`

Generated/final rule:
- compare every master table `mxCell` except `value`
- compare all `mxGeometry` attributes and child points
- fail on changed line width, style, font metadata, alignment, row/column geometry, cell ID, parent, edge/vertex flag, missing cell, or extra table cell
- allow only approved text-cell value changes

Reports:
- Markdown: `docs/bstu_master_table_lock_report.md`
- JSON: `build/reports/bstu_master_table_lock.json`

Measured result:
- Master table cell count: `101`
- Generated table cell count: `101`
- Final table cell count: `101`
- Generated geometry matches master: `true`
- Final geometry matches master: `true`
- Geometry hash: `34ef44b8ced36aa76933db11fa585bb5d57ca868ab93e5d2f95193670983edf0`
- Value-only changed cells per candidate: `36`

## BOM Text Note
The master List of Elements has a fixed row count. To obey the new rule, the ESP32 BOM is merged into the existing master rows instead of adding/removing rows or modifying table geometry. This keeps all required ESP32 refs and descriptions visible while preserving the master table body exactly.

## Validation Performed
- `python3 -m pytest tests/test_bstu_master_table_lock.py tests/test_jlc_kicad_netlist_equivalence.py tests/test_kicad_schematic_workflow.py -q`
  - Result: `27 passed`
- `python3 -m py_compile hardware/eda/tools/validate_generated_tables_match_master.py hardware/eda/tools/update_generated_element_list.py hardware/eda/tools/update_generated_title_block.py hardware/eda/tools/embed_kicad_schematic_into_bstu_frame.py hardware/eda/tools/check_jlc_kicad_netlist_equivalence.py tools/export_artifact_lint.py tests/test_bstu_master_table_lock.py tests/test_jlc_kicad_netlist_equivalence.py tests/test_kicad_schematic_workflow.py`
  - Result: passed
- `/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli sch erc --format json --output build/reports/kicad_schematic_erc_master_table_lock.json hardware/kicad_schematic/esp32_temperature_control_unit.kicad_sch`
  - Result: `0` violations
- `python3 hardware/eda/tools/validate_generated_tables_match_master.py --master hardware/eda/functiondiagramYUANLITU.drawio --candidate hardware/eda/functiondiagramYUANLITU.generated.drawio --final-candidate hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.drawio --report docs/bstu_master_table_lock_report.md --json-report build/reports/bstu_master_table_lock.json`
  - Result: `PASS`
- `python3 tools/export_artifact_lint.py --export-dir hardware/eda/exports/final --basename esp32_temperature_control_unit_electrical_schematic --label final-bstu-table-geometry --reports-dir build/reports/final-master-table-lock-export`
  - Result: `0` errors

## Final Artifacts
- Draw.io: `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.drawio`
- SVG: `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.svg`
- PDF: `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.pdf`
- PNG: `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.png`
- PNG resolution: `6433 x 4670 px`

## Files Changed In Engineering Commit
- `hardware/eda/functiondiagramYUANLITU.generated.drawio`
- `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.drawio`
- `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.svg`
- `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.pdf`
- `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.png`
- `hardware/eda/tools/embed_kicad_schematic_into_bstu_frame.py`
- `hardware/eda/tools/export_final_artifacts.sh`
- `hardware/eda/tools/update_generated_element_list.py`
- `hardware/eda/tools/update_generated_title_block.py`
- `hardware/eda/tools/validate_generated_tables_match_master.py`
- `tools/export_artifact_lint.py`
- `tests/test_bstu_master_table_lock.py`
- `docs/bstu_master_table_lock_report.md`
- `docs/kicad_schematic_workflow.md`
- deleted old generated-table rebuild files listed above

## Files Intentionally Not Changed
- `hardware/eda/functiondiagramYUANLITU.drawio`
- `hardware/kicad_schematic/esp32_temperature_control_unit.kicad_sch`
- `hardware/kicad_schematic/esp32_temperature_control_unit.kicad_sym`
- `hardware/kicad_schematic/esp32_temperature_control_unit.kicad_pro`
- `hardware/kicad_schematic/exports/*`
- `hardware/eda/jlc_netlist_altium.tel`
- `hardware/eda/ref_mapping.yaml`
- `hardware/eda/schematic_model.yaml`
- `hardware/eda/net_equivalence_rules.yaml`
- Confirmed refs and canonical net names
- Schematic topology
- Unrelated dirty files

## ERC Status
PASSED.

KiCad CLI was available:
`/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli`

ERC report:
`build/reports/kicad_schematic_erc_master_table_lock.json`

Summary:
- Total ERC violations: `0`

## Remaining Risks / Human Review Points
1. The table body is now locked to the master draw.io exactly; if a reviewer wants different row count or official GOST cell coordinates, that must be done in the master file first, not in generated/final.
2. Because the master table has limited rows, several BOM items are merged in existing rows. This is intentional under the new “only text replacement” rule but should be reviewed visually for readability.
3. The final PDF/PNG still needs reviewer visual inspection for thesis aesthetics.

## Open Questions For ChatGPT
1. Does this correction properly satisfy the new user rule: master draw.io table body is the only standard and generated/final may only replace text?
2. Is merging BOM items into existing master rows acceptable under a locked-table workflow, or should the master List of Elements itself be manually redesigned first?
3. Are there any additional automated checks needed to prove no table geometry/font/alignment/line-width metadata changed?
4. What should the next focused checkpoint be after this correction?

## Suggested Next Step
Send the new engineering commit and this handoff to ChatGPT reviewer. If accepted, continue only with the next focused reviewer prompt. Do not alter KiCad topology, refs, nets, or the master table body without a specific confirmed issue.
