# BOM MPN / Manufacturer Audit Report

- Status: `WARN`
- Warnings: `2`
- Errors: `0`
- Source BOM: `hardware/eda/jlc_schematic_bom.csv`
- External confirmation file: `hardware/eda/bom_mpn_manufacturer_confirmed.json`
- Final draw.io: `hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.drawio`
- Unresolved MPN/Manufacturer items: `0`
- External confirmations used: `21`
- Package/order review warnings: `2`

## Policy

- Name column should use real purchasable model/MPN plus specs.
- Note column should use Manufacturer, not supplier.
- Missing source MPN/Manufacturer is reported as `NEEDS_BOM_MPN_CONFIRMATION`; no AI-invented values are created.

## Unresolved Items

No unresolved MPN/Manufacturer items.

## Package / Ordering Review Items

- `C3` `CL31A107MQHNNNE` `Samsung Electro-Mechanics`: The JLC BOM footprint says C0603. A common purchasable 100 uF MLCC found in distributor data is 1206, so package/voltage must be reviewed before ordering.
- `A1` `Header45.08-4P` `JLCPCB Assembly`: This is the connector/interface used for the DC/DC module in the source BOM, not the DC/DC converter module manufacturer itself.

## Findings

- `warning` `BOM_PACKAGE_OR_ORDERING_REVIEW_REQUIRED` `C3`: External BOM source is usable for the table, but package/ordering details need review before purchasing
- `warning` `BOM_PACKAGE_OR_ORDERING_REVIEW_REQUIRED` `A1`: External BOM source is usable for the table, but package/ordering details need review before purchasing
