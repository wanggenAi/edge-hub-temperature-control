# ML Training Data Pipeline

This directory contains the offline pipeline from TDengine time-series data and
control-action feedback into training-ready datasets.

The online AI recommendation runtime lives under `hmi/backend/app/services/ai`.
This `ml` module focuses on offline data preparation and export.

## Current Scope

Telemetry training pipeline:

- export TDengine raw tables to parquet
- build cleaned sliding-window samples from telemetry parquet
- extract feature rows from window samples
- generate rule-based pseudo labels

Feedback learning pipeline:

- export unified control-action feedback samples
- prepare recommendation outcome data for training/evaluation scripts under
  `hmi/backend/ai/scripts`

Out of scope for this module:

- serving online inference
- changing HMI runtime behavior directly
- publishing MQTT messages

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
    export_control_action_feedback_samples.py
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

Default config:

- `ml/configs/training_data.yaml`

Contains:

- TDengine REST connection settings
- export table mapping (`name`, `time_column`, `device_column`, `order_by`)
- window length, stride, and minimum points
- parameter stability thresholds
- sampling quality thresholds (`max_gap_ms`, `max_mean_actual_dt_ms`,
  `min_sampling_ratio`)
- feature extraction defaults (`target_band`, `saturation_pwm_threshold`)
- pseudo-label thresholds for `problem_type`
- retained point columns for `points` JSON payload

## Step 1: Export TDengine Raw Data

Script:

- `ml/scripts/export_tdengine_data.py`

Exports these tables to `ml/data/raw/*.parquet`:

- `telemetry`
- `params_ack`
- `params_set`
- `telemetry_summary`
- `alarm_events`

Example:

```bash
python ml/scripts/export_tdengine_data.py \
  --config ml/configs/training_data.yaml \
  --device-id edge-node-001 \
  --start-ms 1712200000000 \
  --end-ms 1712203600000
```

## Step 2: Build Cleaned Training Windows

Script:

- `ml/scripts/build_training_windows.py`

Input:

- `ml/data/raw/telemetry.parquet`

Cleaning rules:

- drop rows where `sensor_valid != true`
- drop rows where `fault_latched == true`
- drop rows with missing key fields such as `device_id`, `run_id`,
  `target_temp_c`, `sensor_temp_c`, `control_mode`, `kp`, `ki`, `kd`, and
  timestamp
- require parameter stability within each window
- normalize null-ish string IDs/modes to stable tokens

Output:

- `ml/data/cleaned/training_windows.parquet`

Example:

```bash
python ml/scripts/build_training_windows.py \
  --config ml/configs/training_data.yaml
```

## Step 3: Extract Features

Script:

- `ml/scripts/extract_features.py`

Input:

- `ml/data/cleaned/training_windows.parquet`

Output:

- `ml/data/features/training_features.parquet`

Feature groups:

- base window columns
- temperature/error statistics
- control output statistics
- dynamic metrics such as zero crossings, in-band ratio, overshoot, and settling
  time
- sampling quality stats
- state ratios and dominant state

Example:

```bash
python ml/scripts/extract_features.py \
  --config ml/configs/training_data.yaml
```

## Step 4: Generate Rule Labels

Script:

- `ml/scripts/label_samples.py`

Input:

- `ml/data/features/training_features.parquet`

Output:

- `ml/data/datasets/labeled_samples.parquet`

Supported classes:

- `normal`
- `slow_response`
- `steady_state_error`
- `overshoot_high`
- `oscillation`
- `saturation_limited`

Important:

- These are rule-based pseudo labels for data preparation.
- They are not production ground truth.

Example:

```bash
python ml/scripts/label_samples.py \
  --config ml/configs/training_data.yaml
```

## Control-Action Feedback Export

Use the unified control-action feedback table as the offline recommendation
training source:

```bash
python ml/scripts/export_control_action_feedback_samples.py
```

Output:

- `ml/data/datasets/control_action_feedback_samples.parquet`

By default the exporter keeps only samples with:

- `is_training_eligible = true`
- `insufficient_data = false`

This dataset is used by AI scripts such as recommendation-success and preview-gap
model training.

Documentation sync date: 2026-05-09.
