# hardware

This directory stores the staged hardware design documentation for the project.

The current goal of the hardware section is not to claim that a final production-ready board has already been completed. Instead, the goal is to document the hardware design logic clearly enough that the project can move from simulation to a realistic hardware implementation in a controlled and traceable way.

## Current Stage

The current project stage is:

- simulation first
- hardware architecture clarified in documentation
- final schematic and board-level implementation deferred to a later stage

This means the project already has a validated simulation connection structure in Wokwi, but that simulation connection structure is not the same as a formal engineering schematic.

## Confirmed Hardware Modules

The following hardware directions are already confirmed at the project level:

- main controller: ESP32 development board
- temperature sensor: DS18B20
- control output: PWM
- power-driving approach: low-side MOSFET switching
- debugging and observation: serial interface, status LED, and simulation-side waveform observation

## Not Yet Completed

The following items are not yet claimed as completed:

- final hardware schematic
- final PCB design
- real-hardware power-stage validation
- complete component selection and protection design
- production-oriented board design

## File Guide

- `pin-map.md`: current edge-node pin allocation and basic connection meaning
- `system-overview.md`: hardware-module view of the current edge node
- `power-and-driver-plan.md`: staged design notes for power input, regulation, and MOSFET driving
- `schematic-notes.md`: notes on what the current Wokwi connection can express and what a formal schematic still needs to cover

## Important Note About Wokwi

The current Wokwi `diagram.json` is a simulation connection diagram.

It is useful for:

- validating pin assignment
- verifying basic signal paths
- checking simulation wiring logic
- supporting early-stage simulation and control experiments

It should not be treated as:

- a complete electrical schematic
- a board-level implementation drawing
- a final hardware design package

The purpose of this directory is to bridge that gap step by step.

Documentation sync date: 2026-04-04.
