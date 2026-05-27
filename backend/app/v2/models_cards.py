from sqlmodel import SQLModel, Field, Column, String
from pgvector.sqlalchemy import Vector
from typing import Optional

class CardProject(SQLModel, table=True):
    __tablename__ = "projects"
    workspace_id: str = Field(default="default", index=True)
    id: str = Field(primary_key=True)
    name: str
    seed_sentence: str
    scenario_text: str
    project_mode: str
    sample_character_target_count: int
    lorebook_scan_depth: int
    lorebook_token_budget: int
    lorebook_recursive_scanning: int
    scenario_image_relative_path: Optional[str] = None
    genre: str
    tone: str
    gm_card_profile_json: str
    model_settings_override_json: str
    archived_at: Optional[str] = None
    created_at: str
    updated_at: str
    embedding: Optional[list[float]] = Field(default=None, sa_column=Column(Vector(384)))

class CardCharacter(SQLModel, table=True):
    __tablename__ = "characters"
    workspace_id: str = Field(default="default", index=True)
    id: str = Field(primary_key=True)
    project_id: str
    name: str
    description: str
    personality: str
    scenario: str
    first_message: str
    example_dialogue: str
    tags_json: str
    creator_notes: str
    system_prompt: str
    post_history_instructions: str
    alternate_greetings_json: str
    creator: str
    character_version: str
    character_note: str
    character_note_depth: int
    character_note_role: str
    talkativeness: Optional[float] = None
    appearance_summary: str
    booru_character_name: str
    booru_copyright: str
    avatar_relative_path: Optional[str] = None
    portrait_relative_path: Optional[str] = None
    cowboy_shot_relative_path: Optional[str] = None
    fullbody_shot_relative_path: Optional[str] = None
    created_at: str
    updated_at: str
    embedding: Optional[list[float]] = Field(default=None, sa_column=Column(Vector(384)))

class CardLoreEntry(SQLModel, table=True):
    __tablename__ = "lore_entries"
    workspace_id: str = Field(default="default", index=True)
    id: str = Field(primary_key=True)
    project_id: str
    name: str
    keys_json: str
    secondary_keys_json: str
    content: str
    comment: str
    image_relative_path: Optional[str] = None
    enabled: int
    insertion_order: int
    position: str
    constant: int
    selective_logic: int
    probability: int
    case_sensitive: int
    priority: int
    scan_depth: Optional[int] = None
    match_whole_words: Optional[int] = None
    group_name: str
    group_weight: int
    prevent_recursion: int
    delay_until_recursion: int
    character_filter_json: str
    automation_id: str
    role: str
    extensions_json: str
    created_at: str
    updated_at: str
    embedding: Optional[list[float]] = Field(default=None, sa_column=Column(Vector(384)))

class CardUserProfile(SQLModel, table=True):
    __tablename__ = "user_profiles"
    workspace_id: str = Field(default="default", index=True)
    project_id: str = Field(primary_key=True)
    name: str
    description: str
    title: str
    personality: str
    scenario_role: str
    first_message: str
    tags_json: str
    persona_note: str
    persona_note_depth: int
    persona_note_role: str
    appearance_summary: str
    booru_character_name: str
    booru_copyright: str
    avatar_relative_path: Optional[str] = None
    portrait_relative_path: Optional[str] = None
    cowboy_shot_relative_path: Optional[str] = None
    fullbody_shot_relative_path: Optional[str] = None
    created_at: str
    updated_at: str

class CardGenerationRun(SQLModel, table=True):
    __tablename__ = "generation_runs"
    workspace_id: str = Field(default="default", index=True)
    id: str = Field(primary_key=True)
    project_id: str
    task_type: str
    status: str
    progress: float
    error_text: Optional[str] = None
    created_at: str
    updated_at: str
    completed_at: Optional[str] = None

class CardAppSetting(SQLModel, table=True):
    __tablename__ = "app_settings"
    workspace_id: str = Field(default="default", index=True)
    key: str = Field(primary_key=True)
    value_text: str
    updated_at: str

class CardImageCandidate(SQLModel, table=True):
    __tablename__ = "image_candidates"
    workspace_id: str = Field(default="default", index=True)
    id: str = Field(primary_key=True)
    project_id: str
    owner_type: str
    owner_id: str
    image_slot: str
    relative_path: str
    prompt_text: str
    negative_prompt: str
    created_at: str

class CardSharedCharacterVault(SQLModel, table=True):
    __tablename__ = "shared_character_vault"
    workspace_id: str = Field(default="default", index=True)
    id: str = Field(primary_key=True)
    source_module: str
    source_id: str
    name: str
    description: str
    personality: str
    role_summary: str
    prompt_tags_json: str
    avatar_path: Optional[str] = None
    source_metadata_json: str
    created_at: str
    updated_at: str
    embedding: Optional[list[float]] = Field(default=None, sa_column=Column(Vector(384)))

class CardSharedLoreVault(SQLModel, table=True):
    __tablename__ = "shared_lore_vault"
    workspace_id: str = Field(default="default", index=True)
    id: str = Field(primary_key=True)
    source_module: str
    source_id: str
    name: str
    keys_json: str
    content: str
    source_metadata_json: str
    created_at: str
    updated_at: str
    embedding: Optional[list[float]] = Field(default=None, sa_column=Column(Vector(384)))

class CardCompatibilityReport(SQLModel, table=True):
    __tablename__ = "compatibility_reports"
    workspace_id: str = Field(default="default", index=True)
    id: str = Field(primary_key=True)
    project_id: str
    status: str
    critical_count: int
    warning_count: int
    report_json: str
    created_at: str
