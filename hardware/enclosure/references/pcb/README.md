# PCB Reference Files

Place the real PCB reference files for enclosure development in this directory.

Recommended naming:

- `pcb_assembly.step`
- `pcb_outline.dxf`

Use them with the following intent:

- `STEP`: component height, connector body envelope, collision checking
- `DXF`: board outline, mounting-hole centers, 2D reference geometry

For V1, these files are stored here first and then consumed gradually by the CadQuery workflow.
