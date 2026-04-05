from __future__ import annotations

from datetime import datetime
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db_dep, require_roles
from app.models.entities import StorageRule, User
from app.schemas.storage_rule import (
    StorageRuleCreateIn,
    StorageRuleDeleteResponse,
    StorageRuleItem,
    StorageRuleListResponse,
    StorageRuleMutationResponse,
    StorageRuleUpdateIn,
)
from app.services.mqtt_publisher import MqttPublisher

router = APIRouter(prefix="/storage-rules", tags=["storage-rules"])
mqtt_publisher = MqttPublisher()
log = logging.getLogger(__name__)


def _to_item(rule: StorageRule) -> StorageRuleItem:
    return StorageRuleItem(
        id=rule.id,
        scope_type=rule.scope_type,
        scope_value=rule.scope_value,
        raw_mode=rule.raw_mode,
        summary_enabled=rule.summary_enabled,
        summary_min_samples=rule.summary_min_samples,
        heartbeat_interval_ms=rule.heartbeat_interval_ms,
        target_temp_deadband=rule.target_temp_deadband,
        sim_temp_deadband=rule.sim_temp_deadband,
        sensor_temp_deadband=rule.sensor_temp_deadband,
        error_deadband=rule.error_deadband,
        integral_error_deadband=rule.integral_error_deadband,
        control_output_deadband=rule.control_output_deadband,
        pwm_duty_deadband=rule.pwm_duty_deadband,
        pwm_norm_deadband=rule.pwm_norm_deadband,
        parameter_deadband=rule.parameter_deadband,
        enabled=rule.enabled,
        updated_at=rule.updated_at,
        updated_by=rule.updated_by,
    )


def _publish_change(rule: StorageRule, action: str) -> None:
    mqtt_publisher.publish_json(
        topic="edgehub/config/storage-rules/updated",
        payload_obj={
            "entity": "storage_rule",
            "action": action,
            "rule_id": rule.id,
            "scope_type": rule.scope_type,
            "scope_value": rule.scope_value,
            "updated_at": rule.updated_at.isoformat(),
            "updated_by": rule.updated_by,
        },
    )


@router.get("", response_model=StorageRuleListResponse)
def list_storage_rules(
    db: Session = Depends(get_db_dep),
    _: User = Depends(require_roles("admin")),
) -> StorageRuleListResponse:
    rows = db.scalars(select(StorageRule).order_by(StorageRule.scope_type.asc(), StorageRule.scope_value.asc())).all()
    items = [_to_item(row) for row in rows]
    return StorageRuleListResponse(items=items, total=len(items))


@router.post("", response_model=StorageRuleMutationResponse)
def create_storage_rule(
    payload: StorageRuleCreateIn,
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(require_roles("admin")),
) -> StorageRuleMutationResponse:
    now = datetime.utcnow()
    rule = StorageRule(
        scope_type=payload.scope_type,
        scope_value=payload.scope_value,
        raw_mode=payload.raw_mode,
        summary_enabled=payload.summary_enabled,
        summary_min_samples=payload.summary_min_samples,
        heartbeat_interval_ms=payload.heartbeat_interval_ms,
        target_temp_deadband=payload.target_temp_deadband,
        sim_temp_deadband=payload.sim_temp_deadband,
        sensor_temp_deadband=payload.sensor_temp_deadband,
        error_deadband=payload.error_deadband,
        integral_error_deadband=payload.integral_error_deadband,
        control_output_deadband=payload.control_output_deadband,
        pwm_duty_deadband=payload.pwm_duty_deadband,
        pwm_norm_deadband=payload.pwm_norm_deadband,
        parameter_deadband=payload.parameter_deadband,
        enabled=payload.enabled,
        updated_at=now,
        updated_by=current_user.username,
    )
    db.add(rule)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Storage rule with this scope already exists") from exc
    db.refresh(rule)
    try:
        _publish_change(rule, "created")
    except Exception:  # noqa: BLE001
        log.exception("failed to publish storage rule create notification rule_id=%s", rule.id)
    return StorageRuleMutationResponse(item=_to_item(rule))


@router.put("/{rule_id}", response_model=StorageRuleMutationResponse)
def update_storage_rule(
    rule_id: int,
    payload: StorageRuleUpdateIn,
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(require_roles("admin")),
) -> StorageRuleMutationResponse:
    rule = db.scalar(select(StorageRule).where(StorageRule.id == rule_id))
    if not rule:
        raise HTTPException(status_code=404, detail="Storage rule not found")

    rule.scope_type = payload.scope_type
    rule.scope_value = payload.scope_value
    rule.raw_mode = payload.raw_mode
    rule.summary_enabled = payload.summary_enabled
    rule.summary_min_samples = payload.summary_min_samples
    rule.heartbeat_interval_ms = payload.heartbeat_interval_ms
    rule.target_temp_deadband = payload.target_temp_deadband
    rule.sim_temp_deadband = payload.sim_temp_deadband
    rule.sensor_temp_deadband = payload.sensor_temp_deadband
    rule.error_deadband = payload.error_deadband
    rule.integral_error_deadband = payload.integral_error_deadband
    rule.control_output_deadband = payload.control_output_deadband
    rule.pwm_duty_deadband = payload.pwm_duty_deadband
    rule.pwm_norm_deadband = payload.pwm_norm_deadband
    rule.parameter_deadband = payload.parameter_deadband
    rule.enabled = payload.enabled
    rule.updated_at = datetime.utcnow()
    rule.updated_by = current_user.username

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Storage rule with this scope already exists") from exc

    db.refresh(rule)
    try:
        _publish_change(rule, "updated")
    except Exception:  # noqa: BLE001
        log.exception("failed to publish storage rule update notification rule_id=%s", rule.id)
    return StorageRuleMutationResponse(item=_to_item(rule))


@router.delete("/{rule_id}", response_model=StorageRuleDeleteResponse)
def delete_storage_rule(
    rule_id: int,
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(require_roles("admin")),
) -> StorageRuleDeleteResponse:
    rule = db.scalar(select(StorageRule).where(StorageRule.id == rule_id))
    if not rule:
        raise HTTPException(status_code=404, detail="Storage rule not found")

    rule.updated_at = datetime.utcnow()
    rule.updated_by = current_user.username
    db.delete(rule)
    db.commit()
    try:
        mqtt_publisher.publish_json(
            topic="edgehub/config/storage-rules/updated",
            payload_obj={
                "entity": "storage_rule",
                "action": "deleted",
                "rule_id": rule_id,
                "scope_type": rule.scope_type,
                "scope_value": rule.scope_value,
                "updated_at": datetime.utcnow().isoformat(),
                "updated_by": current_user.username,
            },
        )
    except Exception:  # noqa: BLE001
        log.exception("failed to publish storage rule delete notification rule_id=%s", rule_id)
    return StorageRuleDeleteResponse(ok=True)
