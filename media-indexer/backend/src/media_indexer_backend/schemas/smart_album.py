from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from media_indexer_backend.models.enums import MediaType, ReviewStatus
from media_indexer_backend.schemas.asset import AssetBrowseItem


class SmartAlbumRule(BaseModel):
    media_type: MediaType | None = None
    source_ids: list[UUID] = Field(default_factory=list)
    tags_any: list[str] = Field(default_factory=list)
    auto_tags_any: list[str] = Field(default_factory=list)
    people_ids: list[UUID] = Field(default_factory=list)
    review_status: ReviewStatus | None = None
    min_rating: int | None = Field(default=None, ge=1, le=5)
    flagged: bool | None = None
    has_gps: bool | None = None
    date_from: date | None = None
    date_to: date | None = None


class SmartAlbumCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    enabled: bool = True
    rule: SmartAlbumRule = Field(default_factory=SmartAlbumRule)


class SmartAlbumUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    enabled: bool | None = None
    rule: SmartAlbumRule | None = None


class SmartAlbumSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None = None
    owner_id: UUID
    enabled: bool
    last_synced_at: datetime | None = None
    asset_count: int
    cover_asset_id: UUID | None = None
    source: str
    created_at: datetime
    updated_at: datetime
    rule: SmartAlbumRule


class SmartAlbumDetail(SmartAlbumSummary):
    items: list[AssetBrowseItem]
    suggested: bool = False
