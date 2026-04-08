# ML Training Data Pipeline (Phase 1)

This directory contains the first-stage offline pipeline from TDengine raw time-series to cleaned training windows.

Current scope (Phase 1 + Phase 2 data prep):
- Export TDengine raw tables to parquet
- Build cleaned sliding-window samples from telemetry parquet
- Extract feature rows from window samples
- Generate rule-based pseudo labels

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
    extract_features.py
    label_samples.py
  data/
    raw/
    cleaned/
    features/
    datasets/
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
- export table mapping (`name`, `time_column`, `device_column`, `order_by`)
- window length/stride/min points
- parameter stability thresholds
- sampling quality thresholds (`max_gap_ms`, `max_mean_actual_dt_ms`, `min_sampling_ratio`)
- feature extraction defaults (`target_band`, `saturation_pwm_threshold`)
- pseudo-label thresholds for `problem_type`
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
- Filters are applied using per-table config columns:
  - device filter -> configured `device_column`
  - time range -> configured `time_column`
  - ordering -> configured `order_by`
- If a table is missing mapping config, defaults are used:
  - `device_column=device_id`, `time_column=ts`, `order_by=ts`
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
- normalize null-ish string IDs/modes (`nan`, `None`, blank) to stable tokens

Sampling quality checks:
- reject windows with excessive max timestamp gap (`quality.max_gap_ms`)
- optionally reject windows with large mean `actual_dt_ms` (`quality.max_mean_actual_dt_ms`, skipped if column is absent)
- reject windows with low effective sampling ratio (`quality.min_sampling_ratio`)

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

## Step 3: Extract Features

Script: `ml/scripts/extract_features.py`

Input:
- `ml/data/cleaned/training_windows.parquet`

Output:
- `ml/data/features/training_features.parquet`

Each output row corresponds to one training window and includes:
- base columns (`device_id`, `run_id`, window range, params)
- temp/error statistics
- control output statistics
- dynamic metrics (`zero_crossings`, `in_band_ratio`, `overshoot`, `settling_sec`)
- sampling quality stats
- state ratios and dominant state

### Example

```bash
python ml/scripts/extract_features.py \
  --config ml/configs/training_data.yaml
```

## Step 4: Generate Rule Labels (Pseudo Labels)

Script: `ml/scripts/label_samples.py`

Input:
- `ml/data/features/training_features.parquet`

Output:
- `ml/data/datasets/labeled_samples.parquet`

Adds:
- `primary_problem_type`
- `secondary_problem_types`
- `problem_flags`
- `problem_type`
- `label_version`
- `labeled_at`

Compatibility:
- `problem_type` is kept and equals `primary_problem_type`.

Supported `problem_type` classes:
- `normal`
- `slow_response`
- `steady_state_error`
- `overshoot_high`
- `oscillation`
- `saturation_limited`

Important:
- These are rules-based pseudo labels for Phase-2 data preparation.
- They are not model predictions and not production ground truth.

### Example

```bash
python ml/scripts/label_samples.py \
  --config ml/configs/training_data.yaml
```

## Extensibility (Next Phase)

This scaffold is intentionally prepared for next scripts:
- `extract_features.py`
- `label_samples.py`

No online modules are imported or modified in runtime paths.

Documentation sync date: 2026-04-07.

## Control-Action Feedback Export

Use the unified control-action feedback table as the offline training source:

```bash
python ml/scripts/export_control_action_feedback_samples.py
```

Output:
- `ml/data/datasets/control_action_feedback_samples.parquet`

By default the exporter keeps only samples with:
- `is_training_eligible = true`
- `insufficient_data = false`
