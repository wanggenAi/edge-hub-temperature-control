from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import require_permission
from app.models.auth import UserPublic
from app.models.hmi import RealtimeSeriesResponse, TelemetrySnapshot
from app.services.demo_data import demo_data_service

router = APIRouter(prefix="/realtime", tags=["realtime"])


@router.get("/snapshot", response_model=TelemetrySnapshot)
def read_snapshot(
    device_id: str | None = Query(default=None),
    current_user: UserPublic = Depends(require_permission("realtime.view")),
) -> TelemetrySnapshot:
  return demo_data_service.get_realtime_snapshot(current_user.username, device_id)


@router.get("/series", response_model=RealtimeSeriesResponse)
def read_series(
    device_id: str | None = Query(default=None),
    current_user: UserPublic = Depends(require_permission("realtime.view")),
) -> RealtimeSeriesResponse:
  return demo_data_service.get_realtime_series(current_user.username, device_id)
