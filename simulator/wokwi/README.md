# Wokwi Edge Node Simulation

## Purpose

This directory contains the first formal Wokwi-based edge node simulation for the project. It is the current runnable result of the repository and serves as the engineering baseline for the edge control layer.

The simulation focuses on validating the embedded node behavior rather than building the full three-layer system at this stage.

## Current Implementation

The current simulation node already verifies the following functions:

- ESP32 minimum runtime
- serial communication through the Wokwi Serial Monitor
- DS18B20 temperature acquisition
- GPIO2 heartbeat status LED
- GPIO18 PWM output
- simple proportional control V1 based on a target temperature

This means the repository has moved beyond a documentation-only skeleton and now includes a concrete runnable edge-layer result.

## Files

- `diagram.json`: Wokwi circuit definition, including ESP32, DS18B20, pull-up resistor, status LED, LED resistor, Logic Analyzer, and Serial Monitor wiring
- `sketch.ino`: Arduino sketch for the current edge node simulation
- `libraries.txt`: required Arduino libraries for the Wokwi project
- `README.md`: simulation usage and engineering notes

## How To Run In Wokwi

1. Open Wokwi and create or import an ESP32 Arduino project.
2. Copy the files from this directory into the Wokwi project:
   - `diagram.json`
   - `sketch.ino`
   - `libraries.txt`
3. Start the simulation.
4. Open the Serial Monitor to observe runtime logs.
5. Observe:
   - DS18B20 temperature readings
   - target temperature
   - control error
   - PWM duty cycle
   - GPIO2 heartbeat LED activity
   - GPIO18 waveform through the Logic Analyzer

## Current Control Logic

The current controller is a simple proportional controller.

Control flow:

1. Read the temperature from DS18B20.
2. Compute the error between the target temperature and the measured temperature.
3. Convert the error into a PWM duty cycle using a proportional gain.
4. Clamp the PWM output to the valid duty range.
5. Output the duty cycle on GPIO18.
6. Print target temperature, current temperature, error, and PWM duty cycle to the serial interface.

This version is intentionally simple so that the control behavior is easy to explain, verify, and document in the thesis.

## Current Limitations

The current simulation is still an open thermal loop in practice.

- The DS18B20 reading does not actually change according to PWM output in the current Wokwi setup.
- The current implementation only validates the edge node control logic and signal path.
- A true thermal closed loop has not been formed yet.

## Next Step

The next simulation milestone is to introduce a virtual thermal model.

Planned work:

- implement a virtual thermal model
- make temperature evolve with PWM output
- upgrade the simulation into a more complete closed-loop temperature control demonstration

That step will provide a much stronger basis for later control experiments, performance analysis, and thesis writing.
