from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from media_indexer_backend.schemas.asset import AssetSummary


class InboxItemRead(BaseModel):
    id: UUID
    filename: str
    inbox_path: str
    file_size: int
    phash: str | None = None
    clip_distance_min: float | None = None
    nearest_asset_id: UUID | None = None
    status: str
    target_source_id: UUID | None = None
    target_source_name: str | None = None
    created_at: datetime
    reviewed_at: datetime | None = None
    reviewed_by: UUID | None = None
    error_message: str | None = None
    thumbnail_url: str | None = None


class InboxCompareResponse(BaseModel):
    item: InboxItemRead
    nearest_asset: AssetSummary | None = None


class InboxApproveRequest(BaseModel):
    target_source_id: UUID | None = None


class InboxCountResponse(BaseModel):
    count: int
