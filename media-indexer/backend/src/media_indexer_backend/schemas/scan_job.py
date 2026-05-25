from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from media_indexer_backend.models.enums import ScanStatus

ScanMode = Literal[
    "basic",
    "metadata",
    "ai",
    "workflow",
    "preview",
    "similarity",
    "caption",
    "ocr",
    "tags",
    "safety_quality",
    "faces",
    "video_intel",
    "vision_llm",
    "sillytavern_card",
]
ScanTargetType = Literal["source", "collection", "assets"]


class ScanJobTarget(BaseModel):
    type: ScanTargetType = "source"
    source_id: UUID | None = None
    path_filter: str | None = None
    collection_id: UUID | None = None
    asset_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_target(self) -> "ScanJobTarget":
        if self.type == "source" and self.source_id is None:
            raise ValueError("source target requires source_id")
        if self.type == "collection" and self.collection_id is None:
            raise ValueError("collection target requires collection_id")
        if self.type == "assets" and not self.asset_ids:
            raise ValueError("assets target requires at least one asset_id")
        return self


class ScanJobCreate(BaseModel):
    scan_mode: ScanMode = "basic"
    path_filter: str | None = None
    target: ScanJobTarget | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class ScanJobRead(BaseModel):
    id: UUID
    source_id: UUID | None = None
    status: ScanStatus
    scan_mode: str = "basic"
    target_type: str = "source"
    collection_id: UUID | None = None
    asset_ids_json: list[str] | None = None
    path_filter: str | None = None
    options_json: dict[str, Any] = Field(default_factory=dict)
    progress: int
    total_count: int | None = None
    stage: str | None = None
    scanned_count: int
    new_count: int
    updated_count: int
    deleted_count: int
    error_count: int
    message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    worker_heartbeat_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ScanJobErrorEntry(BaseModel):
    id: UUID | None = None
    job_id: UUID | None = None
    source_id: UUID | None = None
    asset_id: UUID | None = None
    relative_path: str | None = None
    path: str | None = None
    stage: str | None = None
    error: str
    at: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
