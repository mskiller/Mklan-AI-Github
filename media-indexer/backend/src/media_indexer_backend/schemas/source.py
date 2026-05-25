from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from media_indexer_backend.models.enums import MediaType, SourceStatus, SourceType
from media_indexer_backend.schemas.asset import AssetAnnotationRead


class SourceCreate(BaseModel):
    name: str
    type: SourceType = SourceType.MOUNTED_FS
    root_path: str


class SourceRead(BaseModel):
    id: UUID
    name: str
    type: SourceType
    root_path: str | None
    display_root_path: str
    status: SourceStatus
    last_scan_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SourceBreadcrumb(BaseModel):
    label: str
    path: str


class SourceBrowseEntry(BaseModel):
    name: str
    relative_path: str
    entry_type: Literal["directory", "file"]
    media_type: MediaType | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    modified_at: datetime | None = None
    indexed_asset_id: UUID | None = None
    index_state: Literal["indexed", "metadata_refresh_pending", "processing", "live_browse"] | None = None
    preview_url: str | None = None
    content_url: str | None = None


class SourceBrowseResponse(BaseModel):
    source_id: UUID
    current_path: str
    parent_path: str | None
    breadcrumbs: list[SourceBreadcrumb]
    entries: list[SourceBrowseEntry]


class SourceBrowseInspect(BaseModel):
    source_id: UUID
    relative_path: str
    indexed_asset_id: UUID | None = None
    index_state: Literal["indexed", "metadata_refresh_pending", "processing", "live_browse"] | None = None
    preview_url: str | None = None
    content_url: str | None = None
    blur_hash: str | None = None
    deepzoom_available: bool = False
    deepzoom_url: str | None = None
    width: int | None = None
    height: int | None = None
    generator: str | None = None
    prompt_excerpt: str | None = None
    prompt_tags: list[str] = []
    prompt_tag_string: str | None = None
    annotation: AssetAnnotationRead | None = None


class SourceTreeFileEntry(BaseModel):
    name: str
    relative_path: str
    indexed: bool


class SourceTreeResponse(BaseModel):
    path: str
    dirs: list[str]
    files: list[SourceTreeFileEntry]


class SourceUploadRead(BaseModel):
    source_id: UUID
    folder: str
    uploaded_files: list[str]
    scan_job_id: UUID | None = None
