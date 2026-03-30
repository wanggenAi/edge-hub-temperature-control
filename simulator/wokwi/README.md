# Wokwi Edge Node Simulation

## Purpose

This directory contains the current runnable Wokwi-based edge node module for the project. It is the implementation baseline for the edge control layer and now represents the V3.1 simulation stage.

The goal of this directory is to support engineering verification of the temperature control node in a way that is easy to run, easy to observe, and easy to describe in the thesis.

## Current Version

The current version is **Temperature Control Node V3.1**.

Compared with the initial V3 PI version, this tuned V3.1 version focuses on reducing overshoot and improving convergence smoothness while keeping the controller simple and explainable.

## Current Implementation

The current simulation node verifies the following functions:

- ESP32 minimum runtime
- serial communication through the Wokwi Serial Monitor
- DS18B20 temperature acquisition as a physical reference value
- GPIO2 heartbeat status LED
- GPIO18 PWM output
- tuned PI controller with a bounded integral state
- virtual thermal model driven by PWM duty cycle
- telemetry message abstraction aligned with the MQTT interface design
- serial-simulated telemetry publish in JSON-like payload form
- minimal public MQTT broker integration for telemetry publish
- runtime-config-based control parameters
- params/set subscription with minimal runtime parameter application
- observable closed-loop temperature regulation behavior

This is an important engineering step because the simulation has moved from "control interface verification" to "closed-loop process verification".

## Files

- `diagram.json`: Wokwi circuit definition, including ESP32, DS18B20, pull-up resistor, status LED, LED resistor, Logic Analyzer, and Serial Monitor wiring
- `sketch.ino`: single-file implementation for the current simulation node, including control logic, message structures, and minimal MQTT connectivity
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
   - the JSON-style telemetry payload printed to the serial output
   - MQTT telemetry publish attempts to the public test broker
   - incoming `params/set` messages printed to the serial output

## Current Control Logic

The current controller is a simplified PI controller with light anti-windup behavior.

Control flow:

1. Read the DS18B20 value as a physical reference reading.
2. Use the simulated temperature as the controlled process variable.
3. Compute the error between target temperature and simulated temperature.
4. Accumulate the integral of the error once per control period.
5. Apply integral limiting and a simple anti-windup rule.
6. If the output is already saturated and the current error would push it further into saturation, pause integral accumulation for that control cycle.
7. Compute the PI control output and clamp it to the valid PWM range.
8. Update the thermal model using the PWM duty cycle.
9. Print both human-readable and CSV-style logs for observation and later experiment recording.

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

The current V3.1 simulation is a useful engineering closed loop, but it is still simplified.

- The controller acts on the simulated temperature rather than on a DS18B20 value that physically changes with heating.
- The thermal model is a first-order approximation and does not yet represent more complex thermal lag, disturbance, or sensor dynamics.
- The controller is still a simplified PI controller rather than a full industrial PID strategy.

## Why This Step Matters

This version is important because it further improves a key limitation that remained after the first PI upgrade:

- overshoot and slow integral recovery in the first PI version

to:

- a smoother PI-based regulation process with bounded integral action and simple anti-windup

That makes the simulation much more valuable for thesis writing, experiment planning, and later control refinement.

## Experiment Support

The serial output now includes:

- a human-readable runtime line
- a CSV-style line for later copy-and-analyze workflows
- a JSON-style telemetry line that simulates a future MQTT publish payload

## MQTT Connectivity Preparation

The current version moves beyond serial-only publish simulation and adds a minimal real MQTT path.

Current scope:

- Wi-Fi connection through `Wokwi-GUEST`
- telemetry publish to a public test MQTT broker
- subscription to the node-specific `params/set` topic
- received `params/set` payloads printed to the serial output
- supported runtime fields include target temperature, controller gains, control period, and control mode
- `apply_immediately=true` allows the new parameters to take effect at runtime

Current boundary:

- telemetry publish is real
- parameter downlink handling is intentionally lightweight rather than a full remote configuration subsystem
- no broker authentication or production security mechanism is added yet

Why this step matters:

- it validates that the edge node can reach an external broker from Wokwi
- it validates the telemetry topic and payload structure with a real MQTT path
- it prepares the codebase for later migration to a private authenticated broker with minimal changes

## Message-Structure Preparation

The current code now starts to abstract the future MQTT message structure inside the simulation module.

Current scope:

- telemetry message structure is represented in code
- parameter-downlink structure is reserved in code
- optimizer recommendation structure is reserved in code

Important boundary:

- this is still not a real broker integration
- the current implementation only simulates publish behavior through serial JSON output

Why this step matters:

- it validates payload field choices before real MQTT integration
- it stabilizes the message structure early
- it reduces future integration risk when a real authenticated MQTT broker is added later

This makes it easier to support:

- P vs PI comparison experiments
- PI initial version vs PI tuned version comparison
- parameter tuning
- step-response observation
- steady-state error experiments
- disturbance experiments
- future comparison with simplified PID versions

## Recommended Next Steps

The most natural next tasks are:

- refine staged-parameter handling when `apply_immediately=false`
- add safer runtime application rules for gain updates if needed
- compare P, PI initial, and PI tuned versions under the same thermal-model parameters
- tune `Kp` and `Ki` using metrics such as settling time, overshoot, and steady-state error
- run step-response and steady-state error experiments
- add disturbance injection scenarios
- upgrade the controller from proportional control to simplified PID when needed
