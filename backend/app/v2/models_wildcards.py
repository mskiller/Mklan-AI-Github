from typing import Any, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel
from pgvector.sqlalchemy import Vector

class WildcardSourceFile(SQLModel, table=True):
    __tablename__ = "wildcard_source_files"

    id: Optional[int] = Field(default=None, primary_key=True)
    original_path: str = Field(unique=True)
    relative_path: str
    extension: str
    size_bytes: int
    sha256: str
    last_modified: str
    wildcard_path: str = Field(index=True)
    import_status: str
    warning_count: int = 0
    created_at: str
    updated_at: str
    workspace_id: str = Field(default="default", index=True)

class WildcardEntry(SQLModel, table=True):
    __tablename__ = "wildcard_entries"

    id: Optional[int] = Field(default=None, primary_key=True)
    source_file_id: int = Field(foreign_key="wildcard_source_files.id", ondelete="CASCADE", index=True)
    wildcard_path: str = Field(index=True)
    item_index: int
    raw_text: str
    staged_text: Optional[str] = None
    normalized_text: str
    kind: str
    prompt_mode: str = Field(default="unknown", index=True)
    tags_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    positive_tags_json: dict[str, Any] = Field(default_factory=list, sa_column=Column(JSON))
    negative_tags_json: dict[str, Any] = Field(default_factory=list, sa_column=Column(JSON))
    all_extracted_tags_json: dict[str, Any] = Field(default_factory=list, sa_column=Column(JSON))
    prompt_parts_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    tag_categories_json: dict[str, Any] = Field(default_factory=list, sa_column=Column(JSON))
    refs_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    warnings_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    embedding: Optional[Any] = Field(default=None, sa_column=Column(Vector(384)))
    created_at: str
    updated_at: str
    workspace_id: str = Field(default="default", index=True)

class WildcardEntryHistory(SQLModel, table=True):
    __tablename__ = "wildcard_entry_history"

    id: Optional[int] = Field(default=None, primary_key=True)
    entry_id: int = Field(foreign_key="wildcard_entries.id", ondelete="CASCADE")
    previous_text: Optional[str] = None
    next_text: str
    created_at: str
    workspace_id: str = Field(default="default", index=True)

class WildcardScanRun(SQLModel, table=True):
    __tablename__ = "wildcard_scan_runs"

    id: Optional[int] = Field(default=None, primary_key=True)
    source_root: str
    summary_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: str
    workspace_id: str = Field(default="default", index=True)

class WildcardTagIndex(SQLModel, table=True):
    __tablename__ = "wildcard_tag_index"

    tag: str = Field(primary_key=True)
    category: str = Field(primary_key=True)
    usage_count: int
    workspace_id: str = Field(default="default", index=True, primary_key=True)

class WildcardCategoryIndex(SQLModel, table=True):
    __tablename__ = "wildcard_category_index"

    category: str = Field(primary_key=True)
    usage_count: int
    workspace_id: str = Field(default="default", index=True, primary_key=True)

class WildcardCategoryStat(SQLModel, table=True):
    __tablename__ = "wildcard_category_stats"

    category: str = Field(primary_key=True)
    entry_count: int
    file_count: int
    tag_count: int
    wildcard_count: int
    workspace_id: str = Field(default="default", index=True, primary_key=True)

class WildcardPromptModeIndex(SQLModel, table=True):
    __tablename__ = "wildcard_prompt_mode_index"

    prompt_mode: str = Field(primary_key=True)
    entry_count: int
    file_count: int
    wildcard_count: int
    workspace_id: str = Field(default="default", index=True, primary_key=True)

class WildcardPromptRecipe(SQLModel, table=True):
    __tablename__ = "wildcard_prompt_recipes"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    preset: str
    slots_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    negative_tags_json: dict[str, Any] = Field(default_factory=list, sa_column=Column(JSON))
    wildcard_refs_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: str
    updated_at: str
    workspace_id: str = Field(default="default", index=True)

class WildcardTagOverride(SQLModel, table=True):
    __tablename__ = "wildcard_tag_overrides"

    tag: str = Field(primary_key=True)
    canonical_tag: Optional[str] = None
    category: Optional[str] = None
    is_ignored: int = 0
    updated_at: str
    workspace_id: str = Field(default="default", index=True, primary_key=True)

class WildcardTaxonomyRule(SQLModel, table=True):
    __tablename__ = "wildcard_taxonomy_rules"

    category: str = Field(primary_key=True)
    keyword: str = Field(primary_key=True)
    enabled: int = 1
    updated_at: str
    workspace_id: str = Field(default="default", index=True, primary_key=True)

class WildcardTaxonomyMeta(SQLModel, table=True):
    __tablename__ = "wildcard_taxonomy_meta"

    key: str = Field(primary_key=True)
    value: str
    updated_at: str
    workspace_id: str = Field(default="default", index=True, primary_key=True)

class WildcardSourceFileStat(SQLModel, table=True):
    __tablename__ = "wildcard_source_file_stats"

    source_file_id: int = Field(primary_key=True, foreign_key="wildcard_source_files.id", ondelete="CASCADE")
    entry_count: int = 0
    prompt_count: int = 0
    duplicate_count: int = 0
    unresolved_refs: int = 0
    categories_json: dict[str, Any] = Field(default_factory=list, sa_column=Column(JSON))
    prompt_modes_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    updated_at: str
    workspace_id: str = Field(default="default", index=True, primary_key=True)

class WildcardLlmJob(SQLModel, table=True):
    __tablename__ = "wildcard_llm_jobs"

    id: Optional[int] = Field(default=None, primary_key=True)
    task: str
    prompt_mode: str
    endpoint: str
    model: str
    input_text: str
    status: str
    suggestion: str = ""
    error: Optional[str] = None
    endpoint_used: Optional[str] = None
    raw_json: Optional[str] = None
    created_at: str
    updated_at: str
    accepted_at: Optional[str] = None
    rejected_at: Optional[str] = None
    cancelled_at: Optional[str] = None
    workspace_id: str = Field(default="default", index=True)

class WildcardTagPolarityIndex(SQLModel, table=True):
    __tablename__ = "wildcard_tag_polarity_index"

    tag: str = Field(primary_key=True)
    category: str = Field(primary_key=True)
    polarity: str = Field(primary_key=True)
    usage_count: int
    workspace_id: str = Field(default="default", index=True, primary_key=True)
