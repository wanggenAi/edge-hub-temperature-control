# Enclosure Workflow Notes

## Current V1 Flow

1. Maintain the real PCB exports in `references/pcb/`.
2. Keep the CQ-editor entry point in `cq_editor/enclosure_v1.py`.
3. Use `cq_editor/pcb_reference.py` for the manually adjustable dimensions that should stay under engineering control.
4. Preview the enclosure in CQ-editor while comparing against the real PCB `STEP` and `DXF`.

## Dimension Ownership

- `DXF` should drive the board outline and mounting-hole centers.
- `STEP` should drive component-height checks and connector collision checks.
- wall thickness, print clearance, lid thickness, and opening tolerance should remain manual parameters.

## Why This Starts Manually

For a V1 printed enclosure, a partially manual workflow is more robust than full automation.

It gives us:

- clear ownership of trusted dimensions
- easy inspection in CQ-editor
- fewer hidden failures when a PCB export is incomplete
