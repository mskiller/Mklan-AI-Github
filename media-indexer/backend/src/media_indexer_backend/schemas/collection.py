from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from media_indexer_backend.schemas.asset import AssetBrowseItem


class CollectionCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""


class CollectionUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None


class CollectionAssetAddRequest(BaseModel):
    asset_ids: list[UUID] = Field(min_length=1)


class CollectionSearchAddRequest(BaseModel):
    q: str | None = None
    media_type: str | None = None
    caption: str | None = None
    ocr_text: str | None = None
    camera_make: str | None = None
    camera_model: str | None = None
    year: int | None = None
    width_min: int | None = None
    width_max: int | None = None
    height_min: int | None = None
    height_max: int | None = None
    duration_min: float | None = None
    duration_max: float | None = None
    tags: list[str] = []
    auto_tags: list[str] = []


class CollectionSummary(BaseModel):
    id: UUID
    name: str
    description: str
    created_by: UUID
    asset_count: int
    created_at: datetime
    updated_at: datetime


class CollectionDetail(CollectionSummary):
    items: list[AssetBrowseItem]
    page: int
    page_size: int
    total: int
