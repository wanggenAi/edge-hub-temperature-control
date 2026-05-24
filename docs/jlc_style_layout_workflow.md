# JLC-Style Layout Workflow

This checkpoint replaces the rejected KiCad-style middle schematic visual route with a JLC-style faithful layout route.

## Source Of Truth

- Topology source: `hardware/eda/jlc_netlist_altium.tel`
- Topology equivalence reference: `hardware/kicad_schematic/esp32_temperature_control_unit.kicad_sch`
- Visual symbol source: `hardware/eda/jlc_schematic_original.svg`
- Locked school frame/table/title source: `hardware/eda/functiondiagramYUANLITU.drawio`
- Confirmed ref/net mapping: `hardware/eda/ref_mapping.yaml` and `hardware/eda/net_equivalence_rules.yaml`

## Generation

`hardware/eda/tools/create_jlc_style_schematic_drawio.py` crops and embeds the original JLC SVG schematic body into the locked BSTU draw.io frame. It preserves the JLC vector symbol geometry and normalizes only visible school refs and canonical net names. It also restores DD1 pin/value text that is blank in the parsed JLC SVG payload so the A1 review crop remains readable.

The generator writes:

- `hardware/eda/functiondiagramYUANLITU.generated.drawio`
- `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.drawio`
- final SVG/PDF/PNG exports through draw.io CLI

## Locked Areas

The following regions are cloned from `hardware/eda/functiondiagramYUANLITU.drawio` and are not redrawn by the JLC-style generator:

- outer frame
- right-top List of Elements
- right-bottom Title Block

`hardware/eda/tools/validate_generated_tables_match_master.py` verifies that generated/final table geometry, style, line widths, fonts, alignment metadata, and cell IDs match the master. Only approved text-cell value replacement is allowed.

## Audits

Required checks for this workflow:

- JLC/KiCad netlist equivalence: `hardware/eda/tools/check_jlc_kicad_netlist_equivalence.py`
- master table lock: `hardware/eda/tools/validate_generated_tables_match_master.py`
- JLC-style layout audit: `hardware/eda/tools/audit_jlc_style_layout.py`
- export lint: `tools/export_artifact_lint.py --label final-jlc-style-layout`
- visual review package: `hardware/eda/tools/create_final_schematic_review_package.py`

## Human Review Boundary

Automated checks can verify topology equivalence, locked table geometry, visible refs/nets, stale-name removal, export existence, PNG size, and absence of KiCad-style markers. They do not grant final human visual approval.

Current human visual status remains `PENDING_REVIEW` until ChatGPT/user reviews the screenshot pack in `docs/final_visual_review_index.md`.
