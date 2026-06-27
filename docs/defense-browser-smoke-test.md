# Defense Browser Smoke Test

Run this checklist after:

```bash
python scripts/seed_defense_demo_data.py --reset --scenario all
python scripts/preflight-defense-demo.py
```

## 1. Open HMI

- Expected result: `http://127.0.0.1:5173` opens without a blank page.
- If failed, what to try: Run `./scripts/start-hmi-dev.sh --skip-install --without-ai`, then refresh.

## 2. Login

- Expected result: Login succeeds and the app shell/sidebar appears.
- If failed, what to try: Confirm the backend is healthy at `http://127.0.0.1:8000/health`; reseed base users if needed.

## 3. Search DEF

- Expected result: Searching `DEF` shows `DEF-101` through `DEF-114`.
- If failed, what to try: Run `python scripts/seed_defense_demo_data.py --report`; if DEF count is below 14, rerun seed with `--reset --scenario all`.

## 4. Open DEF-101 Normal Baseline

- Expected result: Device detail shows a stable temperature curve around target and no active fault.
- If failed, what to try: Check the selected time range and reload the page; confirm `DEF-101` has telemetry in the seed report.

## 5. Open DEF-108 Steady-state Error and AI Recommendation

- Expected result: Device detail shows sustained setpoint bias. After clicking `Generate Recommendation`, AI shows `Primary Issue: Steady State Error` and `Expected Effect: Reduce Steady-state Error`.
- If failed, what to try: Reload the page, confirm the selected device is `DEF-108`, and rerun `python scripts/preflight-defense-demo.py`.

## 6. Open DEF-105 Post-apply Success

- Expected result: Post-Apply Validation shows baseline, preview, and actual curves; `Overall Result: Improved real-device behavior after apply`; `Prediction Gap: Low`; no `Unavailable` or `NOT COMPARABLE` labels.
- If failed, what to try: Use Backend docs to query recommendation history for `DEF-105`; confirm preflight has `postgres:post_apply_success rec/action/feedback` PASS.

## 7. Open DEF-106 Preview Mismatch

- Expected result: Post-Apply Validation shows all three curves; `Prediction Gap: High`; no `Unavailable` or `NOT COMPARABLE` labels.
- If failed, what to try: Use Backend docs or preflight output; confirm `postgres:preview_mismatch high gap` PASS.

## 8. Open DEF-112 ACK Success

- Expected result: Report/preflight shows successful ACK and action status `applied`; UI may show it through action/recommendation history rather than a dedicated ACK card.
- If failed, what to try: In Backend docs or TDengine, inspect `params_ack` for `device_id='DEF-112'`, `ack_type='applied'`, `success=true`.

## 9. Open DEF-113 Validation Error

- Expected result: Report/preflight shows rejected action and `failure_reason=kp_out_of_range`; TDengine has `validation_error` ACK.
- If failed, what to try: Query `params_ack` for `device_id='DEF-113'`; confirm preflight has `tdengine:DEF-113 ACK validation failure` PASS.

## 10. Open DEF-110 or DEF-111 Safety

- Expected result: Device detail or alarms page shows fault/safety evidence; telemetry has `pwm_duty=0`.
- If failed, what to try: Open the alarms page and search `DEF-110` or `DEF-111`; confirm preflight safety checks PASS.

## 11. Open DEF-109 Saturation

- Expected result: Curve and evaluation show high PWM saturation while temperature remains below target.
- If failed, what to try: Check control evaluation or TDengine telemetry; preflight should show `DEF-109 saturation high PWM` PASS.

## 12. Open Backend Docs

- Expected result: `http://127.0.0.1:8000/docs` opens and device/recommendation APIs are listed.
- If failed, what to try: Restart HMI backend with `./scripts/start-hmi-dev.sh --skip-install --without-ai`.

## 13. Confirm API Returns Non-empty Data

- Expected result: Device list/search, device metrics, AI recommendation/history, alarms, and ops endpoints return non-empty JSON for the demo cases.
- If failed, what to try: Rerun `python scripts/preflight-defense-demo.py` and use the failed check name as the first debug target.

## Quick Manual Order

1. Dashboard: search `DEF`.
2. `DEF-101`: stable baseline.
3. `DEF-108`: steady-state error and AI recommendation.
4. `DEF-105`: post-apply stability success.
5. `DEF-106`: preview mismatch.
6. `DEF-112`: ACK success via report/preflight/API.
7. `DEF-113`: validation error via report/preflight/API.
8. `DEF-110` or `DEF-111`: safety fault.
9. `DEF-109`: saturation limited.
10. Backend docs: verify APIs are open.
