# Enclosure Modeling Workspace

This directory is the working area for the PCB-driven enclosure model.

The goal of this workspace is to let us iterate on a practical V1 3D-printable enclosure in CQ-editor without redesigning the rest of the repository.

## Directory Guide

- `cq_editor/`: CadQuery entry scripts intended to be opened directly in CQ-editor
- `references/pcb/`: real PCB reference files such as exported `STEP` and `DXF`
- `docs/`: short workflow notes for enclosure development
- `exports/`: generated STL and STEP output files, ignored by git

Start with `docs/model-map.md` if the CQ-editor object list feels too dense.
It explains which objects are final printable parts, real physical subfeatures,
and visual references.

## Recommended First Use

1. Place the real PCB reference files in `references/pcb/`.
2. Open `cq_editor/enclosure_v1_presentation.py` in CQ-editor for thesis-defense
   screenshots and walkthroughs.
3. Open `cq_editor/enclosure_v1_print.py` in CQ-editor when reviewing final
   printable parts.
4. Export `printable_body`, `lid_print`, and `electronics_cover_print` when a
   first physical print is needed.

The shared model implementation still lives in `cq_editor/enclosure_v1.py`.
The presentation and print files are intentionally small CQ-editor entry points
for two different audiences.

## Two CQ-editor Entry Points

- `cq_editor/enclosure_v1_presentation.py`: defense/demo view. It uses a
  transparent enclosure body and shows the real PCB reference, PCB outline,
  heated sample area, heater location, and temperature sensor reference.
- `cq_editor/enclosure_v1_print.py`: fabrication view. It shows only the final
  printable parts: `printable_body`, `lid_print`, and
  `electronics_cover_print`.
- `cq_editor/enclosure_v1.py`: shared model source. Use this when changing
  geometry or debugging individual helper objects.

## Current Status

This is an active V1 enclosure model.

It already gives you:

- a stable place for enclosure code
- a CQ-editor-friendly entry script
- a small parameter file for board and enclosure tuning
- a documented location for the real PCB `STEP` and `DXF`
- a chamber-first enclosure layout with a separated electronics bay
- PCB support shelf and side guide rails
- DS18B20 probe clip and divider pass-through
- heater wire strain-relief helper
- raised thermal safety barrier between sample and heater zones
- lid insert and front grip tab

It still does not fully consume every external reference automatically.

That is intentional for V1: we keep the modeling workflow robust and inspectable before adding more automation.

## Current Printable Objects

- `printable_body`: main body with integrated support, guide, passage, frame,
  sensor-clip, heater strain-relief, and thermal safety-barrier features
- `lid_print`: lid positioned for standalone export/printing
- `electronics_cover_print`: bottom electronics-bay cover positioned for
  standalone export/printing

Display-only helper/reference objects such as `board_proxy`, `step_reference`,
`heater_placeholder`, and `sample_area_reference` should not be exported as
printed parts.

## Automated Export And Inspection

Use the existing CadQuery environment when exporting or checking the model:

```bash
/Users/seker./miniforge/envs/cadq/bin/python hardware/enclosure/scripts/export_enclosure_v1.py --strict
```

The script exports STL/STEP files, writes `layout_debug.json` and
`inspection_report.json`, and renders PNG previews under `exports/v1/`.
Generated exports are intentionally ignored by git.

The current automated inspection checks:

- printable body stays inside the nominal enclosure envelope
- integrated body helpers stay inside the body envelope
- printable parts do not go below the build plane
- lid pull-tab extension is reported as intentional information

The preview output includes both presentation images and print-inspection
images, including `preview_presentation_transparent_iso.png` and
`preview_all_parts_iso.png`.

Documentation sync date: 2026-05-09.
