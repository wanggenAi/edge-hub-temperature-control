# BOM MPN / Manufacturer Audit Report

- Status: `WARN`
- Warnings: `10`
- Errors: `0`
- Source BOM: `hardware/eda/jlc_schematic_bom.csv`
- External confirmation file: `hardware/eda/bom_mpn_manufacturer_confirmed.json`
- Final draw.io: `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.drawio`
- Unresolved MPN/Manufacturer items: `0`
- External confirmations used: `21`
- Package/order review warnings: `10`

## Policy

- Name column should use real purchasable model/MPN plus specs.
- Note column should use Manufacturer, not supplier.
- Missing source MPN/Manufacturer is reported as `NEEDS_BOM_MPN_CONFIRMATION`; no AI-invented values are created.

## Unresolved Items

No unresolved MPN/Manufacturer items.

## Package / Ordering Review Items

- `C3` `CL31A107MQHNNNE` `Samsung Electro-Mechanics`: The JLC BOM footprint says C0603. A common purchasable 100 uF MLCC found in distributor data is 1206, so package/voltage must be reviewed before ordering.
- `HL1` `LED0603-RD_RED` `NEEDS_CONFIRMATION`: manufacturer not verified beyond JLCPCB Assembly supplier listing
- `XS2` `2P-P3.81_KF2EDGV-3.81-2P` `NEEDS_CONFIRMATION`: manufacturer not verified beyond JLCPCB Assembly supplier listing
- `XS3` `2P-P3.81_KF2EDGV-3.81-2P` `NEEDS_CONFIRMATION`: manufacturer not verified beyond JLCPCB Assembly supplier listing
- `XS5` `KF301-2P` `NEEDS_CONFIRMATION`: manufacturer not verified beyond JLCPCB Assembly supplier listing
- `VT1` `NMOS3400` `NEEDS_CONFIRMATION`: manufacturer not verified beyond JLCPCB Assembly supplier listing
- `A1` `Header45.08-4P` `NEEDS_CONFIRMATION`: This is the connector/interface used for the DC/DC module in the source BOM, not the DC/DC converter module manufacturer itself. DC/DC converter/module-interface manufacturer requires user purchase confirmation
- `XS4` `Header45.08-4P` `NEEDS_CONFIRMATION`: manufacturer not verified beyond JLCPCB Assembly supplier listing
- `SB1` `TactswitchSMT6x6x7_5` `NEEDS_CONFIRMATION`: manufacturer not verified beyond JLCPCB Assembly supplier listing
- `SB2` `TactswitchSMT6x6x7_5` `NEEDS_CONFIRMATION`: manufacturer not verified beyond JLCPCB Assembly supplier listing

## Findings

- `warning` `BOM_PACKAGE_OR_ORDERING_REVIEW_REQUIRED` `C3`: External BOM source is usable for the table, but package/ordering details need review before purchasing
- `warning` `BOM_PACKAGE_OR_ORDERING_REVIEW_REQUIRED` `HL1`: External BOM source is usable for the table, but package/ordering details need review before purchasing
- `warning` `BOM_PACKAGE_OR_ORDERING_REVIEW_REQUIRED` `XS2`: External BOM source is usable for the table, but package/ordering details need review before purchasing
- `warning` `BOM_PACKAGE_OR_ORDERING_REVIEW_REQUIRED` `XS3`: External BOM source is usable for the table, but package/ordering details need review before purchasing
- `warning` `BOM_PACKAGE_OR_ORDERING_REVIEW_REQUIRED` `XS5`: External BOM source is usable for the table, but package/ordering details need review before purchasing
- `warning` `BOM_PACKAGE_OR_ORDERING_REVIEW_REQUIRED` `VT1`: External BOM source is usable for the table, but package/ordering details need review before purchasing
- `warning` `BOM_PACKAGE_OR_ORDERING_REVIEW_REQUIRED` `A1`: External BOM source is usable for the table, but package/ordering details need review before purchasing
- `warning` `BOM_PACKAGE_OR_ORDERING_REVIEW_REQUIRED` `XS4`: External BOM source is usable for the table, but package/ordering details need review before purchasing
- `warning` `BOM_PACKAGE_OR_ORDERING_REVIEW_REQUIRED` `SB1`: External BOM source is usable for the table, but package/ordering details need review before purchasing
- `warning` `BOM_PACKAGE_OR_ORDERING_REVIEW_REQUIRED` `SB2`: External BOM source is usable for the table, but package/ordering details need review before purchasing
