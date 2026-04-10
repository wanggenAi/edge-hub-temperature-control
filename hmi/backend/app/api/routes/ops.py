from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db_dep, require_roles
from app.models.entities import User
from app.schemas.ops import (
    OpsAiObservabilityOut,
    OpsDataHubOut,
    OpsLearningLoopOut,
    OpsModelRuntimeOut,
    OpsOverviewOut,
    OpsRuntimeOut,
)
from app.schemas.ops_runbook import OpsRunbookListOut, OpsRunbookOut, OpsRunbookUpdateIn
from app.services.ops_console import ops_console_service
from app.services.ops_runbook_service import ops_runbook_service

router = APIRouter(prefix="/ops", tags=["ops"])


@router.get("/overview", response_model=OpsOverviewOut)
def get_ops_overview(
    db: Session = Depends(get_db_dep),
    _: User = Depends(require_roles("admin")),
) -> OpsOverviewOut:
    return ops_console_service.build_overview(db)


@router.get("/data-hub", response_model=OpsDataHubOut)
def get_ops_data_hub(
    _: User = Depends(require_roles("admin")),
) -> OpsDataHubOut:
    return ops_console_service.build_data_hub()


@router.get("/runtime", response_model=OpsRuntimeOut)
def get_ops_runtime(
    _: User = Depends(require_roles("admin")),
) -> OpsRuntimeOut:
    return ops_console_service.build_runtime()


@router.get("/learning-loop", response_model=OpsLearningLoopOut)
def get_ops_learning_loop(
    db: Session = Depends(get_db_dep),
    _: User = Depends(require_roles("admin")),
) -> OpsLearningLoopOut:
    return ops_console_service.build_learning_loop(db)


@router.get("/models", response_model=OpsModelRuntimeOut)
def get_ops_models(
    db: Session = Depends(get_db_dep),
    _: User = Depends(require_roles("admin")),
) -> OpsModelRuntimeOut:
    return ops_console_service.build_models(db)


@router.get("/ai/observability", response_model=OpsAiObservabilityOut)
def get_ops_ai_observability(
    db: Session = Depends(get_db_dep),
    _: User = Depends(require_roles("admin")),
) -> OpsAiObservabilityOut:
    return ops_console_service.build_ai_observability(db)


@router.get("/runbooks", response_model=OpsRunbookListOut)
def list_ops_runbooks(
    db: Session = Depends(get_db_dep),
    _: User = Depends(require_roles("admin")),
) -> OpsRunbookListOut:
    return OpsRunbookListOut(items=ops_runbook_service.list_runbooks(db))


@router.get("/runbooks/{key}", response_model=OpsRunbookOut)
def get_ops_runbook(
    key: str,
    db: Session = Depends(get_db_dep),
    _: User = Depends(require_roles("admin")),
) -> OpsRunbookOut:
    return ops_runbook_service.get_runbook(db, key)


@router.patch("/runbooks/{key}", response_model=OpsRunbookOut)
def patch_ops_runbook(
    key: str,
    payload: OpsRunbookUpdateIn,
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(require_roles("admin")),
) -> OpsRunbookOut:
    return ops_runbook_service.update_runbook(db, key, payload, updated_by=current_user.username)


@router.post("/runbooks/{key}/reset-default", response_model=OpsRunbookOut)
def reset_ops_runbook_default(
    key: str,
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(require_roles("admin")),
) -> OpsRunbookOut:
    return ops_runbook_service.reset_to_default(db, key, updated_by=current_user.username)
