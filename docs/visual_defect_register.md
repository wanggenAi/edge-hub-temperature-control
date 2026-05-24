# Visual Defect Register

This register tracks human-style visual review defects that are outside automated topology/lint checks. The current JLC-style round has a Web ChatGPT visual checkpoint pass, but final university/teacher approval is not claimed here.

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
| LAYOUT_OPTIMIZER_SCORE | Pending reviewer check | User requested an engineering layout optimizer instead of one-off manual placement. | Added quantified score fields and candidate evaluation. Current visually approved placement remains the best candidate: previous score `71.344`, new score `71.344`, adopted candidate `false`. |
| BOM_MPN_MANUFACTURER_GAPS | Needs BOM confirmation | User requested real purchasable MPN/model in Name and Manufacturer in Note. The JLC BOM lacks true Manufacturer Part and/or Manufacturer for 19 refs. | Added BOM audit. Known MPN/model fields from the BOM are visible where available. Missing MPN/Manufacturer values are reported as `NEEDS_BOM_MPN_CONFIRMATION`; no AI-invented values were added. |

## Current Checkpoint Notes

- Workflow: `JLC-style faithful layout beautification`, engineering layout optimizer checkpoint.
- The generated middle schematic uses the JLC original SVG style, school refs, and canonical net labels.
- The right-top List of Elements and right-bottom Title Block are locked to `hardware/eda/functiondiagramYUANLITU.drawio`.
- Web ChatGPT review of the previous checkpoint: `NEEDS_MINOR_REPAIR`.
- Web ChatGPT review of Round 2: `VISUAL_PASS_FOR_CHECKPOINT`.
- Current optimizer pass changes review status back to `PENDING_REVIEW` until the refreshed screenshots are reviewed.
- Automated result is not human visual approval.
- Visual Review Result: `PENDING_REVIEW`.
- Human Approval Status: `FINAL_TEACHER_APPROVAL_NOT_CLAIMED`.
