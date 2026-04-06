#!/usr/bin/env bash
set -euo pipefail

# Reset development databases while preserving schema structure:
# - PostgreSQL: run migrations, truncate all public tables, then optional seed.
# - TDengine: create database/stables (optional), delete all rows in key super tables.

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HMI_BACKEND_DIR="${HMI_BACKEND_DIR:-${PROJECT_ROOT}/hmi/backend}"

POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-edgehub-postgres}"
POSTGRES_DB="${POSTGRES_DB:-edgehub}"
POSTGRES_USER="${POSTGRES_USER:-edgehub}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-edgehub}"

TDENGINE_URL="${TDENGINE_URL:-http://127.0.0.1:6041}"
TDENGINE_DATABASE="${TDENGINE_DATABASE:-edgehub}"
TDENGINE_USERNAME="${TDENGINE_USERNAME:-root}"
TDENGINE_PASSWORD="${TDENGINE_PASSWORD:-taosdata}"
TDENGINE_TIMEOUT_SECONDS="${TDENGINE_TIMEOUT_SECONDS:-15}"

RESET_POSTGRES=true
RESET_TDENGINE=true
INIT_POSTGRES_SCHEMA=true
INIT_TDENGINE_SCHEMA=true
SEED_RULES=true
SEED_DEMO=false

log() {
  printf '[%s] %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"
}

usage() {
  cat <<USAGE
Usage: ./scripts/reset-dev-databases.sh [options]

Options:
  --postgres-only       Reset PostgreSQL only
  --tdengine-only       Reset TDengine only
  --skip-postgres-init  Skip PostgreSQL migration/seed step
  --skip-tdengine-init  Skip TDengine CREATE DATABASE/CREATE STABLE step
  --with-demo           Seed PostgreSQL demo users/devices/metrics
  --no-rules            Do not seed default alarm rules
  -h, --help            Show this help

Environment overrides:
  POSTGRES_CONTAINER, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
  TDENGINE_URL, TDENGINE_DATABASE, TDENGINE_USERNAME, TDENGINE_PASSWORD, TDENGINE_TIMEOUT_SECONDS
  HMI_BACKEND_DIR
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --postgres-only)
      RESET_POSTGRES=true
      RESET_TDENGINE=false
      ;;
    --tdengine-only)
      RESET_POSTGRES=false
      RESET_TDENGINE=true
      ;;
    --skip-postgres-init)
      INIT_POSTGRES_SCHEMA=false
      ;;
    --skip-tdengine-init)
      INIT_TDENGINE_SCHEMA=false
      ;;
    --with-demo)
      SEED_DEMO=true
      ;;
    --no-rules)
      SEED_RULES=false
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
  shift
done

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd" >&2
    exit 1
  fi
}

require_cmd docker
require_cmd curl
require_cmd python3

if [[ "$RESET_POSTGRES" == "false" && "$RESET_TDENGINE" == "false" ]]; then
  echo "Nothing selected to reset." >&2
  exit 1
fi

run_postgres_sql() {
  local sql="$1"
  docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "$POSTGRES_CONTAINER" \
    psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$sql"
}

reset_postgres() {
  log "PostgreSQL: checking container=${POSTGRES_CONTAINER}"
  if ! docker ps --format '{{.Names}}' | rg -x "$POSTGRES_CONTAINER" >/dev/null 2>&1; then
    echo "PostgreSQL container is not running: ${POSTGRES_CONTAINER}" >&2
    echo "Start it first: docker compose -f docker-compose.postgresql.yml up -d" >&2
    exit 1
  fi

  if [[ "$INIT_POSTGRES_SCHEMA" == "true" ]]; then
    log "PostgreSQL: running Alembic migrations (hmi/backend/scripts/db_migrate.py)"
    (
      cd "$HMI_BACKEND_DIR"
      python3 scripts/db_migrate.py
    )
  fi

  log "PostgreSQL: truncating all tables in schema public (preserve structure)"
  run_postgres_sql "DO \$\$ DECLARE stmt text; BEGIN SELECT 'TRUNCATE TABLE ' || string_agg(format('%I.%I', schemaname, tablename), ', ') || ' RESTART IDENTITY CASCADE' INTO stmt FROM pg_tables WHERE schemaname = 'public'; IF stmt IS NOT NULL THEN EXECUTE stmt; END IF; END \$\$;"

  if [[ "$INIT_POSTGRES_SCHEMA" == "true" ]]; then
    local seed_args=()
    if [[ "$SEED_RULES" == "true" ]]; then
      seed_args+=(--rules)
    fi
    if [[ "$SEED_DEMO" == "true" ]]; then
      seed_args+=(--demo)
    fi

    if [[ ${#seed_args[@]} -gt 0 ]]; then
      log "PostgreSQL: seeding $(printf '%s ' "${seed_args[@]}")"
      (
        cd "$HMI_BACKEND_DIR"
        python3 scripts/db_seed.py "${seed_args[@]}"
      )
    else
      log "PostgreSQL: seed skipped (--no-rules and no --with-demo)"
    fi
  else
    log "PostgreSQL: init/seed skipped by --skip-postgres-init"
  fi

  log "PostgreSQL reset completed"
}

td_query() {
  local sql="$1"
  local endpoint="${TDENGINE_URL%/}/rest/sql"
  curl -sS --max-time "$TDENGINE_TIMEOUT_SECONDS" \
    -u "${TDENGINE_USERNAME}:${TDENGINE_PASSWORD}" \
    -H 'Content-Type: text/plain; charset=UTF-8' \
    --data-binary "$sql" \
    "$endpoint"
}

parse_code() {
  python3 -c 'import json,sys
raw=sys.stdin.read()
try:
    payload=json.loads(raw)
except Exception:
    print(-1); raise SystemExit(0)
print(int(payload.get("code",-1)))'
}

parse_desc() {
  python3 -c 'import json,sys
raw=sys.stdin.read()
try:
    payload=json.loads(raw)
except Exception:
    compact=" ".join(raw.strip().split())
    print(compact[:240] if compact else "non-json response"); raise SystemExit(0)
print(payload.get("desc",""))'
}

is_table_not_exist_desc() {
  local desc_lower
  desc_lower="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  [[ "$desc_lower" == *"table does not exist"* || "$desc_lower" == *"stable does not exist"* || "$desc_lower" == *"invalid table name"* ]]
}

run_td_sql_or_fail() {
  local sql="$1"
  local resp
  if ! resp="$(td_query "$sql")"; then
    log "TDengine request failed: $sql"
    exit 1
  fi

  local code
  code="$(printf '%s' "$resp" | parse_code)"
  if [[ "$code" != "0" ]]; then
    local desc
    desc="$(printf '%s' "$resp" | parse_desc)"
    log "TDengine SQL failed: ${sql}"
    log "TDengine response: code=${code} desc=${desc}"
    exit 1
  fi
}

run_td_delete_allow_missing() {
  local stable="$1"
  local sql="DELETE FROM ${TDENGINE_DATABASE}.${stable} WHERE ts >= 0"
  local resp
  if ! resp="$(td_query "$sql")"; then
    log "TDengine request failed while deleting stable=${stable}"
    exit 1
  fi

  local code
  code="$(printf '%s' "$resp" | parse_code)"
  if [[ "$code" == "0" ]]; then
    log "TDengine: cleared stable=${stable}"
    return 0
  fi

  local desc
  desc="$(printf '%s' "$resp" | parse_desc)"
  if is_table_not_exist_desc "$desc"; then
    log "TDengine: stable=${stable} not found, skipped"
    return 0
  fi

  log "TDengine SQL failed: ${sql}"
  log "TDengine response: code=${code} desc=${desc}"
  exit 1
}

init_tdengine_schema() {
  run_td_sql_or_fail "CREATE DATABASE IF NOT EXISTS ${TDENGINE_DATABASE} PRECISION 'ms'"

  run_td_sql_or_fail "CREATE STABLE IF NOT EXISTS ${TDENGINE_DATABASE}.telemetry (
    ts TIMESTAMP,
    uptime_ms BIGINT,
    target_temp_c DOUBLE,
    sim_temp_c DOUBLE,
    sensor_temp_c DOUBLE,
    error_c DOUBLE,
    integral_error DOUBLE,
    control_output DOUBLE,
    pwm_duty INT,
    pwm_norm DOUBLE,
    control_period_ms BIGINT,
    saturation_state VARCHAR(32),
    sensor_valid BOOL,
    run_id VARCHAR(128),
    control_mode VARCHAR(64),
    controller_version VARCHAR(64),
    kp DOUBLE,
    ki DOUBLE,
    kd DOUBLE,
    system_state VARCHAR(64),
    sensor_status VARCHAR(32),
    actual_dt_ms BIGINT,
    dt_error_ms BIGINT,
    wifi_connected BOOL,
    mqtt_connected BOOL,
    mqtt_reconnect_count BIGINT,
    mqtt_publish_fail_count BIGINT,
    safety_output_forced_off BOOL,
    fault_latched BOOL,
    fault_reason VARCHAR(255),
    software_max_safe_temp_c DOUBLE,
    has_pending_params BOOL,
    pending_params_age_ms BIGINT
  ) TAGS (
    device_id BINARY(128),
    mqtt_topic BINARY(255)
  )"

  run_td_sql_or_fail "CREATE STABLE IF NOT EXISTS ${TDENGINE_DATABASE}.telemetry_summary (
    ts TIMESTAMP,
    run_id VARCHAR(128),
    window_start_ts TIMESTAMP,
    window_end_ts TIMESTAMP,
    duration_ms BIGINT,
    flush_reason VARCHAR(64),
    sample_count INT,
    control_period_ms BIGINT,
    uptime_start_ms BIGINT,
    uptime_end_ms BIGINT,
    target_temp_avg DOUBLE,
    sim_temp_avg DOUBLE,
    sensor_temp_avg DOUBLE,
    sensor_temp_min DOUBLE,
    sensor_temp_max DOUBLE,
    error_avg DOUBLE,
    abs_error_avg DOUBLE,
    abs_error_max DOUBLE,
    control_output_avg DOUBLE,
    control_output_min DOUBLE,
    control_output_max DOUBLE,
    pwm_duty_avg DOUBLE,
    pwm_duty_min INT,
    pwm_duty_max INT,
    pwm_norm_avg DOUBLE,
    pwm_norm_min DOUBLE,
    pwm_norm_max DOUBLE,
    control_mode VARCHAR(64),
    system_state VARCHAR(64),
    kp DOUBLE,
    ki DOUBLE,
    kd DOUBLE
  ) TAGS (
    device_id BINARY(128),
    mqtt_topic BINARY(255)
  )"

  run_td_sql_or_fail "CREATE STABLE IF NOT EXISTS ${TDENGINE_DATABASE}.params_set (
    ts TIMESTAMP,
    target_temp_c DOUBLE,
    kp DOUBLE,
    ki DOUBLE,
    kd DOUBLE,
    control_period_ms BIGINT,
    control_mode VARCHAR(64),
    apply_immediately BOOL
  ) TAGS (
    device_id BINARY(128),
    mqtt_topic BINARY(255)
  )"

  run_td_sql_or_fail "CREATE STABLE IF NOT EXISTS ${TDENGINE_DATABASE}.params_ack (
    ts TIMESTAMP,
    ack_type VARCHAR(64),
    success BOOL,
    applied_immediately BOOL,
    has_pending_params BOOL,
    target_temp_c DOUBLE,
    kp DOUBLE,
    ki DOUBLE,
    kd DOUBLE,
    control_period_ms BIGINT,
    control_mode VARCHAR(64),
    reason VARCHAR(255),
    uptime_ms BIGINT,
    sensor_valid BOOL,
    fault_latched BOOL,
    fault_reason VARCHAR(255),
    software_max_safe_temp_c DOUBLE
  ) TAGS (
    device_id BINARY(128),
    mqtt_topic BINARY(255)
  )"

  run_td_sql_or_fail "CREATE STABLE IF NOT EXISTS ${TDENGINE_DATABASE}.device_status (
    ts TIMESTAMP,
    last_seen_ts TIMESTAMP,
    online BOOL,
    status_reason VARCHAR(64),
    system_state VARCHAR(64),
    last_message_kind VARCHAR(32)
  ) TAGS (
    device_id BINARY(128),
    mqtt_topic BINARY(255)
  )"

  run_td_sql_or_fail "CREATE STABLE IF NOT EXISTS ${TDENGINE_DATABASE}.alarm_events (
    ts TIMESTAMP,
    severity VARCHAR(16),
    source VARCHAR(32),
    reason VARCHAR(255),
    alarm_event_type VARCHAR(16),
    triggered_at TIMESTAMP,
    duration_seconds BIGINT,
    context_json VARCHAR(2048)
  ) TAGS (
    device_id BINARY(128),
    rule_code BINARY(64)
  )"
}

reset_tdengine() {
  log "TDengine: endpoint=${TDENGINE_URL%/}/rest/sql database=${TDENGINE_DATABASE}"

  if [[ "$INIT_TDENGINE_SCHEMA" == "true" ]]; then
    log "TDengine: ensuring database/stables exist"
    init_tdengine_schema
  else
    log "TDengine: schema init skipped by --skip-tdengine-init"
  fi

  run_td_delete_allow_missing "telemetry"
  run_td_delete_allow_missing "telemetry_summary"
  run_td_delete_allow_missing "params_set"
  run_td_delete_allow_missing "params_ack"
  run_td_delete_allow_missing "device_status"
  run_td_delete_allow_missing "alarm_events"

  log "TDengine reset completed"
}

log "Starting reset (postgres=${RESET_POSTGRES}, tdengine=${RESET_TDENGINE})"

if [[ "$RESET_POSTGRES" == "true" ]]; then
  reset_postgres
fi

if [[ "$RESET_TDENGINE" == "true" ]]; then
  reset_tdengine
fi

log "All requested database reset actions completed"
