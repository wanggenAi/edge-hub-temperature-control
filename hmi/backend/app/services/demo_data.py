from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status

from app.core.security import hash_password
from app.models.auth import LoginRequest, UserPublic
from app.models.hmi import (
    AIRecommendation,
    AckRecord,
    ArchitectureNode,
    HistoryResponse,
    MetricCard,
    OverviewResponse,
    ParameterCommandRequest,
    ParameterPageResponse,
    ParameterState,
    QuickAction,
    RealtimeSeriesResponse,
    RunSummary,
    Series,
    TelemetrySnapshot,
    TimePoint,
)


@dataclass(frozen=True)
class DemoUserRecord:
  display_name: str
  role: str
  password_hash: str


class DemoDataService:

  def __init__(self) -> None:
    self._device_id = "edge-node-001"
    self._boot_at = datetime.now(UTC) - timedelta(hours=19, minutes=24)
    self._current_parameters = ParameterState(
        target_temp_c=35.0,
        kp=120.0,
        ki=12.0,
        kd=0.0,
        control_period_ms=1000,
        control_mode="pi_control",
        updated_at=self._iso_now(),
        data_source="fastapi_aggregate",
    )
    initial_ack = self._build_ack_record(
        reason="Initial parameter baseline synchronized for HMI demonstration.",
        received_at=datetime.now(UTC) - timedelta(minutes=18),
    )
    self._ack_history = [initial_ack]
    self._users = {
        "operator": DemoUserRecord(
            display_name="Control Operator",
            role="operator",
            password_hash=hash_password("operator123"),
        ),
        "viewer": DemoUserRecord(
            display_name="Monitoring Viewer",
            role="viewer",
            password_hash=hash_password("viewer123"),
        ),
    }

  def authenticate(self, login: LoginRequest) -> UserPublic:
    record = self._users.get(login.username)
    if not record or record.password_hash != hash_password(login.password):
      raise HTTPException(
          status_code=status.HTTP_401_UNAUTHORIZED,
          detail="Invalid username or password.",
      )
    return UserPublic(
        username=login.username,
        display_name=record.display_name,
        role=record.role,
    )

  def get_user(self, username: str) -> UserPublic:
    record = self._users.get(username)
    if not record:
      raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return UserPublic(username=username, display_name=record.display_name, role=record.role)

  def get_overview(self) -> OverviewResponse:
    snapshot = self.get_realtime_snapshot()
    latest_summary = self.get_history().runs[0]
    return OverviewResponse(
        hero_title="Intelligent Temperature Control Experimental Platform",
        hero_description=(
            "A thesis-defense-oriented HMI that separates realtime monitoring, "
            "historical analysis, parameter closed-loop control, and future AI guidance."
        ),
        live_cards=[
            self._metric("current_temp", "Current Temperature", f"{snapshot.sensor_temp_c:.2f}", "C", "Realtime telemetry", "realtime_link"),
            self._metric("target_temp", "Target Temperature", f"{snapshot.target_temp_c:.1f}", "C", "Control objective", "realtime_link"),
            self._metric("pwm", "PWM Duty", str(snapshot.pwm_duty), "", "Actuator output", "realtime_link"),
            self._metric("mode", "Control Mode", snapshot.control_mode, None, "Current controller", "fastapi_aggregate"),
        ],
        current_parameters=self._current_parameters,
        recent_ack=self._ack_history[0],
        latest_summary=latest_summary,
        architecture=[
            ArchitectureNode(name="Edge Device", role="Sampling and PWM actuation", status="running"),
            ArchitectureNode(name="Java DataHub", role="MQTT ingestion and TDengine write path", status="connected"),
            ArchitectureNode(name="TDengine", role="Historical telemetry and summary storage", status="ready"),
            ArchitectureNode(name="FastAPI HMI", role="Portal aggregation and control interaction", status="online"),
            ArchitectureNode(name="AI Layer", role="Reserved recommendation interface", status="reserved"),
        ],
        quick_actions=[
            QuickAction(title="Realtime Monitoring", route="/realtime", description="Observe current temperature, target, and PWM."),
            QuickAction(title="History Analysis", route="/history", description="Review runs, curves, and summary metrics."),
            QuickAction(title="Parameter Control", route="/params", description="Submit parameters and inspect params/ack feedback."),
            QuickAction(title="AI Guidance", route="/ai", description="Reserve a future intelligent tuning extension."),
        ],
    )

  def get_realtime_snapshot(self) -> TelemetrySnapshot:
    now = datetime.now(UTC)
    uptime_ms = int((now - self._boot_at).total_seconds() * 1000)
    phase = now.timestamp() / 45.0
    sensor_temp = self._current_parameters.target_temp_c - 0.45 + math.sin(phase) * 0.35
    sim_temp = sensor_temp + 0.22
    error_c = self._current_parameters.target_temp_c - sensor_temp
    pwm_norm = max(0.18, min(0.82, 0.54 + error_c * 0.08 + math.sin(phase / 2.8) * 0.06))
    control_output = pwm_norm * 255.0
    return TelemetrySnapshot(
        device_id=self._device_id,
        collected_at=now.isoformat(),
        uptime_ms=uptime_ms,
        target_temp_c=self._current_parameters.target_temp_c,
        sim_temp_c=round(sim_temp, 2),
        sensor_temp_c=round(sensor_temp, 2),
        error_c=round(error_c, 3),
        integral_error=round(11.4 + math.sin(phase / 3.0) * 1.6, 3),
        control_output=round(control_output, 2),
        pwm_duty=int(round(control_output)),
        pwm_norm=round(pwm_norm, 3),
        control_period_ms=self._current_parameters.control_period_ms,
        control_mode=self._current_parameters.control_mode,
        controller_version="pi_tuned_v3_1",
        kp=self._current_parameters.kp,
        ki=self._current_parameters.ki,
        kd=self._current_parameters.kd,
        system_state="running",
        has_pending_params=False,
        pending_params_age_ms=0,
        data_source="realtime_link",
    )

  def get_realtime_series(self) -> RealtimeSeriesResponse:
    now = datetime.now(UTC)
    points = []
    target_points = []
    pwm_points = []
    for index in range(24):
      ts = now - timedelta(seconds=(23 - index) * 5)
      phase = ts.timestamp() / 45.0
      sensor_temp = self._current_parameters.target_temp_c - 0.45 + math.sin(phase) * 0.35
      error_c = self._current_parameters.target_temp_c - sensor_temp
      pwm_norm = max(0.18, min(0.82, 0.54 + error_c * 0.08 + math.sin(phase / 2.8) * 0.06))
      points.append(TimePoint(ts=ts.isoformat(), value=round(sensor_temp, 2)))
      target_points.append(TimePoint(ts=ts.isoformat(), value=self._current_parameters.target_temp_c))
      pwm_points.append(TimePoint(ts=ts.isoformat(), value=round(pwm_norm * 255.0, 2)))
    return RealtimeSeriesResponse(
        window_label="Last 120 seconds",
        series=[
            Series(name="Measured Temperature", color="#005ea8", unit="C", data_source="realtime_link", points=points),
            Series(name="Target Temperature", color="#b45f06", unit="C", data_source="realtime_link", points=target_points),
            Series(name="PWM Duty", color="#3f7d20", unit="duty", data_source="realtime_link", points=pwm_points),
        ],
    )

  def get_history(self) -> HistoryResponse:
    now = datetime.now(UTC)
    temp_points = []
    target_points = []
    pwm_points = []
    for index in range(36):
      ts = now - timedelta(minutes=(35 - index) * 10)
      wave = math.sin(ts.timestamp() / 350.0)
      sensor_temp = self._current_parameters.target_temp_c - 0.6 + wave * 0.9
      pwm_duty = 142 + wave * 22
      temp_points.append(TimePoint(ts=ts.isoformat(), value=round(sensor_temp, 2)))
      target_points.append(TimePoint(ts=ts.isoformat(), value=self._current_parameters.target_temp_c))
      pwm_points.append(TimePoint(ts=ts.isoformat(), value=round(pwm_duty, 2)))

    runs = [
        RunSummary(
            run_id="run-20260403-01",
            window_start=(now - timedelta(minutes=58)).isoformat(),
            window_end=(now - timedelta(minutes=22)).isoformat(),
            duration_ms=2_160_000,
            sample_count=128,
            sensor_temp_avg=34.82,
            abs_error_max=0.88,
            pwm_duty_min=126,
            pwm_duty_max=171,
            flush_reason="window_complete",
            data_source="historical_store",
        ),
        RunSummary(
            run_id="run-20260402-03",
            window_start=(now - timedelta(hours=5, minutes=36)).isoformat(),
            window_end=(now - timedelta(hours=5, minutes=2)).isoformat(),
            duration_ms=2_040_000,
            sample_count=122,
            sensor_temp_avg=34.75,
            abs_error_max=1.02,
            pwm_duty_min=119,
            pwm_duty_max=178,
            flush_reason="idle_flush",
            data_source="historical_store",
        ),
        RunSummary(
            run_id="run-20260402-01",
            window_start=(now - timedelta(hours=11, minutes=44)).isoformat(),
            window_end=(now - timedelta(hours=11, minutes=8)).isoformat(),
            duration_ms=2_160_000,
            sample_count=130,
            sensor_temp_avg=34.69,
            abs_error_max=1.15,
            pwm_duty_min=118,
            pwm_duty_max=183,
            flush_reason="window_complete",
            data_source="historical_store",
        ),
    ]
    return HistoryResponse(
        range_label="Recent 6 hours",
        kpis=[
            self._metric("avg_temp", "Average Temperature", "34.75", "C", "Historical mean", "historical_store"),
            self._metric("max_error", "Max Absolute Error", "1.15", "C", "Tracking quality", "historical_store"),
            self._metric("avg_pwm", "Average PWM", "149", "", "Actuation intensity", "historical_store"),
            self._metric("runs", "Recorded Summaries", "3", "", "DataHub summary windows", "fastapi_aggregate"),
        ],
        series=[
            Series(name="Historical Temperature", color="#005ea8", unit="C", data_source="historical_store", points=temp_points),
            Series(name="Historical Target", color="#b45f06", unit="C", data_source="historical_store", points=target_points),
            Series(name="Historical PWM", color="#3f7d20", unit="duty", data_source="historical_store", points=pwm_points),
        ],
        runs=runs,
    )

  def get_parameters_page(self) -> ParameterPageResponse:
    return ParameterPageResponse(
        current=self._current_parameters,
        latest_ack=self._ack_history[0],
        recent_acks=self._ack_history[:5],
    )

  def submit_parameters(self, command: ParameterCommandRequest) -> AckRecord:
    self._current_parameters = ParameterState(
        target_temp_c=command.target_temp_c,
        kp=command.kp,
        ki=command.ki,
        kd=command.kd,
        control_period_ms=command.control_period_ms,
        control_mode=command.control_mode,
        updated_at=self._iso_now(),
        data_source="fastapi_aggregate",
    )
    ack = self._build_ack_record(
        reason="Parameter command accepted and synchronized with the edge control path.",
        received_at=datetime.now(UTC),
    )
    self._ack_history.insert(0, ack)
    return ack

  def get_ai_recommendations(self) -> list[AIRecommendation]:
    return [
        AIRecommendation(
            title="Reduce overshoot during heating ramp",
            category="PID Tuning Reserve",
            summary="A future optimizer can slightly lower Kp while preserving current target tracking.",
            reason="Recent historical windows show a mild overshoot band near the target plateau.",
            confidence=0.82,
            status="reserved",
            suggested_target_temp_c=self._current_parameters.target_temp_c,
            suggested_kp=116.0,
            suggested_ki=11.0,
            suggested_kd=0.0,
            data_source="ai_reserved",
        ),
        AIRecommendation(
            title="Flag actuator load fluctuation",
            category="Anomaly Reserve",
            summary="A future AI module can inspect PWM variance and identify unstable thermal behavior early.",
            reason="The HMI reserves a slot for health scoring and experiment interpretation.",
            confidence=0.71,
            status="reserved",
            data_source="ai_reserved",
        ),
    ]

  def _build_ack_record(self, reason: str, received_at: datetime) -> AckRecord:
    uptime_ms = int((received_at - self._boot_at).total_seconds() * 1000)
    return AckRecord(
        ack_type="params_applied",
        success=True,
        applied_immediately=True,
        has_pending_params=False,
        target_temp_c=self._current_parameters.target_temp_c,
        kp=self._current_parameters.kp,
        ki=self._current_parameters.ki,
        kd=self._current_parameters.kd,
        control_period_ms=self._current_parameters.control_period_ms,
        control_mode=self._current_parameters.control_mode,
        reason=reason,
        uptime_ms=uptime_ms,
        received_at=received_at.isoformat(),
        data_source="fastapi_aggregate",
    )

  def _iso_now(self) -> str:
    return datetime.now(UTC).isoformat()

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


demo_data_service = DemoDataService()
