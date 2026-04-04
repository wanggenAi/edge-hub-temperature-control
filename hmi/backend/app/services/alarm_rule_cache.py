from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from app.core.config import settings
from app.models.entities import AlarmRule

log = logging.getLogger(__name__)

try:
    import redis
except Exception:  # pragma: no cover
    redis = None


def _get_client() -> Optional["redis.Redis"]:
    if not settings.redis_enabled:
        return None
    if redis is None:
        return None
    return redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        password=settings.redis_password or None,
        db=settings.redis_db,
        decode_responses=True,
    )


def _to_payload(rule: AlarmRule) -> dict:
    updated_at = rule.updated_at if isinstance(rule.updated_at, datetime) else None
    return {
        "name": rule.name,
        "target": rule.target,
        "operator": rule.operator,
        "threshold": rule.threshold,
        "hold_seconds": int(rule.hold_seconds),
        "severity": rule.severity,
        "enabled": bool(rule.enabled),
        "scope_type": rule.scope_type,
        "scope_value": rule.scope_value,
        "updated_at": updated_at.isoformat() if updated_at else None,
        "updated_by": rule.updated_by,
    }


def sync_rule_to_redis(rule: AlarmRule) -> None:
    client = _get_client()
    if client is None:
        return

    key = settings.redis_alarm_rules_key
    value = json.dumps(_to_payload(rule), ensure_ascii=True)
    try:
        client.hset(key, rule.rule_code, value)
        client.expire(key, max(60, settings.redis_alarm_rules_ttl_seconds))
    except Exception:
        log.exception("failed to sync alarm rule to redis rule_code=%s", rule.rule_code)
