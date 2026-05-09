# Wokwi Edge Node Simulation

## Purpose

This directory contains the runnable Wokwi-based edge node module for the
project. It is the implementation baseline for the edge control layer and also
supports a real-hardware build profile.

The goal is to support engineering verification of a temperature-control node in
a way that is easy to run, observe, debug, and explain during a thesis defense.

## Current Version

The current version is **Temperature Control Node V3.1**.

Compared with the initial V3 PI version, V3.1 focuses on reducing overshoot and
improving convergence smoothness while keeping the controller simple and
explainable.

## Current Implementation

The current node verifies these functions:

- ESP32 runtime bootstrap
- Wokwi serial observability
- DS18B20 temperature acquisition as a physical reference value
- GPIO2 heartbeat status LED
- GPIO18 PWM output
- tuned PI controller with bounded integral state
- PID-compatible runtime parameter structure (`kp`, `ki`, `kd`)
- virtual thermal model driven by PWM duty cycle
- structured telemetry payload generation
- configurable MQTT broker connection
- MQTT username/password support through local `secrets.h`
- MQTT telemetry publish to `edge/temperature/<device_id>/telemetry`
- subscription to `edge/temperature/<device_id>/params/set`
- runtime parameter parsing, validation, immediate apply, or staging
- MQTT `params/ack` publish after parse/validation/apply
- safety/fault/connectivity fields in telemetry
- simulator and real-hardware build profiles

This is an important engineering step because the simulation has moved from
control-interface verification to an observable MQTT-connected closed loop.

## Files

- `diagram.json`: Wokwi circuit definition, including ESP32, DS18B20, pull-up
  resistor, status LED, LED resistor, Logic Analyzer, and Serial Monitor wiring
- `src/sketch.ino`: application bootstrap and wiring entrypoint
- `src/app/`: edge application loop and integration glue
- `src/controller/`: PI/PID-compatible control logic
- `src/comms/`: MQTT gateway, topic handling, telemetry builder, parameter
  parser, validator, and ACK builder
- `src/hardware/`: simulator and real-hardware adapters
- `src/secrets.example.h`: safe template for local Wi-Fi / MQTT settings
- `platformio.ini`: PlatformIO build configuration
- `wokwi.toml`: Wokwi project configuration
- `libraries.txt`: Arduino libraries used by Wokwi

## Local Secrets

The project uses a local-only secrets file for Wi-Fi and MQTT credentials.

- `src/secrets.h`: local machine settings, intentionally ignored by Git
- `src/secrets.example.h`: committed template that documents expected fields

Create the local file with:

```bash
cd simulator/wokwi
cp src/secrets.example.h src/secrets.h
```

Fill these values locally:

- `kWifiSsid`
- `kWifiPassword`
- `kMqttHost`
- `kMqttPort`
- `kMqttUsername`
- `kMqttPassword`

Do not commit real MQTT credentials.

## How To Run In Wokwi

1. Open the project with the Wokwi VS Code extension.
2. Provide local credentials in `src/secrets.h`.
3. Build the firmware with PlatformIO.
4. Start the Wokwi simulation.
5. Open the Wokwi Serial Monitor.
6. Observe:
   - simulated temperature rising toward the target
   - control error shrinking
   - PWM duty cycle decreasing as the system approaches setpoint
   - GPIO2 heartbeat LED activity
   - GPIO18 waveform through Logic Analyzer
   - JSON telemetry printed to serial
   - MQTT connect/reconnect/publish status
   - incoming `params/set` messages
   - outgoing `params/ack` messages

## Current Control Logic

The current controller is a simplified PI controller with light anti-windup
behavior and a PID-compatible interface.

Control flow:

1. Read DS18B20 value as a physical reference reading.
2. Use simulated temperature as the controlled process variable.
3. Compute the error between target temperature and simulated temperature.
4. Accumulate the integral of the error once per control period.
5. Apply integral limiting and a simple anti-windup rule.
6. Pause integral accumulation if saturated output would be pushed further into
   saturation.
7. Compute control output and clamp it to the valid PWM range.
8. Update the thermal model using PWM duty cycle.
9. Publish/print telemetry for observation and downstream ingestion.

The default `kd` is `0.0`, so the tuned default behaves as PI while preserving a
PID-compatible payload contract.

## Virtual Thermal Model

The simulation uses a first-order virtual thermal model.

Model equation:

```text
simTemp = simTemp + heatGainPerCycleC * dutyNorm
                    - coolingFactor * (simTemp - ambientTemp)
```

Interpretation:

- heating increases with PWM duty cycle
- passive cooling increases when simulated temperature is above ambient
- the combined effect produces a gradual rise-and-settle behavior suitable for
  repeatable experiments

## MQTT Contract Implemented Here

Implemented topics:

- telemetry publish: `edge/temperature/edge-node-001/telemetry`
- parameter downlink subscribe: `edge/temperature/edge-node-001/params/set`
- parameter ACK publish: `edge/temperature/edge-node-001/params/ack`

Telemetry fields include:

- control state: `target_temp_c`, `sim_temp_c`, `error_c`, `pwm_duty`, `pwm_norm`
- controller parameters: `control_mode`, `controller_version`, `kp`, `ki`, `kd`
- timing: `control_period_ms`, `actual_dt_ms`, `dt_error_ms`
- sensor/safety: `sensor_status`, `sensor_valid`, `fault_latched`, `fault_reason`
- network: `wifi_connected`, `mqtt_connected`, `mqtt_reconnect_count`,
  `mqtt_publish_fail_count`
- pending config state: `has_pending_params`, `pending_params_age_ms`

`params/set` supports:

- `target_temp_c`
- `kp`
- `ki`
- `kd`
- `control_period_ms`
- `control_mode`
- `apply_immediately`

`params/ack` reports:

- `ack_type`
- `success`
- `applied_immediately`
- `has_pending_params`
- applied runtime parameters
- safety/fault state
- reason and uptime

See `docs/mqtt_interface.md` for the repository-level MQTT contract.

## Experiment Support

The serial output and MQTT payloads support:

- P/PI/PID-compatible comparison experiments
- PI initial vs PI tuned comparison
- parameter tuning demonstrations
- step-response observation
- steady-state error experiments
- disturbance scenarios through seeded data or script-driven demos
- AI recommendation apply and post-apply validation demos

## Current Limitations

The simulation is useful and runnable, but it is still simplified:

- the controller acts on simulated temperature rather than a physically heated
  DS18B20 value
- the thermal model is first-order and does not model complex sensor lag or heat
  distribution
- the default controller is PI-like (`kd = 0.0`) even though the interface is
  PID-compatible
- Wokwi network behavior can produce transient MQTT disconnects, so serial logs
  and Data Hub metrics should be used together when debugging

These boundaries are thesis-friendly if stated clearly: they show controlled
scope and explain why seeded/demo data scripts are useful for stable defense
presentation.

## Build, Flash, And Mode Switch

This project supports two build profiles without changing application logic.

- `esp32dev`: simulator-oriented build (`EDGE_BUILD_SIMULATOR=1`, default)
- `esp32dev-real`: real hardware build (`EDGE_BUILD_SIMULATOR=0`)

Build simulator mode:

```bash
cd simulator/wokwi
~/.platformio/penv/bin/pio run -e esp32dev
```

Build and flash real hardware:

```bash
cd simulator/wokwi
~/.platformio/penv/bin/pio run -e esp32dev-real -t upload
~/.platformio/penv/bin/pio device monitor -b 115200
```

If serial auto-detection fails, set explicit ports in `platformio.ini`:

```ini
[env:esp32dev-real]
upload_port = /dev/cu.usbserial-xxxx
monitor_port = /dev/cu.usbserial-xxxx
```

Real-board hardware mapping:

- OneWire bus (DS18B20 DATA): `GPIO21` with external `4.7k` pull-up to `3V3`
- Heater PWM output (MOSFET gate): `GPIO18`
- Status LED: `GPIO2`

## Recommended Next Steps

- refine staged-parameter handling when `apply_immediately=false`
- add safer runtime application rules for large gain updates if needed
- run comparable experiments for P, PI initial, and PI tuned settings
- add explicit disturbance injection scenarios for defense demos
- compare live Wokwi output with seeded post-apply validation scenarios

Documentation sync date: 2026-05-09.
