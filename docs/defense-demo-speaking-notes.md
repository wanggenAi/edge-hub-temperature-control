# Defense Demo Speaking Notes

## 1. 30-second Project Summary

EdgeHub Temperature Control is an edge-based temperature control and monitoring system. It integrates telemetry collection, time-series storage, HMI visualization, AI-assisted PID tuning, MQTT-based parameter application, ACK confirmation, and post-apply validation.

The goal is not only to control temperature, but also to make control decisions observable, explainable, and verifiable. In other words, the system does not just say "change PID parameters"; it records why the change was suggested, previews the expected effect, sends the command through MQTT, waits for device ACK, and then compares the actual telemetry with the prediction.

## 2. 3-minute Demo Script

### 1. Dashboard

- What I click: Open the HMI dashboard and search for `DEF`.
- What I say: "These are controlled defense demo devices. They use the same PostgreSQL and TDengine schema as the real runtime, but the data is deterministic so the demo is stable."
- What the teacher should notice: DEF devices are visible after login and are not hidden test records.

### 2. Normal Baseline

- What I click: Open `DEF-101 normal_stable`.
- What I say: "This is the normal baseline. The temperature stays close to the target, the error is small, and the system should not recommend unnecessary tuning."
- What the teacher should notice: The curve is stable and the system is not only designed to find faults.

### 3. Steady Setpoint Error

- What I click: Open `DEF-108 steady_state_error`.
- What I say: "For an incubator, the core goal is stable temperature around the setpoint. This device has a persistent same-sign error, so the problem is not one noisy sample; it is a sustained setpoint bias."
- What the teacher should notice: The curve and metrics support the diagnosis: error remains positive, in-band ratio is low, and the system is not treating this as random noise.

### 4. AI Recommendation

- What I click: In `DEF-108`, click `Generate Recommendation`.
- What I say: "The recommendation is based on extracted features such as mean error, mean absolute error, in-band ratio, settling time, temperature swing, overshoot, zero crossings, and saturation ratio."
- What the teacher should notice: The AI decision shows `steady_state_error`, a conservative PID delta, evidence metrics, and a required confirmation step.

### 5. Preview

- What I click: Show the preview curve or move to `DEF-105 post_apply_success`.
- What I say: "Preview is a prediction of what may happen after applying the suggested PID parameters. It helps the operator inspect risk before applying changes, but it is not treated as proof."
- What the teacher should notice: Preview is clearly separated from actual post-apply validation.

### 6. Post-apply Success

- What I click: Open `DEF-105 post_apply_success`.
- What I say: "This scenario closes the loop for setpoint stability: baseline had sustained error, preview predicted improvement, and actual telemetry also moved closer to the target."
- What the teacher should notice: The system records `actual_effect_label=improved` and `preview_gap_label=low`.

### 7. Preview Mismatch

- What I click: Open `DEF-106 preview_mismatch`.
- What I say: "This is important because it shows honesty. The preview looked good, but the actual telemetry did not match well, so the system records a high preview gap."
- What the teacher should notice: The system does not blindly trust AI predictions.

### 8. ACK Success and Failure

- What I click: Use `DEF-112 ack_success` and `DEF-113 ack_failure_validation_error`; if the page does not show ACK directly, use Backend docs or preflight/report output.
- What I say: "Parameter application is not considered complete after clicking a button. The device must return `params_ack`. Invalid parameters are rejected with a validation error."
- What the teacher should notice: MQTT command intent and device confirmation are separate pieces of evidence.

### 9. Safety Protection

- What I click: Open `DEF-110 sensor_invalid` or `DEF-111 over_temperature_safety`.
- What I say: "When sensor data is invalid or the measured temperature exceeds the safety limit, the system prioritizes safety and forces PWM output to zero."
- What the teacher should notice: The system has safety boundaries and does not keep tuning during unsafe states.

### 10. Saturation Limited

- What I click: Open `DEF-109 saturation_limited`.
- What I say: "If the actuator is already near full power and the temperature is still far below target, the system flags a hardware or load limitation instead of pretending PID can solve everything."
- What the teacher should notice: The design respects engineering constraints.

## 3. Scenario One-liners

- `DEF-101 normal_stable`: Stable baseline showing that the system recognizes normal operation and avoids unnecessary tuning.
- `DEF-102 slow_response`: Temperature approaches the target too slowly, so AI recommends stronger but still bounded PID tuning.
- `DEF-103 overshoot_high`: Temperature exceeds the target, showing why conservative tuning is needed to reduce overshoot.
- `DEF-104 oscillation`: Error crosses zero repeatedly, showing oscillation detection from telemetry patterns.
- `DEF-105 post_apply_success`: Baseline, preview, and actual telemetry all support a successful recommendation.
- `DEF-106 preview_mismatch`: The system does not blindly trust preview results; it compares prediction with actual telemetry and records the gap.
- `DEF-107 insufficient_data`: The system waits for more telemetry instead of making a confident judgment from too few points.
- `DEF-108 steady_state_error`: Long-term same-sign error shows persistent bias, not short-term noise.
- `DEF-109 saturation_limited`: High PWM saturation shows actuator or load limits that PID alone cannot fix.
- `DEF-110 sensor_invalid`: Sensor failure triggers a safety state and forces output off.
- `DEF-111 over_temperature_safety`: Over-temperature protection forces output off even when a control target exists.
- `DEF-112 ack_success`: MQTT parameter application is confirmed by a successful device ACK.
- `DEF-113 ack_failure_validation_error`: Illegal parameters are rejected and recorded with a validation failure reason.
- `DEF-114 post_apply_partial`: Partial improvement is recorded as learning data instead of being hidden as a success.

## 4. Teacher Q&A

Q1: Are these data fake?

A: They are deterministic controlled demo telemetry. They are not random screenshots or front-end-only values. The rows are written into PostgreSQL and TDengine using the same schema that the HMI, AI recommendation, ACK, and feedback logic read.

Q2: Why do you use seeded demo data?

A: A defense demo has limited time and unstable factors such as network, serial bridge, MQTT timing, and Wokwi startup. Seeded data lets me reproduce the same engineering cases reliably while preserving the real data structure and control semantics.

Q3: How do you know the AI recommendation is useful?

A: The system extracts measurable features from telemetry, generates a recommendation, previews the expected curve, and then evaluates actual post-apply telemetry. Usefulness is not assumed; it is checked after application.

Q4: What if the AI prediction is wrong?

A: The `preview_mismatch` scenario shows this. The system compares preview and actual telemetry, records a high gap, and keeps the sample for future learning. AI is treated as decision support, not an absolute authority.

Q5: What if the sensor fails?

A: The system enters a safety-first state. In `DEF-110`, `sensor_valid=false`, `fault_latched=true`, and PWM is forced to zero. It should not continue normal PID tuning without trustworthy sensor input.

Q6: What if the temperature exceeds the safety limit?

A: `DEF-111` demonstrates over-temperature protection. Even if the control target still exists, the output is forced off when measured temperature exceeds the software safety limit.

Q7: What if the actuator is already saturated?

A: `DEF-109` shows high PWM saturation. The system flags a limitation such as insufficient heating capacity, load condition, or hardware constraint. It does not claim PID can solve every physical limitation.

Q8: What if the parameter command fails?

A: Parameter application requires ACK confirmation. `DEF-113` shows an invalid parameter rejected with `ack_type=validation_error`, `success=false`, and a clear failure reason.

Q9: What is the role of TDengine?

A: TDengine stores time-series facts: telemetry, summaries, parameter set events, ACK events, device status, and alarm events. It supports historical curves, feature extraction, and post-apply validation.

Q10: What is the role of PostgreSQL?

A: PostgreSQL stores control-plane data: devices, users, permissions, parameters, AI recommendation records, control actions, alarms, and feedback samples. It complements TDengine instead of replacing it.

Q11: Why MQTT?

A: MQTT is lightweight, suitable for edge devices, and naturally supports telemetry publish, parameter command topics, and ACK topics. It also separates command intent from device confirmation.

Q12: What is the difference between preview and post-apply validation?

A: Preview is a simulation before applying the recommendation. Post-apply validation is based on actual telemetry after the command is applied. The system needs both because prediction can be wrong.

Q13: How can this system be improved in the future?

A: The next steps are stronger real-hardware validation, more diverse training samples, automatic rollback for risky recommendations, richer safety rules, and more robust model lifecycle monitoring.

## 5. Emergency Lines

- If Wokwi is unstable: "The live edge simulator is optional for this part. I will switch to seeded DEF telemetry, which uses the same TDengine and PostgreSQL schemas and demonstrates the control cases deterministically."
- If AI runtime is not running: "The backend has fallback recommendation logic, and seeded recommendations are already stored. The demo can still show diagnosis, preview, and post-apply validation."
- If DataHub actuator is not running: "The runtime actuator is optional for the controlled demo. I can use seeded `params_set` and `params_ack` records, or MQTT loopback, to show the ACK semantics."
- If live data is delayed: "This is exactly why the demo has controlled telemetry. The system design supports live data, but the defense story does not depend on one timing-sensitive stream."
- If the teacher asks why using controlled data: "Controlled data is used to make the demonstration repeatable. It is not replacing the real system; it is reproducing important operating scenarios through the same storage and API paths."
