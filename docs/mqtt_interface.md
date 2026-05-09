# MQTT Interface Contract

## 1. Purpose

This document defines the MQTT contract used by the edge temperature-control
node, HMI backend, and Java Data Hub.

The current repository already implements the core MQTT path:

- edge telemetry publish
- HMI/Data Hub parameter intent through `params/set`
- edge acknowledgement through `params/ack`
- config-change notifications for Data Hub rule refresh

The optimizer/recommendation topic is intentionally kept as a reserved extension
point. In the current implementation, AI recommendations are generated in the
HMI/backend AI layer and applied through the normal `params/set` command path.

## 2. Implemented Topic Scope

Device-scoped topics:

- `edge/temperature/<device_id>/telemetry`
- `edge/temperature/<device_id>/params/set`
- `edge/temperature/<device_id>/params/ack`

Configuration notification topics:

- `edgehub/config/alarm-rules/updated`
- `edgehub/config/storage-rules/updated`

Reserved advisory topic:

- `edge/temperature/<device_id>/optimizer/recommendation`

The reserved optimizer topic is not the current device-side apply mechanism. It
is documented so future work can introduce advisory MQTT messages without
breaking the implemented telemetry/set/ack contract.

## 3. Topic Design Rationale

`edge/temperature/<device_id>/...` keeps the contract scalable from one Wokwi
node to multiple physical or simulated devices.

The final topic segment separates responsibilities:

- `telemetry`: runtime observation from device to upper layers
- `params/set`: upper-layer control intent to device
- `params/ack`: device response after parsing, validation, staging, or apply
- `optimizer/recommendation`: reserved advisory channel for future direct
  optimizer-device integration

This separation is important because a command being published is not the same
thing as a command being applied. The ACK topic gives the system traceability.

## 4. Telemetry Payload

Telemetry is published periodically by the edge node and consumed by Data Hub.
The payload is JSON.

Current example:

```json
{
  "device_id": "edge-node-001",
  "uptime_ms": 50274,
  "target_temp_c": 35.0,
  "sim_temp_c": 34.98,
  "sensor_temp_c": 22.0,
  "sensor_status": "ok",
  "error_c": 0.03,
  "integral_error": 13.56,
  "derivative_error": -0.006,
  "d_term": 0.0,
  "control_output": 166.11,
  "pwm_duty": 166,
  "pwm_norm": 0.651,
  "control_period_ms": 1000,
  "actual_dt_ms": 1628,
  "dt_error_ms": 628,
  "saturation_state": "none",
  "sensor_valid": true,
  "run_id": "edge-node-001-run-e5850259",
  "control_mode": "pid_control",
  "controller_version": "pi_tuned_v3_1",
  "kp": 120.0,
  "ki": 12.0,
  "kd": 0.0,
  "system_state": "running",
  "wifi_connected": true,
  "mqtt_connected": true,
  "mqtt_reconnect_count": 2,
  "mqtt_publish_fail_count": 6,
  "safety_output_forced_off": false,
  "fault_latched": false,
  "fault_reason": "none",
  "software_max_safe_temp_c": 65.0,
  "has_pending_params": false,
  "pending_params_age_ms": 0
}
```

Important field groups:

- identity: `device_id`, `run_id`, `uptime_ms`
- process values: `target_temp_c`, `sim_temp_c`, `sensor_temp_c`, `error_c`
- controller output: `control_output`, `pwm_duty`, `pwm_norm`, `saturation_state`
- timing quality: `control_period_ms`, `actual_dt_ms`, `dt_error_ms`
- controller identity: `control_mode`, `controller_version`, `kp`, `ki`, `kd`
- sensor/safety: `sensor_status`, `sensor_valid`, `fault_latched`, `fault_reason`,
  `safety_output_forced_off`, `software_max_safe_temp_c`
- communication state: `wifi_connected`, `mqtt_connected`,
  `mqtt_reconnect_count`, `mqtt_publish_fail_count`
- staged config state: `has_pending_params`, `pending_params_age_ms`

Notes:

- `kd` is carried even when the tuned controller behaves as PI (`kd = 0`) so the
  interface remains PID-compatible.
- `sim_temp_c` and `sensor_temp_c` are both retained because the current Wokwi
  simulation uses a virtual controlled temperature while still exposing a
  physical sensor reference.
- Data Hub accepts unknown extra JSON fields, so telemetry can evolve without
  immediately breaking ingestion.

## 5. Parameter Downlink Payload: `params/set`

`params/set` is the implemented command-intent path used by HMI manual parameter
updates and AI recommendation apply actions.

Example:

```json
{
  "target_temp_c": 35.0,
  "kp": 118.0,
  "ki": 11.5,
  "kd": 0.0,
  "control_period_ms": 1000,
  "control_mode": "pid_control",
  "apply_immediately": true,
  "source": "hmi",
  "requested_at": "2026-05-09T12:00:00Z"
}
```

Fields parsed by the edge node and Data Hub:

- `target_temp_c`
- `kp`
- `ki`
- `kd`
- `control_period_ms`
- `control_mode`
- `apply_immediately`

Fields such as `source` and `requested_at` are useful for traceability. The edge
parser can ignore unsupported metadata while Data Hub can archive the full
intent payload.

Current semantics:

- `apply_immediately=true`: validated parameters are applied at runtime
- `apply_immediately=false`: parameters may be staged and later acknowledged as
  pending, depending on the edge-side handler
- invalid payloads should result in `params/ack` with a failure ACK type/reason

## 6. Parameter ACK Payload: `params/ack`

The device publishes `params/ack` after it receives and handles a parameter
message.

Example:

```json
{
  "device_id": "edge-node-001",
  "ack_type": "applied",
  "success": true,
  "applied_immediately": true,
  "has_pending_params": false,
  "target_temp_c": 35.0,
  "kp": 118.0,
  "ki": 11.5,
  "kd": 0.0,
  "control_period_ms": 1000,
  "control_mode": "pid_control",
  "reason": "applied_ok",
  "uptime_ms": 54322,
  "sensor_valid": true,
  "fault_latched": false,
  "fault_reason": "none",
  "software_max_safe_temp_c": 65.0
}
```

Common ACK types and reasons:

- `applied` / `applied_ok`
- `staged` / `staged_waiting`
- `pending_applied` / `pending_params_applied`
- `parse_error` / `payload_parse_failed`
- `validation_error` / validation-specific reason

Why ACK matters:

- HMI can distinguish publish success from device apply success
- Data Hub can persist command intent and device result as separate facts
- AI apply can be audited before post-apply telemetry validation begins

## 7. AI Recommendation And MQTT Apply

Current AI recommendation flow:

```text
HMI/backend AI service
-> recommendation stored in PostgreSQL
-> preview simulation stored with recommendation metadata
-> operator/admin applies recommendation
-> HMI backend publishes params/set
-> edge validates/applies parameters
-> edge publishes params/ack
-> HMI/Data Hub observe ACK and later telemetry effect
```

This is why the implemented AI path does not require the edge node to subscribe
to `optimizer/recommendation` today. The edge only needs to understand the
normal runtime configuration contract.

## 8. Data Hub Consumption

Data Hub parses and persists the implemented topic types:

- telemetry -> `telemetry` supertable / JSONL/log depending on storage mode
- `params/set` -> `params_set`
- `params/ack` -> `params_ack`
- config update topics -> rule/cache refresh notifications

The Java parser is intentionally tolerant of extra JSON properties, which keeps
field additions backward compatible.

## 9. Compatibility Rules

When extending this contract:

- prefer additive JSON fields over renaming existing fields
- keep `device_id` and topic device id consistent
- preserve `params/set` and `params/ack` separation
- keep `kd` in payloads even when the active controller is PI-like
- keep telemetry safety/connectivity fields because they support operations and
  post-apply diagnosis
- do not place credentials in committed examples or README files

Documentation sync date: 2026-05-09.
