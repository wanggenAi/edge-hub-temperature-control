from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db_dep, require_roles
from app.models.entities import User
from app.schemas.ops import (
    OpsModelLifecycleRunOut,
    OpsModelLifecycleStatusOut,
    OpsAiObservabilityOut,
    OpsDataHubOut,
    OpsLearningLoopOut,
    OpsModelRuntimeOut,
    OpsOverviewOut,
    OpsRuntimeOut,
)
from app.core.config import settings
from app.models.entities import ModelLifecycleRun
from app.schemas.ops_runbook import OpsRunbookListOut, OpsRunbookOut, OpsRunbookUpdateIn
from app.services.ai.model_lifecycle_service import model_lifecycle_service
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
    include_inactive: bool = Query(default=True),
    db: Session = Depends(get_db_dep),
    _: User = Depends(require_roles("admin")),
) -> OpsRunbookListOut:
    return OpsRunbookListOut(items=ops_runbook_service.list_runbooks(db, include_inactive=include_inactive))


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


def _to_lifecycle_out(row: ModelLifecycleRun) -> OpsModelLifecycleRunOut:
    return OpsModelLifecycleRunOut(
        id=row.id,
        lifecycle_run_id=row.lifecycle_run_id,
        model_family=row.model_family,
        trigger_source=row.trigger_source,
        status=row.status,
        promoted=bool(row.promoted),
        dry_run=bool(row.dry_run),
        reason=row.reason,
        gate_reasons=[str(x) for x in (row.gate_reasons or [])],
        training_sample_count=int(row.training_sample_count or 0),
        new_eligible_samples_since_last=int(row.new_eligible_samples_since_last or 0),
        recent_eligible_samples_7d=int(row.recent_eligible_samples_7d or 0),
        validation_size=row.validation_size,
        candidate_artifact_dir=row.candidate_artifact_dir,
        active_artifact_dir_before=row.active_artifact_dir_before,
        archive_artifact_dir=row.archive_artifact_dir,
        comparison_summary=row.comparison_summary if isinstance(row.comparison_summary, dict) else None,
        started_at=row.started_at,
        completed_at=row.completed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/ai/model-lifecycle/runs", response_model=list[OpsModelLifecycleRunOut])
def list_ai_model_lifecycle_runs(
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db_dep),
    _: User = Depends(require_roles("admin")),
) -> list[OpsModelLifecycleRunOut]:
    return [_to_lifecycle_out(row) for row in model_lifecycle_service.list_runs(db, limit=limit)]


@router.get("/ai/model-lifecycle/status", response_model=OpsModelLifecycleStatusOut)
def get_ai_model_lifecycle_status(
    db: Session = Depends(get_db_dep),
    _: User = Depends(require_roles("admin")),
) -> OpsModelLifecycleStatusOut:
    rows = model_lifecycle_service.list_runs(db, limit=100)
    last_run = rows[0] if rows else None
    last_promoted = next((x for x in rows if x.promoted), None)
    last_rejected = next((x for x in rows if x.status == "rejected"), None)
    last_skipped = next((x for x in rows if x.status == "skipped"), None)
    return OpsModelLifecycleStatusOut(
        as_of=datetime.utcnow(),
        enabled=bool(settings.model_lifecycle_enabled),
        check_interval_seconds=int(settings.model_lifecycle_check_interval_seconds),
        last_run_at=last_run.started_at if last_run else None,
        last_run_status=last_run.status if last_run else None,
        last_trigger_source=last_run.trigger_source if last_run else None,
        last_promoted_at=last_promoted.completed_at if last_promoted else None,
        last_promoted_model_family=last_promoted.model_family if last_promoted else None,
        last_rejected_at=last_rejected.completed_at if last_rejected else None,
        last_rejected_reason=last_rejected.reason if last_rejected else None,
        last_skipped_at=last_skipped.completed_at if last_skipped else None,
        last_skipped_reason=last_skipped.reason if last_skipped else None,
        recent_runs=[_to_lifecycle_out(x) for x in rows[:20]],
    )


@router.post("/ai/model-lifecycle/run")
def run_ai_model_lifecycle(
    dry_run: bool = Query(default=False),
    db: Session = Depends(get_db_dep),
    _: User = Depends(require_roles("admin")),
) -> dict:
    return model_lifecycle_service.run_lifecycle(db, trigger_source="manual", dry_run=dry_run)
