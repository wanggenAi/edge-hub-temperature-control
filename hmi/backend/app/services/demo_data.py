from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import HTTPException, status

from app.models.auth import (
    DeleteResult,
    LoginRequest,
    ManagedUser,
    RoleDefinition,
    RoleUpsertRequest,
    UserPublic,
    UserUpsertRequest,
)
from app.models.hmi import (
    AIPageResponse,
    AIRecommendation,
    AckRecord,
    ControlGoalsConfig,
    ControlEffectComparison,
    DevicePageResponse,
    DeviceStatsResponse,
    DeviceSummary,
    DeviceUpsertRequest,
    HistoryResponse,
    MetricCard,
    OverviewResponse,
    ParameterCommandRequest,
    ParameterPageResponse,
    ParameterState,
    RealtimeSeriesResponse,
    RunSummary,
    Series,
    SystemAccessResponse,
    TelemetrySnapshot,
    TimePoint,
)
from app.services.json_store import JsonStore
from app.services.access_control import access_control_service
from app.services.control_compare import CompareConfig, build_ai_adoption_compare, build_compare_config, build_params_tuning_compare


class DemoDataService:

  def __init__(self) -> None:
    store_path = Path(__file__).resolve().parents[2] / "data" / "store.json"
    self._store = JsonStore(store_path)

  def authenticate(self, login: LoginRequest) -> UserPublic:
    return access_control_service.authenticate(login)

  def get_user(self, username: str) -> UserPublic:
    return access_control_service.get_user(username)

  def list_devices(self, username: str) -> list[DeviceSummary]:
    return access_control_service.list_devices_for_user(username)

  def list_devices_paginated(self, username: str, page: int, page_size: int, q: str | None = None) -> DevicePageResponse:
    return access_control_service.list_devices_for_user_paginated(username, page, page_size, q=q)

  def get_device_stats(self, username: str) -> DeviceStatsResponse:
    return access_control_service.get_device_stats_for_user(username)

  def create_device(self, username: str, payload: DeviceUpsertRequest) -> DeviceSummary:

    def updater(store_payload: dict) -> dict:
      existing = next((item for item in store_payload["devices"] if item["device_id"] == payload.device_id), None)
      if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Device already exists.")
      now = datetime.now(UTC)
      store_payload["devices"].append(
          {
              "device_id": payload.device_id,
              "name": payload.name,
              "location": payload.location,
              "status": payload.status,
              "target_temp_c": payload.target_temp_c,
              "kp": 100.0,
              "ki": 10.0,
              "kd": 0.0,
              "control_period_ms": 1000,
              "control_mode": payload.control_mode,
              "controller_version": "pi_default_v1",
              "booted_at": now.isoformat(),
              "base_temp_c": max(20.0, min(payload.target_temp_c - 0.5, 59.0)),
              "variation": 0.25,
              "updated_at": now.isoformat(),
          },
      )
      store_payload.setdefault("acks", {})[payload.device_id] = []
      return store_payload

    self._store.update(updater)
    access_control_service.reconcile_devices_from_store()
    access_control_service.grant_device_to_user(username, payload.device_id)
    devices = access_control_service.list_devices_for_user(username)
    created = next((device for device in devices if device.device_id == payload.device_id), None)
    if created is None:
      raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Device create failed.")
    return created

  def update_device(self, username: str, device_id: str, payload: DeviceUpsertRequest) -> DeviceSummary:
    if payload.device_id != device_id:
      raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Device ID in path and body must match.")
    if not access_control_service.can_manage_device(username, device_id):
      raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Device access denied.")

    def updater(store_payload: dict) -> dict:
      existing = next((item for item in store_payload["devices"] if item["device_id"] == device_id), None)
      if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found.")
      existing["name"] = payload.name
      existing["location"] = payload.location
      existing["status"] = payload.status
      existing["target_temp_c"] = payload.target_temp_c
      existing["control_mode"] = payload.control_mode
      existing["updated_at"] = self._iso_now()
      return store_payload

    self._store.update(updater)
    access_control_service.reconcile_devices_from_store()
    devices = access_control_service.list_devices_for_user(username)
    updated = next((device for device in devices if device.device_id == payload.device_id), None)
    if updated is None:
      raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found.")
    return updated

  def delete_device(self, username: str, device_id: str) -> DeleteResult:
    if not access_control_service.can_manage_device(username, device_id):
      raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Device access denied.")

    def updater(store_payload: dict) -> dict:
      current = next((item for item in store_payload["devices"] if item["device_id"] == device_id), None)
      if current is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found.")
      store_payload["devices"] = [item for item in store_payload["devices"] if item["device_id"] != device_id]
      store_payload.setdefault("acks", {}).pop(device_id, None)
      return store_payload

    self._store.update(updater)
    access_control_service.reconcile_devices_from_store()
    return DeleteResult(resource="device", key=device_id)

  def get_overview(self, username: str, device_id: str | None = None) -> OverviewResponse:
    payload = self._store.read()
    device = self._resolve_device(payload, username, device_id)
    snapshot = self._snapshot_from_device(device)
    history = self._history_for_device(device)
    recent_ack = self._latest_ack(payload, device["device_id"])
    return OverviewResponse(
        hero_title="EdgeHub HMI",
        hero_description="Monitor current state, history, and parameter updates.",
        selected_device=self._device_summary(device),
        telemetry_collected_at=snapshot.collected_at,
        live_cards=[
            self._metric("current_temp", "Current Temperature", f"{snapshot.sensor_temp_c:.2f}", "C", None, "realtime_link"),
            self._metric("target_temp", "Target Temperature", f"{snapshot.target_temp_c:.1f}", "C", None, "realtime_link"),
            self._metric("pwm", "PWM Output", str(snapshot.pwm_duty), None, None, "realtime_link"),
            self._metric("mode", "Mode", snapshot.control_mode, None, None, "fastapi_aggregate"),
        ],
        current_parameters=self._parameter_state(device),
        recent_ack=recent_ack,
        latest_summary=history.runs[0],
        architecture=[],
        quick_actions=[],
    )

  def get_realtime_snapshot(self, username: str, device_id: str | None = None) -> TelemetrySnapshot:
    payload = self._store.read()
    device = self._resolve_device(payload, username, device_id)
    return self._snapshot_from_device(device)

  def get_realtime_series(self, username: str, device_id: str | None = None) -> RealtimeSeriesResponse:
    payload = self._store.read()
    device = self._resolve_device(payload, username, device_id)
    goals = self._control_goals_config(payload)
    now = datetime.now(UTC)
    temp_points: list[TimePoint] = []
    target_points: list[TimePoint] = []
    pwm_points: list[TimePoint] = []
    steady_error_points: list[TimePoint] = []
    recent_errors: list[float] = []
    hold_samples = max(1, math.ceil(goals.steady_hold_seconds / 5))
    for index in range(24):
      ts = now - timedelta(seconds=(23 - index) * 5)
      sensor_temp, pwm_duty = self._realtime_wave(device, ts)
      error_c = device["target_temp_c"] - sensor_temp
      temp_points.append(TimePoint(ts=ts.isoformat(), value=round(sensor_temp, 2)))
      target_points.append(TimePoint(ts=ts.isoformat(), value=device["target_temp_c"]))
      pwm_points.append(TimePoint(ts=ts.isoformat(), value=round(pwm_duty, 2)))
      recent_errors.append(error_c)
      if len(recent_errors) > hold_samples:
        recent_errors.pop(0)
      steady_error = sum(abs(value) for value in recent_errors) / len(recent_errors)
      steady_error_points.append(TimePoint(ts=ts.isoformat(), value=round(steady_error, 3)))
    return RealtimeSeriesResponse(
        device_id=device["device_id"],
        window_label="Last 120 seconds",
        series=[
            Series(name="Temperature", color="#124B8F", unit="C", data_source="realtime_link", points=temp_points),
            Series(name="Target", color="#D97706", unit="C", data_source="realtime_link", points=target_points),
            Series(name="PWM", color="#2B8C83", unit="duty", data_source="realtime_link", points=pwm_points),
        ],
        steady_error_series=Series(
            name="Steady-state error",
            color="#D97706",
            unit="C",
            data_source="fastapi_aggregate",
            points=steady_error_points,
        ),
        goals=ControlGoalsConfig(**goals.__dict__),
    )

  def get_history(self, username: str, device_id: str | None = None) -> HistoryResponse:
    payload = self._store.read()
    device = self._resolve_device(payload, username, device_id)
    return self._history_for_device(device)

  def get_parameters_page(self, username: str, device_id: str | None = None) -> ParameterPageResponse:
    payload = self._store.read()
    device = self._resolve_device(payload, username, device_id)
    ack_history = self._acks_for_device(payload, device["device_id"])
    return ParameterPageResponse(
        device_id=device["device_id"],
        current=self._parameter_state(device),
        latest_ack=self._latest_ack(payload, device["device_id"]),
        recent_acks=self._recent_acks(payload, device["device_id"]),
        latest_tuning_compare=build_params_tuning_compare(device, ack_history, self._control_goals_config(payload)),
    )

  def submit_parameters(self, username: str, command: ParameterCommandRequest) -> AckRecord:
    target_device_id = access_control_service.resolve_device_scope(username, command.device_id)

    def updater(payload: dict) -> dict:
      device = self._resolve_device_by_id(payload, target_device_id)
      device["target_temp_c"] = command.target_temp_c
      device["kp"] = command.kp
      device["ki"] = command.ki
      device["kd"] = command.kd
      device["control_period_ms"] = command.control_period_ms
      device["control_mode"] = command.control_mode
      device["updated_at"] = self._iso_now()
      ack = self._build_ack_record(device, "Parameter command accepted and synchronized.")
      payload.setdefault("acks", {}).setdefault(device["device_id"], []).insert(0, ack.model_dump())
      return payload

    payload = self._store.update(updater)
    device = self._resolve_device_by_id(payload, target_device_id)
    return self._latest_ack(payload, device["device_id"])

  def get_ai_page(self, username: str, device_id: str | None = None) -> AIPageResponse:
    payload = self._store.read()
    device = self._resolve_device(payload, username, device_id)
    history = self._history_for_device(device)
    max_error = history.runs[0].abs_error_max
    recommendations = [
        AIRecommendation(
            device_id=device["device_id"],
            title="Reduce overshoot during approach",
            category="PID tuning",
            summary="Lower Kp slightly while keeping Ki steady to reduce overshoot near the setpoint.",
            reason=f"Latest run on {device['device_id']} shows max error {max_error:.2f} C with stable average tracking.",
            confidence=0.82,
            status="Advisory",
            suggested_target_temp_c=device["target_temp_c"],
            suggested_kp=max(60.0, device["kp"] - 4.0),
            suggested_ki=max(1.0, device["ki"] - 1.0),
            suggested_kd=device["kd"],
            data_source="ai_reserved",
        ),
        AIRecommendation(
            device_id=device["device_id"],
            title="Watch actuator load fluctuation",
            category="Stability review",
            summary="Check the next run for narrower PWM spread before further parameter changes.",
            reason=f"{device['device_id']} shows sustained PWM activity across recent windows and may still be settling.",
            confidence=0.71,
            status="Observe",
            data_source="ai_reserved",
        ),
    ]
    ack_history = self._acks_for_device(payload, device["device_id"])
    compare: ControlEffectComparison = build_ai_adoption_compare(
        device=device,
        acks=ack_history,
        recommendation=recommendations[0] if recommendations else None,
        config=self._control_goals_config(payload),
    )
    return AIPageResponse(
        device_id=device["device_id"],
        recommendations=recommendations,
        adoption_compare=compare,
    )

  def get_access_control(self) -> SystemAccessResponse:
    return access_control_service.get_access_control()

  def get_control_goals(self) -> ControlGoalsConfig:
    payload = self._store.read()
    config = self._control_goals_config(payload)
    return ControlGoalsConfig(**config.__dict__)

  def upsert_control_goals(self, config: ControlGoalsConfig) -> ControlGoalsConfig:
    def updater(store_payload: dict) -> dict:
      store_payload["control_goals"] = config.model_dump()
      return store_payload

    self._store.update(updater)
    return config

  def upsert_user(self, request: UserUpsertRequest) -> ManagedUser:
    return access_control_service.upsert_user(request)

  def delete_user(self, username: str) -> DeleteResult:
    return access_control_service.delete_user(username)

  def upsert_role(self, request: RoleUpsertRequest) -> RoleDefinition:
    return access_control_service.upsert_role(request)

  def _to_user_public(self, payload: dict, user_record: dict) -> UserPublic:
    role = self._resolve_role(payload, user_record["role"])
    return UserPublic(
        username=user_record["username"],
        display_name=user_record["display_name"],
        role=user_record["role"],
        permissions=self._permissions_for_role(payload, role["key"]),
    )

  def _to_managed_user(self, payload: dict, user_record: dict) -> ManagedUser:
    public = self._to_user_public(payload, user_record)
    return ManagedUser(**public.model_dump(), enabled=user_record.get("enabled", True))

  def _resolve_role(self, payload: dict, role_key: str) -> dict:
    role = next((item for item in payload["roles"] if item["key"] == role_key), None)
    if role is None:
      raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Role missing in store.")
    return role

  def _permissions_for_role(self, payload: dict, role_key: str) -> list[str]:
    if role_key == "admin":
      return [item["key"] for item in payload["permissions"]]
    role = self._resolve_role(payload, role_key)
    return role["permissions"]

  def _ensure_role_exists(self, payload: dict, role_key: str) -> None:
    if next((item for item in payload["roles"] if item["key"] == role_key), None) is None:
      raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Assigned role does not exist.")

  def _find_user_record(self, payload: dict, username: str) -> dict | None:
    return next((item for item in payload["users"] if item["username"] == username), None)

  def _resolve_device(self, payload: dict, username: str, device_id: str | None) -> dict:
    resolved_id = access_control_service.resolve_device_scope(username, device_id)
    return self._resolve_device_by_id(payload, resolved_id)

  def _resolve_device_by_id(self, payload: dict, device_id: str) -> dict:
    devices = payload["devices"]
    if not devices:
      raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No devices configured.")
    device = next((item for item in devices if item["device_id"] == device_id), None)
    if device is None:
      raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found.")
    return device

  def _device_summary(self, device: dict) -> DeviceSummary:
    return DeviceSummary(
        device_id=device["device_id"],
        name=device["name"],
        location=device["location"],
        status=device["status"],
        target_temp_c=device["target_temp_c"],
        control_mode=device["control_mode"],
        updated_at=device["updated_at"],
    )

  def _parameter_state(self, device: dict) -> ParameterState:
    return ParameterState(
        device_id=device["device_id"],
        target_temp_c=device["target_temp_c"],
        kp=device["kp"],
        ki=device["ki"],
        kd=device["kd"],
        control_period_ms=device["control_period_ms"],
        control_mode=device["control_mode"],
        updated_at=device["updated_at"],
        data_source="fastapi_aggregate",
    )

  def _latest_ack(self, payload: dict, device_id: str) -> AckRecord:
    ack_payload = payload.get("acks", {}).get(device_id, [])
    if not ack_payload:
      device = self._resolve_device_by_id(payload, device_id)
      return self._build_ack_record(device, "No ack history available yet.")
    return AckRecord.model_validate(ack_payload[0])

  def _recent_acks(self, payload: dict, device_id: str) -> list[AckRecord]:
    ack_payload = payload.get("acks", {}).get(device_id, [])
    return [AckRecord.model_validate(item) for item in ack_payload[:5]]

  def _acks_for_device(self, payload: dict, device_id: str) -> list[AckRecord]:
    ack_payload = payload.get("acks", {}).get(device_id, [])
    return [AckRecord.model_validate(item) for item in ack_payload]

  def _build_ack_record(self, device: dict, reason: str) -> AckRecord:
    booted_at = datetime.fromisoformat(device["booted_at"])
    received_at = datetime.now(UTC)
    uptime_ms = int((received_at - booted_at).total_seconds() * 1000)
    return AckRecord(
        device_id=device["device_id"],
        ack_type="params_applied",
        success=True,
        applied_immediately=True,
        has_pending_params=False,
        target_temp_c=device["target_temp_c"],
        kp=device["kp"],
        ki=device["ki"],
        kd=device["kd"],
        control_period_ms=device["control_period_ms"],
        control_mode=device["control_mode"],
        reason=reason,
        uptime_ms=uptime_ms,
        received_at=received_at.isoformat(),
        data_source="fastapi_aggregate",
    )

  def _snapshot_from_device(self, device: dict) -> TelemetrySnapshot:
    now = datetime.now(UTC)
    booted_at = datetime.fromisoformat(device["booted_at"])
    uptime_ms = int((now - booted_at).total_seconds() * 1000)
    sensor_temp, pwm_duty = self._realtime_wave(device, now)
    sim_temp = sensor_temp + 0.18
    error_c = device["target_temp_c"] - sensor_temp
    pwm_norm = max(0.0, min(1.0, pwm_duty / 255.0))
    return TelemetrySnapshot(
        device_id=device["device_id"],
        collected_at=now.isoformat(),
        uptime_ms=uptime_ms,
        target_temp_c=device["target_temp_c"],
        sim_temp_c=round(sim_temp, 2),
        sensor_temp_c=round(sensor_temp, 2),
        error_c=round(error_c, 3),
        integral_error=round(10.2 + math.sin(now.timestamp() / 160.0) * 1.4, 3),
        control_output=round(float(pwm_duty), 2),
        pwm_duty=int(round(pwm_duty)),
        pwm_norm=round(pwm_norm, 3),
        control_period_ms=device["control_period_ms"],
        control_mode=device["control_mode"],
        controller_version=device["controller_version"],
        kp=device["kp"],
        ki=device["ki"],
        kd=device["kd"],
        system_state=device["status"],
        has_pending_params=False,
        pending_params_age_ms=0,
        data_source="realtime_link",
    )

  def _realtime_wave(self, device: dict, ts: datetime) -> tuple[float, float]:
    phase = ts.timestamp() / 45.0
    base_temp = device["base_temp_c"]
    variation = device["variation"]
    sensor_temp = base_temp + math.sin(phase) * variation
    error_c = device["target_temp_c"] - sensor_temp
    pwm_norm = max(0.12, min(0.84, 0.48 + error_c * 0.08 + math.sin(phase / 2.6) * 0.05))
    if device["status"] == "idle":
      pwm_norm = min(pwm_norm, 0.2)
    return sensor_temp, pwm_norm * 255.0

  def _history_for_device(self, device: dict) -> HistoryResponse:
    now = datetime.now(UTC)
    temp_points: list[TimePoint] = []
    target_points: list[TimePoint] = []
    pwm_points: list[TimePoint] = []
    for index in range(36):
      ts = now - timedelta(minutes=(35 - index) * 10)
      wave = math.sin(ts.timestamp() / 350.0)
      sensor_temp = device["base_temp_c"] + wave * (device["variation"] * 2.1)
      pwm_duty = 132 + wave * 18 + (device["kp"] / 12)
      temp_points.append(TimePoint(ts=ts.isoformat(), value=round(sensor_temp, 2)))
      target_points.append(TimePoint(ts=ts.isoformat(), value=device["target_temp_c"]))
      pwm_points.append(TimePoint(ts=ts.isoformat(), value=round(pwm_duty, 2)))

    runs = [
        RunSummary(
            device_id=device["device_id"],
            run_id=f"{device['device_id']}-run-01",
            window_start=(now - timedelta(minutes=58)).isoformat(),
            window_end=(now - timedelta(minutes=22)).isoformat(),
            duration_ms=2_160_000,
            sample_count=128,
            sensor_temp_avg=round(device["base_temp_c"] + 0.24, 2),
            abs_error_max=round(abs(device["target_temp_c"] - device["base_temp_c"]) + 0.42, 2),
            pwm_duty_min=126,
            pwm_duty_max=171,
            flush_reason="window_complete",
            data_source="historical_store",
        ),
        RunSummary(
            device_id=device["device_id"],
            run_id=f"{device['device_id']}-run-00",
            window_start=(now - timedelta(hours=5, minutes=36)).isoformat(),
            window_end=(now - timedelta(hours=5, minutes=2)).isoformat(),
            duration_ms=2_040_000,
            sample_count=122,
            sensor_temp_avg=round(device["base_temp_c"] + 0.18, 2),
            abs_error_max=round(abs(device["target_temp_c"] - device["base_temp_c"]) + 0.61, 2),
            pwm_duty_min=119,
            pwm_duty_max=178,
            flush_reason="idle_flush",
            data_source="historical_store",
        ),
    ]
    return HistoryResponse(
        device_id=device["device_id"],
        range_label="Recent 6 hours",
        kpis=[
            self._metric("avg_temp", "Average Temperature", f"{runs[0].sensor_temp_avg:.2f}", "C", None, "historical_store"),
            self._metric("max_error", "Max Absolute Error", f"{runs[0].abs_error_max:.2f}", "C", None, "historical_store"),
            self._metric("avg_pwm", "Average PWM", "149", None, None, "historical_store"),
            self._metric("runs", "Recorded Runs", str(len(runs)), None, None, "fastapi_aggregate"),
        ],
        series=[
            Series(name="Temperature", color="#124B8F", unit="C", data_source="historical_store", points=temp_points),
            Series(name="Target", color="#D97706", unit="C", data_source="historical_store", points=target_points),
            Series(name="PWM", color="#2B8C83", unit="duty", data_source="historical_store", points=pwm_points),
        ],
        runs=runs,
    )

  def _metric(
      self,
      key: str,
      label: str,
      value: str,
      unit: str | None,
      trend_hint: str | None,
      data_source: str,
  ) -> MetricCard:
    return MetricCard(
        key=key,
        label=label,
        value=value,
        unit=unit,
        trend_hint=trend_hint,
        data_source=data_source,
    )

  def _iso_now(self) -> str:
    return datetime.now(UTC).isoformat()

  def _control_goals_config(self, payload: dict) -> CompareConfig:
    return build_compare_config(payload.get("control_goals"))


demo_data_service = DemoDataService()
