from __future__ import annotations

from pydantic import BaseModel, Field


class AdminSettings(BaseModel):
    tag_similarity_threshold_percent: int = Field(ge=1, le=100)
    max_thumbnail_size: int = Field(ge=128, le=2048, default=512)
    duplicate_phash_threshold: int = Field(ge=1, le=20, default=8)
    semantic_similarity_threshold: float = Field(ge=0.0, le=1.0, default=0.22)
    semantic_neighbor_limit: int = Field(ge=1, le=200, default=24)
    clip_enabled: bool = True
    preview_cache_max_mb: int = Field(ge=128, le=20480, default=2048)
    worker_poll_interval_seconds: int = Field(ge=1, le=60, default=5)


class AdminSettingsUpdateRequest(BaseModel):
    tag_similarity_threshold_percent: int = Field(ge=1, le=100)
    max_thumbnail_size: int = Field(ge=128, le=2048, default=512)
    duplicate_phash_threshold: int = Field(ge=1, le=20, default=8)
    semantic_similarity_threshold: float = Field(ge=0.0, le=1.0, default=0.22)
    semantic_neighbor_limit: int = Field(ge=1, le=200, default=24)
    clip_enabled: bool = True
    preview_cache_max_mb: int = Field(ge=128, le=20480, default=2048)
    worker_poll_interval_seconds: int = Field(ge=1, le=60, default=5)


class TagSimilarityRebuildResponse(BaseModel):
    rebuilt_assets: int
    rebuilt_links: int
