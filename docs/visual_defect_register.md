# Visual Defect Register

This register tracks human-style visual review defects that are outside automated topology/lint checks. Visual approval remains pending until the regenerated crops are reviewed.

| ID | Status | Reviewer Finding | Repair Action / Constraint |
| --- | --- | --- | --- |
| KICAD_STYLE_REJECTED | Superseded | Previous KiCad-style visual polish did not satisfy the user's real requirement. | Stop maintaining the KiCad-style middle schematic route for final visual output. KiCad remains only a topology verification reference. |
| JLC_SYMBOL_STYLE_REQUIRED | Active | User requires the middle circuit to keep the original JLC schematic symbol shapes and visual style. | `create_jlc_style_schematic_drawio.py` embeds the source JLC SVG body and does not replace resistors, capacitors, LED, MOSFET, switches, connectors, or DD1 with KiCad-style symbols. |
| DD1_PIN_TEXT_LOST_IN_SVG | Repaired in this checkpoint | Parsed JLC SVG had blank DD1 pin text, leaving the ESP32 module too empty in final review crops. | Restored DD1 pin/value labels at JLC source coordinates without changing symbol geometry or topology. |
| WHOLE_SHEET_IMBALANCE | Improved, pending review | Earlier middle block sat too high, leaving excessive bottom blank area. | JLC-style block placement moved down within the A1 main field while preserving gaps to List of Elements and Title Block. |
| MASTER_TABLE_LOCK | Active constraint | Right-top List of Elements and right-bottom Title Block must remain identical to the master draw.io table geometry/style. | Table geometry/style/font/alignment/line-width/cell IDs are locked by `validate_generated_tables_match_master.py`; only approved text values may differ. |
| ELEMENT_LIST_COMPRESSED | Needs master-table decision if rejected | Right-top BOM text can still look compressed because the master table has fixed rows. | Do not secretly edit table geometry. Escalate as `NEEDS_MASTER_TABLE_EDIT` if reviewer rejects readability. |
| TITLE_BLOCK_SMALL_FIELD_CROWDING | Needs master-table decision if rejected | Right-bottom title block small fields may remain crowded because the master title block is locked. | Do not secretly edit title block geometry. Escalate as `NEEDS_MASTER_TABLE_EDIT` if reviewer rejects readability. |

## Current Checkpoint Notes

- Workflow: `JLC-style faithful layout beautification`.
- The generated middle schematic uses the JLC original SVG style, school refs, and canonical net labels.
- The right-top List of Elements and right-bottom Title Block are locked to `hardware/eda/functiondiagramYUANLITU.drawio`.
- Automated result is not human visual approval.
- Visual Review Result: `PENDING_REVIEW`.
