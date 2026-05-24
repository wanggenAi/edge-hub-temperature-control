# Visual Defect Register

This register tracks human-style visual review defects that are outside KiCad ERC/topology equivalence. Visual approval remains pending until the regenerated crops are reviewed.

| ID | Status | Reviewer Finding | Repair Action / Constraint |
| --- | --- | --- | --- |
| WHOLE_SHEET_IMBALANCE | Round 2 repair applied | Middle circuit was too scattered, too small, and left large blank areas. | Round 1 compacted the schematic around DD1. Round 2 made a focused polish pass without topology changes; visual approval is still pending reviewer inspection. |
| KICAD_BLOCK_FRAGMENTED | Round 2 repair applied | DD1, reset/boot/LED, sensor/UART, heater/power relationships felt weak. | Functional blocks remain grouped by signal direction. Round 2 tightened the sensor/UART and heater/power visual groupings. |
| LOCAL_BLOCK_ISLAND_FEEL | Round 2 repair applied | Local blocks looked like isolated short-label islands. | Local true-wire chains were kept. Round 2 adjusted labels and nearby wires to reduce DD1 right-side clutter while preserving canonical nets. |
| SENSOR_UART_RELATION_WEAK | Round 2 repair applied | XS1/XS4 relationship to DD1 was visually weak. | XS4 was moved under XS1 as part of a tighter sensor/UART column; connector labels remain canonical and wires remain orthogonal. |
| HEATER_POWER_PATH_WEAK | Round 2 repair applied | +12V, HEAT+, HEAT-, GATE/GATE_R visual paths were weak. | Heater output labels and the MOSFET source label were separated for readability; the heater/power path remains unchanged electrically. |
| ELEMENT_LIST_COMPRESSED | Needs master-table decision | Right-top BOM text is crowded in fixed master table rows. | Master table geometry/style is locked by user instruction. Mark as `NEEDS_MASTER_TABLE_EDIT` if reviewer still finds it unreadable. |
| TITLE_BLOCK_SMALL_FIELD_CROWDING | Needs master-table decision | Right-bottom title block small fields are crowded. | Master title block geometry/style is locked by user instruction. Content/geometry not changed in this repair round. |

## Round 1 Notes

- Automated checks are not a substitute for visual approval.
- The current repair round changes KiCad schematic layout/property/label/wire coordinates only.
- The locked BSTU frame, List of Elements table body, Title Block body, document code, BOM, refs, nets, symbol library, project file, and net-equivalence inputs must remain unchanged.

## Round 2 Notes

- Web ChatGPT reviewer result after Round 1: `CONDITIONAL_PASS` with human approval status `NEEDS_MINOR_REPAIR`.
- Round 2 scope is limited to KiCad middle schematic composition polish:
  - DD1 right-side net labels were staggered to reduce label crowding.
  - XS4 was grouped below XS1 to reduce the sensor/UART island feel.
  - C3/C4 were moved closer to A1 while keeping their original `+12V/GND` nets.
  - Heater/power labels were separated to avoid label collisions near VT1/XS2.
- Right-top List of Elements and right-bottom Title Block remain locked to the master draw.io geometry/style/content. If readability is still rejected, that must be escalated as `NEEDS_MASTER_TABLE_EDIT`.
