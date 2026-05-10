# Enclosure Workflow Notes

## Current V1 Flow

1. Maintain the real PCB exports in `references/pcb/`.
2. Use `cq_editor/enclosure_v1_presentation.py` for defense/demo screenshots.
3. Use `cq_editor/enclosure_v1_print.py` for final printable part review.
3. Use `cq_editor/pcb_reference.py` for the manually adjustable dimensions that should stay under engineering control.
4. Use `cq_editor/enclosure_v1.py` directly only when changing geometry or
   debugging individual helper objects.
5. Use `layout_debug` in CQ-editor to sanity-check outer size, PCB offset,
   passage positions, and service-opening positions.
6. Export only the printable objects when preparing a first print:
   `printable_body`, `lid_print`, and `electronics_cover_print`.

For object-by-object meaning, see `docs/model-map.md`.

## Dimension Ownership

- `DXF` should drive the board outline and mounting-hole centers.
- `STEP` should drive component-height checks and connector collision checks.
- wall thickness, print clearance, lid thickness, and opening tolerance should remain manual parameters.

## Current V1 Mechanical Features

- chamber-first body with separated electronics bay
- removable lid with insert rim and front grip tab
- removable electronics-bay cover
- PCB support shelf with side guide rails and end stops
- divider pass-through rings for DS18B20 and heater wiring
- DS18B20 C-style probe clip near the sample region
- heater wire strain-relief base near the heater passage
- raised thermal safety barrier between the sample area and heater zone
- service-opening frames for debug, power, and TS1 access

## Export Notes

- `printable_body` is the main printable body.
- `lid_print` is moved near the build plane for standalone lid export.
- `electronics_cover_print` is moved away from the body for standalone cover
  export.
- Reference helpers such as `board_proxy`, `step_reference`,
  `sample_area_reference`, `heater_pad`, and `heater_placeholder` are for visual
  checking only.
- Run automated export and inspection with the existing CadQuery environment:

```bash
/Users/seker./miniforge/envs/cadq/bin/python hardware/enclosure/scripts/export_enclosure_v1.py --strict
```

The export script produces:

- STL and STEP files for `printable_body`, `lid_print`, and
  `electronics_cover_print`
- `layout_debug.json` with the model's key dimensions and positions
- `inspection_report.json` with blocking geometry checks and intentional notes
- PNG previews for the transparent presentation view, bounding boxes, all
  printable parts, body ISO/top/front inspection, and lid ISO inspection

Treat a non-zero `--strict` run as a geometry regression that should be fixed
before printing.

## Why This Starts Manually

For a V1 printed enclosure, a partially manual workflow is more robust than full automation.

It gives us:

- clear ownership of trusted dimensions
- easy inspection in CQ-editor
- fewer hidden failures when a PCB export is incomplete
