# Wokwi Edge Node Simulation

## Purpose

This directory contains the current runnable Wokwi-based edge node module for the project. It is the implementation baseline for the edge control layer and now represents the V3 simulation stage.

The goal of this directory is to support engineering verification of the temperature control node in a way that is easy to run, easy to observe, and easy to describe in the thesis.

## Current Version

The current version is **Temperature Control Node V3**.

Compared with V2, this version upgrades the controller from simple proportional control to PI control. The purpose is to reduce the steady-state error that remained in the V2 closed-loop simulation.

## Current Implementation

The current simulation node verifies the following functions:

- ESP32 minimum runtime
- serial communication through the Wokwi Serial Monitor
- DS18B20 temperature acquisition as a physical reference value
- GPIO2 heartbeat status LED
- GPIO18 PWM output
- PI controller with a bounded integral state
- virtual thermal model driven by PWM duty cycle
- observable closed-loop temperature regulation behavior

This is an important engineering step because the simulation has moved from "control interface verification" to "closed-loop process verification".

## Files

- `diagram.json`: Wokwi circuit definition, including ESP32, DS18B20, pull-up resistor, status LED, LED resistor, Logic Analyzer, and Serial Monitor wiring
- `sketch.ino`: Arduino sketch for the V3 edge node simulation with a virtual thermal model and PI controller
- `libraries.txt`: required Arduino libraries for the Wokwi project
- `README.md`: simulation usage notes and engineering explanation

## How To Run In Wokwi

1. Open Wokwi and create or import an ESP32 Arduino project.
2. Copy the files from this directory into the Wokwi project:
   - `diagram.json`
   - `sketch.ino`
   - `libraries.txt`
3. Start the simulation.
4. Open the Serial Monitor.
5. Observe:
   - the simulated temperature rising from a lower initial value
   - the control error gradually shrinking
   - the PWM duty cycle decreasing as the simulated temperature approaches the target
   - the GPIO2 heartbeat LED activity
   - the GPIO18 waveform through the Logic Analyzer

## Current Control Logic

The current controller is now a simplified PI controller.

Control flow:

1. Read the DS18B20 value as a physical reference reading.
2. Use the simulated temperature as the controlled process variable.
3. Compute the error between target temperature and simulated temperature.
4. Accumulate the integral of the error once per control period.
5. Apply simple integral limiting to prevent excessive windup.
6. Compute the PI control output and clamp it to the valid PWM range.
7. Update the thermal model using the PWM duty cycle.
8. Print both human-readable and CSV-style logs for observation and later experiment recording.

This controller is intentionally simple. It is not the final industrial-grade control algorithm of the project, but it is appropriate for the current stage because it is stable, explainable, and suitable for simulation-based experiments.

## Virtual Thermal Model

The V3 simulation still uses the same first-order virtual thermal model.

State variables and parameters:

- `simulatedTemperatureC`: current simulated controlled temperature
- `ambientTemperatureC`: surrounding environment temperature
- `normalizedDuty`: PWM duty cycle normalized to the range `[0, 1]`
- `heatGainPerCycleC`: heating contribution introduced by PWM during one control cycle
- `coolingFactor`: passive cooling intensity toward ambient temperature

Model equation:

```text
simTemp = simTemp + heatGainPerCycleC * dutyNorm
                    - coolingFactor * (simTemp - ambientTemp)
```

Interpretation:

- the heating term increases with PWM duty cycle
- the cooling term increases when the simulated temperature is above ambient temperature
- the combined effect produces a gradual rise-and-settle behavior that is easy to observe and explain

## Current Limitations

The current V3 simulation is a useful engineering closed loop, but it is still simplified.

- The controller acts on the simulated temperature rather than on a DS18B20 value that physically changes with heating.
- The thermal model is a first-order approximation and does not yet represent more complex thermal lag, disturbance, or sensor dynamics.
- The controller is still a simplified PI controller rather than a full industrial PID strategy.

## Why This Step Matters

This version is important because it reduces a key limitation of V2:

- steady-state error under proportional-only control

to:

- a more accurate closed-loop regulation process with a bounded integral term

That makes the simulation much more valuable for thesis writing, experiment planning, and later control refinement.

## Experiment Support

The serial output now includes:

- a human-readable runtime line
- a CSV-style line for later copy-and-analyze workflows

This makes it easier to support:

- P vs PI comparison experiments
- parameter tuning
- step-response observation
- steady-state error experiments
- disturbance experiments
- future comparison with simplified PID versions

## Recommended Next Steps

The most natural next tasks are:

- compare P and PI under the same thermal-model parameters
- tune `Kp` and `Ki` for clearer response behavior
- run step-response and steady-state error experiments
- add disturbance injection scenarios
- upgrade the controller from proportional control to simplified PID when needed
