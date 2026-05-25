"""Pydantic schemas for the Wildcards module."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ScanRequest(BaseModel):
    source_root: str | None = None
    reset: bool = True
    background: bool = False
    mode: Literal["incremental", "reset"] | None = None


class ScanSummary(BaseModel):
    source_root: str
    scan_mode: Literal["incremental", "reset"] = "reset"
    files_seen: int
    files_indexed: int
    files_skipped: int = 0
    files_changed: int = 0
    entries_indexed: int
    txt_files: int
    yaml_files: int
    total_mb: float
    warnings: list[str]


class ScanStatus(BaseModel):
    running: bool
    started_at: str | None = None
    finished_at: str | None = None
    summary: ScanSummary | None = None
    error: str | None = None


class WildcardListItem(BaseModel):
    id: int
    wildcard_path: str
    relative_path: str
    extension: str
    size_bytes: int
    entry_count: int
    prompt_count: int
    duplicate_count: int
    unresolved_refs: int
    categories: list[str]
    prompt_modes: dict[str, int]
    updated_at: str


class EntryItem(BaseModel):
    id: int
    source_file_id: int
    wildcard_path: str
    item_index: int
    raw_text: str
    staged_text: str | None
    effective_text: str
    normalized_text: str
    kind: str
    prompt_mode: str
    tags: list[str]
    positive_tags: list[str]
    negative_tags: list[str]
    all_extracted_tags: list[str]
    prompt_parts: dict[str, Any]
    tag_categories: list[str]
    refs: list[str]
    warnings: list[str]
    is_dirty: bool


class WildcardDetail(BaseModel):
    file: dict[str, Any]
    entries: list[EntryItem]
    refs: list[str]
    unresolved_refs: list[str]
    warnings: list[str]


class EntryPatch(BaseModel):
    staged_text: str


class TagsResponse(BaseModel):
    tags: list[dict[str, Any]]


class CategoriesResponse(BaseModel):
    categories: list[dict[str, Any]]


class PromptComposeRequest(BaseModel):
    positive_tags: list[str] = Field(default_factory=list)
    negative_tags: list[str] = Field(default_factory=list)
    wildcard_refs: list[str] = Field(default_factory=list)
    model_profile: Literal["NoobAI", "Illustrious", "Generic Danbooru"] = "Illustrious"
    quality_preset: Literal["balanced", "high", "minimal"] = "balanced"
    preset: Literal["Illustrious balanced", "NoobAI tag-heavy", "Wildcard-heavy randomizer"] = "Illustrious balanced"
    prompt_mode: Literal["danbooru_tags", "sdxl_natural"] = "danbooru_tags"
    slots: dict[str, list[str]] = Field(default_factory=dict)
    sdxl: dict[str, str] = Field(default_factory=dict)


class PromptComposeResponse(BaseModel):
    positive: str
    negative: str
    wildcard_prompt: str
    model_profile: str
    preset: str
    prompt_mode: str
    slot_order: list[str]
    unresolved_refs: list[str]


class LlmSuggestRequest(BaseModel):
    task: Literal[
        "normalize_tags",
        "split_prose_to_tags",
        "suggest_category",
        "detect_duplicates",
        "improve_prompt_order",
        "improve_sdxl_prompt",
        "convert_tags_to_sdxl",
        "convert_sdxl_to_tags",
    ]
    text: str
    endpoint: str = "http://localhost:5001/v1/chat/completions"
    model: str = "local-model"
    prompt_mode: Literal["danbooru_tags", "sdxl_natural"] = "danbooru_tags"


class LlmSuggestResponse(BaseModel):
    ok: bool
    endpoint_used: str
    suggestion: str
    raw: Any | None = None
    error: str | None = None


class LlmJobRequest(LlmSuggestRequest):
    pass


class LlmJobItem(BaseModel):
    id: int
    task: str
    prompt_mode: str
    endpoint: str
    model: str
    input_text: str
    status: Literal["pending", "running", "completed", "failed", "cancelled"]
    suggestion: str = ""
    error: str | None = None
    endpoint_used: str | None = None
    created_at: str
    updated_at: str
    accepted_at: str | None = None
    rejected_at: str | None = None
    cancelled_at: str | None = None


class CleanupPreviewRequest(BaseModel):
    text: str


class CleanupPreviewResponse(BaseModel):
    normalized_lines: list[str]
    duplicate_lines: list[str]
    case_conflicts: list[list[str]]
    prose_candidates: list[str]


class PromptRecipeSaveRequest(BaseModel):
    name: str
    preset: str
    slots: dict[str, list[str]] = Field(default_factory=dict)
    negative_tags: list[str] = Field(default_factory=list)
    wildcard_refs: list[str] = Field(default_factory=list)


class TagOverrideRequest(BaseModel):
    tag: str
    canonical_tag: str | None = None
    category: str | None = None
    is_ignored: bool = False


class TaxonomyPatchRequest(BaseModel):
    rules: dict[str, list[str]] | None = None
    category: str | None = None
    keywords: list[str] | None = None


class ExportRequest(BaseModel):
    target_root: str | None = None
    format: Literal["txt_tree", "yaml", "sd_yaml", "both"] = "txt_tree"
    wildcard_ids: list[int] | None = None
    prompt_mode: Literal["all", "danbooru_tags", "sdxl_natural", "mixed", "unknown"] = "all"
    include_manifest: bool = True
    overwrite: bool = False


class ExportPlan(BaseModel):
    target_root: str
    format: str
    created: list[str]
    changed: list[str]
    skipped: list[str]
    conflicts: list[str]
    manifest_path: str | None
    unresolved_refs: list[str]