from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

from fastapi import HTTPException, status
from sqlalchemy import delete, func, or_, select

from app.core.config import settings
from app.core.security import hash_password
from app.db import SessionLocal, init_db
from app.db.models import (
    DeviceRow,
    PermissionRow,
    RolePermissionRow,
    RoleRow,
    UserDeviceGrantRow,
    UserRow,
)
from app.models.auth import (
    DeleteResult,
    LoginRequest,
    ManagedUser,
    PermissionDefinition,
    RoleDefinition,
    RoleUpsertRequest,
    UserPublic,
    UserUpsertRequest,
)
from app.models.hmi import DevicePageResponse, DeviceStatsResponse, DeviceSummary, SystemAccessResponse
from app.services.json_store import JsonStore

REQUIRED_PERMISSIONS: dict[str, tuple[str, str]] = {
    "devices.manage": ("Devices Manage", "Create, edit, delete, and page device inventory"),
}


class AccessControlService:

  def __init__(self) -> None:
    store_path = Path(__file__).resolve().parents[2] / "data" / "store.json"
    self._telemetry_store = JsonStore(store_path)
    init_db()
    self._seed_defaults()

  @contextmanager
  def _session(self) -> Iterator:
    session = SessionLocal()
    try:
      yield session
      session.commit()
    except Exception:
      session.rollback()
      raise
    finally:
      session.close()

  def authenticate(self, login: LoginRequest) -> UserPublic:
    with self._session() as session:
      user_row = session.get(UserRow, login.username)
      if user_row is None or not user_row.enabled:
        raise self._unauthorized()
      if user_row.password_hash != hash_password(login.password):
        raise self._unauthorized()
      return self._user_public_from_row(session, user_row)

  def get_user(self, username: str) -> UserPublic:
    with self._session() as session:
      user_row = session.get(UserRow, username)
      if user_row is None or not user_row.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
      return self._user_public_from_row(session, user_row)

  def list_devices_for_user(self, username: str) -> list[DeviceSummary]:
    with self._session() as session:
      user_row = session.get(UserRow, username)
      if user_row is None or not user_row.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
      rows = session.scalars(
          self._scoped_devices_query(username=username, role_key=user_row.role_key).order_by(DeviceRow.device_id),
      ).all()
      return [
          DeviceSummary(
              device_id=row.device_id,
              name=row.name,
              location=row.location,
              status=row.status,
              target_temp_c=row.target_temp_c,
              control_mode=row.control_mode,
              updated_at=row.updated_at.isoformat(),
          )
          for row in rows
      ]

  def list_devices_for_user_paginated(self, username: str, page: int, page_size: int, q: str | None = None) -> DevicePageResponse:
    page = max(page, 1)
    page_size = max(1, min(page_size, 200))
    needle = (q or "").strip().lower()
    with self._session() as session:
      user_row = session.get(UserRow, username)
      if user_row is None or not user_row.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

      base_query = self._scoped_devices_query(username=username, role_key=user_row.role_key)
      if needle:
        pattern = f"%{needle}%"
        base_query = base_query.where(
            or_(
                func.lower(DeviceRow.device_id).like(pattern),
                func.lower(DeviceRow.name).like(pattern),
            ),
        )

      total = session.scalar(select(func.count()).select_from(base_query.subquery())) or 0
      rows = session.scalars(
          base_query.order_by(DeviceRow.device_id).offset((page - 1) * page_size).limit(page_size),
      ).all()
      return DevicePageResponse(
          items=[
              DeviceSummary(
                  device_id=row.device_id,
                  name=row.name,
                  location=row.location,
                  status=row.status,
                  target_temp_c=row.target_temp_c,
                  control_mode=row.control_mode,
                  updated_at=row.updated_at.isoformat(),
              )
              for row in rows
          ],
          total=total,
          page=page,
          page_size=page_size,
      )

  def get_device_stats_for_user(self, username: str) -> DeviceStatsResponse:
    with self._session() as session:
      user_row = session.get(UserRow, username)
      if user_row is None or not user_row.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

      base = self._scoped_devices_query(username=username, role_key=user_row.role_key).with_only_columns(DeviceRow.status)
      base_subquery = base.subquery()
      grouped = session.execute(
          select(base_subquery.c.status, func.count()).select_from(base_subquery).group_by(base_subquery.c.status),
      ).all()
      stats = {str(status): int(count) for status, count in grouped}
      total = sum(stats.values())
      return DeviceStatsResponse(
          total=total,
          running=stats.get("running", 0),
          idle=stats.get("idle", 0),
          offline=stats.get("offline", 0),
      )

  def _scoped_devices_query(self, username: str, role_key: str):
    query = select(DeviceRow)
    if role_key == "admin":
      return query
    scoped_device_ids = (
        select(UserDeviceGrantRow.device_id)
        .where(UserDeviceGrantRow.username == username)
        .distinct()
        .subquery()
    )
    return query.join(scoped_device_ids, scoped_device_ids.c.device_id == DeviceRow.device_id)

  def can_manage_device(self, username: str, device_id: str) -> bool:
    with self._session() as session:
      user_row = session.get(UserRow, username)
      if user_row is None or not user_row.enabled:
        return False
      if user_row.role_key == "admin":
        return True
      exists_grant = session.scalar(
          select(UserDeviceGrantRow.id)
          .where(UserDeviceGrantRow.username == username, UserDeviceGrantRow.device_id == device_id)
          .limit(1),
      )
      return exists_grant is not None

  def grant_device_to_user(self, username: str, device_id: str) -> None:
    with self._session() as session:
      user_row = session.get(UserRow, username)
      if user_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
      device_row = session.get(DeviceRow, device_id)
      if device_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found.")
      existing = session.scalar(
          select(UserDeviceGrantRow.id)
          .where(UserDeviceGrantRow.username == username, UserDeviceGrantRow.device_id == device_id)
          .limit(1),
      )
      if existing is None:
        session.add(UserDeviceGrantRow(username=username, device_id=device_id))
      self._ensure_admin_has_all_devices(session)

  def reconcile_devices_from_store(self) -> None:
    payload = self._telemetry_store.read()
    with self._session() as session:
      self._sync_devices(session, payload.get("devices", []))
      self._ensure_admin_has_all_devices(session)

  def resolve_device_scope(self, username: str, requested_device_id: str | None) -> str:
    with self._session() as session:
      user_row = session.get(UserRow, username)
      if user_row is None or not user_row.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

      if user_row.role_key == "admin":
        if requested_device_id is None:
          default_device_id = session.scalar(select(DeviceRow.device_id).order_by(DeviceRow.device_id).limit(1))
          if default_device_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No device scope assigned for this user.",
            )
          return default_device_id
        exists_row = session.scalar(
            select(DeviceRow.device_id).where(DeviceRow.device_id == requested_device_id).limit(1),
        )
        if exists_row is None:
          raise HTTPException(
              status_code=status.HTTP_403_FORBIDDEN,
              detail=f"Device access denied: {requested_device_id}",
          )
        return requested_device_id

      if requested_device_id is None:
        default_device_id = session.scalar(
            select(UserDeviceGrantRow.device_id)
            .where(UserDeviceGrantRow.username == username)
            .order_by(UserDeviceGrantRow.device_id)
            .limit(1),
        )
        if default_device_id is None:
          raise HTTPException(
              status_code=status.HTTP_403_FORBIDDEN,
              detail="No device scope assigned for this user.",
          )
        return default_device_id

      grant_exists = session.scalar(
          select(UserDeviceGrantRow.id)
          .where(
              UserDeviceGrantRow.username == username,
              UserDeviceGrantRow.device_id == requested_device_id,
          )
          .limit(1),
      )
      if grant_exists is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Device access denied: {requested_device_id}",
        )
      return requested_device_id

  def get_access_control(self) -> SystemAccessResponse:
    with self._session() as session:
      permissions = session.scalars(select(PermissionRow).order_by(PermissionRow.key)).all()
      roles = session.scalars(select(RoleRow).order_by(RoleRow.key)).all()
      users = session.scalars(select(UserRow).order_by(UserRow.username)).all()
      devices = session.scalars(select(DeviceRow).order_by(DeviceRow.device_id)).all()
      role_permissions = session.scalars(select(RolePermissionRow)).all()
      grants = session.scalars(select(UserDeviceGrantRow)).all()

      permission_by_role: dict[str, list[str]] = defaultdict(list)
      for role_permission in role_permissions:
        permission_by_role[role_permission.role_key].append(role_permission.permission_key)
      for role_key in permission_by_role:
        permission_by_role[role_key].sort()

      devices_by_user: dict[str, list[str]] = defaultdict(list)
      for grant in grants:
        devices_by_user[grant.username].append(grant.device_id)
      for username in devices_by_user:
        devices_by_user[username].sort()

      managed_users = []
      for user in users:
        assigned_devices = devices_by_user.get(user.username, [])
        if user.role_key == "admin":
          assigned_devices = [device.device_id for device in devices]
        managed_users.append(
            ManagedUser(
                username=user.username,
                display_name=user.display_name,
                role=user.role_key,
                permissions=self._permissions_for_role(
                    role_key=user.role_key,
                    all_permission_keys=[permission.key for permission in permissions],
                    permission_by_role=permission_by_role,
                ),
                enabled=user.enabled,
                assigned_device_ids=assigned_devices,
            ),
        )

      role_models = [
          RoleDefinition(
              key=role.key,
              name=role.name,
              permissions=self._permissions_for_role(
                  role_key=role.key,
                  all_permission_keys=[permission.key for permission in permissions],
                  permission_by_role=permission_by_role,
              ),
          )
          for role in roles
      ]
      permission_models = [
          PermissionDefinition(key=permission.key, label=permission.label, description=permission.description)
          for permission in permissions
      ]
      device_models = [
          DeviceSummary(
              device_id=device.device_id,
              name=device.name,
              location=device.location,
              status=device.status,
              target_temp_c=device.target_temp_c,
              control_mode=device.control_mode,
              updated_at=device.updated_at.isoformat(),
          )
          for device in devices
      ]
      return SystemAccessResponse(
          users=managed_users,
          roles=role_models,
          permissions=permission_models,
          devices=device_models,
      )

  def upsert_user(self, request: UserUpsertRequest) -> ManagedUser:
    with self._session() as session:
      role_row = session.get(RoleRow, request.role)
      if role_row is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Assigned role does not exist.")

      user_row = session.get(UserRow, request.username)
      if user_row is None and not request.password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password required for new user.")

      if user_row is None:
        user_row = UserRow(
            username=request.username,
            display_name=request.display_name,
            role_key=request.role,
            password_hash=hash_password(request.password or ""),
            enabled=request.enabled,
        )
        session.add(user_row)
      else:
        user_row.display_name = request.display_name
        user_row.role_key = request.role
        user_row.enabled = request.enabled
        user_row.updated_at = datetime.now(UTC)
        if request.password:
          user_row.password_hash = hash_password(request.password)

      session.flush()
      self._replace_user_device_grants(
          session=session,
          username=request.username,
          role_key=request.role,
          requested_device_ids=request.device_ids,
      )
      return self._managed_user(session, request.username)

  def delete_user(self, username: str) -> DeleteResult:
    if username == "admin":
      raise HTTPException(
          status_code=status.HTTP_400_BAD_REQUEST,
          detail="The admin account cannot be deleted.",
      )
    with self._session() as session:
      user_row = session.get(UserRow, username)
      if user_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
      session.delete(user_row)
      return DeleteResult(resource="user", key=username)

  def upsert_role(self, request: RoleUpsertRequest) -> RoleDefinition:
    with self._session() as session:
      permission_rows = session.scalars(select(PermissionRow).order_by(PermissionRow.key)).all()
      allowed_permission_keys = {permission.key for permission in permission_rows}
      unknown = [permission for permission in request.permissions if permission not in allowed_permission_keys]
      if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown permissions: {', '.join(unknown)}",
        )

      role_row = session.get(RoleRow, request.key)
      if role_row is None:
        role_row = RoleRow(key=request.key, name=request.name)
        session.add(role_row)
      else:
        role_row.name = request.name

      session.flush()
      normalized_permissions = sorted(allowed_permission_keys) if request.key == "admin" else sorted(request.permissions)
      session.execute(delete(RolePermissionRow).where(RolePermissionRow.role_key == request.key))
      for permission_key in normalized_permissions:
        session.add(RolePermissionRow(role_key=request.key, permission_key=permission_key))
      return RoleDefinition(key=request.key, name=request.name, permissions=normalized_permissions)

  def _seed_defaults(self) -> None:
    payload = self._telemetry_store.read()
    with self._session() as session:
      has_permissions = session.scalar(select(PermissionRow.key).limit(1)) is not None
      if not has_permissions:
        for permission in payload.get("permissions", []):
          session.add(
              PermissionRow(
                  key=permission["key"],
                  label=permission["label"],
                  description=permission["description"],
              ),
          )

      has_roles = session.scalar(select(RoleRow.key).limit(1)) is not None
      if not has_roles:
        for role in payload.get("roles", []):
          session.add(RoleRow(key=role["key"], name=role["name"]))
        session.flush()
        for role in payload.get("roles", []):
          for permission_key in role.get("permissions", []):
            session.add(RolePermissionRow(role_key=role["key"], permission_key=permission_key))

      has_users = session.scalar(select(UserRow.username).limit(1)) is not None
      if not has_users:
        for user in payload.get("users", []):
          session.add(
              UserRow(
                  username=user["username"],
                  display_name=user["display_name"],
                  role_key=user["role"],
                  password_hash=user["password_hash"],
                  enabled=user.get("enabled", True),
              ),
          )

      self._sync_devices(session, payload.get("devices", []))
      self._ensure_required_permissions(session)
      self._ensure_admin_has_all_devices(session)
      self._seed_default_device_grants(session)

  def _sync_devices(self, session, payload_devices: list[dict]) -> None:
    payload_device_ids: set[str] = set()
    for payload_device in payload_devices:
      payload_device_ids.add(payload_device["device_id"])
      row = session.get(DeviceRow, payload_device["device_id"])
      updated_at = _safe_datetime(payload_device.get("updated_at"))
      if row is None:
        session.add(
            DeviceRow(
                device_id=payload_device["device_id"],
                name=payload_device["name"],
                location=payload_device.get("location", ""),
                status=payload_device.get("status", "unknown"),
                target_temp_c=float(payload_device.get("target_temp_c", 0.0)),
                control_mode=payload_device.get("control_mode", "unknown"),
                updated_at=updated_at,
            ),
        )
      else:
        row.name = payload_device["name"]
        row.location = payload_device.get("location", row.location)
        row.status = payload_device.get("status", row.status)
        row.target_temp_c = float(payload_device.get("target_temp_c", row.target_temp_c))
        row.control_mode = payload_device.get("control_mode", row.control_mode)
        row.updated_at = updated_at

    if payload_device_ids:
      stale_rows = session.scalars(select(DeviceRow).where(~DeviceRow.device_id.in_(payload_device_ids))).all()
      for stale in stale_rows:
        session.execute(delete(UserDeviceGrantRow).where(UserDeviceGrantRow.device_id == stale.device_id))
        session.delete(stale)

  def _seed_default_device_grants(self, session) -> None:
    has_grants = session.scalar(select(UserDeviceGrantRow.id).limit(1)) is not None
    if has_grants:
      return
    device_ids = [device_id for (device_id,) in session.execute(select(DeviceRow.device_id)).all()]
    users = session.scalars(select(UserRow)).all()
    for user in users:
      if user.role_key == "admin":
        continue
      for device_id in device_ids:
        session.add(UserDeviceGrantRow(username=user.username, device_id=device_id))

  def _ensure_admin_has_all_devices(self, session) -> None:
    admin_row = session.get(UserRow, "admin")
    if admin_row is None:
      return
    admin_row.role_key = "admin"
    device_ids = [device_id for (device_id,) in session.execute(select(DeviceRow.device_id)).all()]
    existing = {
        device_id
        for (device_id,) in session.execute(
            select(UserDeviceGrantRow.device_id).where(UserDeviceGrantRow.username == "admin"),
        ).all()
    }
    for device_id in device_ids:
      if device_id not in existing:
        session.add(UserDeviceGrantRow(username="admin", device_id=device_id))

  def _ensure_required_permissions(self, session) -> None:
    for key, value in REQUIRED_PERMISSIONS.items():
      current = session.get(PermissionRow, key)
      if current is None:
        session.add(PermissionRow(key=key, label=value[0], description=value[1]))
      else:
        current.label = value[0]
        current.description = value[1]

    operator_row = session.get(RoleRow, "operator")
    if operator_row is not None:
      existing_permission = session.scalar(
          select(RolePermissionRow.permission_key)
          .where(RolePermissionRow.role_key == "operator", RolePermissionRow.permission_key == "devices.manage")
          .limit(1),
      )
      if existing_permission is None:
        session.add(RolePermissionRow(role_key="operator", permission_key="devices.manage"))

  def _replace_user_device_grants(
      self,
      session,
      username: str,
      role_key: str,
      requested_device_ids: list[str] | None,
  ) -> None:
    if role_key == "admin":
      requested_ids = [device_id for (device_id,) in session.execute(select(DeviceRow.device_id)).all()]
    elif requested_device_ids is None:
      requested_ids = [
          device_id
          for (device_id,) in session.execute(
              select(UserDeviceGrantRow.device_id).where(UserDeviceGrantRow.username == username),
          ).all()
      ]
    else:
      if len(requested_device_ids) > settings.max_device_ids_per_request:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many device IDs in one request. Max is {settings.max_device_ids_per_request}.",
        )
      requested_ids = sorted(set(requested_device_ids))

    available_device_ids = {device_id for (device_id,) in session.execute(select(DeviceRow.device_id)).all()}
    missing_ids = [device_id for device_id in requested_ids if device_id not in available_device_ids]
    if missing_ids:
      raise HTTPException(
          status_code=status.HTTP_400_BAD_REQUEST,
          detail=f"Unknown device IDs: {', '.join(missing_ids)}",
      )

    session.execute(delete(UserDeviceGrantRow).where(UserDeviceGrantRow.username == username))
    for device_id in requested_ids:
      session.add(UserDeviceGrantRow(username=username, device_id=device_id))

  def _managed_user(self, session, username: str) -> ManagedUser:
    user_row = session.get(UserRow, username)
    if user_row is None:
      raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    all_permission_keys = [key for (key,) in session.execute(select(PermissionRow.key)).all()]
    role_permissions = defaultdict(list)
    for role_key, permission_key in session.execute(
        select(RolePermissionRow.role_key, RolePermissionRow.permission_key),
    ):
      role_permissions[role_key].append(permission_key)
    assigned_ids = [
        device_id
        for (device_id,) in session.execute(
            select(UserDeviceGrantRow.device_id).where(UserDeviceGrantRow.username == username),
        ).all()
    ]
    if user_row.role_key == "admin":
      assigned_ids = [device_id for (device_id,) in session.execute(select(DeviceRow.device_id)).all()]
    return ManagedUser(
        username=user_row.username,
        display_name=user_row.display_name,
        role=user_row.role_key,
        permissions=self._permissions_for_role(user_row.role_key, all_permission_keys, role_permissions),
        enabled=user_row.enabled,
        assigned_device_ids=sorted(assigned_ids),
    )

  def _user_public_from_row(self, session, user_row: UserRow) -> UserPublic:
    all_permission_keys = [key for (key,) in session.execute(select(PermissionRow.key)).all()]
    role_permissions = defaultdict(list)
    for role_key, permission_key in session.execute(
        select(RolePermissionRow.role_key, RolePermissionRow.permission_key),
    ):
      role_permissions[role_key].append(permission_key)
    permissions = self._permissions_for_role(user_row.role_key, all_permission_keys, role_permissions)
    return UserPublic(
        username=user_row.username,
        display_name=user_row.display_name,
        role=user_row.role_key,
        permissions=permissions,
    )

  def _permissions_for_role(
      self,
      role_key: str,
      all_permission_keys: list[str],
      permission_by_role: dict[str, list[str]],
  ) -> list[str]:
    if role_key == "admin":
      return sorted(all_permission_keys)
    return sorted(permission_by_role.get(role_key, []))

  def _unauthorized(self) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid username or password.",
    )


def _safe_datetime(value: str | None) -> datetime:
  if value is None:
    return datetime.now(UTC)
  try:
    return datetime.fromisoformat(value)
  except ValueError:
    return datetime.now(UTC)


access_control_service = AccessControlService()
