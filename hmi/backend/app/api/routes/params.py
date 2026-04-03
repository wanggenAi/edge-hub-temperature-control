from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import require_permission
from app.models.auth import UserPublic
from app.models.hmi import AckRecord, ParameterCommandRequest, ParameterPageResponse
from app.services.demo_data import demo_data_service

router = APIRouter(prefix="/params", tags=["params"])


@router.get("", response_model=ParameterPageResponse)
def read_parameters(
    device_id: str | None = Query(default=None),
    current_user: UserPublic = Depends(require_permission("params.view")),
) -> ParameterPageResponse:
  return demo_data_service.get_parameters_page(current_user.username, device_id)


@router.post("/commands", response_model=AckRecord)
def submit_parameters(
    payload: ParameterCommandRequest,
    current_user: UserPublic = Depends(require_permission("params.write")),
) -> AckRecord:
  return demo_data_service.submit_parameters(current_user.username, payload)
