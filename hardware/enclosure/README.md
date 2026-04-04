# Enclosure Modeling Workspace

This directory is the working area for the PCB-driven enclosure model.

The goal of this workspace is to let us iterate on a practical V1 3D-printable enclosure in CQ-editor without redesigning the rest of the repository.

## Directory Guide

- `cq_editor/`: CadQuery entry scripts intended to be opened directly in CQ-editor
- `references/pcb/`: real PCB reference files such as exported `STEP` and `DXF`
- `docs/`: short workflow notes for enclosure development
- `exports/`: generated STL and STEP output files, ignored by git

## Recommended First Use

1. Place the real PCB reference files in `references/pcb/`.
2. Open `cq_editor/enclosure_v1.py` in CQ-editor.
3. Run the script and confirm the placeholder enclosure preview appears.
4. Replace the placeholder board dimensions in `cq_editor/pcb_reference.py` with the real measured values until we wire in the external references more deeply.

## Current Status

This is an initial project scaffold.

It already gives you:

- a stable place for enclosure code
- a CQ-editor-friendly entry script
- a small parameter file for board and enclosure tuning
- a documented location for the real PCB `STEP` and `DXF`

It does not yet fully consume the external reference files automatically.

That is intentional for V1: we keep the modeling workflow robust and inspectable before adding more automation.

Documentation sync date: 2026-04-04.
