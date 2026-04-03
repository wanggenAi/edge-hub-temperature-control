from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import require_permission
from app.models.auth import DeleteResult, ManagedUser, RoleDefinition, UserPublic, RoleUpsertRequest, UserUpsertRequest
from app.models.hmi import SystemAccessResponse
from app.services.demo_data import demo_data_service

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/access", response_model=SystemAccessResponse)
def read_access_control(
    current_user: UserPublic = Depends(require_permission("system.manage")),
) -> SystemAccessResponse:
  del current_user
  return demo_data_service.get_access_control()


@router.post("/users", response_model=ManagedUser)
def upsert_user(
    payload: UserUpsertRequest,
    current_user: UserPublic = Depends(require_permission("system.manage")),
) -> ManagedUser:
  del current_user
  return demo_data_service.upsert_user(payload)


@router.post("/roles", response_model=RoleDefinition)
def upsert_role(
    payload: RoleUpsertRequest,
    current_user: UserPublic = Depends(require_permission("system.manage")),
) -> RoleDefinition:
  del current_user
  return demo_data_service.upsert_role(payload)


@router.delete("/users/{username}", response_model=DeleteResult)
def delete_user(
    username: str,
    current_user: UserPublic = Depends(require_permission("system.manage")),
) -> DeleteResult:
  del current_user
  return demo_data_service.delete_user(username)
