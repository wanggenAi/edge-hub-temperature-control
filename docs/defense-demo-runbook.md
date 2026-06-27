# Defense Demo Runbook

## 1. Demo Objective

This demo uses deterministic controlled telemetry, not random fake rows. The goal is to reproduce the same data structures and control logic used by the real system while avoiding defense-day risk from network, serial, broker, or timing instability.

The story to prove is:

```text
edge telemetry -> TDengine -> HMI -> AI diagnosis -> PID recommendation
-> preview -> apply / ACK -> post-apply validation -> feedback learning sample
```

The `DEF-101` to `DEF-114` devices are presentation devices. They are safe to reset because every seeded row uses `device_code like 'DEF-%'` and `run_id like 'defense_%'`.

## 2. Start Services

Run commands from the repository root unless noted.

```bash
cd /Users/seker./edge-hub-temperature-control
docker compose -f docker-compose.postgresql.yml up -d
docker compose -f docker-compose.tdengine.yml up -d
```

Start HMI. Use the AI runtime if it is stable; otherwise the backend fallback and seeded recommendations are enough for the defense demo.

```bash
./scripts/start-hmi-dev.sh --skip-install --without-ai
```

Optional DataHub runtime:

```bash
cd /Users/seker./edge-hub-temperature-control/data-hub
./gradlew bootRun
```

Optional Wokwi or Python edge node can be used for a live hardware-style segment, but the seeded DEF devices are the fallback for the core defense story.

Main URLs:

- HMI: `http://127.0.0.1:5173`
- Backend docs: `http://127.0.0.1:8000/docs`
- DataHub actuator, if running: `http://127.0.0.1:8081/actuator/health`

## 3. Seed Demo Data

Use one command to reset only demo devices and reseed all defense scenarios:

```bash
python scripts/seed_defense_demo_data.py --reset --scenario all
python scripts/preflight-defense-demo.py
python scripts/seed_defense_demo_data.py --report
```

Useful targeted commands:

```bash
python scripts/seed_defense_demo_data.py --dry-run --scenario all
python scripts/seed_defense_demo_data.py --scenario slow_response
python scripts/seed_defense_demo_data.py --scenario ack_success
python scripts/seed_defense_demo_data.py --scenario over_temperature_safety
```

## 4. 15-Minute Defense Demo Path

1. Open the HMI dashboard and show the `DEF-*` device list.
2. Open `DEF-101 normal_stable` and explain the normal baseline.
3. Open `DEF-108 steady_state_error`; show sustained setpoint bias and generate the AI recommendation.
4. Explain feature extraction: mean error, mean absolute error, in-band ratio, settling time, temperature swing, and saturation ratio.
5. Open `DEF-105 post_apply_success`; show baseline / preview / actual curves and the improved validation result.
6. Open `DEF-106 preview_mismatch`; explain the system compares preview and actual instead of blindly trusting AI.
7. Keep `DEF-102 slow_response` as backup only if a teacher asks about response speed.
8. Open `DEF-112 ack_success`; show seeded params/set and successful params/ack evidence.
9. Open `DEF-113 ack_failure_validation_error`; show illegal parameters are rejected.
10. Open `DEF-110 sensor_invalid` or `DEF-111 over_temperature_safety`; show safety forced output off.
11. Open `DEF-109 saturation_limited`; explain actuator limits and why PID is not magic.
12. If time remains, open Ops / learning pages and show feedback labels used by the learning loop.

## 5. Scenario Table

| Device | Scenario | What to show | Expected result | Teacher question it answers |
|---|---|---|---|---|
| `DEF-101` | `normal_stable` | Stable telemetry curve | Error stays near zero; no adjustment needed | Can the system distinguish normal operation from faults? |
| `DEF-102` | `slow_response` | Slow rise toward target | AI problem is `slow_response`; after curve settles faster | Backup: how does AI find slow response? |
| `DEF-103` | `overshoot_high` | Temperature exceeds target | Overshoot is reduced after conservative tuning | Can it handle too aggressive control? |
| `DEF-104` | `oscillation` | Repeated crossings around target | Amplitude and error variance shrink after tuning | Can it detect oscillation rather than one noisy point? |
| `DEF-105` | `post_apply_success` | Before / preview / actual comparison | Steady-state error improves; `actual_effect_label=improved`, `preview_gap_label=low` | Does recommendation improve setpoint stability? |
| `DEF-106` | `preview_mismatch` | Preview good, actual weaker | Steady-state error is not improved as much as predicted; `preview_gap_label=high` | What happens if AI prediction is wrong? |
| `DEF-107` | `insufficient_data` | Too few post-apply points | Evaluation is pending or insufficient | Does it avoid false conclusions with little data? |
| `DEF-108` | `steady_state_error` | Long-term same-sign error | AI problem is `steady_state_error` | Does it detect persistent bias, not just transient error? |
| `DEF-109` | `saturation_limited` | PWM near 100 percent | AI flags actuator or load limitation | Does it know hardware limits matter? |
| `DEF-110` | `sensor_invalid` | Fault-latched safety state | `sensor_valid=false`, PWM forced to zero | What if the sensor fails? |
| `DEF-111` | `over_temperature_safety` | Temperature above safety limit | Over-temperature alarm and output off | What if the process becomes unsafe? |
| `DEF-112` | `ack_success` | `params_set` then `params_ack` | ACK success and action status applied | Is apply confirmed by the device? |
| `DEF-113` | `ack_failure_validation_error` | Invalid `kp` attempt | Validation ACK rejects the command | Are dangerous parameters blocked? |
| `DEF-114` | `post_apply_partial` | Some improvement, not enough | `actual_effect_label=unchanged`, `preview_gap_label=medium` | Does the learning loop record partial failures? |

## 6. Teacher Q&A Cheat Sheet

Q: Are these data fake?

A: They are deterministic controlled demo telemetry. The real edge path can produce the same kinds of records, but the defense uses controlled telemetry to avoid network, serial, and timing instability. The seeded rows still go into PostgreSQL and TDengine using the same schema that HMI, AI, ACK, and learning pages read.

Q: Is the AI recommendation just written by hand?

A: The recommendation path uses TDengine history and PostgreSQL device parameters to extract features such as mean absolute error, overshoot, settling time, zero crossings, in-band ratio, and saturation ratio. The seeded recommendation records preserve those inputs and expected labels so the page can demonstrate the same reasoning path reliably.

Q: What if the AI prediction is wrong?

A: `DEF-106 preview_mismatch` shows exactly that. The preview looks strong, but the actual telemetry does not match. The system labels the gap as high and records it as feedback instead of assuming the recommendation was correct.

Q: What if the sensor breaks?

A: `DEF-110 sensor_invalid` shows `sensor_valid=false`, `fault_latched=true`, and `pwm_duty=0`. The system prioritizes safety and blocks normal tuning.

Q: What if a parameter is illegal?

A: `DEF-113 ack_failure_validation_error` shows an invalid `kp` attempt rejected by `params_ack` with `ack_type=validation_error`, `success=false`, and `reason=kp_out_of_range`. The current safe parameters are not overwritten.

Q: What if the actuator is not strong enough?

A: `DEF-109 saturation_limited` keeps PWM near 100 percent while the temperature remains below target. The system flags actuator saturation and hardware/load limits instead of pretending PID can solve everything.

Q: Why is `error_c` positive when temperature is below target?

A: The project definition is `error_c = target_temp_c - sensor_temp_c`. Positive error means the measured temperature is below target and heating demand remains.

## 7. Fallback Plan

- AI runtime is not running: use backend fallback and seeded recommendations.
- Wokwi is unstable: use seeded `DEF-*` telemetry for the core story.
- DataHub actuator is not running: use seeded `params_set` and `params_ack` data for ACK evidence; DataHub runtime health remains a warning unless explicitly required.
- MQTT broker is unstable: use seeded TDengine and PostgreSQL data to show HMI, AI, validation, and feedback.
- Time window shows no data: rerun `python scripts/seed_defense_demo_data.py --reset --scenario all` and then rerun preflight.
- Browser route looks stale after login: use the dashboard/device navigation directly and search for `DEF-102`.

## 8. Final Preflight Checklist

Run this five minutes before defense:

```bash
python scripts/seed_defense_demo_data.py --reset --scenario all
python scripts/preflight-defense-demo.py
python scripts/seed_defense_demo_data.py --report
```

Checklist:

- HMI opens at `http://127.0.0.1:5173`.
- Backend docs open at `http://127.0.0.1:8000/docs`.
- Seed report shows at least 14 `DEF-*` devices.
- Preflight prints `required_failed=0`.
- `DEF-102` historical curve is visible.
- `DEF-105` has improved / low feedback.
- `DEF-106` has high preview gap feedback.
- `DEF-112` has a successful ACK.
- `DEF-113` has a validation-error ACK.
- `DEF-110` or `DEF-111` shows safety fault evidence.
