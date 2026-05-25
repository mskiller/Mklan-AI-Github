from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

class ShareLinkCreate(BaseModel):
    target_type: Literal["asset", "collection"]
    target_id: UUID
    label: str | None = None
    expires_at: datetime | None = None
    allow_download: bool = False

class ShareLinkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    target_type: str
    target_id: str
    label: str | None
    expires_at: datetime | None
    allow_download: bool
    view_count: int
    created_at: datetime


class PublicShareItem(BaseModel):
    id: UUID
    filename: str
    size_bytes: int
    preview_url: str | None
    content_url: str | None


class PublicShareResponse(BaseModel):
    type: Literal["asset", "collection"]
    label: str
    item: PublicShareItem | None = None
    items: list[PublicShareItem] = Field(default_factory=list)
    allow_download: bool
