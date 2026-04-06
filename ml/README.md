# ML Training Data Pipeline (Phase 1)

This directory contains the first-stage offline pipeline from TDengine raw time-series to cleaned training windows.

Current scope (Phase 1 only):
- Export TDengine raw tables to parquet
- Build cleaned sliding-window samples from telemetry parquet

Out of scope for this phase:
- Model training
- Online inference
- HMI runtime behavior changes

## Directory Layout

```text
ml/
  README.md
  configs/
    training_data.yaml
  scripts/
    export_tdengine_data.py
    build_training_windows.py
  data/
    raw/
    cleaned/
```

## Prerequisites

Use Python 3.9+ and install dependencies:

```bash
pip install pandas pyarrow pyyaml
```

## Config

Default config: `ml/configs/training_data.yaml`

Contains:
- TDengine REST connection settings
- export table list
- window length/stride/min points
- parameter stability thresholds
- retained point columns for `points` JSON payload

## Step 1: Export TDengine Raw Data

Script: `ml/scripts/export_tdengine_data.py`

Exports these tables to `ml/data/raw/*.parquet`:
- `telemetry`
- `params_ack`
- `params_set`
- `telemetry_summary`
- `alarm_events`

### Example

```bash
python ml/scripts/export_tdengine_data.py \
  --config ml/configs/training_data.yaml \
  --device-id edge-node-001 \
  --start-ms 1712200000000 \
  --end-ms 1712203600000
```

Notes:
- `--device-id` is repeatable.
- Filters are applied with `device_id`, `ts >= start_ms`, `ts <= end_ms`.
- Output parquet files are written under `ml/data/raw/`.

## Step 2: Build Cleaned Training Windows

Script: `ml/scripts/build_training_windows.py`

Input:
- `ml/data/raw/telemetry.parquet`

Cleaning rules:
- drop rows where `sensor_valid != true`
- drop rows where `fault_latched == true`
- drop rows with obvious missing values (`device_id`, `run_id`, `target_temp_c`, `sensor_temp_c`, `control_mode`, `kp`, `ki`, `kd`, timestamp)
- require parameter stability within window (`kp/ki/kd` max delta threshold + single `control_mode`)

Window rules:
- default window length: 30 minutes
- default stride: 5 minutes
- grouped by `device_id + run_id`
- sorted by ascending `ts`

Output:
- `ml/data/cleaned/training_windows.parquet`
- one row per window sample with fields:
  - `device_id`
  - `run_id`
  - `window_start_ms`
  - `window_end_ms`
  - `target_temp_c`
  - `control_mode`
  - `kp`
  - `ki`
  - `kd`
  - `points` (JSON string)

### Example

```bash
python ml/scripts/build_training_windows.py \
  --config ml/configs/training_data.yaml
```

## Extensibility (Next Phase)

This scaffold is intentionally prepared for next scripts:
- `extract_features.py`
- `label_samples.py`

No online modules are imported or modified in runtime paths.
