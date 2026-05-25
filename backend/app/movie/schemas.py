from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    canceled = "canceled"


class JobType(str, Enum):
    render = "render"
    export = "export"
    continuity_review = "continuity_review"
    image_generation = "image_generation"
    video_generation = "video_generation"
    character_image_generation = "character_image_generation"


class PromptTask(str, Enum):
    scenario_assistant = "scenario_assistant"
    beat_board_generation = "beat_board_generation"
    character_extraction = "character_extraction"
    scene_generation = "scene_generation"
    scene_image_prompt_generation = "scene_image_prompt_generation"
    sequence_generation = "sequence_generation"
    wan_prompt_generation = "wan_prompt_generation"
    continuity_review = "continuity_review"


class BeatBoardStatus(str, Enum):
    empty = "empty"
    generated = "generated"
    edited = "edited"
    stale = "stale"


class SequenceBatchTextMode(str, Enum):
    set = "set"
    append = "append"
    fill_empty = "fill_empty"


class ContinuityFindingCategory(str, Enum):
    identity = "identity"
    wardrobe = "wardrobe"
    location = "location"
    lighting = "lighting"
    props = "props"
    camera = "camera"
    action = "action"
    missing_media = "missing_media"


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


class StyleAnchor(BaseModel):
    id: str
    project_id: str
    content: str
    updated_at: str


class MediaAssetRead(BaseModel):
    id: str
    project_id: str
    scene_id: str | None = None
    sequence_id: str | None = None
    relative_path: str
    asset_url: str
    original_filename: str
    mime_type: str | None = None
    size_bytes: int
    created_at: str


class GeneratedImageVariantRead(BaseModel):
    id: str
    scene_id: str
    provider: str
    model_name: str
    seed: int | None = None
    prompt_text: str = ""
    asset: MediaAssetRead
    created_at: str


class GeneratedVideoVariantRead(BaseModel):
    id: str
    sequence_id: str
    provider: str
    model_name: str
    seed: int | None = None
    prompt_text: str = ""
    native_duration_s: float = 0.0
    output_duration_s: float = 0.0
    asset: MediaAssetRead
    input_frame_asset: MediaAssetRead | None = None
    last_frame_asset: MediaAssetRead | None = None
    created_at: str


class ExportAssetRead(BaseModel):
    id: str
    project_id: str
    job_id: str
    relative_path: str
    asset_url: str
    duration_s: float
    created_at: str


class SequenceRead(BaseModel):
    id: str
    project_id: str
    scene_id: str
    order: int
    absolute_order: int
    title: str
    target_duration_s: int
    narrative_text: str
    duration_locked: bool = False
    camera_direction: str
    action_direction: str
    wan_prompt_text: str
    uploaded_video_asset: MediaAssetRead | None = None
    approved_video_asset: MediaAssetRead | None = None
    approved_video_source: Literal["uploaded", "generated"] | None = None
    generated_video_variants: list[GeneratedVideoVariantRead] = Field(default_factory=list)
    input_frame_asset: MediaAssetRead | None = None
    last_frame_asset: MediaAssetRead | None = None
    chain_state: Literal["ready", "missing_input", "stale_upstream", "generated"] = "missing_input"
    trim_in_ms: int
    trim_out_ms: int
    include_in_assembly: bool
    created_at: str
    updated_at: str


class SceneRead(BaseModel):
    id: str
    project_id: str
    order: int
    title: str
    target_duration_s: int
    narrative_text: str
    duration_locked: bool = False
    first_image_prompt_text: str
    first_image_asset: MediaAssetRead | None = None
    first_image_source: Literal["uploaded", "generated"] | None = None
    generated_image_variants: list[GeneratedImageVariantRead] = Field(default_factory=list)
    image_generation_status: str = "idle"
    sequences: list[SequenceRead] = Field(default_factory=list)
    continuity_review: ContinuityReviewRead | None = None
    created_at: str
    updated_at: str


class BeatCardRead(BaseModel):
    id: str
    project_id: str
    act_index: int = Field(ge=1, le=3)
    order_index: int = Field(ge=1)
    title: str
    summary_text: str
    purpose_text: str
    source: str
    created_at: str
    updated_at: str


class BeatBoardRead(BaseModel):
    project_id: str
    status: BeatBoardStatus
    beats: list[BeatCardRead] = Field(default_factory=list)
    updated_at: str | None = None


class ContinuityFindingRead(BaseModel):
    category: ContinuityFindingCategory
    severity: Literal["info", "warning", "issue"]
    summary_text: str
    detail_text: str = ""
    sequence_id: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ContinuitySuggestionRead(BaseModel):
    sequence_id: str
    suggested_prompt_fix: str
    rationale: str


class ContinuityReviewRead(BaseModel):
    id: str
    project_id: str
    scene_id: str
    source: str
    summary_text: str
    findings: list[ContinuityFindingRead] = Field(default_factory=list)
    sequence_suggestions: list[ContinuitySuggestionRead] = Field(default_factory=list)
    created_at: str
    updated_at: str


class CharacterRead(BaseModel):
    id: str
    project_id: str
    name: str
    role_summary: str
    prompt_tags: str
    order_index: int
    portrait_image_url: str | None = None
    cowboyshot_image_url: str | None = None
    fullbody_image_url: str | None = None
    created_at: str
    updated_at: str


class CharacterCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    role_summary: str = ""
    prompt_tags: str = ""
    order_index: int = 1


class CharacterUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    role_summary: str | None = None
    prompt_tags: str | None = None
    order_index: int | None = None
    portrait_image_url: str | None = None
    cowboyshot_image_url: str | None = None
    fullbody_image_url: str | None = None


class CharacterGenerateRequest(BaseModel):
    overwrite_existing: bool = True


class CharacterImageGenerateRequest(BaseModel):
    shot_type: Literal["portrait", "cowboyshot", "fullbody"]


class PromptPackageSequenceRead(BaseModel):
    sequence_id: str
    order: int
    absolute_order: int
    title: str
    target_duration_s: int
    narrative_text: str
    camera_direction: str
    action_direction: str
    wan_prompt_text: str
    uploaded_video_asset: MediaAssetRead | None = None


class PromptPackageSceneRead(BaseModel):
    scene_id: str
    order: int
    title: str
    target_duration_s: int
    narrative_text: str
    first_image_prompt_text: str
    first_image_asset: MediaAssetRead | None = None
    sequences: list[PromptPackageSequenceRead] = Field(default_factory=list)


class PromptPackageRead(BaseModel):
    project_id: str
    name: str
    genre: str
    tone: str
    target_duration_s: int
    style_anchor_text: str
    prompt_package_status: str
    scenes: list[PromptPackageSceneRead] = Field(default_factory=list)
    created_at: str
    updated_at: str


class ComfySceneExtractProjectRead(BaseModel):
    id: str
    name: str


class ComfySceneExtractSceneRead(BaseModel):
    id: str
    order: int
    title: str
    target_duration_s: int


class ComfySceneExtractBlockRead(BaseModel):
    start_order: int
    end_order: int


class ComfySceneExtractPromptsRead(BaseModel):
    first_image_prompt: str
    sequence_1_wan_prompt: str
    sequence_2_wan_prompt: str
    sequence_3_wan_prompt: str


class ComfySceneExtractSequenceRead(BaseModel):
    id: str
    order: int
    title: str
    wan_prompt_text: str


class ComfySceneExtractRead(BaseModel):
    format: str
    project: ComfySceneExtractProjectRead
    scene: ComfySceneExtractSceneRead
    block: ComfySceneExtractBlockRead
    prompts: ComfySceneExtractPromptsRead
    sequences: list[ComfySceneExtractSequenceRead] = Field(default_factory=list)


class JobRead(BaseModel):
    id: str
    project_id: str
    scene_id: str | None = None
    job_type: JobType
    status: JobStatus
    progress: float
    payload: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    error_text: str | None = None
    cancel_requested: bool = False
    created_at: str
    updated_at: str
    started_at: str | None = None
    completed_at: str | None = None


class ProjectListItem(BaseModel):
    id: str
    name: str
    target_duration_s: int
    genre: str
    tone: str
    scene_count: int
    workflow_version: int
    upgrade_available: bool = False
    archived_at: str | None = None
    created_at: str
    updated_at: str


class ProjectRead(BaseModel):
    id: str
    name: str
    scenario_text: str
    genre: str
    tone: str
    target_duration_s: int
    output_width: int
    output_height: int
    output_fps: int
    aspect_ratio: str
    workflow_version: int
    upgrade_available: bool = False
    legacy_sequence_count: int = 0
    beat_board_status: BeatBoardStatus = BeatBoardStatus.empty
    style_anchor: StyleAnchor | None = None
    model_settings_override: ProjectModelSettingsOverrideRead | None = None
    prompt_package_status: str
    hardware_profile: HardwareProfile
    beat_board: BeatBoardRead | None = None
    characters: list[CharacterRead] = Field(default_factory=list)
    scenes: list[SceneRead] = Field(default_factory=list)
    recent_jobs: list[JobRead] = Field(default_factory=list)
    exports: list[ExportAssetRead] = Field(default_factory=list)
    archived_at: str | None = None
    created_at: str
    updated_at: str


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scenario_text: str = ""
    genre: str = "cinematic drama"
    tone: str = "grounded and atmospheric"
    target_duration_s: int = Field(default=240, ge=180, le=300)
    output_width: int = Field(default=1280, ge=640, le=3840)
    output_height: int = Field(default=720, ge=360, le=2160)
    output_fps: int = Field(default=24, ge=12, le=60)
    aspect_ratio: str = "16:9"


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    scenario_text: str | None = None
    genre: str | None = None
    tone: str | None = None
    target_duration_s: int | None = Field(default=None, ge=180, le=300)
    output_width: int | None = Field(default=None, ge=640, le=3840)
    output_height: int | None = Field(default=None, ge=360, le=2160)
    output_fps: int | None = Field(default=None, ge=12, le=60)
    aspect_ratio: str | None = None
    style_anchor_text: str | None = None


class GenerateScenesRequest(BaseModel):
    replace_existing: bool = True
    source: Literal["scenario", "beat_board"] = "scenario"


class GenerateSceneImagePromptsRequest(BaseModel):
    overwrite_existing: bool = True
    scene_ids: list[str] | None = None


class GenerateSequencesRequest(BaseModel):
    overwrite_existing: bool = True
    scene_ids: list[str] | None = None


class GenerateWanPromptsRequest(BaseModel):
    overwrite_existing: bool = True
    scene_ids: list[str] | None = None
    sequence_ids: list[str] | None = None


class SceneImageGenerateRequest(BaseModel):
    model_name: str | None = None
    variant_count: int = Field(default=1, ge=1, le=8)
    auto_approve: bool = False
    steps: int | None = Field(default=None, ge=1, le=150)
    cfg_scale: float | None = Field(default=None, ge=0.0, le=30.0)
    sampler: str | None = None
    scheduler: str | None = None
    width: int | None = Field(default=None, ge=256, le=2048)
    height: int | None = Field(default=None, ge=256, le=2048)
    seed_mode: Literal["random", "fixed"] = "random"
    seed: int | None = None


class SequenceVideoGenerateRequest(BaseModel):
    model_name: str | None = None
    auto_approve: bool = False
    seed_mode: Literal["random", "fixed"] = "random"
    seed: int | None = None


class SceneVideoChainGenerateRequest(BaseModel):
    model_name: str | None = None
    auto_approve: bool = False
    seed_mode: Literal["random", "fixed"] = "random"
    seed: int | None = None


class BeatBoardGenerateRequest(BaseModel):
    overwrite_existing: bool = True


class BeatBoardReorderItem(BaseModel):
    beat_id: str
    act_index: int = Field(ge=1, le=3)
    order_index: int = Field(ge=1)


class BeatBoardReorderRequest(BaseModel):
    beats: list[BeatBoardReorderItem] = Field(default_factory=list)


class CreateBeatRequest(BaseModel):
    act_index: int = Field(ge=1, le=3)
    title: str = Field(min_length=1, max_length=120)
    summary_text: str = ""
    purpose_text: str = ""
    source: str = "manual"


class UpdateBeatRequest(BaseModel):
    act_index: int | None = Field(default=None, ge=1, le=3)
    order_index: int | None = Field(default=None, ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    summary_text: str | None = None
    purpose_text: str | None = None
    source: str | None = None


class UpdateSceneRequest(BaseModel):
    order: int | None = Field(default=None, ge=1, le=10)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    target_duration_s: int | None = Field(default=None, ge=30, le=90)
    narrative_text: str | None = None
    duration_locked: bool | None = None
    first_image_prompt_text: str | None = None


class UpdateSequenceRequest(BaseModel):
    order: int | None = Field(default=None, ge=1, le=200)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    target_duration_s: int | None = Field(default=None, ge=5, le=10)
    narrative_text: str | None = None
    duration_locked: bool | None = None
    camera_direction: str | None = None
    action_direction: str | None = None


class UpdateSequenceWanPromptRequest(BaseModel):
    wan_prompt_text: str


class SequenceBatchUpdateRequest(BaseModel):
    sequence_ids: list[str] = Field(default_factory=list, min_length=1)
    camera_direction: str | None = None
    camera_direction_mode: SequenceBatchTextMode | None = None
    action_direction: str | None = None
    action_direction_mode: SequenceBatchTextMode | None = None
    include_in_assembly: bool | None = None


class UpdateAssemblyRequest(BaseModel):
    trim_in_ms: int | None = Field(default=None, ge=0)
    trim_out_ms: int | None = Field(default=None, ge=0)
    include_in_assembly: bool | None = None


class ExportRequest(BaseModel):
    filename: str | None = None


class ScenarioAssistantRequest(BaseModel):
    focus: str = Field(default="rewrite", min_length=1, max_length=40)
    instruction: str = ""
    rewrite_scenario: bool = True
    max_suggestions: int = Field(default=4, ge=2, le=8)


class ScenarioAssistantResponse(BaseModel):
    source: str
    provider: str
    model: str
    focus: str
    instruction: str
    summary: str
    revised_scenario_text: str
    suggestions: list[str] = Field(default_factory=list)
    beat_notes: list[str] = Field(default_factory=list)
    title_options: list[str] = Field(default_factory=list)


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
    id: PromptTask
    label: str
    variables: list[str] = Field(default_factory=list)


class ModelSettingsDefaultsRead(BaseModel):
    runtime: ModelRuntimeSettings
    generation_defaults: GenerationDefaults
    task_profiles: dict[PromptTask, TaskPromptProfile] = Field(default_factory=dict)


class ModelSettingsRead(BaseModel):
    runtime: ModelRuntimeSettings
    generation_defaults: GenerationDefaults
    task_profiles: dict[PromptTask, TaskPromptProfile] = Field(default_factory=dict)
    defaults: ModelSettingsDefaultsRead
    task_catalog: list[TaskPromptCatalogItem] = Field(default_factory=list)


class ModelSettingsUpdateRequest(BaseModel):
    runtime: ModelRuntimeSettings
    generation_defaults: GenerationDefaults
    task_profiles: dict[PromptTask, TaskPromptProfile] = Field(default_factory=dict)


class ProjectModelSettingsOverrideRead(BaseModel):
    enabled: bool = False
    default_model_override: str | None = None
    generation_defaults_override: GenerationDefaultsOverride = Field(default_factory=GenerationDefaultsOverride)
    task_profiles: dict[PromptTask, TaskPromptProfileOverride] = Field(default_factory=dict)


class ProjectModelSettingsOverrideUpdateRequest(BaseModel):
    enabled: bool = False
    default_model_override: str | None = None
    generation_defaults_override: GenerationDefaultsOverride = Field(default_factory=GenerationDefaultsOverride)
    task_profiles: dict[PromptTask, TaskPromptProfileOverride] = Field(default_factory=dict)


class PromptPreviewRequest(BaseModel):
    task: PromptTask
    project_id: str | None = None
    scene_id: str | None = None
    sequence_id: str | None = None
    focus: str = Field(default="rewrite", min_length=1, max_length=40)
    instruction: str = ""
    rewrite_scenario: bool = True
    max_suggestions: int = Field(default=4, ge=2, le=8)
    run_model: bool = False


class PromptPreviewResponse(BaseModel):
    task: PromptTask
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


class VideoGenerationSettings(BaseModel):
    enabled: bool = True
    provider: Literal["mock", "lightx2v", "wan_gguf"] = "mock"
    model_root: str = ""
    model_class: str = "wan2.2_i2v"
    # GGUF quantised transformer (wan_gguf provider only).
    # Set to the absolute path of your .gguf file, e.g.
    #   /models/video/Wan-2.2-Remix-I2V-Q4_K_M.gguf
    # Leave empty to use a full-precision safetensors model (lightx2v provider).
    gguf_model_path: str = ""
    # Text encoder: path to a single safetensors file or directory.
    # e.g. nsfw_wan_umt5-xxl_fp8_scaled.safetensors (Osrivers on HF)
    # Leave empty to use the encoder bundled inside model_root.
    encoder_root: str = ""
    # WAN VAE: path to safetensors file or directory.
    # Leave empty to use the VAE bundled inside model_root.
    vae_root: str = ""
    # Distill / accelerator LoRA path (file or directory).
    # e.g. lightx2v/Wan2.2-Distill-Models  or  the GGUF variant
    #      jayn7/WAN2.2-I2V_A14B-DISTILL-LIGHTX2V-4STEP-GGUF
    # Leave empty to run without a distill LoRA.
    lora_path: str = ""
    lora_scale: float = Field(default=1.0, ge=0.0, le=2.0)
    # lightx2v provider quantisation preset ("auto", "bf16", "fp8", …)
    # Ignored for wan_gguf – quantisation is encoded in the .gguf file.
    quantization_preset: str = "auto"
    attention_mode: str = "sage_attn2"
    infer_steps: int = Field(default=4, ge=1, le=80)
    native_height: int = Field(default=480, ge=256, le=1080)
    native_width: int = Field(default=832, ge=256, le=1920)
    native_frame_count: int = Field(default=49, ge=8, le=161)
    guidance_scale: float = Field(default=3.5, ge=0.0, le=20.0)
    sample_shift: float = Field(default=5.0, ge=0.0, le=20.0)
    cpu_offload: bool = True
    text_encoder_offload: bool = True
    image_encoder_offload: bool = False
    vae_offload: bool = False
    retime_mode: Literal["none", "fit_duration", "frame_interpolate_fit"] = "fit_duration"
    target_output_fps: int = Field(default=24, ge=6, le=60)
    seed_mode: Literal["random", "fixed"] = "random"
    seed: int | None = None


class MediaGenerationSettingsRead(BaseModel):
    image: ImageGenerationSettings
    video: VideoGenerationSettings


class MediaGenerationSettingsUpdateRequest(BaseModel):
    image: ImageGenerationSettings
    video: VideoGenerationSettings


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
    video: MediaGenerationProviderTestResult


class MediaModelDownloadRequest(BaseModel):
    target: Literal["image", "video"]
    repo_id: str = Field(min_length=1)
    revision: str = ""
    filename: str = ""
    include_patterns: list[str] = Field(default_factory=list)
    ignore_patterns: list[str] = Field(default_factory=list)
    destination_name: str = ""
    token: str = ""
    apply_to_settings: bool = True


class MediaModelDownloadStatusRead(BaseModel):
    id: str
    target: Literal["image", "video"]
    status: Literal["queued", "running", "succeeded", "failed"]
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    repo_id: str
    revision: str = ""
    destination_path: str = ""
    downloaded_path: str | None = None
    applied_to_settings: bool = False
    message: str = ""
    error_text: str | None = None
    created_at: str
    updated_at: str


class VideoModelAutoConfig(BaseModel):
    """Best-guess component paths auto-detected by scanning the video-models folder.

    Each field is an absolute path string when a matching file/dir was found,
    or an empty string when nothing was detected for that component.
    Fields map 1-to-1 to VideoGenerationSettings fields.
    """

    gguf_model_path: str = ""
    model_root: str = ""
    encoder_root: str = ""
    vae_root: str = ""
    lora_path: str = ""


class VideoModelInventoryRead(BaseModel):
    """Result of scanning the video-models drop folder."""

    root_path: str
    # Files / dirs grouped by detected component type.
    transformer_gguf: list[MediaGenerationModelOptionRead] = Field(default_factory=list)
    model_dirs: list[MediaGenerationModelOptionRead] = Field(default_factory=list)
    encoders: list[MediaGenerationModelOptionRead] = Field(default_factory=list)
    vaes: list[MediaGenerationModelOptionRead] = Field(default_factory=list)
    loras: list[MediaGenerationModelOptionRead] = Field(default_factory=list)
    other: list[MediaGenerationModelOptionRead] = Field(default_factory=list)
    # Best-guess auto-config derived from the scan.
    auto_config: VideoModelAutoConfig = Field(default_factory=VideoModelAutoConfig)
