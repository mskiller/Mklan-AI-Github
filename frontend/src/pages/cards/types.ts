export type ProjectScope = "active" | "archived" | "all";
export type ProjectMode = "game_master" | "character";
export type MessageRole = "system" | "user" | "assistant";
export type LoreEntryPosition = "before_char" | "after_char" | "before_examples" | "after_examples";

export type GenerationStatus = "queued" | "running" | "succeeded" | "failed";
export type GenerationTask =
  | "scenario_generation"
  | "character_card_generation"
  | "lore_generation"
  | "user_profile_generation"
  | "game_master_card_generation"
  | "image_prompt_generation";

export type ImageShotFormat = "portrait" | "cowboy_shot" | "fullbody_shot";

export interface GenerationRun {
  id: string;
  project_id: string;
  task_type: GenerationTask;
  status: GenerationStatus;
  progress: number;
  error_text: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface Character {
  id: string;
  project_id: string;
  name: string;
  description: string;
  personality: string;
  scenario: string;
  first_message: string;
  example_dialogue: string;
  tags: string[];
  creator_notes: string;
  system_prompt: string;
  post_history_instructions: string;
  alternate_greetings: string[];
  creator: string;
  character_version: string;
  character_note: string;
  character_note_depth: number;
  character_note_role: MessageRole;
  talkativeness: number | null;
  appearance_summary: string;
  booru_character_name: string;
  booru_copyright: string;
  avatar_url: string | null;
  portrait_url: string | null;
  cowboy_shot_url: string | null;
  fullbody_shot_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface LoreEntry {
  id: string;
  project_id: string;
  name: string;
  keys: string[];
  secondary_keys: string[];
  content: string;
  comment: string;
  enabled: boolean;
  insertion_order: number;
  position: LoreEntryPosition;
  constant: boolean;
  selective_logic: number;
  probability: number;
  case_sensitive: boolean;
  priority: number;
  scan_depth: number | null;
  match_whole_words: boolean | null;
  group: string;
  group_weight: number;
  prevent_recursion: boolean;
  delay_until_recursion: boolean;
  character_filter_json: string;
  automation_id: string;
  role: MessageRole;
  extensions_json: string;
  image_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface UserProfile {
  project_id: string;
  name: string;
  description: string;
  title: string;
  personality: string;
  scenario_role: string;
  first_message: string;
  tags: string[];
  persona_note: string;
  persona_note_depth: number;
  persona_note_role: MessageRole;
  appearance_summary: string;
  booru_character_name: string;
  booru_copyright: string;
  avatar_url: string | null;
  portrait_url: string | null;
  cowboy_shot_url: string | null;
  fullbody_shot_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectListItem {
  id: string;
  name: string;
  seed_sentence: string;
  project_mode: ProjectMode;
  sample_character_target_count: number;
  archived_at: string | null;
  character_count: number;
  lore_count: number;
  created_at: string;
  updated_at: string;
}

export interface GMCardProfile {
  name: string;
  description: string;
  personality: string;
  scenario: string;
  first_message: string;
  example_dialogue: string;
  tags: string[];
  creator_notes: string;
  system_prompt: string;
  post_history_instructions: string;
  alternate_greetings: string[];
  creator: string;
  character_version: string;
  character_note: string;
  character_note_depth: number;
  character_note_role: MessageRole;
  talkativeness: number | null;
}

export interface Project {
  id: string;
  name: string;
  seed_sentence: string;
  scenario_text: string;
  scenario_world_image_url: string | null;
  project_mode: ProjectMode;
  sample_character_target_count: number;
  lorebook_scan_depth: number;
  lorebook_token_budget: number;
  lorebook_recursive_scanning: boolean;
  genre: string;
  tone: string;
  gm_card_profile: GMCardProfile;
  characters: Character[];
  lore_entries: LoreEntry[];
  user_profile: UserProfile;
  generation_runs: GenerationRun[];
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CompatibilityIssue {
  severity: "critical" | "warning";
  code: string;
  message: string;
  target: string;
}

export interface CompatibilityReport {
  project_id: string;
  status: "ok" | "warnings" | "blocked";
  critical_count: number;
  warning_count: number;
  issues: CompatibilityIssue[];
  checked_at: string;
}

export interface ProjectCreateRequest {
  name: string;
  seed_sentence: string;
  scenario_text: string;
  project_mode: ProjectMode;
  sample_character_target_count: number;
  lorebook_scan_depth?: number;
  lorebook_token_budget?: number;
  lorebook_recursive_scanning?: boolean;
  genre: string;
  tone: string;
}

export interface ProjectUpdateRequest {
  name?: string;
  seed_sentence?: string;
  scenario_text?: string;
  project_mode?: ProjectMode;
  sample_character_target_count?: number;
  lorebook_scan_depth?: number;
  lorebook_token_budget?: number;
  lorebook_recursive_scanning?: boolean;
  genre?: string;
  tone?: string;
}

export interface CharacterCreateRequest {
  name: string;
  description: string;
  personality: string;
  scenario: string;
  first_message: string;
  example_dialogue: string;
  tags: string[];
  creator_notes: string;
  system_prompt: string;
  post_history_instructions: string;
  alternate_greetings: string[];
  creator: string;
  character_version: string;
  character_note: string;
  character_note_depth: number;
  character_note_role: MessageRole;
  talkativeness: number | null;
  appearance_summary: string;
  booru_character_name: string;
  booru_copyright: string;
}

export interface CharacterUpdateRequest {
  name?: string;
  description?: string;
  personality?: string;
  scenario?: string;
  first_message?: string;
  example_dialogue?: string;
  tags?: string[];
  creator_notes?: string;
  system_prompt?: string;
  post_history_instructions?: string;
  alternate_greetings?: string[];
  creator?: string;
  character_version?: string;
  character_note?: string;
  character_note_depth?: number;
  character_note_role?: MessageRole;
  talkativeness?: number | null;
  appearance_summary?: string;
  booru_character_name?: string;
  booru_copyright?: string;
  avatar_relative_path?: string | null;
}

export interface LoreEntryCreateRequest {
  name: string;
  keys: string[];
  secondary_keys: string[];
  content: string;
  comment: string;
  enabled: boolean;
  insertion_order: number;
  position: LoreEntryPosition;
  constant: boolean;
  selective_logic: number;
  probability: number;
  case_sensitive: boolean;
  priority: number;
  scan_depth: number | null;
  match_whole_words: boolean | null;
  group: string;
  group_weight: number;
  prevent_recursion: boolean;
  delay_until_recursion: boolean;
  character_filter_json: string;
  automation_id: string;
  role: MessageRole;
  extensions_json: string;
}

export interface LoreEntryUpdateRequest {
  name?: string;
  keys?: string[];
  secondary_keys?: string[];
  content?: string;
  comment?: string;
  enabled?: boolean;
  insertion_order?: number;
  position?: LoreEntryPosition;
  constant?: boolean;
  selective_logic?: number;
  probability?: number;
  case_sensitive?: boolean;
  priority?: number;
  scan_depth?: number | null;
  match_whole_words?: boolean | null;
  group?: string;
  group_weight?: number;
  prevent_recursion?: boolean;
  delay_until_recursion?: boolean;
  character_filter_json?: string;
  automation_id?: string;
  role?: MessageRole;
  extensions_json?: string;
}

export interface UserProfileUpdateRequest {
  name?: string;
  description?: string;
  title?: string;
  personality?: string;
  scenario_role?: string;
  first_message?: string;
  tags?: string[];
  persona_note?: string;
  persona_note_depth?: number;
  persona_note_role?: MessageRole;
  appearance_summary?: string;
  booru_character_name?: string;
  booru_copyright?: string;
  avatar_relative_path?: string | null;
}

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

export type PromptTask = GenerationTask;

export interface ModelRuntimeSettings {
  provider: "ollama" | "openai_compatible" | "koboldcpp";
  base_url: string;
  api_key: string;
  default_model: string;
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

export interface ModelSettings {
  runtime: ModelRuntimeSettings;
  generation_defaults: GenerationDefaults;
  task_profiles: Record<PromptTask, TaskPromptProfile>;
  defaults: {
    runtime: ModelRuntimeSettings;
    generation_defaults: GenerationDefaults;
    task_profiles: Record<PromptTask, TaskPromptProfile>;
  };
  task_catalog: TaskPromptCatalogItem[];
}

export interface ProjectModelSettingsOverride {
  enabled: boolean;
  default_model_override: string | null;
  generation_defaults_override: {
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
  };
  task_profiles: Record<PromptTask, TaskPromptProfileOverride>;
}

export interface PromptPreviewRequest {
  task: PromptTask;
  project_id?: string;
  character_id?: string;
  lore_entry_id?: string;
  instruction: string;
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

export interface MediaGenerationSettings {
  image: ImageGenerationSettings;
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
}

export interface SillyTavernStatus {
  enabled: boolean;
  healthy: boolean;
  public_url: string;
  internal_url: string;
  data_root: string;
  warnings: string[];
}

export interface SillyTavernSyncedFile {
  kind: string;
  path: string;
}

export interface SillyTavernSyncResponse {
  project_id: string;
  public_url: string;
  synced_files: SillyTavernSyncedFile[];
  warnings: string[];
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

export interface GeneratedImagePrompt {
  prompt: string;
  negative_prompt: string;
  style_profile: string;
  image_slot: string;
}

export interface ImageCandidate {
  id: string;
  project_id: string;
  owner_type: "scenario" | "character" | "lore" | "user";
  owner_id: string;
  image_slot: string;
  relative_path: string;
  image_url: string;
  prompt_text: string;
  negative_prompt: string;
  created_at: string;
  approved: boolean;
}
