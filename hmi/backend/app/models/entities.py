from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
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
    control_mode: Mapped[str] = mapped_column(String(32), default="PID")
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


class AIRecommendation(Base):
    __tablename__ = "ai_recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str] = mapped_column(String(255))
    suggestion: Mapped[str] = mapped_column(String(255))
    confidence: Mapped[float] = mapped_column(Float, default=0.78)
    risk: Mapped[str] = mapped_column(String(128), default="Minor overshoot risk")
    last_run_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    device: Mapped[Device] = relationship(back_populates="ai_recommendations")


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
