from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
  pass


class PermissionRow(Base):
  __tablename__ = "permissions"

  key: Mapped[str] = mapped_column(String(64), primary_key=True)
  label: Mapped[str] = mapped_column(String(128), nullable=False)
  description: Mapped[str] = mapped_column(String(255), nullable=False)


class RoleRow(Base):
  __tablename__ = "roles"

  key: Mapped[str] = mapped_column(String(64), primary_key=True)
  name: Mapped[str] = mapped_column(String(128), nullable=False)


class RolePermissionRow(Base):
  __tablename__ = "role_permissions"

  role_key: Mapped[str] = mapped_column(ForeignKey("roles.key", ondelete="CASCADE"), primary_key=True)
  permission_key: Mapped[str] = mapped_column(
      ForeignKey("permissions.key", ondelete="CASCADE"),
      primary_key=True,
  )


class UserRow(Base):
  __tablename__ = "users"

  username: Mapped[str] = mapped_column(String(64), primary_key=True)
  display_name: Mapped[str] = mapped_column(String(128), nullable=False)
  role_key: Mapped[str] = mapped_column(ForeignKey("roles.key", ondelete="RESTRICT"), nullable=False)
  password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
  enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
  created_at: Mapped[datetime] = mapped_column(
      DateTime(timezone=True),
      nullable=False,
      default=lambda: datetime.now(UTC),
  )
  updated_at: Mapped[datetime] = mapped_column(
      DateTime(timezone=True),
      nullable=False,
      default=lambda: datetime.now(UTC),
  )


class DeviceRow(Base):
  __tablename__ = "devices"

  device_id: Mapped[str] = mapped_column(String(128), primary_key=True)
  name: Mapped[str] = mapped_column(String(128), nullable=False)
  location: Mapped[str] = mapped_column(String(128), nullable=False)
  status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
  target_temp_c: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
  control_mode: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
  updated_at: Mapped[datetime] = mapped_column(
      DateTime(timezone=True),
      nullable=False,
      default=lambda: datetime.now(UTC),
  )


class UserDeviceGrantRow(Base):
  __tablename__ = "user_device_grants"
  __table_args__ = (UniqueConstraint("username", "device_id", name="uq_user_device_grant"),)

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  username: Mapped[str] = mapped_column(ForeignKey("users.username", ondelete="CASCADE"), nullable=False)
  device_id: Mapped[str] = mapped_column(ForeignKey("devices.device_id", ondelete="CASCADE"), nullable=False)
