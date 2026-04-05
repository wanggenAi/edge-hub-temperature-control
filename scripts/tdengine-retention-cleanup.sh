#!/usr/bin/env bash
set -euo pipefail

# TDengine retention cleanup
# Deletes old rows from TDengine super tables by timestamp age.
# Safe by default with DRY_RUN=true.

TDENGINE_URL="${TDENGINE_URL:-http://127.0.0.1:6041}"
TDENGINE_DATABASE="${TDENGINE_DATABASE:-edgehub}"
TDENGINE_USERNAME="${TDENGINE_USERNAME:-root}"
TDENGINE_PASSWORD="${TDENGINE_PASSWORD:-taosdata}"
TDENGINE_TIMEOUT_SECONDS="${TDENGINE_TIMEOUT_SECONDS:-15}"

DRY_RUN="${DRY_RUN:-true}"

RETENTION_TELEMETRY_DAYS="${RETENTION_TELEMETRY_DAYS:-7}"
RETENTION_TELEMETRY_SUMMARY_DAYS="${RETENTION_TELEMETRY_SUMMARY_DAYS:-30}"
RETENTION_PARAMS_SET_DAYS="${RETENTION_PARAMS_SET_DAYS:-30}"
RETENTION_PARAMS_ACK_DAYS="${RETENTION_PARAMS_ACK_DAYS:-30}"
RETENTION_DEVICE_STATUS_DAYS="${RETENTION_DEVICE_STATUS_DAYS:-14}"
RETENTION_ALARM_EVENTS_DAYS="${RETENTION_ALARM_EVENTS_DAYS:-90}"

log() {
  printf '[%s] %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"
}

is_true() {
  local normalized
  normalized="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  case "$normalized" in
    true|1|yes|y) return 0 ;;
    *) return 1 ;;
  esac
}

cutoff_ms_for_days() {
  local days="$1"
  python3 - "$days" <<'PY'
import sys, time

days = int(float(sys.argv[1]))
now_ms = int(time.time() * 1000)
print(now_ms - days * 24 * 60 * 60 * 1000)
PY
}

td_query() {
  local sql="$1"
  local endpoint="${TDENGINE_URL%/}/rest/sql"
  local resp
  if ! resp="$(
    curl -sS --max-time "$TDENGINE_TIMEOUT_SECONDS" \
      -u "${TDENGINE_USERNAME}:${TDENGINE_PASSWORD}" \
      -H 'Content-Type: text/plain; charset=UTF-8' \
      --data-binary "$sql" \
      "$endpoint"
  )"; then
    log "ERROR request failed endpoint=${endpoint}"
    return 1
  fi
  printf '%s' "$resp"
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

parse_first_count() {
  python3 -c 'import json,sys
payload=json.loads(sys.stdin.read())
data=payload.get("data") or []
print(0 if (not data or not data[0]) else int(data[0][0]))'
}

run_sql_or_fail() {
  local sql="$1"
  local resp
  if ! resp="$(td_query "$sql")"; then
    log "ERROR SQL request error: ${sql}"
    exit 1
  fi
  local code
  code="$(printf '%s' "$resp" | parse_code)"
  if [[ "$code" != "0" ]]; then
    local desc
    desc="$(printf '%s' "$resp" | parse_desc)"
    log "ERROR SQL failed: ${sql}"
    log "ERROR TDengine response: code=${code} desc=${desc}"
    exit 1
  fi
  printf '%s' "$resp"
}

cleanup_table() {
  local stable="$1"
  local days="$2"

  local cutoff_ms
  cutoff_ms="$(cutoff_ms_for_days "$days")"

  local count_sql="SELECT COUNT(*) FROM ${TDENGINE_DATABASE}.${stable} WHERE ts < ${cutoff_ms}"
  local before_resp
  before_resp="$(run_sql_or_fail "$count_sql")"
  local before_count
  before_count="$(printf '%s' "$before_resp" | parse_first_count)"

  log "table=${stable} retention_days=${days} cutoff_ms=${cutoff_ms} old_rows=${before_count}"

  if is_true "$DRY_RUN"; then
    log "DRY-RUN table=${stable} would execute: DELETE FROM ${TDENGINE_DATABASE}.${stable} WHERE ts < ${cutoff_ms}"
    return 0
  fi

  if [[ "$before_count" -eq 0 ]]; then
    log "table=${stable} nothing to delete"
    return 0
  fi

  local delete_sql="DELETE FROM ${TDENGINE_DATABASE}.${stable} WHERE ts < ${cutoff_ms}"
  run_sql_or_fail "$delete_sql" >/dev/null

  local after_resp
  after_resp="$(run_sql_or_fail "$count_sql")"
  local after_count
  after_count="$(printf '%s' "$after_resp" | parse_first_count)"

  local deleted=$((before_count - after_count))
  if (( deleted < 0 )); then
    deleted=0
  fi

  log "table=${stable} deleted_rows=${deleted} remaining_old_rows=${after_count}"
}

main() {
  log "Starting TDengine retention cleanup"
  log "endpoint=${TDENGINE_URL%/}/rest/sql database=${TDENGINE_DATABASE} dry_run=${DRY_RUN}"

  cleanup_table "telemetry" "$RETENTION_TELEMETRY_DAYS"
  cleanup_table "telemetry_summary" "$RETENTION_TELEMETRY_SUMMARY_DAYS"
  cleanup_table "params_set" "$RETENTION_PARAMS_SET_DAYS"
  cleanup_table "params_ack" "$RETENTION_PARAMS_ACK_DAYS"
  cleanup_table "device_status" "$RETENTION_DEVICE_STATUS_DAYS"
  cleanup_table "alarm_events" "$RETENTION_ALARM_EVENTS_DAYS"

  log "TDengine retention cleanup finished"
}

main "$@"
