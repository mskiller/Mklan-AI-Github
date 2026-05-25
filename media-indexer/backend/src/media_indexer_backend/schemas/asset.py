from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from media_indexer_backend.models.enums import MatchType, MediaType, ReviewStatus


class AssetAnnotationRead(BaseModel):
    id: UUID | None = None
    user_id: UUID | None = None
    rating: int | None = None
    review_status: ReviewStatus = ReviewStatus.UNREVIEWED
    note: str | None = None
    flagged: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class BulkAnnotateRequest(BaseModel):
    asset_ids: list[UUID] = Field(min_length=1)
    rating: int | None = Field(default=None, ge=1, le=5)
    review_status: ReviewStatus | None = None
    flagged: bool | None = None
    note: str | None = None
    tags: list[str] | None = None


class AssetSummary(BaseModel):
    id: UUID
    source_id: UUID
    relative_path: str
    filename: str
    extension: str
    media_type: MediaType
    mime_type: str
    size_bytes: int
    modified_at: datetime
    created_at: datetime | None
    indexed_at: datetime
    preview_url: str | None
    content_url: str
    blur_hash: str | None
    deepzoom_available: bool = False
    deepzoom_url: str | None = None
    tags: list[str]
    normalized_metadata: dict
    caption: str | None = None
    caption_source: str | None = None
    ocr_text: str | None = None
    ocr_confidence: float | None = None
    annotation: AssetAnnotationRead | None = None
    workflow_export_available: bool = False
    waveform_url: str | None = None
    video_keyframes: list[str] | None = None


class AssetDetail(AssetSummary):
    raw_metadata: dict
    source_name: str
    workflow_export_url: str | None = None
    visual_workflow_json: dict | list | None = None
    visual_workflow_confidence: float | None = None
    visual_workflow_updated_at: datetime | None = None



class AssetListResponse(BaseModel):
    items: list[AssetSummary]
    total: int
    page: int
    page_size: int


class AssetBrowseItem(BaseModel):
    id: UUID
    source_id: UUID
    source_name: str
    filename: str
    relative_path: str
    preview_url: str | None
    content_url: str
    blur_hash: str | None
    deepzoom_available: bool = False
    deepzoom_url: str | None = None
    width: int | None
    height: int | None
    modified_at: datetime
    created_at: datetime | None
    size_bytes: int
    generator: str | None
    prompt_excerpt: str | None
    prompt_tags: list[str]
    prompt_tag_string: str | None
    caption: str | None = None
    ocr_text: str | None = None
    annotation: AssetAnnotationRead | None = None
    workflow_export_available: bool = False
    media_type: MediaType = MediaType.UNKNOWN
    waveform_url: str | None = None
    video_keyframes: list[str] | None = None


class AssetBrowseResponse(BaseModel):
    items: list[AssetBrowseItem]
    total: int
    page: int
    page_size: int


class TagCount(BaseModel):
    tag: str
    count: int


class SimilarAsset(BaseModel):
    asset: AssetSummary
    match_type: MatchType
    distance: float
    score: float
    prompt_tag_overlap: int = 0
    shared_prompt_tags: list[str] = []


class CompareAsset(BaseModel):
    id: UUID
    filename: str
    preview_url: str | None
    content_url: str
    deepzoom_available: bool = False
    deepzoom_url: str | None = None
    size_bytes: int
    created_at: datetime | None
    modified_at: datetime
    normalized_metadata: dict
    tags: list[str]


class CompareDiffEntry(BaseModel):
    field: str
    left: str | int | float | None
    right: str | int | float | None


class CompareResponse(BaseModel):
    asset_a: CompareAsset
    asset_b: CompareAsset
    phash_distance: int | None
    semantic_similarity: float | None
    prompt_tag_overlap: int = 0
    shared_prompt_tags: list[str] = []
    left_only_prompt_tags: list[str] = []
    right_only_prompt_tags: list[str] = []
    metadata_diff: list[CompareDiffEntry]


class CompareReviewRequest(BaseModel):
    asset_id_a: UUID
    asset_id_b: UUID
    action: str
