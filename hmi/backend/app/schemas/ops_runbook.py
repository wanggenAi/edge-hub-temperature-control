from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class OpsRunbookOut(BaseModel):
    key: str
    title: str
    section: str
    tags: list[str] = Field(default_factory=list)
    markdown_body: str
    is_active: bool = True
    is_customized: bool = False
    version: int = 1
    updated_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class OpsRunbookUpdateIn(BaseModel):
    title: Optional[str] = None
    section: Optional[str] = None
    tags: Optional[list[str]] = None
    markdown_body: Optional[str] = None
    is_active: Optional[bool] = None


class OpsRunbookListOut(BaseModel):
    items: list[OpsRunbookOut] = Field(default_factory=list)
