# JLC / KiCad Netlist Equivalence Report

Final status: **PASS**

## Summary

- total_jlc_nets_parsed: 15
- total_jlc_raw_nets_parsed: 15
- total_jlc_canonical_nets_parsed: 14
- total_kicad_nets_parsed: 14
- total_jlc_connections: 57
- total_kicad_connections: 57
- mapped_refs_count: 21
- mapped_nets_count: 15
- unmapped_refs_count: 0
- unmapped_nets_count: 0
- blocker_count: 0
- warning_count: 0

## Per-Net Comparison

| Net | Status | JLC Pins | KiCad Pins | Missing | Extra |
| --- | --- | --- | --- | --- | --- |
| +12V | PASS | A1.1, C3.2, C4.2, XS3.1, XS5.2 | A1.1, C3.2, C4.2, XS3.1, XS5.2 |  |  |
| +3V3 | PASS | A1.4, C1.1, C2.1, DD1.2, R1.1, R2.1, R3.1, R6.1, XS1.1, XS4.4 | A1.4, C1.1, C2.1, DD1.2, R1.1, R2.1, R3.1, R6.1, XS1.1, XS4.4 |  |  |
| BOOT | PASS | DD1.25, R6.2, SB2.2 | DD1.25, R6.2, SB2.2 |  |  |
| DQ | PASS | DD1.33, R2.2, XS1.2 | DD1.33, R2.2, XS1.2 |  |  |
| EN | PASS | DD1.3, R1.2, SB1.2 | DD1.3, R1.2, SB1.2 |  |  |
| GATE | PASS | DD1.30, R4.1 | DD1.30, R4.1 |  |  |
| GATE_R | PASS | R4.2, R5.1, VT1.1 | R4.2, R5.1, VT1.1 |  |  |
| GND | PASS | A1.2, A1.3, C1.2, C2.2, C3.1, C4.1, DD1.1, DD1.38, DD1.39, R5.2, SB1.1, SB2.1, VT1.3, XS1.3, XS3.2, XS4.3 | A1.2, A1.3, C1.2, C2.2, C3.1, C4.1, DD1.1, DD1.38, DD1.39, R5.2, SB1.1, SB2.1, VT1.3, XS1.3, XS3.2, XS4.3 |  |  |
| HEAT+ | PASS | XS2.2, XS5.1 | XS2.2, XS5.1 |  |  |
| HEAT- | PASS | VT1.2, XS2.1 | VT1.2, XS2.1 |  |  |
| LED | PASS | DD1.24, HL1.2 | DD1.24, HL1.2 |  |  |
| LED_A | PASS | HL1.1, R3.2 | HL1.1, R3.2 |  |  |
| RXD0 | PASS | DD1.34, XS4.2 | DD1.34, XS4.2 |  |  |
| TXD0 | PASS | DD1.35, XS4.1 | DD1.35, XS4.1 |  |  |

## Per-Component Comparison

| Ref | Status | JLC Pin Nets | KiCad Pin Nets |
| --- | --- | --- | --- |
| A1 | PASS | 1:+12V, 2:GND, 3:GND, 4:+3V3 | 1:+12V, 2:GND, 3:GND, 4:+3V3 |
| C1 | PASS | 1:+3V3, 2:GND | 1:+3V3, 2:GND |
| C2 | PASS | 1:+3V3, 2:GND | 1:+3V3, 2:GND |
| C3 | PASS | 1:GND, 2:+12V | 1:GND, 2:+12V |
| C4 | PASS | 1:GND, 2:+12V | 1:GND, 2:+12V |
| DD1 | PASS | 1:GND, 2:+3V3, 24:LED, 25:BOOT, 3:EN, 30:GATE, 33:DQ, 34:RXD0, 35:TXD0, 38:GND, 39:GND | 1:GND, 2:+3V3, 24:LED, 25:BOOT, 3:EN, 30:GATE, 33:DQ, 34:RXD0, 35:TXD0, 38:GND, 39:GND |
| HL1 | PASS | 1:LED_A, 2:LED | 1:LED_A, 2:LED |
| R1 | PASS | 1:+3V3, 2:EN | 1:+3V3, 2:EN |
| R2 | PASS | 1:+3V3, 2:DQ | 1:+3V3, 2:DQ |
| R3 | PASS | 1:+3V3, 2:LED_A | 1:+3V3, 2:LED_A |
| R4 | PASS | 1:GATE, 2:GATE_R | 1:GATE, 2:GATE_R |
| R5 | PASS | 1:GATE_R, 2:GND | 1:GATE_R, 2:GND |
| R6 | PASS | 1:+3V3, 2:BOOT | 1:+3V3, 2:BOOT |
| SB1 | PASS | 1:GND, 2:EN | 1:GND, 2:EN |
| SB2 | PASS | 1:GND, 2:BOOT | 1:GND, 2:BOOT |
| VT1 | PASS | 1:GATE_R, 2:HEAT-, 3:GND | 1:GATE_R, 2:HEAT-, 3:GND |
| XS1 | PASS | 1:+3V3, 2:DQ, 3:GND | 1:+3V3, 2:DQ, 3:GND |
| XS2 | PASS | 1:HEAT-, 2:HEAT+ | 1:HEAT-, 2:HEAT+ |
| XS3 | PASS | 1:+12V, 2:GND | 1:+12V, 2:GND |
| XS4 | PASS | 1:TXD0, 2:RXD0, 3:GND, 4:+3V3 | 1:TXD0, 2:RXD0, 3:GND, 4:+3V3 |
| XS5 | PASS | 1:HEAT+, 2:+12V | 1:HEAT+, 2:+12V |

## Blockers

- None

## Warnings

- None
