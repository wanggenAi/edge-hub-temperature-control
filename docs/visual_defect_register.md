# Visual Defect Register

This register tracks human-style visual review defects that are outside KiCad ERC/topology equivalence. Visual approval remains pending until the regenerated crops are reviewed.

| ID | Status | Reviewer Finding | Repair Action / Constraint |
| --- | --- | --- | --- |
| WHOLE_SHEET_IMBALANCE | In repair | Middle circuit was too scattered, too small, and left large blank areas. | KiCad symbols, labels, and wire routes were compacted around DD1; no topology/ref/net/BOM changes. |
| KICAD_BLOCK_FRAGMENTED | In repair | DD1, reset/boot/LED, sensor/UART, heater/power relationships felt weak. | Functional blocks were moved closer to the ESP32 core and grouped by signal direction. |
| LOCAL_BLOCK_ISLAND_FEEL | In repair | Local blocks looked like isolated short-label islands. | Local true-wire chains were kept and shortened; labels were moved closer to their functional blocks. |
| SENSOR_UART_RELATION_WEAK | In repair | XS1/XS4 relationship to DD1 was visually weak. | Sensor pull-up/connector and UART connector were moved nearer to DD1 right-side signal pins. |
| HEATER_POWER_PATH_WEAK | In repair | +12V, HEAT+, HEAT-, GATE/GATE_R visual paths were weak. | Heater driver and power sections were compacted; gate pull-down, MOSFET, heater and safety terminal were aligned more tightly. |
| ELEMENT_LIST_COMPRESSED | Needs master-table decision | Right-top BOM text is crowded in fixed master table rows. | Master table geometry/style is locked by user instruction. Mark as `NEEDS_MASTER_TABLE_EDIT` if reviewer still finds it unreadable. |
| TITLE_BLOCK_SMALL_FIELD_CROWDING | Needs master-table decision | Right-bottom title block small fields are crowded. | Master title block geometry/style is locked by user instruction. Content/geometry not changed in this repair round. |

## Round 1 Notes

- Automated checks are not a substitute for visual approval.
- The current repair round changes KiCad schematic layout/property/label/wire coordinates only.
- The locked BSTU frame, List of Elements table body, Title Block body, document code, BOM, refs, nets, symbol library, project file, and net-equivalence inputs must remain unchanged.
