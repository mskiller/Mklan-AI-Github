from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class GenerationStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class GenerationTask(str, Enum):
    scenario_generation = "scenario_generation"
    character_card_generation = "character_card_generation"
    lore_generation = "lore_generation"
    user_profile_generation = "user_profile_generation"
    game_master_card_generation = "game_master_card_generation"
    image_prompt_generation = "image_prompt_generation"


class ProjectScope(str, Enum):
    active = "active"
    archived = "archived"
    all = "all"


class ProjectMode(str, Enum):
    game_master = "game_master"
    character = "character"


MessageRole = Literal["system", "user", "assistant"]
LoreEntryPosition = Literal["before_char", "after_char", "before_examples", "after_examples"]


class HardwareProfile(BaseModel):
    gpu_vendor: str | None = None
    gpu_name: str | None = None
    vram_gb: float | None = None
    ram_gb: float | None = None
    cpu_cores: int
    cuda_available: bool
    support_tier: str
    supported_for_v1: bool
    recommended_renderer: str
    notes: list[str] = Field(default_factory=list)


class CharacterRead(BaseModel):
    id: str
    project_id: str
    name: str
    description: str
    personality: str
    scenario: str
    first_message: str
    example_dialogue: str
    tags: list[str] = Field(default_factory=list)
    creator_notes: str
    system_prompt: str
    post_history_instructions: str
    alternate_greetings: list[str] = Field(default_factory=list)
    creator: str = ""
    character_version: str = ""
    character_note: str = ""
    character_note_depth: int = 4
    character_note_role: MessageRole = "system"
    talkativeness: float | None = None
    appearance_summary: str = ""
    booru_character_name: str = ""
    booru_copyright: str = ""
    avatar_url: str | None = None
    portrait_url: str | None = None
    cowboy_shot_url: str | None = None
    fullbody_shot_url: str | None = None
    created_at: str
    updated_at: str


class CharacterCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    personality: str = ""
    scenario: str = ""
    first_message: str = ""
    example_dialogue: str = ""
    tags: list[str] = Field(default_factory=list)
    creator_notes: str = ""
    system_prompt: str = ""
    post_history_instructions: str = ""
    alternate_greetings: list[str] = Field(default_factory=list)
    creator: str = ""
    character_version: str = ""
    character_note: str = ""
    character_note_depth: int = 4
    character_note_role: MessageRole = "system"
    talkativeness: float | None = Field(default=None, ge=0.0, le=1.0)
    appearance_summary: str = ""
    booru_character_name: str = ""
    booru_copyright: str = ""


class CharacterUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    personality: str | None = None
    scenario: str | None = None
    first_message: str | None = None
    example_dialogue: str | None = None
    tags: list[str] | None = None
    creator_notes: str | None = None
    system_prompt: str | None = None
    post_history_instructions: str | None = None
    alternate_greetings: list[str] | None = None
    creator: str | None = None
    character_version: str | None = None
    character_note: str | None = None
    character_note_depth: int | None = None
    character_note_role: MessageRole | None = None
    talkativeness: float | None = Field(default=None, ge=0.0, le=1.0)
    appearance_summary: str | None = None
    booru_character_name: str | None = None
    booru_copyright: str | None = None
    avatar_relative_path: str | None = None
    portrait_relative_path: str | None = None
    cowboy_shot_relative_path: str | None = None
    fullbody_shot_relative_path: str | None = None


class LoreEntryRead(BaseModel):
    id: str
    project_id: str
    name: str
    keys: list[str] = Field(default_factory=list)
    secondary_keys: list[str] = Field(default_factory=list)
    content: str
    comment: str
    enabled: bool = True
    insertion_order: int = 100
    position: LoreEntryPosition = "after_char"
    constant: bool = False
    selective_logic: int = 0
    probability: int = 100
    case_sensitive: bool = False
    priority: int = 0
    scan_depth: int | None = None
    match_whole_words: bool | None = None
    group: str = ""
    group_weight: int = 100
    prevent_recursion: bool = True
    delay_until_recursion: bool = False
    character_filter_json: str = ""
    automation_id: str = ""
    role: MessageRole = "system"
    extensions_json: str = "{}"
    image_url: str | None = None
    created_at: str
    updated_at: str


class LoreEntryCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    keys: list[str] = Field(default_factory=list)
    secondary_keys: list[str] = Field(default_factory=list)
    content: str = ""
    comment: str = ""
    enabled: bool = True
    insertion_order: int = 100
    position: LoreEntryPosition = "after_char"
    constant: bool = False
    selective_logic: int = 0
    probability: int = Field(default=100, ge=0, le=100)
    case_sensitive: bool = False
    priority: int = 0
    scan_depth: int | None = None
    match_whole_words: bool | None = None
    group: str = ""
    group_weight: int = 100
    prevent_recursion: bool = True
    delay_until_recursion: bool = False
    character_filter_json: str = ""
    automation_id: str = ""
    role: MessageRole = "system"
    extensions_json: str = "{}"


class LoreEntryUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    keys: list[str] | None = None
    secondary_keys: list[str] | None = None
    content: str | None = None
    comment: str | None = None
    enabled: bool | None = None
    insertion_order: int | None = None
    position: LoreEntryPosition | None = None
    constant: bool | None = None
    selective_logic: int | None = None
    probability: int | None = Field(default=None, ge=0, le=100)
    case_sensitive: bool | None = None
    priority: int | None = None
    scan_depth: int | None = None
    match_whole_words: bool | None = None
    group: str | None = None
    group_weight: int | None = None
    prevent_recursion: bool | None = None
    delay_until_recursion: bool | None = None
    character_filter_json: str | None = None
    automation_id: str | None = None
    role: MessageRole | None = None
    extensions_json: str | None = None
    image_relative_path: str | None = None


class UserProfileRead(BaseModel):
    project_id: str
    name: str
    description: str
    title: str = ""
    personality: str
    scenario_role: str
    first_message: str
    tags: list[str] = Field(default_factory=list)
    persona_note: str = ""
    persona_note_depth: int = 4
    persona_note_role: MessageRole = "system"
    appearance_summary: str = ""
    booru_character_name: str = ""
    booru_copyright: str = ""
    avatar_url: str | None = None
    portrait_url: str | None = None
    cowboy_shot_url: str | None = None
    fullbody_shot_url: str | None = None
    created_at: str
    updated_at: str


class UserProfileUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    title: str | None = None
    personality: str | None = None
    scenario_role: str | None = None
    first_message: str | None = None
    tags: list[str] | None = None
    persona_note: str | None = None
    persona_note_depth: int | None = None
    persona_note_role: MessageRole | None = None
    appearance_summary: str | None = None
    booru_character_name: str | None = None
    booru_copyright: str | None = None
    avatar_relative_path: str | None = None
    portrait_relative_path: str | None = None
    cowboy_shot_relative_path: str | None = None
    fullbody_shot_relative_path: str | None = None


class GenerationRunRead(BaseModel):
    id: str
    project_id: str
    task_type: GenerationTask
    status: GenerationStatus
    progress: float
    error_text: str | None = None
    created_at: str
    updated_at: str
    completed_at: str | None = None


class ProjectListItem(BaseModel):
    id: str
    name: str
    seed_sentence: str
    project_mode: ProjectMode = ProjectMode.character
    sample_character_target_count: int = Field(default=5, ge=1, le=10)
    archived_at: str | None = None
    character_count: int
    lore_count: int
    created_at: str
    updated_at: str


class GMCardProfileRead(BaseModel):
    name: str = ""
    description: str = ""
    personality: str = ""
    scenario: str = ""
    first_message: str = ""
    example_dialogue: str = ""
    tags: list[str] = Field(default_factory=list)
    creator_notes: str = ""
    system_prompt: str = ""
    post_history_instructions: str = ""
    alternate_greetings: list[str] = Field(default_factory=list)
    creator: str = ""
    character_version: str = ""
    character_note: str = ""
    character_note_depth: int = 4
    character_note_role: MessageRole = "system"
    talkativeness: float | None = None


class GMCardProfileUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    personality: str | None = None
    scenario: str | None = None
    first_message: str | None = None
    example_dialogue: str | None = None
    tags: list[str] | None = None
    creator_notes: str | None = None
    system_prompt: str | None = None
    post_history_instructions: str | None = None
    alternate_greetings: list[str] | None = None
    creator: str | None = None
    character_version: str | None = None
    character_note: str | None = None
    character_note_depth: int | None = None
    character_note_role: MessageRole | None = None
    talkativeness: float | None = Field(default=None, ge=0.0, le=1.0)


class ProjectRead(BaseModel):
    id: str
    name: str
    seed_sentence: str
    scenario_text: str
    scenario_world_image_url: str | None = None
    project_mode: ProjectMode = ProjectMode.character
    sample_character_target_count: int = Field(default=5, ge=1, le=10)
    lorebook_scan_depth: int = 4
    lorebook_token_budget: int = 512
    lorebook_recursive_scanning: bool = False
    genre: str
    tone: str
    gm_card_profile: GMCardProfileRead = Field(default_factory=GMCardProfileRead)
    characters: list[CharacterRead] = Field(default_factory=list)
    lore_entries: list[LoreEntryRead] = Field(default_factory=list)
    user_profile: UserProfileRead
    generation_runs: list[GenerationRunRead] = Field(default_factory=list)
    archived_at: str | None = None
    created_at: str
    updated_at: str


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    seed_sentence: str = ""
    scenario_text: str = ""
    project_mode: ProjectMode = ProjectMode.character
    sample_character_target_count: int = Field(default=5, ge=1, le=10)
    lorebook_scan_depth: int = Field(default=4, ge=0, le=100)
    lorebook_token_budget: int = Field(default=512, ge=0, le=32768)
    lorebook_recursive_scanning: bool = False
    genre: str = "roleplay"
    tone: str = "immersive"


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    seed_sentence: str | None = None
    scenario_text: str | None = None
    project_mode: ProjectMode | None = None
    sample_character_target_count: int | None = Field(default=None, ge=1, le=10)
    lorebook_scan_depth: int | None = Field(default=None, ge=0, le=100)
    lorebook_token_budget: int | None = Field(default=None, ge=0, le=32768)
    lorebook_recursive_scanning: bool | None = None
    scenario_image_relative_path: str | None = None
    genre: str | None = None
    tone: str | None = None


class GenerateCharactersRequest(BaseModel):
    overwrite_existing: bool = True
    target_count: int = Field(default=5, ge=1, le=10)
    instruction: str = ""


class GenerateLoreRequest(BaseModel):
    overwrite_existing: bool = True
    instruction: str = ""


class GenerateScenarioRequest(BaseModel):
    instruction: str = ""


class GenerateUserRequest(BaseModel):
    instruction: str = ""


class GenerateAllRequest(BaseModel):
    overwrite_characters: bool = True
    overwrite_lore: bool = True
    target_count: int | None = Field(default=None, ge=1, le=10)
    instruction: str = ""


class CharacterImageGenerateRequest(BaseModel):
    format: Literal["portrait", "cowboy_shot", "fullbody_shot", "fullbody", "reference"] = "portrait"
    instruction: str = ""
    prompt: str = ""
    negative_prompt: str = ""
    wildcard_recipe_id: str = ""
    wildcard_tags: list[str] = Field(default_factory=list)
    style_anchor: str = ""


class ScenarioImageGenerateRequest(BaseModel):
    instruction: str = ""
    prompt: str = ""
    negative_prompt: str = ""
    wildcard_recipe_id: str = ""
    wildcard_tags: list[str] = Field(default_factory=list)
    style_anchor: str = ""


class LoreImageGenerateRequest(BaseModel):
    instruction: str = ""
    prompt: str = ""
    negative_prompt: str = ""
    wildcard_recipe_id: str = ""
    wildcard_tags: list[str] = Field(default_factory=list)
    style_anchor: str = ""


class UserImageGenerateRequest(BaseModel):
    format: Literal["portrait", "cowboy_shot", "fullbody_shot", "fullbody", "reference"] = "portrait"
    instruction: str = ""
    prompt: str = ""
    negative_prompt: str = ""
    wildcard_recipe_id: str = ""
    wildcard_tags: list[str] = Field(default_factory=list)
    style_anchor: str = ""


class ImagePromptGenerateRequest(BaseModel):
    instruction: str = ""
    wildcard_recipe_id: str = ""
    wildcard_tags: list[str] = Field(default_factory=list)
    style_anchor: str = ""


class GeneratedImagePromptRead(BaseModel):
    prompt: str
    negative_prompt: str
    style_profile: str
    image_slot: str


class ImageCandidateRead(BaseModel):
    id: str
    project_id: str
    owner_type: Literal["scenario", "character", "lore", "user"]
    owner_id: str
    image_slot: str
    relative_path: str
    image_url: str
    prompt_text: str
    negative_prompt: str
    created_at: str
    approved: bool = False


class ModelRuntimeSettings(BaseModel):
    provider: Literal["ollama", "openai_compatible", "koboldcpp"]
    base_url: str = Field(min_length=1)
    api_key: str = ""
    default_model: str = Field(min_length=1)
    timeout_s: int = Field(default=120, ge=5, le=600)


class GenerationDefaults(BaseModel):
    temperature: float = Field(default=0.4, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    top_k: int = Field(default=40, ge=0, le=500)
    min_p: float = Field(default=0.05, ge=0.0, le=1.0)
    repeat_penalty: float = Field(default=1.05, ge=0.0, le=5.0)
    max_output_tokens: int = Field(default=1600, ge=64, le=8192)
    seed: int | None = None
    stop_sequences: list[str] = Field(default_factory=list)
    json_retries: int = Field(default=2, ge=1, le=6)
    strip_markdown_fences: bool = True
    fallback_to_heuristics: bool = True


class GenerationDefaultsOverride(BaseModel):
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    top_k: int | None = Field(default=None, ge=0, le=500)
    min_p: float | None = Field(default=None, ge=0.0, le=1.0)
    repeat_penalty: float | None = Field(default=None, ge=0.0, le=5.0)
    max_output_tokens: int | None = Field(default=None, ge=64, le=8192)
    seed: int | None = None
    stop_sequences: list[str] | None = None
    json_retries: int | None = Field(default=None, ge=1, le=6)
    strip_markdown_fences: bool | None = None
    fallback_to_heuristics: bool | None = None


class TaskPromptProfile(BaseModel):
    model_override: str | None = None
    temperature_override: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p_override: float | None = Field(default=None, ge=0.0, le=1.0)
    max_output_tokens_override: int | None = Field(default=None, ge=64, le=8192)
    system_template: str = ""
    user_template: str = ""


class TaskPromptProfileOverride(BaseModel):
    model_override: str | None = None
    temperature_override: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p_override: float | None = Field(default=None, ge=0.0, le=1.0)
    max_output_tokens_override: int | None = Field(default=None, ge=64, le=8192)
    system_template: str | None = None
    user_template: str | None = None


class TaskPromptCatalogItem(BaseModel):
    id: GenerationTask
    label: str
    variables: list[str] = Field(default_factory=list)


class ModelSettingsDefaultsRead(BaseModel):
    runtime: ModelRuntimeSettings
    generation_defaults: GenerationDefaults
    task_profiles: dict[GenerationTask, TaskPromptProfile] = Field(default_factory=dict)


class ModelSettingsRead(BaseModel):
    runtime: ModelRuntimeSettings
    generation_defaults: GenerationDefaults
    task_profiles: dict[GenerationTask, TaskPromptProfile] = Field(default_factory=dict)
    defaults: ModelSettingsDefaultsRead
    task_catalog: list[TaskPromptCatalogItem] = Field(default_factory=list)


class ModelSettingsUpdateRequest(BaseModel):
    runtime: ModelRuntimeSettings
    generation_defaults: GenerationDefaults
    task_profiles: dict[GenerationTask, TaskPromptProfile] = Field(default_factory=dict)


class ProjectModelSettingsOverrideRead(BaseModel):
    enabled: bool = False
    default_model_override: str | None = None
    generation_defaults_override: GenerationDefaultsOverride = Field(default_factory=GenerationDefaultsOverride)
    task_profiles: dict[GenerationTask, TaskPromptProfileOverride] = Field(default_factory=dict)


class ProjectModelSettingsOverrideUpdateRequest(BaseModel):
    enabled: bool = False
    default_model_override: str | None = None
    generation_defaults_override: GenerationDefaultsOverride = Field(default_factory=GenerationDefaultsOverride)
    task_profiles: dict[GenerationTask, TaskPromptProfileOverride] = Field(default_factory=dict)


class PromptPreviewRequest(BaseModel):
    task: GenerationTask
    project_id: str | None = None
    character_id: str | None = None
    lore_entry_id: str | None = None
    instruction: str = ""
    run_model: bool = False


class PromptPreviewResponse(BaseModel):
    task: GenerationTask
    system_prompt: str
    user_prompt: str
    rendered_variables: dict[str, str] = Field(default_factory=dict)
    provider: str
    effective_model: str
    effective_parameters: dict[str, Any] = Field(default_factory=dict)
    output_text: str | None = None
    error_text: str | None = None


class AssistantSettingsRead(BaseModel):
    provider: Literal["ollama", "openai_compatible", "koboldcpp"]
    base_url: str
    model: str
    api_key: str = ""
    timeout_s: int = Field(ge=5, le=600)


class AssistantSettingsUpdateRequest(BaseModel):
    provider: Literal["ollama", "openai_compatible", "koboldcpp"]
    base_url: str = Field(min_length=1)
    model: str = Field(min_length=1)
    api_key: str = ""
    timeout_s: int = Field(default=120, ge=5, le=600)


class AssistantConnectionTestRequest(BaseModel):
    provider: Literal["ollama", "openai_compatible", "koboldcpp"]
    base_url: str = Field(min_length=1)
    model: str = Field(min_length=1)
    api_key: str = ""
    timeout_s: int = Field(default=120, ge=5, le=600)


class AssistantRuntimeCapabilitiesRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    text: bool = False
    json_capable: bool = Field(default=False, alias="json", serialization_alias="json")
    vision: bool = False


class AssistantConnectionTestResponse(BaseModel):
    ok: bool
    ready: bool
    status: str
    message: str
    provider: str
    base_url: str
    resolved_base_url: str | None = None
    model: str
    available_models: list[str] = Field(default_factory=list)
    response_ms: int | None = None
    capabilities: AssistantRuntimeCapabilitiesRead = Field(default_factory=AssistantRuntimeCapabilitiesRead)
    vision_message: str | None = None


class ImageGenerationSettings(BaseModel):
    enabled: bool = True
    provider: Literal["mock", "diffusers", "comfyui"] = "mock"
    checkpoint_root: str = ""
    default_model: str = "mock-sdxl"
    comfy_endpoint: str = "http://host.docker.internal:8188"
    comfy_workflow_json: str = ""
    comfy_timeout_s: int = Field(default=300, ge=30, le=3600)
    vae_path: str = ""
    lora_dir: str = ""
    device: str = "auto"
    dtype: str = "auto"
    sampler: str = "res_multistep"
    scheduler: str = "simple"
    steps: int = Field(default=24, ge=1, le=150)
    cfg_scale: float = Field(default=6.5, ge=0.0, le=30.0)
    width: int = Field(default=1024, ge=256, le=2048)
    height: int = Field(default=1024, ge=256, le=2048)
    seed_mode: Literal["random", "fixed"] = "random"
    seed: int | None = None
    default_negative_prompt: str = ""
    variant_count: int = Field(default=1, ge=1, le=8)


class MediaGenerationSettingsRead(BaseModel):
    image: ImageGenerationSettings


class MediaGenerationSettingsUpdateRequest(BaseModel):
    image: ImageGenerationSettings


class MediaGenerationModelOptionRead(BaseModel):
    label: str
    value: str
    kind: Literal["file", "directory"]
    absolute_path: str
    size_bytes: int | None = None


class ImageModelInventoryRead(BaseModel):
    root_path: str
    default_model: str = ""
    models: list[MediaGenerationModelOptionRead] = Field(default_factory=list)


class ImageModelUploadResponse(BaseModel):
    uploaded_model: MediaGenerationModelOptionRead
    inventory: ImageModelInventoryRead
    settings: MediaGenerationSettingsRead


class MediaGenerationProviderTestResult(BaseModel):
    ok: bool
    ready: bool
    status: str
    message: str
    provider: str
    resolved_paths: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class MediaGenerationSettingsTestResponse(BaseModel):
    image: MediaGenerationProviderTestResult


class SillyTavernStatusRead(BaseModel):
    enabled: bool
    healthy: bool
    public_url: str
    internal_url: str
    data_root: str
    warnings: list[str] = Field(default_factory=list)


class SillyTavernSyncedFileRead(BaseModel):
    kind: str
    path: str


class SillyTavernSyncResponse(BaseModel):
    project_id: str
    public_url: str
    synced_files: list[SillyTavernSyncedFileRead] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class LorebookExportEntry(BaseModel):
    uid: int
    key: list[str] = Field(default_factory=list)
    keysecondary: list[str] = Field(default_factory=list)
    name: str = ""
    comment: str = ""
    content: str
    constant: bool = False
    selective: bool = True
    insertion_order: int = 100
    enabled: bool = True
    position: LoreEntryPosition = "after_char"
    selective_logic: int = 0
    probability: int = 100
    case_sensitive: bool = False
    priority: int = 0
    scan_depth: int | None = None
    match_whole_words: bool | None = None
    group: str = ""
    group_weight: int = 100
    prevent_recursion: bool = True
    delay_until_recursion: bool = False
    character_filter_json: str = ""
    automation_id: str = ""
    role: MessageRole = "system"
    extensions: dict[str, Any] = Field(default_factory=dict)


class LorebookExport(BaseModel):
    name: str
    description: str = ""
    scan_depth: int = 4
    token_budget: int = 512
    recursive_scanning: bool = False
    entries: dict[str, LorebookExportEntry]


class PersonaExport(BaseModel):
    spec: str = "st_persona_v1"
    spec_version: str = "1.0"
    name: str
    description: str
    title: str = ""
    avatar_url: str | None = None
    personality: str
    scenario_role: str
    first_message: str
    tags: list[str] = Field(default_factory=list)
    persona_note: str = ""
    persona_note_depth: int = 4
    persona_note_role: MessageRole = "system"
    linked_lorebook: str | None = None
    appearance_summary: str = ""
    booru_character_name: str = ""
    booru_copyright: str = ""


class CharacterCardExport(BaseModel):
    spec: str = "chara_card_v2"
    spec_version: str = "2.0"
    data: dict[str, Any]


class GenerationRunCreateResult(BaseModel):
    run: GenerationRunRead
    project: ProjectRead
