from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ActiveAlarmItem(BaseModel):
    id: int
    device_id: int
    device_code: str
    device_name: str
    alarm_name: str
    severity: str
    triggered_at: datetime
    status: str
    reason: str
    acknowledged: bool


class ActiveAlarmStats(BaseModel):
    active_total: int
    critical: int
    warning: int


class ActiveAlarmResponse(BaseModel):
    stats: ActiveAlarmStats
    items: list[ActiveAlarmItem]
    total: int
    page: int
    page_size: int


class AlarmHistoryItem(BaseModel):
    id: int
    time: datetime
    device_id: int
    device_code: str
    device_name: str
    alarm_type: str
    severity: str
    duration_seconds: Optional[int]
    recovery: str
    source: str


class AlarmHistoryResponse(BaseModel):
    items: list[AlarmHistoryItem]
    total: int
    page: int
    page_size: int


class AlarmRuleItem(BaseModel):
    id: int
    rule_code: str
    name: str
    target: str
    operator: str
    threshold: str
    hold_seconds: int
    severity: str
    enabled: bool
    scope_type: str
    scope_value: str
    updated_at: datetime
    updated_by: str


class AlarmRuleListResponse(BaseModel):
    items: list[AlarmRuleItem]
    total: int


class AlarmRuleUpdateIn(BaseModel):
    threshold: str
    hold_seconds: int
    level: str
    enabled: bool


class AlarmRuleUpdateOut(BaseModel):
    item: AlarmRuleItem
    applied: bool = True
