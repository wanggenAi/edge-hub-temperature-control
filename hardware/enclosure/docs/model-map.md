# Enclosure V1 Model Map

This file explains what each CadQuery object in `cq_editor/enclosure_v1.py` is for.

The model has three different kinds of objects:

- final printable parts: export these to STL/STEP for printing
- physical subfeatures: real geometry that is merged into a printable part
- visual references: helper objects used only to understand placement and clearance

## CQ-editor Entry Points

There are two main files to open in CQ-editor:

- `cq_editor/enclosure_v1_presentation.py`: defense/demo view with a transparent enclosure and visible PCB/system layout
- `cq_editor/enclosure_v1_print.py`: fabrication view with only final printable objects

The shared model implementation is `cq_editor/enclosure_v1.py`.

## Optional View Modes

Set `DISPLAY_OPTIONS["view_mode"]` in `cq_editor/pcb_reference.py`:

- `demo`: default presentation view; shows the enclosure, opened lid, real PCB STEP reference, PCB outline, sample area, heater, and sensor references
- `simple`: human-readable geometry overview; shows only the main body, open lid, PCB size reference, and bottom cover preview
- `debug`: detailed engineering mode; shows individual helpers and references separately
- `print`: export review mode; shows only the standalone printable objects

Most of the time, prefer the dedicated entry files above instead of manually changing view modes.

## Final Printable Parts

These are the only objects that should normally be exported for fabrication.

| Object | Meaning | Print/export? |
| --- | --- | --- |
| `printable_body` | Main enclosure body with integrated shelf, wire pass-through rings, sensor clip, heater strain relief, and service-opening frames | Yes |
| `lid_print` | Removable top lid, moved down to the build plane for standalone printing | Yes |
| `electronics_cover_print` | Bottom electronics-bay cover, moved away from the body for standalone printing | Yes |

## Main Preview Objects

These help you understand the enclosure shape in CQ-editor.

| Object | Meaning | Print/export? |
| --- | --- | --- |
| `enclosure_body` | Main shell only, before helper features are merged in | No, use `printable_body` instead |
| `lid_closed` | Lid shown in the closed position for fit inspection | No |
| `lid_open` | Lid shown above the box so the chamber is easier to see | No |
| `electronics_cover` | Bottom cover shown near its installed position | No, use `electronics_cover_print` instead |

## PCB And Electronics Helpers

These keep the board and service access understandable.

| Object | Meaning | Print/export? |
| --- | --- | --- |
| `board_proxy` | Simplified PCB-size block from the DXF board outline | No |
| `step_reference` | Real PCB STEP import, when available, for component clearance checking | No |
| `pcb_support_shelf` | Physical shelf, side rails, and end stops that hold the PCB | Included in `printable_body` |
| `power_service_pad` | Visual landing area for power-side wiring/service planning | No |
| `ts1_service_pad` | Visual landing area for TS1 thermal-switch wiring planning | No |

## Thermal Chamber Helpers

These explain the chamber, heater, and sensor layout.

| Object | Meaning | Print/export? |
| --- | --- | --- |
| `sample_area_reference` | Visual sample-placement zone in the heated chamber | No |
| `heater_pad` | Visual heater placement footprint | No |
| `heater_placeholder` | Visual heater body proxy for clearance checking | No |
| `thermal_barrier` | Physical raised safety barrier that separates the sample area from the heater zone | Included in `printable_body` |
| `sensor_probe_reference` | Visual DS18B20 probe location reference | No |
| `sensor_probe_clip` | Physical support bracket with a foot, mast, arm, and C-clip that holds the sensor probe at a repeatable height | Included in `printable_body` |
| `sensor_passage_ring` | Physical reinforcement ring around the sensor wire pass-through | Included in `printable_body` |
| `heater_passage_ring` | Physical reinforcement ring around the heater wire pass-through | Included in `printable_body` |
| `heater_strain_relief` | Physical heater wire strain-relief clamp with a wire channel, lead-in guide, and tie-down bridges | Included in `printable_body` |

## Service Opening Features

The openings themselves are cut into `enclosure_body`. These frame objects reinforce the openings and are merged into `printable_body`.

| Object | Meaning | Print/export? |
| --- | --- | --- |
| `debug_opening_frame` | Reinforcement around the debug access window | Included in `printable_body` |
| `power_opening_frame` | Reinforcement around the power access window | Included in `printable_body` |
| `ts1_opening_frame` | Reinforcement around the TS1 wiring access window | Included in `printable_body` |

## Mental Model

Think of the model like this:

```text
printable_body
  = enclosure_body
  + PCB shelf/rails/stops
  + sensor/heater pass-through rings
  + sensor probe clip
  + heater wire strain relief
  + thermal safety barrier between sample and heater zones
  + service opening frames

lid_print
  = lid shell
  + insert rim
  + front grip tab

electronics_cover_print
  = bottom cover plate moved to the print plane
```

## Automated Sanity Check

Run this before printing or after changing any dimensions:

```bash
/Users/seker./miniforge/envs/cadq/bin/python hardware/enclosure/scripts/export_enclosure_v1.py --strict
```

The command exports printable parts, renders preview PNGs, and writes `inspection_report.json`.
A passing `--strict` run means no blocking envelope/build-plane issue was detected.
