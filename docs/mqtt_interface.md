# MQTT Interface Design

## 1. Purpose

This document defines the staged MQTT interface design between the edge temperature-control node and the upper layers of the system.

The purpose of this document is:

- define the message structure between the edge control layer and upper layers
- provide a stable interface basis for later implementation
- support thesis writing related to system integration and interface design
- keep the communication design clear before broker integration is implemented

At the current stage, this document focuses on interface design only. It does not claim that the MQTT communication path has already been fully implemented.

## 2. Interface Scope

The current interface design focuses on three message categories:

1. telemetry
2. params/set
3. optimizer/recommendation

Their roles are:

- telemetry:
  - periodic status reporting from the edge node
- params/set:
  - parameter and mode settings sent from upper layers to the edge node
- optimizer/recommendation:
  - future reserved messages for tuning suggestions or optimization recommendations

## 3. Topic Design

The topic hierarchy is organized around `device_id` so that the system can scale from a single simulated node to multiple edge devices later.

Recommended topics:

- `edge/temperature/<device_id>/telemetry`
- `edge/temperature/<device_id>/params/set`
- `edge/temperature/<device_id>/optimizer/recommendation`

Design considerations:

- `edge`:
  - identifies the edge-side node domain
- `temperature`:
  - identifies the application scenario
- `<device_id>`:
  - supports multi-device extension
- final topic level:
  - separates reporting, parameter update, and future optimization advice

This structure is simple enough for the current stage and still suitable for later expansion into the full three-layer architecture.

## 4. Telemetry Payload Design

The telemetry message is intended for periodic reporting from the edge node to the data hub or upper-layer system.

Recommended payload example:

```json
{
  "device_id": "edge-node-001",
  "timestamp": "2026-03-29T12:00:00Z",
  "target_temp_c": 35.0,
  "sim_temp_c": 34.99,
  "sensor_temp_c": 24.00,
  "error_c": 0.01,
  "integral_error": 10.98,
  "control_output": 167.06,
  "pwm_duty": 167,
  "pwm_norm": 0.655,
  "control_mode": "pi_control",
  "controller_version": "pi_tuned_v3_1",
  "kp": 120.0,
  "ki": 12.0,
  "kd": 0.0,
  "system_state": "running"
}
```

### Field Meaning

Current actively meaningful fields:

- `device_id`
- `timestamp`
- `target_temp_c`
- `sim_temp_c`
- `sensor_temp_c`
- `error_c`
- `integral_error`
- `control_output`
- `pwm_duty`
- `pwm_norm`
- `control_mode`
- `controller_version`
- `kp`
- `ki`
- `system_state`

Current reserved or forward-looking fields:

- `kd`
  - not used by the current PI controller, but reserved for later controller extension

## 5. Parameter Downlink Payload Design

The parameter downlink message is intended for configuration updates from upper layers to the edge node.

Recommended payload example:

```json
{
  "target_temp_c": 35.0,
  "kp": 120.0,
  "ki": 12.0,
  "kd": 0.0,
  "control_period_ms": 1000,
  "control_mode": "pi_control"
}
```

### Current vs Reserved Use

Fields that are already meaningful at the current stage:

- `target_temp_c`
- `kp`
- `ki`
- `control_period_ms`
- `control_mode`

Fields mainly reserved for future extension:

- `kd`
  - reserved for future PID-compatible interfaces

This design allows the future system to update the controller without redesigning the downlink payload structure.

## 6. Optimizer / AI Recommendation Payload Design

The optimizer recommendation message is a reserved interface for future optimization modules.

Important note:

- this message structure is only a reserved interface
- it does not mean the current system already implements AI decision-making
- it is included now so that future optimizer integration does not break the communication model

Recommended payload example:

```json
{
  "source": "future_optimizer",
  "recommended_target_temp_c": 35.0,
  "recommended_kp": 118.0,
  "recommended_ki": 11.5,
  "recommended_kd": 0.0,
  "reason": "reduce overshoot while maintaining low steady-state error",
  "confidence": 0.82,
  "optimization_tag": "pi_tuning_candidate"
}
```

Recommended fields:

- `source`
- `recommended_target_temp_c`
- `recommended_kp`
- `recommended_ki`
- `recommended_kd`
- `reason`
- `confidence`
- `optimization_tag`

## 7. Field Definition Notes

### Why `kd` Is Reserved Now

Although the current controller is PI-based, reserving `kd` now prevents future interface redesign if the controller evolves toward simplified PID control.

### Why Telemetry, Params, and Optimizer Are Separated

These three message types serve different responsibilities:

- telemetry:
  - runtime observation and data collection
- params/set:
  - control configuration from upper layers
- optimizer/recommendation:
  - future advisory messages that should remain logically separate from direct control commands

This separation supports clean architecture and clearer module boundaries.

### Why `sensor_temp_c` and `sim_temp_c` Are Both Retained

In the current simulation stage:

- `sensor_temp_c` represents the physical DS18B20 reading in the simulation
- `sim_temp_c` represents the virtual thermal state used in the control loop

Keeping both fields is important because it preserves transparency about what the controller is using and what the sensor is physically reporting in the current setup.

### Why `control_mode` and `controller_version` Are Useful

- `control_mode` helps upper layers know whether the node is running threshold, P, PI, or later PID logic
- `controller_version` helps distinguish experiment and software revisions, which is valuable for debugging, comparison, and thesis traceability

## 8. Current vs Future Usage

### Fields with direct meaning at the current stage

- `target_temp_c`
- `sim_temp_c`
- `sensor_temp_c`
- `error_c`
- `integral_error`
- `control_output`
- `pwm_duty`
- `pwm_norm`
- `control_mode`
- `controller_version`
- `kp`
- `ki`
- `system_state`
- `control_period_ms`

### Fields reserved for future system integration

- `kd`
- optimizer recommendation fields
- more advanced node-state fields if the system later adds fault states, communication states, or actuator protection states

The design principle is:

- include what is already needed for the current simulation and controller
- reserve a small number of future fields so later integration does not require breaking changes

## 9. Next-Step Suggestion

The recommended implementation sequence is:

1. abstract the telemetry and parameter message structure in code
2. standardize the payload generation and parsing logic
3. connect the edge node to an MQTT broker
4. integrate the broker into the future data-hub layer

This order keeps the current work focused on interface clarity first and communication implementation second.
