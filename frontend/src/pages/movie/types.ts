export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "canceled";
export type JobType =
  | "render"
  | "export"
  | "continuity_review"
  | "image_generation"
  | "video_generation"
  | "character_image_generation";
export type PromptTask =
  | "scenario_assistant"
  | "beat_board_generation"
  | "scene_generation"
  | "scene_image_prompt_generation"
  | "sequence_generation"
  | "wan_prompt_generation"
  | "continuity_review"
  | "character_extraction";
export type BeatBoardStatus = "empty" | "generated" | "edited" | "stale";
export type SequenceBatchTextMode = "set" | "append" | "fill_empty";
export type ContinuityFindingCategory =
  | "identity"
  | "wardrobe"
  | "location"
  | "lighting"
  | "props"
  | "camera"
  | "action"
  | "missing_media";

export interface HardwareProfile {
  gpu_vendor: string | null;
  gpu_name: string | null;
  vram_gb: number | null;
  ram_gb: number | null;
  cpu_cores: number;
  cuda_available: boolean;
  support_tier: string;
  supported_for_v1: boolean;
  recommended_renderer: string;
  notes: string[];
}

export interface MediaAsset {
  id: string;
  project_id: string;
  scene_id: string | null;
  sequence_id: string | null;
  relative_path: string;
  asset_url: string;
  original_filename: string;
  mime_type: string | null;
  size_bytes: number;
  created_at: string;
}

export interface ExportAsset {
  id: string;
  project_id: string;
  job_id: string;
  relative_path: string;
  asset_url: string;
  duration_s: number;
  created_at: string;
}

export interface GeneratedImageVariant {
  id: string;
  scene_id: string;
  provider: string;
  model_name: string;
  seed: number | null;
  prompt_text: string;
  asset: MediaAsset | null;
  created_at: string;
}

export interface GeneratedVideoVariant {
  id: string;
  sequence_id: string;
  provider: string;
  model_name: string;
  seed: number | null;
  prompt_text: string;
  native_duration_s: number;
  output_duration_s: number;
  asset: MediaAsset | null;
  input_frame_asset: MediaAsset | null;
  last_frame_asset: MediaAsset | null;
  created_at: string;
}

export interface Sequence {
  id: string;
  project_id: string;
  scene_id: string;
  order: number;
  absolute_order: number;
  title: string;
  target_duration_s: number;
  narrative_text: string;
  duration_locked: boolean;
  camera_direction: string;
  action_direction: string;
  wan_prompt_text: string;
  uploaded_video_asset: MediaAsset | null;
  approved_video_asset: MediaAsset | null;
  approved_video_source: "uploaded" | "generated" | null;
  generated_video_variants: GeneratedVideoVariant[];
  input_frame_asset: MediaAsset | null;
  last_frame_asset: MediaAsset | null;
  chain_state: "ready" | "missing_input" | "stale_upstream" | "generated";
  trim_in_ms: number;
  trim_out_ms: number;
  include_in_assembly: boolean;
  created_at: string;
  updated_at: string;
}

export interface ContinuityFinding {
  category: ContinuityFindingCategory;
  severity: "info" | "warning" | "issue";
  summary_text: string;
  detail_text: string;
  sequence_id: string | null;
  confidence: number;
}

export interface ContinuitySuggestion {
  sequence_id: string;
  suggested_prompt_fix: string;
  rationale: string;
}

export interface ContinuityReview {
  id: string;
  project_id: string;
  scene_id: string;
  source: string;
  summary_text: string;
  findings: ContinuityFinding[];
  sequence_suggestions: ContinuitySuggestion[];
  created_at: string;
  updated_at: string;
}

export interface Scene {
  id: string;
  project_id: string;
  order: number;
  title: string;
  target_duration_s: number;
  narrative_text: string;
  duration_locked: boolean;
  first_image_prompt_text: string;
  first_image_asset: MediaAsset | null;
  first_image_source: "uploaded" | "generated" | null;
  generated_image_variants: GeneratedImageVariant[];
  image_generation_status: string;
  sequences: Sequence[];
  continuity_review: ContinuityReview | null;
  created_at: string;
  updated_at: string;
}

export interface BeatCard {
  id: string;
  project_id: string;
  act_index: number;
  order_index: number;
  title: string;
  summary_text: string;
  purpose_text: string;
  source: string;
  created_at: string;
  updated_at: string;
}

export interface BeatBoard {
  project_id: string;
  status: BeatBoardStatus;
  beats: BeatCard[];
  updated_at: string | null;
}

export interface StyleAnchor {
  id: string;
  project_id: string;
  content: string;
  updated_at: string;
}

export interface PromptPackageSequence {
  sequence_id: string;
  order: number;
  absolute_order: number;
  title: string;
  target_duration_s: number;
  narrative_text: string;
  camera_direction: string;
  action_direction: string;
  wan_prompt_text: string;
  uploaded_video_asset: MediaAsset | null;
}

export interface PromptPackageScene {
  scene_id: string;
  order: number;
  title: string;
  target_duration_s: number;
  narrative_text: string;
  first_image_prompt_text: string;
  first_image_asset: MediaAsset | null;
  sequences: PromptPackageSequence[];
}

export interface PromptPackage {
  project_id: string;
  name: string;
  genre: string;
  tone: string;
  target_duration_s: number;
  style_anchor_text: string;
  prompt_package_status: string;
  scenes: PromptPackageScene[];
  created_at: string;
  updated_at: string;
}

export interface ComfySceneExtractProject {
  id: string;
  name: string;
}

export interface ComfySceneExtractScene {
  id: string;
  order: number;
  title: string;
  target_duration_s: number;
}

export interface ComfySceneExtractBlock {
  start_order: number;
  end_order: number;
}

export interface ComfySceneExtractPrompts {
  first_image_prompt: string;
  sequence_1_wan_prompt: string;
  sequence_2_wan_prompt: string;
  sequence_3_wan_prompt: string;
}

export interface ComfySceneExtractSequence {
  id: string;
  order: number;
  title: string;
  wan_prompt_text: string;
}

export interface ComfySceneExtract {
  format: string;
  project: ComfySceneExtractProject;
  scene: ComfySceneExtractScene;
  block: ComfySceneExtractBlock;
  prompts: ComfySceneExtractPrompts;
  sequences: ComfySceneExtractSequence[];
}

export interface Job {
  id: string;
  project_id: string;
  scene_id: string | null;
  job_type: JobType;
  status: JobStatus;
  progress: number;
  payload: Record<string, unknown>;
  result: Record<string, unknown>;
  error_text: string | null;
  cancel_requested: boolean;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface ProjectCharacter {
  id: string;
  project_id: string;
  name: string;
  role_summary: string;
  prompt_tags: string;
  order_index: number;
  portrait_image_url: string | null;
  cowboyshot_image_url: string | null;
  fullbody_image_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface CharacterCreateRequest {
  name: string;
  role_summary?: string;
  prompt_tags?: string;
  order_index?: number;
}

export interface CharacterUpdateRequest {
  name?: string;
  role_summary?: string;
  prompt_tags?: string;
  order_index?: number;
  portrait_image_url?: string | null;
  cowboyshot_image_url?: string | null;
  fullbody_image_url?: string | null;
}

export interface CharacterImageGenerateRequest {
  shot_type: "portrait" | "cowboyshot" | "fullbody";
}

export interface CharacterGenerateRequest {
  overwrite_existing: boolean;
}

export interface ProjectListItem {
  id: string;
  name: string;
  target_duration_s: number;
  genre: string;
  tone: string;
  scene_count: number;
  workflow_version: number;
  upgrade_available: boolean;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Project {
  id: string;
  name: string;
  scenario_text: string;
  genre: string;
  tone: string;
  target_duration_s: number;
  output_width: number;
  output_height: number;
  output_fps: number;
  aspect_ratio: string;
  workflow_version: number;
  upgrade_available: boolean;
  legacy_sequence_count: number;
  beat_board_status: BeatBoardStatus;
  style_anchor: StyleAnchor | null;
  model_settings_override: ProjectModelSettingsOverride | null;
  prompt_package_status: string;
  hardware_profile: HardwareProfile;
  characters: ProjectCharacter[];
  beat_board: BeatBoard | null;
  scenes: Scene[];
  recent_jobs: Job[];
  exports: ExportAsset[];
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreateRequest {
  name: string;
  scenario_text: string;
  genre: string;
  tone: string;
  target_duration_s: number;
  output_width: number;
  output_height: number;
  output_fps: number;
  aspect_ratio: string;
}

export interface ProjectUpdateRequest {
  name?: string;
  scenario_text?: string;
  genre?: string;
  tone?: string;
  target_duration_s?: number;
  output_width?: number;
  output_height?: number;
  output_fps?: number;
  aspect_ratio?: string;
  style_anchor_text?: string;
}

export interface SceneUpdateRequest {
  order?: number;
  title?: string;
  target_duration_s?: number;
  narrative_text?: string;
  duration_locked?: boolean;
  first_image_prompt_text?: string;
}

export interface CreateBeatRequest {
  act_index: number;
  title: string;
  summary_text: string;
  purpose_text: string;
  source?: string;
}

export interface BeatUpdateRequest {
  act_index?: number;
  order_index?: number;
  title?: string;
  summary_text?: string;
  purpose_text?: string;
  source?: string;
}

export interface BeatBoardReorderItem {
  beat_id: string;
  act_index: number;
  order_index: number;
}

export interface SequenceBatchUpdateRequest {
  sequence_ids: string[];
  camera_direction?: string;
  camera_direction_mode?: SequenceBatchTextMode;
  action_direction?: string;
  action_direction_mode?: SequenceBatchTextMode;
  include_in_assembly?: boolean;
}

export interface SequenceUpdateRequest {
  order?: number;
  title?: string;
  target_duration_s?: number;
  narrative_text?: string;
  duration_locked?: boolean;
  camera_direction?: string;
  action_direction?: string;
}

export type ProjectScope = "active" | "archived" | "all";

export interface AssemblyUpdateRequest {
  trim_in_ms?: number;
  trim_out_ms?: number;
  include_in_assembly?: boolean;
}

export interface ScenarioAssistantRequest {
  focus: string;
  instruction: string;
  rewrite_scenario: boolean;
  max_suggestions: number;
}

export interface ScenarioAssistantResponse {
  source: string;
  provider: string;
  model: string;
  focus: string;
  instruction: string;
  summary: string;
  revised_scenario_text: string;
  suggestions: string[];
  beat_notes: string[];
  title_options: string[];
}

export interface ModelRuntimeSettings {
  provider: "ollama" | "openai_compatible" | "koboldcpp";
  base_url: string;
  default_model: string;
  api_key: string;
  timeout_s: number;
}

export interface GenerationDefaults {
  temperature: number;
  top_p: number;
  top_k: number;
  min_p: number;
  repeat_penalty: number;
  max_output_tokens: number;
  seed: number | null;
  stop_sequences: string[];
  json_retries: number;
  strip_markdown_fences: boolean;
  fallback_to_heuristics: boolean;
}

export interface GenerationDefaultsOverride {
  temperature: number | null;
  top_p: number | null;
  top_k: number | null;
  min_p: number | null;
  repeat_penalty: number | null;
  max_output_tokens: number | null;
  seed: number | null;
  stop_sequences: string[] | null;
  json_retries: number | null;
  strip_markdown_fences: boolean | null;
  fallback_to_heuristics: boolean | null;
}

export interface TaskPromptProfile {
  model_override: string | null;
  temperature_override: number | null;
  top_p_override: number | null;
  max_output_tokens_override: number | null;
  system_template: string;
  user_template: string;
}

export interface TaskPromptProfileOverride {
  model_override: string | null;
  temperature_override: number | null;
  top_p_override: number | null;
  max_output_tokens_override: number | null;
  system_template: string | null;
  user_template: string | null;
}

export interface TaskPromptCatalogItem {
  id: PromptTask;
  label: string;
  variables: string[];
}

export interface ModelSettingsDefaults {
  runtime: ModelRuntimeSettings;
  generation_defaults: GenerationDefaults;
  task_profiles: Record<PromptTask, TaskPromptProfile>;
}

export interface ModelSettings {
  runtime: ModelRuntimeSettings;
  generation_defaults: GenerationDefaults;
  task_profiles: Record<PromptTask, TaskPromptProfile>;
  defaults: ModelSettingsDefaults;
  task_catalog: TaskPromptCatalogItem[];
}

export interface ProjectModelSettingsOverride {
  enabled: boolean;
  default_model_override: string | null;
  generation_defaults_override: GenerationDefaultsOverride;
  task_profiles: Record<PromptTask, TaskPromptProfileOverride>;
}

export interface PromptPreviewRequest {
  task: PromptTask;
  project_id?: string;
  scene_id?: string;
  sequence_id?: string;
  focus: string;
  instruction: string;
  rewrite_scenario: boolean;
  max_suggestions: number;
  run_model: boolean;
}

export interface PromptPreviewResponse {
  task: PromptTask;
  system_prompt: string;
  user_prompt: string;
  rendered_variables: Record<string, string>;
  provider: string;
  effective_model: string;
  effective_parameters: Record<string, unknown>;
  output_text: string | null;
  error_text: string | null;
}

export interface AssistantConnectionTest {
  ok: boolean;
  ready: boolean;
  status: string;
  message: string;
  provider: string;
  base_url: string;
  resolved_base_url: string | null;
  model: string;
  available_models: string[];
  response_ms: number | null;
  capabilities: {
    text: boolean;
    json: boolean;
    vision: boolean;
  };
  vision_message: string | null;
}

export interface ImageGenerationSettings {
  enabled: boolean;
  provider: "mock" | "diffusers" | "comfyui";
  checkpoint_root: string;
  default_model: string;
  comfy_endpoint: string;
  comfy_workflow_json: string;
  comfy_timeout_s: number;
  vae_path: string;
  lora_dir: string;
  device: string;
  dtype: string;
  sampler: string;
  scheduler: string;
  steps: number;
  cfg_scale: number;
  width: number;
  height: number;
  seed_mode: "random" | "fixed";
  seed: number | null;
  default_negative_prompt: string;
  variant_count: number;
}

export interface VideoGenerationSettings {
  enabled: boolean;
  provider: "mock" | "lightx2v" | "wan_gguf";
  model_root: string;
  model_class: string;
  encoder_root: string;
  vae_root: string;
  gguf_model_path?: string;
  lora_path?: string;
  lora_scale?: number;
  quantization_preset: string;
  attention_mode: string;
  infer_steps: number;
  native_height: number;
  native_width: number;
  native_frame_count: number;
  guidance_scale: number;
  sample_shift: number;
  cpu_offload: boolean;
  text_encoder_offload: boolean;
  image_encoder_offload: boolean;
  vae_offload: boolean;
  retime_mode: "none" | "fit_duration" | "frame_interpolate_fit";
  target_output_fps: number;
  seed_mode: "random" | "fixed";
  seed: number | null;
}

export interface MediaGenerationSettings {
  image: ImageGenerationSettings;
  video: VideoGenerationSettings;
}

export interface MediaGenerationModelOption {
  label: string;
  value: string;
  kind: "file" | "directory";
  absolute_path: string;
  size_bytes: number | null;
}

export interface ImageModelInventory {
  root_path: string;
  default_model: string;
  models: MediaGenerationModelOption[];
}

export interface ImageModelUploadResponse {
  uploaded_model: MediaGenerationModelOption;
  inventory: ImageModelInventory;
  settings: MediaGenerationSettings;
}

export interface MediaGenerationProviderTestResult {
  ok: boolean;
  ready: boolean;
  status: string;
  message: string;
  provider: string;
  resolved_paths: Record<string, string>;
  warnings: string[];
}

export interface MediaGenerationSettingsTestResponse {
  image: MediaGenerationProviderTestResult;
  video: MediaGenerationProviderTestResult;
}

export interface MediaModelDownloadRequest {
  target: "image" | "video";
  repo_id: string;
  revision: string;
  filename: string;
  include_patterns: string[];
  ignore_patterns: string[];
  destination_name: string;
  token: string;
  apply_to_settings: boolean;
}

export interface MediaModelDownloadStatus {
  id: string;
  target: "image" | "video";
  status: "queued" | "running" | "succeeded" | "failed";
  progress: number;
  repo_id: string;
  revision: string;
  destination_path: string;
  downloaded_path: string | null;
  applied_to_settings: boolean;
  message: string;
  error_text: string | null;
  created_at: string;
  updated_at: string;
}

export interface SceneImageGenerationRequest {
  model_name?: string;
  variant_count?: number;
  auto_approve?: boolean;
  steps?: number;
  cfg_scale?: number;
  sampler?: string;
  scheduler?: string;
  width?: number;
  height?: number;
  seed_mode?: "random" | "fixed";
  seed?: number | null;
}
