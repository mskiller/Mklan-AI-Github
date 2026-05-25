from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class TagVocabularyCreate(BaseModel):
    tag: str
    description: str | None = None
    clip_prompt: str
    enabled: bool = True

class TagVocabularyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tag: str
    description: str | None
    clip_prompt: str
    enabled: bool

class TagSuggestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    asset_id: UUID
    tag: str
    tag_group: str | None = None
    confidence: float
    source_model: str | None = None
    rank: int | None = None
    raw_score: float | None = None
    threshold_used: float | None = None
    source_payload: dict | None = None
    status: str
    created_at: datetime


class TagSuggestionAction(BaseModel):
    suggestion_id: int
    action: Literal["accept", "reject"]


class TagProviderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    key: str
    label: str
    status: str
    device: str
    source_model: str
    warm: bool
    detail: str | None = None


class TagProvidersResponse(BaseModel):
    providers: list[TagProviderRead]


class TagRebuildRequest(BaseModel):
    scope: Literal["all", "source", "asset"] = "all"
    source_id: UUID | None = None
    asset_id: UUID | None = None
    provider: Literal["wd_vit_v3", "deepghs_wd_embeddings", "clip_vocab"] | None = None
    compare_mode: bool = False


class TagRebuildResponse(BaseModel):
    processed_assets: int
    created_suggestions: int


class RelatedTagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    tag: str
    score: float
    group: str
    source_model: str
