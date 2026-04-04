from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AlarmListItem(BaseModel):
    id: int
    device_id: int
    device_code: str
    device_name: str
    level: str
    title: str
    message: str
    is_active: bool
    created_at: datetime


class AlarmListResponse(BaseModel):
    items: list[AlarmListItem]
    total: int
    page: int
    page_size: int
