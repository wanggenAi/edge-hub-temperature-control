from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any

from app.core.security import hash_password


class JsonStore:

  def __init__(self, path: Path) -> None:
    self._path = path
    self._lock = Lock()
    self._ensure_store()

  def read(self) -> dict[str, Any]:
    with self._lock:
      return json.loads(self._path.read_text(encoding="utf-8"))

  def write(self, payload: dict[str, Any]) -> None:
    with self._lock:
      self._path.write_text(
          json.dumps(payload, indent=2, ensure_ascii=True),
          encoding="utf-8",
      )

  def update(self, updater: callable) -> dict[str, Any]:
    with self._lock:
      payload = json.loads(self._path.read_text(encoding="utf-8"))
      next_payload = updater(deepcopy(payload))
      self._path.write_text(
          json.dumps(next_payload, indent=2, ensure_ascii=True),
          encoding="utf-8",
      )
      return next_payload

  def _ensure_store(self) -> None:
    self._path.parent.mkdir(parents=True, exist_ok=True)
    if self._path.exists():
      return
    self._path.write_text(
        json.dumps(_default_payload(), indent=2, ensure_ascii=True),
        encoding="utf-8",
    )


def _default_payload() -> dict[str, Any]:
  now = datetime.now(UTC)
  default_permissions = [
      {
          "key": "overview.view",
          "label": "Overview View",
          "description": "View system overview and status",
      },
      {
          "key": "realtime.view",
          "label": "Realtime View",
          "description": "View live telemetry and status",
      },
      {
          "key": "history.view",
          "label": "History View",
          "description": "View historical curves and run summaries",
      },
      {
          "key": "params.view",
          "label": "Parameters View",
          "description": "View active parameter state",
      },
      {
          "key": "params.write",
          "label": "Parameters Write",
          "description": "Submit parameter updates",
      },
      {
          "key": "ai.view",
          "label": "AI View",
          "description": "View AI recommendations and rationale",
      },
      {
          "key": "devices.manage",
          "label": "Devices Manage",
          "description": "Create, edit, delete, and page device inventory",
      },
      {
          "key": "system.manage",
          "label": "System Manage",
          "description": "Manage users, roles, and device inventory",
      },
  ]

  roles = [
      {
          "key": "admin",
          "name": "Administrator",
          "permissions": [permission["key"] for permission in default_permissions],
      },
      {
          "key": "operator",
          "name": "Operator",
          "permissions": [
              "overview.view",
              "realtime.view",
              "history.view",
              "params.view",
              "params.write",
              "ai.view",
              "devices.manage",
          ],
      },
      {
          "key": "viewer",
          "name": "Viewer",
          "permissions": [
              "overview.view",
              "realtime.view",
              "history.view",
              "params.view",
              "ai.view",
          ],
      },
  ]

  devices = [
      {
          "device_id": "edge-node-001",
          "name": "Zone 1 Chamber",
          "location": "Lab A",
          "status": "running",
          "target_temp_c": 35.0,
          "kp": 120.0,
          "ki": 12.0,
          "kd": 0.0,
          "control_period_ms": 1000,
          "control_mode": "pi_control",
          "controller_version": "pi_tuned_v3_1",
          "booted_at": (now - timedelta(hours=19, minutes=24)).isoformat(),
          "base_temp_c": 34.55,
          "variation": 0.35,
          "updated_at": now.isoformat(),
      },
      {
          "device_id": "edge-node-002",
          "name": "Zone 2 Chamber",
          "location": "Lab B",
          "status": "running",
          "target_temp_c": 33.0,
          "kp": 108.0,
          "ki": 10.0,
          "kd": 0.0,
          "control_period_ms": 1000,
          "control_mode": "pi_control",
          "controller_version": "pi_tuned_v3_0",
          "booted_at": (now - timedelta(hours=8, minutes=12)).isoformat(),
          "base_temp_c": 32.62,
          "variation": 0.28,
          "updated_at": now.isoformat(),
      },
      {
          "device_id": "edge-node-003",
          "name": "Aging Rack",
          "location": "Pilot Line",
          "status": "idle",
          "target_temp_c": 30.0,
          "kp": 100.0,
          "ki": 9.0,
          "kd": 0.0,
          "control_period_ms": 1000,
          "control_mode": "manual_hold",
          "controller_version": "pi_safe_v1_4",
          "booted_at": (now - timedelta(hours=4, minutes=3)).isoformat(),
          "base_temp_c": 29.74,
          "variation": 0.18,
          "updated_at": now.isoformat(),
      },
  ]

  acks = {}
  for device in devices:
    received_at = (now - timedelta(minutes=18)).isoformat()
    acks[device["device_id"]] = [
      {
          "device_id": device["device_id"],
          "ack_type": "params_applied",
          "success": True,
          "applied_immediately": True,
          "has_pending_params": False,
          "target_temp_c": device["target_temp_c"],
          "kp": device["kp"],
          "ki": device["ki"],
          "kd": device["kd"],
          "control_period_ms": device["control_period_ms"],
          "control_mode": device["control_mode"],
          "reason": "Initial parameter baseline synchronized for HMI startup.",
          "uptime_ms": 0,
          "received_at": received_at,
          "data_source": "fastapi_aggregate",
      },
    ]

  return {
      "permissions": default_permissions,
      "roles": roles,
      "users": [
          {
              "username": "admin",
              "display_name": "System Admin",
              "role": "admin",
              "password_hash": hash_password("admin123"),
              "enabled": True,
          },
          {
              "username": "operator",
              "display_name": "Control Operator",
              "role": "operator",
              "password_hash": hash_password("operator123"),
              "enabled": True,
          },
          {
              "username": "viewer",
              "display_name": "Monitoring Viewer",
              "role": "viewer",
              "password_hash": hash_password("viewer123"),
              "enabled": True,
          },
      ],
      "devices": devices,
      "acks": acks,
      "control_goals": {
          "target_band_c": 0.3,
          "temp_rate_threshold_c_per_s": 0.02,
          "steady_hold_seconds": 60,
          "flat_change_pct": 5.0,
          "pwm_saturation_low": 10,
          "pwm_saturation_high": 245,
          "realtime_steady_error_axis_c": 1.2,
      },
  }
