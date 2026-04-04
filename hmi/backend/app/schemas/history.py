from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.schemas.device import MetricOut


class SummaryItem(BaseModel):
    id: int
    device_id: int
    device_code: str
    device_name: str
    window_start: datetime
    window_end: datetime
    sample_count: int
    avg_temp: float
    avg_error: float
    max_overshoot_pct: float
    saturation_ratio: float
    observed_settling_sec: Optional[float] = None
    trigger_event: str
    created_at: datetime


class SummaryListResponse(BaseModel):
    items: list[SummaryItem]
    total: int
    page: int
    page_size: int


class SummaryDetailResponse(BaseModel):
    summary: SummaryItem
    metrics: list[MetricOut]
