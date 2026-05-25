from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from media_indexer_backend.schemas.asset import AssetBrowseItem


class AssetFacePersonRead(BaseModel):
    id: UUID
    name: str | None = None


class AssetFaceRead(BaseModel):
    id: UUID
    asset_id: UUID
    bbox_x1: int
    bbox_y1: int
    bbox_x2: int
    bbox_y2: int
    det_score: float
    crop_preview_url: str | None = None
    person: AssetFacePersonRead | None = None


class AssetFacesResponse(BaseModel):
    enabled: bool
    image_width: int | None = None
    image_height: int | None = None
    items: list[AssetFaceRead]


class PersonSummary(BaseModel):
    id: UUID
    name: str | None = None
    cover_face_url: str | None = None
    face_count: int
    asset_count: int
    created_at: datetime


class PersonDetail(PersonSummary):
    faces: list[AssetFaceRead]
    items: list[AssetBrowseItem]


class PersonUpdateRequest(BaseModel):
    name: str | None = None
    cover_face_id: UUID | None = None


class PersonMergeRequest(BaseModel):
    source_person_id: UUID


class ReclusterPeopleResponse(BaseModel):
    reassigned_faces: int
    created_people: int
