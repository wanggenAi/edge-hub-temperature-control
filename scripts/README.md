# scripts

This directory stores helper scripts so that temporary data-processing logic does not leak into the main engineering code.

Suggested future contents:

- serial log parsing scripts
- experiment data cleaning scripts
- CSV conversion scripts
- result plotting scripts

The directory should stay lightweight for now and can grow after the simulation log format is stabilized.

## Python Environment

The MQTT test client in this directory uses `pyenv` and the repository-level
Python version file.

Recommended setup:

```bash
pyenv install 3.11.9
pyenv local 3.11.9
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

To confirm that `pyenv` has switched the current repository to the expected
Python interpreter:

```bash
pyenv version
pyenv which python
python --version
```

Expected result:

- `pyenv version` shows `3.11.9 (set by .../.python-version)`
- `pyenv which python` points to the `pyenv` installation path
- `python --version` reports `Python 3.11.9`

After the virtual environment is activated:

- the shell prompt usually shows `(.venv)`
- `which python` points to `.venv/bin/python`

If the version does not switch as expected, initialize `pyenv` in your shell
first and then reopen the terminal:

```bash
eval "$(pyenv init -)"
```

## MQTT Test Client

The current MQTT test client is:

- `scripts/mqtt_test_client.py`
- `scripts/mqtt_client_config.example.json`

It can be used to:

- subscribe to telemetry messages
- subscribe to parameter ACK messages
- publish an immediate parameter update
- publish a staged parameter update

To use a self-managed broker, create a local config file:

```bash
cp scripts/mqtt_client_config.example.json scripts/mqtt_client_config.json
```

Then edit the local file and fill in your actual:

- broker host
- broker port
- username
- password
- topics if needed

The local file `scripts/mqtt_client_config.json` is ignored by Git so that
broker credentials do not need to be committed.

Examples:

```bash
python scripts/mqtt_test_client.py --mode immediate
python scripts/mqtt_test_client.py --mode staged
```

Documentation sync date: 2026-04-04.

## TDengine Retention Cleanup

Use `scripts/tdengine-retention-cleanup.sh` to purge old TDengine rows by age.

Default retention:

- telemetry: 7 days
- telemetry_summary: 30 days
- params_set: 30 days
- params_ack: 30 days
- device_status: 14 days
- alarm_events: 90 days

Dry-run preview (default):

```bash
./scripts/tdengine-retention-cleanup.sh
```

Actual deletion:

```bash
DRY_RUN=false ./scripts/tdengine-retention-cleanup.sh
```

Example custom env vars:

```bash
export TDENGINE_URL=http://127.0.0.1:6041
export TDENGINE_DATABASE=edgehub
export TDENGINE_USERNAME=root
export TDENGINE_PASSWORD=taosdata

export RETENTION_TELEMETRY_DAYS=7
export RETENTION_TELEMETRY_SUMMARY_DAYS=30
export RETENTION_PARAMS_SET_DAYS=30
export RETENTION_PARAMS_ACK_DAYS=30
export RETENTION_DEVICE_STATUS_DAYS=14
export RETENTION_ALARM_EVENTS_DAYS=90
```

Cron example (daily 02:30 UTC):

```cron
30 2 * * * cd /path/to/edge-hub-temperature-control && DRY_RUN=false ./scripts/tdengine-retention-cleanup.sh >> /var/log/edgehub-tdengine-retention.log 2>&1
```

## One-Click DB Reset (PostgreSQL + TDengine)

Use `scripts/reset-dev-databases.sh` to clear test data while keeping table
structure/stable definitions.

Default behavior:

- PostgreSQL:
  - run Alembic migration to latest (`hmi/backend/scripts/db_migrate.py`)
  - truncate all `public` tables with `RESTART IDENTITY CASCADE`
  - seed default alarm rules (`hmi/backend/scripts/db_seed.py --rules`)
- TDengine:
  - `CREATE DATABASE IF NOT EXISTS`
  - `CREATE STABLE IF NOT EXISTS` for core stables
  - `DELETE` all rows from `telemetry`, `telemetry_summary`, `params_set`,
    `params_ack`, `device_status`, `alarm_events`

Run full reset:

```bash
./scripts/reset-dev-databases.sh
```

Run full reset and also seed demo relational data:

```bash
./scripts/reset-dev-databases.sh --with-demo
```

Reset only one side:

```bash
./scripts/reset-dev-databases.sh --postgres-only
./scripts/reset-dev-databases.sh --tdengine-only
```

Prerequisites:

- PostgreSQL container running as `edgehub-postgres`
- TDengine REST reachable at `http://127.0.0.1:6041`
- Python deps installed in `hmi/backend` (for migrate/seed scripts)

Customize connection via env vars:

```bash
POSTGRES_CONTAINER=edgehub-postgres \
POSTGRES_DB=edgehub \
POSTGRES_USER=edgehub \
POSTGRES_PASSWORD=edgehub \
TDENGINE_URL=http://127.0.0.1:6041 \
TDENGINE_DATABASE=edgehub \
TDENGINE_USERNAME=root \
TDENGINE_PASSWORD=taosdata \
./scripts/reset-dev-databases.sh
```

## Data Hub Stress Test

Use `scripts/data_hub_stress.py` to pressure-test `data-hub` MQTT ingest.

Examples:

```bash
# Local broker, 200 devices, 1000 msg/s, 60s
python scripts/data_hub_stress.py --duration 60 --rate 1000 --devices 200

# Remote broker with auth
python scripts/data_hub_stress.py \
  --host 38.14.195.2 --port 1883 \
  --username edgeadmin --password admin123 \
  --duration 120 --rate 2000 --devices 500 --workers 4 --qos 1
```

What it does:

- publishes telemetry to `edge/temperature/{device_id}/telemetry`
- sends payload schema compatible with current `data-hub` `TelemetryPayload`
- prints per-second success/failure send rates and final average throughput

### Throughput And Limit Method (Recommended)

Use this section to find both:

- `Sustainable TPS`: no sustained drops/failures, backlog does not keep growing
- `Absolute TPS`: first stable saturation point where drops/failures begin

Step-by-step:

1. Start from a conservative rate (for example `--rate 800`), run 3-5 minutes.
2. Increase rate by 10-15% each round.
3. For each round, read `data-hub` `datahub.stats` windows (30s default).
4. Stop when saturation signals appear in consecutive windows.
5. The previous stable round is your `Sustainable TPS`.

Saturation signals (any one is enough):

- `mqtt_dropped_delta > 0`
- `outcome_delta[pipelineDrop] > 0`
- `tdengine_write_failed_delta > 0` (sustained, not one short spike)
- `tdengine_batch_lane_error_delta > 0` or `tdengine_batch_restart_delta > 0`
- `buffer[current_buffer_size]` stays high and does not fall back

Accounting checks (must hold in healthy windows):

- `accounting[unaccounted_delta] == 0`
- `outcome_delta[persisted] + ingressDrop + pipelineDrop + telemetrySkip + parseFail + persistFail == mqtt_received_delta`

TPS formulas (from one `datahub.stats` window):

- Ingest TPS: `mqtt_received_delta / (intervalMs / 1000)`
- Persist TPS (all message kinds): `outcome_delta[persisted] / (intervalMs / 1000)`
- TDengine write TPS (all writes): `tdengine_write_success_delta / (intervalMs / 1000)`

Note:

- `tdengine_write_success_delta` can be higher than telemetry persisted delta because it also includes writes like `device_status`.
- For pure telemetry stress, compare `mqtt_received_delta` with `delta[telemetryOk]`.

### Rate Ramp Example

Example sequence (same device count, increase only rate):

```bash
python scripts/data_hub_stress.py --host 38.14.195.2 --port 1883 --username edgeadmin --password admin123 --duration 180 --devices 200 --workers 4 --qos 0 --rate 800
python scripts/data_hub_stress.py --host 38.14.195.2 --port 1883 --username edgeadmin --password admin123 --duration 180 --devices 200 --workers 4 --qos 0 --rate 1000
python scripts/data_hub_stress.py --host 38.14.195.2 --port 1883 --username edgeadmin --password admin123 --duration 180 --devices 200 --workers 4 --qos 0 --rate 1200
python scripts/data_hub_stress.py --host 38.14.195.2 --port 1883 --username edgeadmin --password admin123 --duration 180 --devices 200 --workers 4 --qos 0 --rate 1400
```

After each round, review:

```bash
rg "datahub.stats" data-hub/runtime/logs/data-hub.log | tail -n 20
```

When the first sustained saturation window appears, record:

- current input rate (attempted)
- max stable ingest TPS
- max stable persist TPS
- first saturation symptoms
