from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import require_permission
from app.models.auth import DeleteResult, UserPublic
from app.models.hmi import DevicePageResponse, DeviceStatsResponse, DeviceSummary, DeviceUpsertRequest
from app.services.demo_data import demo_data_service

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=list[DeviceSummary])
def read_devices(
    current_user: UserPublic = Depends(require_permission("overview.view")),
) -> list[DeviceSummary]:
  return demo_data_service.list_devices(current_user.username)


@router.get("/managed", response_model=DevicePageResponse)
def read_devices_managed(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=200),
    q: str | None = Query(default=None),
    current_user: UserPublic = Depends(require_permission("overview.view")),
) -> DevicePageResponse:
  return demo_data_service.list_devices_paginated(current_user.username, page=page, page_size=page_size, q=q)


@router.get("/stats", response_model=DeviceStatsResponse)
def read_device_stats(
    current_user: UserPublic = Depends(require_permission("overview.view")),
) -> DeviceStatsResponse:
  return demo_data_service.get_device_stats(current_user.username)


@router.post("", response_model=DeviceSummary)
def create_device(
    payload: DeviceUpsertRequest,
    current_user: UserPublic = Depends(require_permission("devices.manage")),
) -> DeviceSummary:
  return demo_data_service.create_device(current_user.username, payload)


@router.put("/{device_id}", response_model=DeviceSummary)
def update_device(
    device_id: str,
    payload: DeviceUpsertRequest,
    current_user: UserPublic = Depends(require_permission("devices.manage")),
) -> DeviceSummary:
  return demo_data_service.update_device(current_user.username, device_id=device_id, payload=payload)


@router.delete("/{device_id}", response_model=DeleteResult)
def delete_device(
    device_id: str,
    current_user: UserPublic = Depends(require_permission("devices.manage")),
) -> DeleteResult:
  return demo_data_service.delete_device(current_user.username, device_id=device_id)
