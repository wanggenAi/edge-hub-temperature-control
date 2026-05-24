# BOM MPN / Manufacturer Confirmation Package

This package is for human confirmation before changing the right-top List of Elements text.
It is generated from the JLC BOM and does not invent missing MPN or Manufacturer values.

## Summary

- Generated at: `2026-05-25T00:22:08`
- Source BOM: `hardware/eda/jlc_schematic_bom.csv`
- Ref mapping: `hardware/eda/ref_mapping.yaml`
- Audit report: `build/reports/bom_mpn_manufacturer_audit.json`
- Total school refs: `21`
- Confirmed from source BOM: `2`
- Needs human confirmation: `19`

## Human Fill-In Instructions

- Fill only `User confirmed MPN` and `User confirmed Manufacturer` for rows marked `needs_human_confirmation`.
- Do not use `LCSC` as Manufacturer unless the actual manufacturer is confirmed to be LCSC.
- Keep supplier PN separate from Manufacturer/MPN evidence.
- After confirmation, update only List of Elements cell values; keep mother draw.io table geometry locked.

## Grouped Confirmation Rows

| Status | Refs | Source refs | Qty | Current source name/comment | Footprint | Source MPN | Source Manufacturer | Supplier PN | User confirmed MPN | User confirmed Manufacturer |
| --- | --- | --- | ---: | --- | --- | --- | --- | --- | --- | --- |
| needs_human_confirmation | C1, C4 | C1, C4 | 2 | 0.1uF | C0603 | **MISSING** | **MISSING** | - |  |  |
| needs_human_confirmation | C2 | C2 | 1 | 10uF | C0603 | **MISSING** | **MISSING** | - |  |  |
| needs_human_confirmation | C3 | C3 | 1 | 100uF | C0603 | **MISSING** | **MISSING** | - |  |  |
| confirmed_from_source_bom | XS1 | CN1 | 1 | XH-3PA | CONN-TH_3P-P2.50_ZHOURI_XH-3PA | XH-3PA | ZHOURI(洲日) | C5258884 |  |  |
| needs_human_confirmation | HL1 | D1 | 1 | 红色LED | LED0603-RD_RED | **MISSING** | **MISSING** | C9900005314 |  |  |
| needs_human_confirmation | XS2, XS3 | J2_heater, J_Power | 2 | 2P-P3.81_KF2EDGV-3.81-2P | CONN-TH_2P-P3.81_KF2EDGV-3.81-2P | 2P-P3.81_KF2EDGV-3.81-2P | **MISSING** | C9900017459 |  |  |
| needs_human_confirmation | XS5 | J_TS1 | 1 | KF301-2P接线端子 | CONN-TH_XY301V-A-5.0-2P | KF301-2P接线端子 | **MISSING** | C9900016950 |  |  |
| needs_human_confirmation | VT1 | Q1 | 1 | NMOS3400 | SOT-23-3_L2.9-W1.3-P0.95-LS2.4-BR | NMOS3400 | **MISSING** | C9900021947 |  |  |
| needs_human_confirmation | R1, R5, R6 | R1, R5, R6 | 3 | 10K | R0603 | **MISSING** | **MISSING** | - |  |  |
| needs_human_confirmation | R2 | R2 | 1 | 4.7K | R0603 | **MISSING** | **MISSING** | - |  |  |
| needs_human_confirmation | R3 | R3 | 1 | 330R | R0603 | **MISSING** | **MISSING** | - |  |  |
| needs_human_confirmation | R4 | R4 | 1 | 100R | R0603 | **MISSING** | **MISSING** | - |  |  |
| confirmed_from_source_bom | DD1 | U1 | 1 | ESP32-WROOM-32 | WIFIM-SMD_ESP-WROOM-32 | ESP32-WROOM-32 | ESPRESSIF(乐鑫) | C95209 |  |  |
| needs_human_confirmation | A1, XS4 | U3_buck, U7 | 2 | Header45.08-4P | CONN-TH_4P-P5.00_HEADER45.08-4P | Header45.08-4P | **MISSING** | C9900007553 |  |  |
| needs_human_confirmation | SB1, SB2 | U3_reset, U4_boot | 2 | TactswitchSMT6x6x7_5 | KEY-SMD_4P-L6.0-W6.0-P4.50-LS9.0 | TactswitchSMT6x6x7_5 | **MISSING** | C9900000320 |  |  |

## Per-Ref Details

| Status | Ref | Source ref | Comment | Footprint | Value | Source MPN | Source Manufacturer | Supplier PN | Supplier | Missing fields |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| needs_human_confirmation | C1 | C1 | 0.1uF | C0603 | 0.1uF | **MISSING** | **MISSING** | - | - | Manufacturer Part, Manufacturer |
| needs_human_confirmation | C4 | C4 | 0.1uF | C0603 | 0.1uF | **MISSING** | **MISSING** | - | - | Manufacturer Part, Manufacturer |
| needs_human_confirmation | C2 | C2 | 10uF | C0603 | 10uF | **MISSING** | **MISSING** | - | - | Manufacturer Part, Manufacturer |
| needs_human_confirmation | C3 | C3 | 100uF | C0603 | 100uF | **MISSING** | **MISSING** | - | - | Manufacturer Part, Manufacturer |
| confirmed_from_source_bom | XS1 | CN1 | XH-3PA | CONN-TH_3P-P2.50_ZHOURI_XH-3PA | - | XH-3PA | ZHOURI(洲日) | C5258884 | LCSC | - |
| needs_human_confirmation | HL1 | D1 | 红色LED | LED0603-RD_RED | - | **MISSING** | **MISSING** | C9900005314 | LCSC | Manufacturer Part, Manufacturer |
| needs_human_confirmation | XS2 | J2_heater | 2P-P3.81_KF2EDGV-3.81-2P | CONN-TH_2P-P3.81_KF2EDGV-3.81-2P | - | 2P-P3.81_KF2EDGV-3.81-2P | **MISSING** | C9900017459 | LCSC | Manufacturer |
| needs_human_confirmation | XS3 | J_Power | 2P-P3.81_KF2EDGV-3.81-2P | CONN-TH_2P-P3.81_KF2EDGV-3.81-2P | - | 2P-P3.81_KF2EDGV-3.81-2P | **MISSING** | C9900017459 | LCSC | Manufacturer |
| needs_human_confirmation | XS5 | J_TS1 | KF301-2P接线端子 | CONN-TH_XY301V-A-5.0-2P | - | KF301-2P接线端子 | **MISSING** | C9900016950 | LCSC | Manufacturer |
| needs_human_confirmation | VT1 | Q1 | NMOS3400 | SOT-23-3_L2.9-W1.3-P0.95-LS2.4-BR | - | NMOS3400 | **MISSING** | C9900021947 | LCSC | Manufacturer |
| needs_human_confirmation | R1 | R1 | 10K | R0603 | 10K | **MISSING** | **MISSING** | - | - | Manufacturer Part, Manufacturer |
| needs_human_confirmation | R5 | R5 | 10K | R0603 | 10K | **MISSING** | **MISSING** | - | - | Manufacturer Part, Manufacturer |
| needs_human_confirmation | R6 | R6 | 10K | R0603 | 10K | **MISSING** | **MISSING** | - | - | Manufacturer Part, Manufacturer |
| needs_human_confirmation | R2 | R2 | 4.7K | R0603 | 4.7K | **MISSING** | **MISSING** | - | - | Manufacturer Part, Manufacturer |
| needs_human_confirmation | R3 | R3 | 330R | R0603 | 330R | **MISSING** | **MISSING** | - | - | Manufacturer Part, Manufacturer |
| needs_human_confirmation | R4 | R4 | 100R | R0603 | 100R | **MISSING** | **MISSING** | - | - | Manufacturer Part, Manufacturer |
| confirmed_from_source_bom | DD1 | U1 | ESP32-WROOM-32 | WIFIM-SMD_ESP-WROOM-32 | - | ESP32-WROOM-32 | ESPRESSIF(乐鑫) | C95209 | LCSC | - |
| needs_human_confirmation | A1 | U3_buck | Header45.08-4P | CONN-TH_4P-P5.00_HEADER45.08-4P | - | Header45.08-4P | **MISSING** | C9900007553 | LCSC | Manufacturer |
| needs_human_confirmation | XS4 | U7 | Header45.08-4P | CONN-TH_4P-P5.00_HEADER45.08-4P | - | Header45.08-4P | **MISSING** | C9900007553 | LCSC | Manufacturer |
| needs_human_confirmation | SB1 | U3_reset | TactswitchSMT6x6x7_5 | KEY-SMD_4P-L6.0-W6.0-P4.50-LS9.0 | - | TactswitchSMT6x6x7_5 | **MISSING** | C9900000320 | LCSC | Manufacturer |
| needs_human_confirmation | SB2 | U4_boot | TactswitchSMT6x6x7_5 | KEY-SMD_4P-L6.0-W6.0-P4.50-LS9.0 | - | TactswitchSMT6x6x7_5 | **MISSING** | C9900000320 | LCSC | Manufacturer |

## Source-Confirmed Items

- `XS1` from `CN1`: MPN `XH-3PA`, Manufacturer `ZHOURI(洲日)`.
- `DD1` from `U1`: MPN `ESP32-WROOM-32`, Manufacturer `ESPRESSIF(乐鑫)`.

## Items Requiring Confirmation

- `C1` from `C1`: missing `Manufacturer Part, Manufacturer`; source hint `0.1uF`; supplier PN `-`.
- `C4` from `C4`: missing `Manufacturer Part, Manufacturer`; source hint `0.1uF`; supplier PN `-`.
- `C2` from `C2`: missing `Manufacturer Part, Manufacturer`; source hint `10uF`; supplier PN `-`.
- `C3` from `C3`: missing `Manufacturer Part, Manufacturer`; source hint `100uF`; supplier PN `-`.
- `HL1` from `D1`: missing `Manufacturer Part, Manufacturer`; source hint `红色LED`; supplier PN `C9900005314`.
- `XS2` from `J2_heater`: missing `Manufacturer`; source hint `2P-P3.81_KF2EDGV-3.81-2P`; supplier PN `C9900017459`.
- `XS3` from `J_Power`: missing `Manufacturer`; source hint `2P-P3.81_KF2EDGV-3.81-2P`; supplier PN `C9900017459`.
- `XS5` from `J_TS1`: missing `Manufacturer`; source hint `KF301-2P接线端子`; supplier PN `C9900016950`.
- `VT1` from `Q1`: missing `Manufacturer`; source hint `NMOS3400`; supplier PN `C9900021947`.
- `R1` from `R1`: missing `Manufacturer Part, Manufacturer`; source hint `10K`; supplier PN `-`.
- `R5` from `R5`: missing `Manufacturer Part, Manufacturer`; source hint `10K`; supplier PN `-`.
- `R6` from `R6`: missing `Manufacturer Part, Manufacturer`; source hint `10K`; supplier PN `-`.
- `R2` from `R2`: missing `Manufacturer Part, Manufacturer`; source hint `4.7K`; supplier PN `-`.
- `R3` from `R3`: missing `Manufacturer Part, Manufacturer`; source hint `330R`; supplier PN `-`.
- `R4` from `R4`: missing `Manufacturer Part, Manufacturer`; source hint `100R`; supplier PN `-`.
- `A1` from `U3_buck`: missing `Manufacturer`; source hint `Header45.08-4P`; supplier PN `C9900007553`.
- `XS4` from `U7`: missing `Manufacturer`; source hint `Header45.08-4P`; supplier PN `C9900007553`.
- `SB1` from `U3_reset`: missing `Manufacturer`; source hint `TactswitchSMT6x6x7_5`; supplier PN `C9900000320`.
- `SB2` from `U4_boot`: missing `Manufacturer`; source hint `TactswitchSMT6x6x7_5`; supplier PN `C9900000320`.
