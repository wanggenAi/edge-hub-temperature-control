# AI Handoff

## Current Commit
786d8c7

## Current Branch
main

## Project Goal
This project is `edge-hub-temperature-control`, used for graduation thesis and defense materials. The current engineering focus is schematic normalization, confirmed reference-designator mapping, reproducible draw.io generation, and thesis-quality technical drawings.

## Reviewer Input Used
- Firefox ChatGPT accepted checkpoint `a97a1b1`.
- Reviewer said the `XS1` + `R2` sensor checkpoint is acceptable.
- Reviewer said the R2-XS1 local `DQ` short wire and DD1 `DQ` canonical net label relationship are acceptable.
- Reviewer explicitly requested the next increment should be only:
  - `XS4` UART / service connector block
- Reviewer explicitly said not to draw BOOT in the same round.
- Reviewer suggested later order:
  - BOOT block: `R6` + `SB2`
  - heater driver
  - power module
  - final layout refinement
  - export SVG/PDF/PNG

## What Was Done In This Round
- Added a renderer checkpoint mode: `--uart-block`.
- The generated draw.io checkpoint now contains only:
  - `DD1`
  - `R1`
  - `SB1`
  - `R3`
  - `HL1`
  - `C1`
  - `C2`
  - `R2`
  - `XS1`
  - `XS4`
- Added the UART/service connector as a small independent interface block:
  - `XS4` value displayed as `UART service`
  - pin `1`: `+3V3`
  - pin `2`: `GND`
  - pin `3`: `RXD0`
  - pin `4`: `TXD0`
- Used short stubs plus canonical net labels for the UART/service nets.
- Did not draw long direct wires from DD1 to XS4 in this checkpoint.
- Kept this checkpoint intentionally small:
  - did not add BOOT (`R6` / `SB2`)
  - did not add `R4` / `R5`
  - did not add `C3` / `C4`
  - did not add `XS2` / `XS3` / `XS5`
  - did not add `VT1`
  - did not add `A1`
- Added a regression test proving the UART checkpoint includes only the intended refs and still passes generated draw.io lint.
- Re-generated `hardware/eda/functiondiagramYUANLITU.generated.drawio`.
- Did not modify `hardware/eda/functiondiagramYUANLITU.drawio`.
- Did not export SVG/PDF/PNG in this round.

## Files Changed
- `hardware/eda/functiondiagramYUANLITU.generated.drawio`
- `hardware/eda/render_esp32_drawio.js`
- `tests/test_visual_schematic_lint.py`
- `docs/ai_handoff/latest_handoff.md`

## Validation Performed
- `node --check hardware/eda/render_esp32_drawio.js`
  - Result: passed
- `node hardware/eda/render_esp32_drawio.js --write-output --uart-block --output /tmp/uart.generated.drawio`
  - Result: passed
  - Summary: `dd1BlockRendered=true`, `resetLedBlockRendered=true`, `decouplingBlockRendered=true`, `sensorBlockRendered=true`, `uartBlockRendered=true`, `finalCircuitRendered=false`
- `python3 tools/visual_schematic_lint.py /tmp/uart.generated.drawio --mode generated --reports-dir /tmp/uart-reports`
  - Result: passed
- `node hardware/eda/render_esp32_drawio.js --write-output --uart-block`
  - Result: generated `hardware/eda/functiondiagramYUANLITU.generated.drawio`
- `python3 tools/visual_schematic_lint.py hardware/eda/functiondiagramYUANLITU.generated.drawio --mode generated --reports-dir build/reports/generated-uart-block`
  - Result: passed
- `python3 tools/visual_schematic_lint.py hardware/eda/functiondiagramYUANLITU.drawio --mode template --reports-dir build/reports/template-check`
  - Result: passed
- `python3 -m pytest tests/test_visual_schematic_lint.py -q`
  - Result: `18 passed`
- `git diff --check -- hardware/eda/render_esp32_drawio.js tests/test_visual_schematic_lint.py`
  - Result: passed
- `git diff --quiet -- hardware/eda/functiondiagramYUANLITU.drawio`
  - Result: passed; source template was not modified

## Current Repository State Notes
- `hardware/eda/functiondiagramYUANLITU.drawio` remains unmodified.
- `hardware/eda/functiondiagramYUANLITU.generated.drawio` contains the incremental checkpoint: DD1 + RESET/EN + LED status + C1/C2 decoupling + XS1/R2 sensor block + XS4 UART/service connector.
- Locked frame, right-side List of Elements, and Title Block are still protected by template lint.
- No final export files were generated.
- No KiCad ERC is expected for this draw.io-only workflow.
- The working tree still contains unrelated uncommitted changes from other project areas.

## Open Questions For ChatGPT
1. Is the `XS4` UART/service connector checkpoint acceptable with short `+3V3`, `GND`, `RXD0`, and `TXD0` stubs plus canonical net labels?
2. Should the next Codex increment add only the BOOT block (`R6` + `SB2`) as previously suggested?
3. Should the BOOT block use the same pattern as RESET/EN: `R6` pull-up plus `SB2` to GND, with short local stubs and canonical `BOOT` net label?
4. Should `XS4` placement be adjusted before adding BOOT, or should layout refinement wait until all blocks exist?

## Risks / Uncertainties
- This is still an incremental visual checkpoint, not the full schematic.
- `RXD0` / `TXD0` are represented by canonical net labels rather than long direct DD1-XS4 wires.
- BOOT, heater driver, and power module are still intentionally not rendered.
- The lint is visual/geometric; it does not perform electrical ERC.
- No SVG/PDF/PNG export has been generated yet because this phase is still focused on draw.io construction.

## Suggested Next Step
Ask ChatGPT to review commit `786d8c7`. If accepted, the next Codex phase should add only one small block, likely BOOT (`R6` + `SB2`), depending on reviewer guidance.
