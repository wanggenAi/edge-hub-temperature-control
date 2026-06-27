# ESP32 Temperature Control Unit Schematic

This folder contains the editable draw.io reconstruction of the ESP32 temperature-control node electrical schematic. The drawing is generated from `render_esp32_gost_schematic.js` so that the source can be rebuilt, exported, and checked consistently.

## Files

- `esp32_temperature_node_gost.drawio` - editable vector source.
- `esp32_temperature_node_gost.png` - exported raster preview.
- `esp32_temperature_node_gost.svg` - exported vector image.
- `esp32_temperature_node_gost.pdf` - exported one-page PDF.
- `render_esp32_gost_schematic.js` - repeatable source generator.

## Drawing Rules Applied

- Plain closed outer and inner rectangular frames only.
- No coordinate grid labels, border ticks, segmented border lines, decorative titles, or standalone notes.
- English-only explanatory content, except the retained document type code `Э3`.
- ASCII net labels: `+3V3`, `+12V`, `GND`, `DQ`, `GATE`, `LED`, `BOOT`, `TXD0`, `RXD0`, `IO23`.
- Right-top `List of Elements` table and right-bottom English title block.
- Orthogonal schematic wires, with repeated power and signal nets shown by labels where this avoids long crossings.

## Designation Mapping

- `DD1` - ESP32-WROOM-32 module.
- `VT1` - N-channel MOSFET heater switch.
- `HL1` - red status LED.
- `XS1` - DS18B20 sensor connector.
- `XS2` - heater connector.
- `XS3` - power input connector.
- `XS4` - UART/service connector.
- `SB1`, `SB2` - reset and boot push buttons.
- `A1` - DC/DC converter.

## Rebuild and Check

```bash
bash tools/run_schematic_checks.sh
```

The script regenerates the draw.io source, exports PNG/SVG/PDF, runs `tools/schematic_lint.py`, writes reports under `build/reports`, and attempts KiCad ERC only when a KiCad schematic source and `kicad-cli` are available.
