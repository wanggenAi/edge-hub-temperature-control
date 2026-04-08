from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class UserRole(Base):
    __tablename__ = "user_roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), index=True)

    user: Mapped["User"] = relationship(back_populates="user_roles")
    role: Mapped["Role"] = relationship(back_populates="user_roles")

    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role"),)


class UserDevice(Base):
    __tablename__ = "user_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)

    user: Mapped["User"] = relationship(back_populates="user_devices")
    device: Mapped["Device"] = relationship(back_populates="user_devices")

    __table_args__ = (UniqueConstraint("user_id", "device_id", name="uq_user_device"),)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user_roles: Mapped[list[UserRole]] = relationship(back_populates="user", cascade="all, delete-orphan")
    user_devices: Mapped[list[UserDevice]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(255), default="")

    user_roles: Mapped[list[UserRole]] = relationship(back_populates="role", cascade="all, delete-orphan")


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    line: Mapped[str] = mapped_column(String(64), default="Line 1")
    location: Mapped[str] = mapped_column(String(128), default="Factory")
    status: Mapped[str] = mapped_column(String(32), default="active")
    current_temp: Mapped[float] = mapped_column(Float, default=25.0)
    target_temp: Mapped[float] = mapped_column(Float, default=37.0)
    pwm_output: Mapped[float] = mapped_column(Float, default=0.0)
    is_alarm: Mapped[bool] = mapped_column(Boolean, default=False)
    is_online: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user_devices: Mapped[list[UserDevice]] = relationship(back_populates="device", cascade="all, delete-orphan")
    metrics: Mapped[list["DeviceMetric"]] = relationship(back_populates="device", cascade="all, delete-orphan")
    parameters: Mapped[list["DeviceParameter"]] = relationship(back_populates="device", cascade="all, delete-orphan")
    alarms: Mapped[list["DeviceAlarm"]] = relationship(back_populates="device", cascade="all, delete-orphan")
    ai_recommendations: Mapped[list["AIRecommendation"]] = relationship(back_populates="device", cascade="all, delete-orphan")
    summaries: Mapped[list["DeviceSummary"]] = relationship(back_populates="device", cascade="all, delete-orphan")
    control_actions: Mapped[list["ControlAction"]] = relationship(back_populates="device", cascade="all, delete-orphan")
    control_action_eval_jobs: Mapped[list["ControlActionEvalJob"]] = relationship(back_populates="device", cascade="all, delete-orphan")
    control_action_feedback_samples: Mapped[list["ControlActionFeedbackSample"]] = relationship(back_populates="device", cascade="all, delete-orphan")


class DeviceMetric(Base):
    __tablename__ = "device_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    current_temp: Mapped[float] = mapped_column(Float)
    target_temp: Mapped[float] = mapped_column(Float)
    error: Mapped[float] = mapped_column(Float)
    pwm_output: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), default="active")
    in_spec: Mapped[bool] = mapped_column(Boolean, default=True)
    is_alarm: Mapped[bool] = mapped_column(Boolean, default=False)

    device: Mapped[Device] = relationship(back_populates="metrics")


class DeviceParameter(Base):
    __tablename__ = "device_parameters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    kp: Mapped[float] = mapped_column(Float, default=2.8)
    ki: Mapped[float] = mapped_column(Float, default=0.45)
    kd: Mapped[float] = mapped_column(Float, default=0.12)
    control_mode: Mapped[str] = mapped_column(String(32), default="pid_control")
    target_band: Mapped[float] = mapped_column(Float, default=0.5)
    overshoot_limit_pct: Mapped[float] = mapped_column(Float, default=3.0)
    saturation_warn_ratio: Mapped[float] = mapped_column(Float, default=0.3)
    saturation_high_ratio: Mapped[float] = mapped_column(Float, default=0.6)
    pwm_saturation_threshold: Mapped[float] = mapped_column(Float, default=85.0)
    steady_window_samples: Mapped[int] = mapped_column(Integer, default=12)
    sampling_period_ms: Mapped[int] = mapped_column(Integer, default=250)
    upload_period_s: Mapped[int] = mapped_column(Integer, default=10)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by: Mapped[str] = mapped_column(String(64), default="system")

    device: Mapped[Device] = relationship(back_populates="parameters")


class DeviceAlarm(Base):
    __tablename__ = "device_alarms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    level: Mapped[str] = mapped_column(String(16), default="warning")
    rule_code: Mapped[str] = mapped_column(String(64), default="out_of_band", index=True)
    source: Mapped[str] = mapped_column(String(32), default="rule_engine", index=True)
    title: Mapped[str] = mapped_column(String(128))
    message: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    cleared_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    device: Mapped[Device] = relationship(back_populates="alarms")


class AlarmRule(Base):
    __tablename__ = "alarm_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    rule_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    target: Mapped[str] = mapped_column(String(64))
    operator: Mapped[str] = mapped_column(String(16), default=">")
    threshold: Mapped[str] = mapped_column(String(128))
    hold_seconds: Mapped[int] = mapped_column(Integer, default=60)
    severity: Mapped[str] = mapped_column(String(16), default="warning")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    scope_type: Mapped[str] = mapped_column(String(16), default="global")
    scope_value: Mapped[str] = mapped_column(String(128), default="*")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by: Mapped[str] = mapped_column(String(64), default="system")


class StorageRule(Base):
    __tablename__ = "storage_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    scope_type: Mapped[str] = mapped_column(String(16), default="global", index=True)
    scope_value: Mapped[str] = mapped_column(String(128), default="*", index=True)
    raw_mode: Mapped[str] = mapped_column(String(16), default="full")
    summary_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    summary_min_samples: Mapped[int] = mapped_column(Integer, default=3)
    heartbeat_interval_ms: Mapped[int] = mapped_column(Integer, default=30000)
    target_temp_deadband: Mapped[float] = mapped_column(Float, default=0.05)
    sim_temp_deadband: Mapped[float] = mapped_column(Float, default=0.05)
    sensor_temp_deadband: Mapped[float] = mapped_column(Float, default=0.05)
    error_deadband: Mapped[float] = mapped_column(Float, default=0.02)
    integral_error_deadband: Mapped[float] = mapped_column(Float, default=1.0)
    control_output_deadband: Mapped[float] = mapped_column(Float, default=1.0)
    pwm_duty_deadband: Mapped[float] = mapped_column(Float, default=1.0)
    pwm_norm_deadband: Mapped[float] = mapped_column(Float, default=0.01)
    parameter_deadband: Mapped[float] = mapped_column(Float, default=0.01)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by: Mapped[str] = mapped_column(String(64), default="system")

    __table_args__ = (UniqueConstraint("scope_type", "scope_value", name="uq_storage_rule_scope"),)


class AIRecommendation(Base):
    __tablename__ = "ai_recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str] = mapped_column(Text)
    suggestion: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.78)
    risk: Mapped[str] = mapped_column(Text, default="Minor overshoot risk")
    last_run_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    device: Mapped[Device] = relationship(back_populates="ai_recommendations")
    control_actions: Mapped[list["ControlAction"]] = relationship(back_populates="source_recommendation")


class DeviceSummary(Base):
    __tablename__ = "device_summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    window_start: Mapped[datetime] = mapped_column(DateTime, index=True)
    window_end: Mapped[datetime] = mapped_column(DateTime, index=True)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_temp: Mapped[float] = mapped_column(Float, default=0.0)
    avg_error: Mapped[float] = mapped_column(Float, default=0.0)
    max_overshoot_pct: Mapped[float] = mapped_column(Float, default=0.0)
    saturation_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    trigger_event: Mapped[str] = mapped_column(String(64), default="steady_state_window")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    device: Mapped[Device] = relationship(back_populates="summaries")


class ControlAction(Base):
    __tablename__ = "control_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(32), default="manual_user", index=True)
    source_ref_id: Mapped[Optional[int]] = mapped_column(ForeignKey("ai_recommendations.id", ondelete="SET NULL"), nullable=True, index=True)
    action_type: Mapped[str] = mapped_column(String(32), default="pid_apply", index=True)
    initiated_by: Mapped[str] = mapped_column(String(128), default="system")
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    status: Mapped[str] = mapped_column(String(32), default="applied", index=True)
    control_mode_before: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    control_mode_after: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    target_temp_before: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_temp_after: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    kp_before: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ki_before: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    kd_before: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    kp_after: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ki_after: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    kd_after: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    delta_kp: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    delta_ki: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    delta_kd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    context_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    device: Mapped[Device] = relationship(back_populates="control_actions")
    source_recommendation: Mapped[Optional[AIRecommendation]] = relationship(back_populates="control_actions")
    eval_jobs: Mapped[list["ControlActionEvalJob"]] = relationship(back_populates="control_action", cascade="all, delete-orphan")
    feedback_samples: Mapped[list["ControlActionFeedbackSample"]] = relationship(back_populates="control_action", cascade="all, delete-orphan")


class ControlActionEvalJob(Base):
    __tablename__ = "control_action_eval_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    control_action_id: Mapped[int] = mapped_column(ForeignKey("control_actions.id", ondelete="CASCADE"), index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    observation_window_minutes: Mapped[int] = mapped_column(Integer, default=15)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    control_action: Mapped[ControlAction] = relationship(back_populates="eval_jobs")
    device: Mapped[Device] = relationship(back_populates="control_action_eval_jobs")


class ControlActionFeedbackSample(Base):
    __tablename__ = "control_action_feedback_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    control_action_id: Mapped[int] = mapped_column(ForeignKey("control_actions.id", ondelete="CASCADE"), unique=True, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(32), default="manual_user", index=True)
    source_ref_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    action_type: Mapped[str] = mapped_column(String(32), default="pid_apply")
    initiated_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    evaluated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    primary_problem_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    secondary_problem_types: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    problem_flags: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    expected_effect: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    risk_level: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    control_mode_before: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    control_mode_after: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    target_temp_before: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_temp_after: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    kp_before: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ki_before: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    kd_before: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    kp_after: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ki_after: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    kd_after: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    delta_kp: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    delta_ki: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    delta_kd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mean_error: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mean_abs_error: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    error_std: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    temp_swing: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pwm_mean: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pwm_max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    zero_crossings: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    in_band_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    overshoot_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    settling_sec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    saturation_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    runtime_decision_summary: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    preview_metrics_summary: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    actual_metrics_summary: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    comparison_to_before: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    comparison_to_preview: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    actual_effect_label: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    preview_gap_label: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    insufficient_data: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    sample_quality: Mapped[str] = mapped_column(String(32), default="reject", index=True)
    is_training_eligible: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    training_exclusion_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    label_source: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    control_action: Mapped[ControlAction] = relationship(back_populates="feedback_samples")
    device: Mapped[Device] = relationship(back_populates="control_action_feedback_samples")
