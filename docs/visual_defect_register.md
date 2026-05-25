# Visual Defect Register

This register tracks human-style visual review defects that are outside automated topology/lint checks. The current exact JLC symbol round has a Web ChatGPT visual checkpoint pass and is marked as a thesis insertion candidate package, but final university/teacher approval is not claimed here.

| ID | Status | Reviewer Finding | Repair Action / Constraint |
| --- | --- | --- | --- |
| KICAD_STYLE_REJECTED | Superseded | Previous KiCad-style visual polish did not satisfy the user's real requirement. | Stop maintaining the KiCad-style middle schematic route for final visual output. KiCad remains only a topology verification reference. |
| JLC_SYMBOL_STYLE_REQUIRED | Active | User requires the middle circuit to keep the original JLC schematic symbol shapes and visual style. | `create_jlc_style_schematic_drawio.py` embeds the source JLC SVG body and does not replace resistors, capacitors, LED, MOSFET, switches, connectors, or DD1 with KiCad-style symbols. |
| DD1_PIN_TEXT_LOST_IN_SVG | Repaired in this checkpoint | Parsed JLC SVG had blank DD1 pin text, leaving the ESP32 module too empty in final review crops. | Restored DD1 pin/value labels at JLC source coordinates without changing symbol geometry or topology. |
| WHOLE_SHEET_IMBALANCE | Improved, pending review | Earlier middle block sat too high, leaving excessive bottom blank area. | JLC-style block placement moved down within the A1 main field while preserving gaps to List of Elements and Title Block. |
| MASTER_TABLE_LOCK | Active constraint | Right-top List of Elements and right-bottom Title Block must remain identical to the master draw.io table geometry/style. | Table geometry/style/font/alignment/line-width/cell IDs are locked by `validate_generated_tables_match_master.py`; only approved text values may differ. |
| ELEMENT_LIST_COMPRESSED | Needs master-table decision if rejected | Right-top BOM text can still look compressed because the master table has fixed rows. | Do not secretly edit table geometry. Escalate as `NEEDS_MASTER_TABLE_EDIT` if reviewer rejects readability. |
| TITLE_BLOCK_SMALL_FIELD_CROWDING | Needs master-table decision if rejected | Right-bottom title block small fields may remain crowded because the master title block is locked. | Do not secretly edit title block geometry. Escalate as `NEEDS_MASTER_TABLE_EDIT` if reviewer rejects readability. |
| ROUND2_A1_COMPOSITION_BALANCE | Checkpoint passed | Web ChatGPT reviewer marked the previous JLC-style checkpoint as `NEEDS_MINOR_REPAIR`: the middle schematic was still slightly too small/high for A1. | Enlarged the JLC-style schematic block from 2100 x 1180 to 2260 x 1270 and moved it down while preserving safe gaps to the List of Elements and Title Block. Web ChatGPT Round 2 result: `VISUAL_PASS_FOR_CHECKPOINT`. |
| ROUND2_DD1_PIN_TEXT_HEAVY | Checkpoint passed | DD1 pin labels were restored but visually heavy/dense. | Reduced restored DD1 pin-label and pin-number font sizes without changing pin content, refs, nets, or symbol geometry. Web ChatGPT Round 2 result: `VISUAL_PASS_FOR_CHECKPOINT`. |
| ROUND2_GATE_VT1_CROWDING | Checkpoint passed | R4 / GATE / GATE_R / VT1 area remained mildly crowded. | Moved only overlay labels around GATE/GATE_R/R4/VT1 to reduce local visual pressure; topology and JLC source symbol shape remain unchanged. Web ChatGPT Round 2 result: `VISUAL_PASS_FOR_CHECKPOINT`. |
| ROUND2_POWER_COHESION | Accepted for checkpoint | A1 / C3 / C4 power area can still read as less cohesive because the JLC source body is embedded as one preserved vector block. | No topology or per-symbol shape edit was made. Web ChatGPT accepted this checkpoint; deeper per-JLC-symbol extraction/regrouping remains optional only if a later human reviewer requests it. |
| LAYOUT_OPTIMIZER_SCORE | Checkpoint passed | User requested an engineering layout optimizer instead of one-off manual placement. | Added quantified score fields and candidate evaluation. Current visually approved placement remains the best candidate: previous score `71.344`, new score `71.344`, adopted candidate `false`. Web ChatGPT optimizer review result: `VISUAL_PASS_FOR_CHECKPOINT`. |
| BOM_MPN_MANUFACTURER_GAPS | Needs BOM confirmation | User requested real purchasable MPN/model in Name and Manufacturer in Note. The JLC BOM lacks true Manufacturer Part and/or Manufacturer for 19 refs. | Added BOM audit. Known MPN/model fields from the BOM are visible where available. Missing MPN/Manufacturer values are reported as `NEEDS_BOM_MPN_CONFIRMATION`; no AI-invented values were added. |
| BOM_CONFIRMATION_PACKAGE | Accepted, waiting on user data | Web ChatGPT reviewed the BOM confirmation package and accepted the format. | Result: `BOM_CONFIRMATION_PACKAGE_ACCEPTED`. Stop visual/layout edits. Wait for true MPN/Manufacturer values, then update only right-top List of Elements cell text while preserving mother table geometry. |

## Current Checkpoint Notes

- Workflow: `JLC-style faithful layout beautification`, engineering layout optimizer checkpoint.
- The generated middle schematic uses the JLC original SVG style, school refs, and canonical net labels.
- The right-top List of Elements and right-bottom Title Block are locked to `hardware/eda/functiondiagramYUANLITU.drawio`.
- Web ChatGPT review of the previous checkpoint: `NEEDS_MINOR_REPAIR`.
- Web ChatGPT review of Round 2: `VISUAL_PASS_FOR_CHECKPOINT`.
- Web ChatGPT review of the optimizer Visual Review Pack: `VISUAL_PASS_FOR_CHECKPOINT`.
- Reviewer caveat: this is not final university/teacher approval; the remaining substantive issue is true purchasable MPN/model and Manufacturer data for the right-top List of Elements.
- Web ChatGPT review of the BOM confirmation package: `BOM_CONFIRMATION_PACKAGE_ACCEPTED`.
- Automated result is not human visual approval.
- Visual Review Result: `VISUAL_PASS_FOR_CHECKPOINT`.
- Web ChatGPT review of the exact-symbol Visual Review Pack: `VISUAL_PASS_FOR_CHECKPOINT`.
- Human Approval Status: `FINAL_TEACHER_APPROVAL_NOT_CLAIMED`.

| MIDDLE_REFINEMENT_SCREENSHOT_BLOCK | Pending Web GPT review | Web ChatGPT reviewer returned `NEEDS_MIDDLE_SCHEMATIC_REFINEMENT`: the middle schematic looked like a screenshot block, not a mature engineering drawing. | Reworked `create_jlc_style_schematic_drawio.py` to reuse individual JLC component symbol groups and lay them out into A1 functional zones with orthogonal wiring. Visual Review Result remains `PENDING_REVIEW` until the new screenshot pack is reviewed. |
| MIDDLE_REFINEMENT_POWER_FLOATING | Pending Web GPT review | Reviewer called out HEAT+/HEAT-/XS2/XS3 and C3/C4/A1 as floating/weakly grouped. | Moved heater/power symbols into clearer right-side and lower-right zones; regenerated `heater_power_area.png` and `power_area.png` crops for review. |
| MIDDLE_REFINEMENT_DD1_CROWDING | Pending Web GPT review | Reviewer called out DD1 surrounding wiring as crowded/cropped. | DD1 remains central-left with preserved JLC symbol shape; surrounding reset, UART, boot, gate, LED, and power subareas were separated more clearly. |
| EXACT_JLC_SYMBOL_FIDELITY | Checkpoint passed | User clarified the requirement is exact JLC symbol reuse, not an approximate JLC-style redraw. | The generator now deep-clones each component group from `jlc_schematic_original.svg`; every symbol fidelity entry records source/final element counts, path counts, geometry hash, stroke hash, and allowed translate-only transform. Audit result: 21/21 PASS, 0 blockers. |
| EXACT_REVIEW_CROP_ALIGNMENT | Checkpoint passed | Previous crops mixed module content, especially sensor/UART, heater/power, and power-only areas. | Review crop boxes were tightened so `sensor_uart_area` focuses on R2/XS1/XS4, `heater_power_area` focuses on R4/R5/VT1/XS2/XS5, and `power_area` focuses on XS3/A1/C3/C4. |
| FINAL_THESIS_CANDIDATE_PACKAGE | Accepted by Web ChatGPT reviewer | Web ChatGPT reviewed the exact-symbol Visual Review Pack continuation and returned `Human Approval Status: READY_FOR_FINAL_THESIS_CANDIDATE_PACKAGE`. | Stop moving the middle schematic. Preserve final artifacts, visual review pack, automated evidence, and final package notes. Final university/teacher approval is still not claimed. |
