# BOM MPN / Manufacturer Audit Report

- Status: `WARN`
- Warnings: `19`
- Errors: `0`
- Source BOM: `hardware/eda/jlc_schematic_bom.csv`
- Final draw.io: `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.drawio`
- Unresolved MPN/Manufacturer items: `19`

## Policy

- Name column should use real purchasable model/MPN plus specs.
- Note column should use Manufacturer, not supplier.
- Missing source MPN/Manufacturer is reported as `NEEDS_BOM_MPN_CONFIRMATION`; no AI-invented values are created.

## Unresolved Items

- `C1` from `C1`: missing `Manufacturer Part, Manufacturer`; supplier PN `` supplier ``
- `C4` from `C4`: missing `Manufacturer Part, Manufacturer`; supplier PN `` supplier ``
- `C2` from `C2`: missing `Manufacturer Part, Manufacturer`; supplier PN `` supplier ``
- `C3` from `C3`: missing `Manufacturer Part, Manufacturer`; supplier PN `` supplier ``
- `HL1` from `D1`: missing `Manufacturer Part, Manufacturer`; supplier PN `C9900005314` supplier `LCSC`
- `XS2` from `J2_heater`: missing `Manufacturer`; supplier PN `C9900017459` supplier `LCSC`
- `XS3` from `J_Power`: missing `Manufacturer`; supplier PN `C9900017459` supplier `LCSC`
- `XS5` from `J_TS1`: missing `Manufacturer`; supplier PN `C9900016950` supplier `LCSC`
- `VT1` from `Q1`: missing `Manufacturer`; supplier PN `C9900021947` supplier `LCSC`
- `R1` from `R1`: missing `Manufacturer Part, Manufacturer`; supplier PN `` supplier ``
- `R5` from `R5`: missing `Manufacturer Part, Manufacturer`; supplier PN `` supplier ``
- `R6` from `R6`: missing `Manufacturer Part, Manufacturer`; supplier PN `` supplier ``
- `R2` from `R2`: missing `Manufacturer Part, Manufacturer`; supplier PN `` supplier ``
- `R3` from `R3`: missing `Manufacturer Part, Manufacturer`; supplier PN `` supplier ``
- `R4` from `R4`: missing `Manufacturer Part, Manufacturer`; supplier PN `` supplier ``
- `A1` from `U3_buck`: missing `Manufacturer`; supplier PN `C9900007553` supplier `LCSC`
- `XS4` from `U7`: missing `Manufacturer`; supplier PN `C9900007553` supplier `LCSC`
- `SB1` from `U3_reset`: missing `Manufacturer`; supplier PN `C9900000320` supplier `LCSC`
- `SB2` from `U4_boot`: missing `Manufacturer`; supplier PN `C9900000320` supplier `LCSC`

## Findings

- `warning` `NEEDS_BOM_MPN_CONFIRMATION` `C1`: Source BOM lacks true MPN and/or Manufacturer; do not invent values for List of Elements
- `warning` `NEEDS_BOM_MPN_CONFIRMATION` `C4`: Source BOM lacks true MPN and/or Manufacturer; do not invent values for List of Elements
- `warning` `NEEDS_BOM_MPN_CONFIRMATION` `C2`: Source BOM lacks true MPN and/or Manufacturer; do not invent values for List of Elements
- `warning` `NEEDS_BOM_MPN_CONFIRMATION` `C3`: Source BOM lacks true MPN and/or Manufacturer; do not invent values for List of Elements
- `warning` `NEEDS_BOM_MPN_CONFIRMATION` `HL1`: Source BOM lacks true MPN and/or Manufacturer; do not invent values for List of Elements
- `warning` `NEEDS_BOM_MPN_CONFIRMATION` `XS2`: Source BOM lacks true MPN and/or Manufacturer; do not invent values for List of Elements
- `warning` `NEEDS_BOM_MPN_CONFIRMATION` `XS3`: Source BOM lacks true MPN and/or Manufacturer; do not invent values for List of Elements
- `warning` `NEEDS_BOM_MPN_CONFIRMATION` `XS5`: Source BOM lacks true MPN and/or Manufacturer; do not invent values for List of Elements
- `warning` `NEEDS_BOM_MPN_CONFIRMATION` `VT1`: Source BOM lacks true MPN and/or Manufacturer; do not invent values for List of Elements
- `warning` `NEEDS_BOM_MPN_CONFIRMATION` `R1`: Source BOM lacks true MPN and/or Manufacturer; do not invent values for List of Elements
- `warning` `NEEDS_BOM_MPN_CONFIRMATION` `R5`: Source BOM lacks true MPN and/or Manufacturer; do not invent values for List of Elements
- `warning` `NEEDS_BOM_MPN_CONFIRMATION` `R6`: Source BOM lacks true MPN and/or Manufacturer; do not invent values for List of Elements
- `warning` `NEEDS_BOM_MPN_CONFIRMATION` `R2`: Source BOM lacks true MPN and/or Manufacturer; do not invent values for List of Elements
- `warning` `NEEDS_BOM_MPN_CONFIRMATION` `R3`: Source BOM lacks true MPN and/or Manufacturer; do not invent values for List of Elements
- `warning` `NEEDS_BOM_MPN_CONFIRMATION` `R4`: Source BOM lacks true MPN and/or Manufacturer; do not invent values for List of Elements
- `warning` `NEEDS_BOM_MPN_CONFIRMATION` `A1`: Source BOM lacks true MPN and/or Manufacturer; do not invent values for List of Elements
- `warning` `NEEDS_BOM_MPN_CONFIRMATION` `XS4`: Source BOM lacks true MPN and/or Manufacturer; do not invent values for List of Elements
- `warning` `NEEDS_BOM_MPN_CONFIRMATION` `SB1`: Source BOM lacks true MPN and/or Manufacturer; do not invent values for List of Elements
- `warning` `NEEDS_BOM_MPN_CONFIRMATION` `SB2`: Source BOM lacks true MPN and/or Manufacturer; do not invent values for List of Elements
