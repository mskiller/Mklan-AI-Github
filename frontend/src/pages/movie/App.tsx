import { startTransition, useEffect, useRef, useState } from "react";

import {
  archiveProject,
  approveSceneImageVariant,
  approveSequenceVideoVariant,
  applyBeatBoardToScenario,
  batchUpdateSequences,
  comfySceneExtractUrl,
  createBeat,
  createCharacter,
  createProject,
  deleteBeat,
  deleteCharacter,
  deleteProject,
  generateBeatBoard,
  generateCharacters,
  generateCharacterImage,
  generateSceneImages,
  generateSceneImagePrompts,
  generateScenes,
  generateSceneVideoChain,
  generateSequences,
  generateSequenceVideo,
  generateWanPrompts,
  getHardware,
  getJob,
  getMediaModelDownload,
  getMediaGenerationSettings,
  getModelSettings,
  getProject,
  getProjectModelSettings,
  listImageModels,
  listProjects,
  promptPackageJsonUrl,
  promptPackageMarkdownUrl,
  reorderBeatBoard,
  restoreProject,
  runScenarioAssistant,
  startContinuityReview,
  startAssemblyExport,
  startMediaModelDownload,
  testMediaGenerationSettings,
  testModelSettingsConnection,
  testPromptPreview,
  updateCharacter,
  updateMediaGenerationSettings,
  updateBeat,
  updateModelSettings,
  updateProject,
  updateProjectModelSettings,
  updateScene,
  updateSequence,
  updateSequenceAssembly,
  updateSequenceWanPrompt,
  uploadImageModel,
  uploadSceneFirstImage,
  uploadSequenceVideo,
  upgradeProjectToV2,
} from "./api";
import type {
  AssistantConnectionTest,
  BeatBoard,
  BeatBoardReorderItem,
  BeatCard,
  BeatUpdateRequest,
  ContinuityReview,
  GenerationDefaults,
  GenerationDefaultsOverride,
  HardwareProfile,
  ImageModelInventory,
  Job,
  MediaModelDownloadStatus,
  MediaGenerationSettings,
  MediaGenerationSettingsTestResponse,
  ModelSettings,
  ProjectModelSettingsOverride,
  Project,
  ProjectCharacter,
  ProjectCreateRequest,
  ProjectListItem,
  ProjectScope,
  PromptPreviewResponse,
  PromptTask,
  CharacterUpdateRequest,
  ScenarioAssistantResponse,
  Scene,
  SequenceBatchTextMode,
  TaskPromptProfile,
  TaskPromptProfileOverride,
  Sequence,
} from "./types";

import { VideoTimeline } from "./components/VideoTimeline";

const defaultProjectForm: ProjectCreateRequest = {
  name: "New Film",
  scenario_text:
    "A disillusioned archivist finds a buried recording that points to a forgotten witness, crosses the city to verify it, and must decide whether to expose the truth before sunrise.",
  genre: "cinematic mystery drama",
  tone: "moody, elegant, and emotionally grounded",
  target_duration_s: 240,
  output_width: 1280,
  output_height: 720,
  output_fps: 24,
  aspect_ratio: "16:9",
};

const scenarioFocusOptions = [
  { id: "rewrite", label: "Rewrite" },
  { id: "structure", label: "Structure" },
  { id: "stakes", label: "Stakes" },
  { id: "character", label: "Character" },
  { id: "pacing", label: "Pacing" },
  { id: "dialogue", label: "Dialogue" },
];

type WorkspaceTab = "scenario" | "characters" | "scenes" | "images" | "sequences" | "video" | "settings";
type RuntimePreset = "ollama" | "gguf" | "koboldcpp";

type MediaDownloadTarget = "image" | "video";

interface ProjectDraft {
  name: string;
  scenario_text: string;
  genre: string;
  tone: string;
  target_duration_s: number;
  style_anchor_text: string;
}

interface SceneDraft {
  id: string;
  order: number;
  title: string;
  target_duration_s: number;
  narrative_text: string;
  duration_locked: boolean;
  first_image_prompt_text: string;
}

interface SequenceDraft {
  id: string;
  order: number;
  title: string;
  target_duration_s: number;
  narrative_text: string;
  duration_locked: boolean;
  camera_direction: string;
  action_direction: string;
  wan_prompt_text: string;
  trim_in_ms: number;
  trim_out_ms: number;
  include_in_assembly: boolean;
}

function CharacterCard({
  character,
  isProjectEditable,
  onUpdate,
  onDelete,
  onGenerateImage,
}: {
  character: ProjectCharacter;
  isProjectEditable: boolean;
  onUpdate: (characterId: string, updates: CharacterUpdateRequest) => Promise<void>;
  onDelete: (characterId: string) => Promise<void>;
  onGenerateImage: (characterId: string, shotType: "portrait" | "cowboyshot" | "fullbody") => Promise<void>;
}) {
  const [name, setName] = useState(character.name);
  const [roleSummary, setRoleSummary] = useState(character.role_summary);
  const [promptTags, setPromptTags] = useState(character.prompt_tags);

  useEffect(() => {
    setName(character.name);
    setRoleSummary(character.role_summary);
    setPromptTags(character.prompt_tags);
  }, [character]);

  const handleBlur = (field: keyof CharacterUpdateRequest) => {
    const value = field === "name" ? name : field === "role_summary" ? roleSummary : promptTags;
    if (value !== (character as any)[field]) {
      void onUpdate(character.id, { [field]: value });
    }
  };

  return (
    <div className="character-card" style={{ padding: "1.5rem", background: "var(--bg-elevated)", border: "1px solid var(--border-color)", borderRadius: "var(--radius-lg)", marginBottom: "1rem" }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 300px", gap: "2rem" }}>
        <div className="character-fields" style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <label className="field">
            <span>Name</span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onBlur={() => handleBlur("name")}
              disabled={!isProjectEditable}
              placeholder="e.g. John Doe"
            />
          </label>
          <label className="field">
            <span>Role Summary</span>
            <input
              type="text"
              value={roleSummary}
              onChange={(e) => setRoleSummary(e.target.value)}
              onBlur={() => handleBlur("role_summary")}
              disabled={!isProjectEditable}
              placeholder="e.g. The mysterious protagonist"
            />
          </label>
          <label className="field">
            <span>Visual Prompt Tags (NoobAI/Tag format)</span>
            <textarea
              rows={4}
              value={promptTags}
              onChange={(e) => setPromptTags(e.target.value)}
              onBlur={() => handleBlur("prompt_tags")}
              disabled={!isProjectEditable}
              placeholder="e.g. 1boy, brown hair, blue eyes, wearing a trench coat, moody lighting"
            />
          </label>
          <div className="action-row" style={{ marginTop: "1rem" }}>
            <button
              className="danger-button ghost-button"
              onClick={() => void onDelete(character.id)}
              disabled={!isProjectEditable}
            >
              Remove Character
            </button>
          </div>
        </div>

        <div className="character-references">
          <h4 style={{ marginBottom: "1rem", opacity: 0.8 }}>Visual References</h4>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.5rem" }}>
            {(["portrait", "cowboyshot", "fullbody"] as const).map((shot) => (
              <div key={shot} style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                <div 
                  className="image-placeholder" 
                  style={{ 
                    aspectRatio: "2/3", 
                    background: "var(--bg-deep)", 
                    borderRadius: "var(--radius-sm)", 
                    overflow: "hidden",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    border: "1px dashed var(--border-color)"
                  }}
                >
                  {character[`${shot}_image_url` as keyof ProjectCharacter] ? (
                    <img 
                      src={character[`${shot}_image_url` as keyof ProjectCharacter] as string} 
                      alt={shot} 
                      style={{ width: "100%", height: "100%", objectFit: "cover" }} 
                    />
                  ) : (
                    <span className="muted-text" style={{ fontSize: "0.7rem", textAlign: "center", padding: "0.5rem" }}>
                      No {shot}
                    </span>
                  )}
                </div>
                <button
                  className="ghost-button compact"
                  style={{ fontSize: "0.65rem", padding: "0.2rem" }}
                  onClick={() => void onGenerateImage(character.id, shot)}
                  disabled={!isProjectEditable}
                >
                  Generate {shot === "cowboyshot" ? "Cowboy" : shot === "fullbody" ? "Full Body" : "Portrait"}
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}


interface MediaDownloadDraft {
  repo_id: string;
  revision: string;
  filename: string;
  include_patterns: string;
  ignore_patterns: string;
  destination_name: string;
  token: string;
}

interface SceneImageGenerationDraft {
  model_name: string;
  variant_count: number;
  steps: number;
  cfg_scale: number;
  sampler: string;
  scheduler: string;
  width: number;
  height: number;
  resolution_preset: ImageResolutionPresetId;
  seed_mode: "random" | "fixed";
  seed: number | null;
}

interface ComfyWindow {
  startOrder: number;
  endOrder: number;
  sequences: Sequence[];
}

interface BeatDraft {
  id: string;
  act_index: number;
  order_index: number;
  title: string;
  summary_text: string;
  purpose_text: string;
  source: string;
}

type SequenceReadinessFilter =
  | "all"
  | "missing_wan"
  | "ready_external"
  | "missing_upload"
  | "ready_assembly"
  | "excluded";

type ImageResolutionPresetId =
  | "sdxl_native_square"
  | "movie_landscape"
  | "movie_portrait"
  | "story_landscape"
  | "story_portrait"
  | "custom";

const promptTaskOrder: PromptTask[] = [
  "scenario_assistant",
  "beat_board_generation",
  "character_extraction",
  "scene_generation",
  "scene_image_prompt_generation",
  "sequence_generation",
  "wan_prompt_generation",
  "continuity_review",
];

const runtimePresets: Record<RuntimePreset, ModelSettings["runtime"]> = {
  ollama: {
    provider: "ollama",
    base_url: "http://127.0.0.1:11434",
    default_model: "llama3.1:8b",
    api_key: "",
    timeout_s: 120,
  },
  koboldcpp: {
    provider: "koboldcpp",
    base_url: "http://127.0.0.1:5001/v1",
    default_model: "koboldcpp",
    api_key: "",
    timeout_s: 120,
  },
  gguf: {
    provider: "openai_compatible",
    base_url: "http://127.0.0.1:8081/v1",
    default_model: "gemma-4-e2b-it-q4_k_m",
    api_key: "",
    timeout_s: 120,
  },
};

const imageSamplerOptions = [
  { value: "lcm", label: "LCM" },
  { value: "res_multistep", label: "RES-MULTISTEP" },
  { value: "dpmpp_sde", label: "DPMPP-SDE" },
  { value: "dpmpp_2s_ancestral", label: "DPMPP-2S-ANCESTRAL" },
];

const imageSchedulerOptions = [
  { value: "simple", label: "Simple" },
  { value: "karras", label: "Karras" },
  { value: "beta", label: "Beta" },
  { value: "gits", label: "GITS" },
  { value: "kl_optimal", label: "KL-Optimal" },
];

const imageResolutionPresets: Array<{
  id: ImageResolutionPresetId;
  label: string;
  width: number;
  height: number;
  note: string;
}> = [
  {
    id: "sdxl_native_square",
    label: "SDXL Native Square",
    width: 1024,
    height: 1024,
    note: "Safest starting point for SDXL-family single-file checkpoints.",
  },
  {
    id: "movie_landscape",
    label: "Movie Landscape",
    width: 1344,
    height: 768,
    note: "Cinematic landscape framing for scene key art.",
  },
  {
    id: "movie_portrait",
    label: "Movie Portrait",
    width: 768,
    height: 1344,
    note: "Vertical poster-style framing for character-led shots.",
  },
  {
    id: "story_landscape",
    label: "Story Landscape",
    width: 1216,
    height: 832,
    note: "Balanced landscape preset when 1344x768 feels too wide.",
  },
  {
    id: "story_portrait",
    label: "Story Portrait",
    width: 832,
    height: 1216,
    note: "Balanced portrait preset with SDXL-friendly dimensions.",
  },
  {
    id: "custom",
    label: "Custom",
    width: 1024,
    height: 1024,
    note: "Use your own width and height.",
  },
];

function cloneValue<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function emptyGenerationDefaultsOverride(): GenerationDefaultsOverride {
  return {
    temperature: null,
    top_p: null,
    top_k: null,
    min_p: null,
    repeat_penalty: null,
    max_output_tokens: null,
    seed: null,
    stop_sequences: null,
    json_retries: null,
    strip_markdown_fences: null,
    fallback_to_heuristics: null,
  };
}

function emptyTaskPromptProfileOverride(): TaskPromptProfileOverride {
  return {
    model_override: null,
    temperature_override: null,
    top_p_override: null,
    max_output_tokens_override: null,
    system_template: null,
    user_template: null,
  };
}

function emptyProjectOverride(): ProjectModelSettingsOverride {
  return {
    enabled: false,
    default_model_override: null,
    generation_defaults_override: emptyGenerationDefaultsOverride(),
    task_profiles: Object.fromEntries(
      promptTaskOrder.map((task) => [task, emptyTaskPromptProfileOverride()]),
    ) as Record<PromptTask, TaskPromptProfileOverride>,
  };
}

function buildModelSettingsPayload(modelSettings: ModelSettings) {
  return {
    runtime: cloneValue(modelSettings.runtime),
    generation_defaults: cloneValue(modelSettings.generation_defaults),
    task_profiles: cloneValue(modelSettings.task_profiles),
  };
}

function splitStopSequences(value: string): string[] {
  return value
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function toOptionalString(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function toOptionalNumber(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  return Number(trimmed);
}

function projectOverrideEnabled(project: Project | null) {
  return Boolean(project?.model_settings_override?.enabled);
}

function buildComfyWindows(scene: Scene | null): ComfyWindow[] {
  if (!scene) {
    return [];
  }
  const orderedSequences = [...scene.sequences].sort((left, right) => left.order - right.order);
  const windows: ComfyWindow[] = [];
  for (let index = 0; index <= orderedSequences.length - 3; index += 1) {
    const block = orderedSequences.slice(index, index + 3);
    if (
      block.length === 3 &&
      block[1].order === block[0].order + 1 &&
      block[2].order === block[1].order + 1
    ) {
      windows.push({
        startOrder: block[0].order,
        endOrder: block[2].order,
        sequences: block,
      });
    }
  }
  return windows;
}

function groupBeatsByAct(beatBoard: BeatBoard | null) {
  const grouped = new Map<number, BeatCard[]>();
  for (let actIndex = 1; actIndex <= 3; actIndex += 1) {
    grouped.set(
      actIndex,
      [...(beatBoard?.beats ?? [])]
        .filter((beat) => beat.act_index === actIndex)
        .sort((left, right) => left.order_index - right.order_index),
    );
  }
  return grouped;
}

function sequenceMatchesFilter(sequence: Sequence, filter: SequenceReadinessFilter) {
  const approvedOrUploadedAsset = sequence.approved_video_asset ?? sequence.uploaded_video_asset;
  switch (filter) {
    case "missing_wan":
      return !sequence.wan_prompt_text.trim();
    case "ready_external":
      return Boolean(sequence.wan_prompt_text.trim()) && !approvedOrUploadedAsset;
    case "missing_upload":
      return sequence.include_in_assembly && !approvedOrUploadedAsset;
    case "ready_assembly":
      return sequence.include_in_assembly && Boolean(approvedOrUploadedAsset);
    case "excluded":
      return !sequence.include_in_assembly;
    default:
      return true;
  }
}

function sequenceVideoAsset(sequence: Sequence) {
  return sequence.approved_video_asset ?? sequence.uploaded_video_asset;
}

function defaultMediaDownloadDraft(): MediaDownloadDraft {
  return {
    repo_id: "",
    revision: "",
    filename: "",
    include_patterns: "",
    ignore_patterns: "",
    destination_name: "",
    token: "",
  };
}

function detectImageResolutionPreset(width: number, height: number): ImageResolutionPresetId {
  const matched = imageResolutionPresets.find(
    (preset) => preset.id !== "custom" && preset.width === width && preset.height === height,
  );
  return matched?.id ?? "custom";
}

function buildSceneImageGenerationDraft(imageSettings: MediaGenerationSettings["image"]): SceneImageGenerationDraft {
  return {
    model_name: imageSettings.default_model,
    variant_count: imageSettings.variant_count,
    steps: imageSettings.steps,
    cfg_scale: imageSettings.cfg_scale,
    sampler: imageSettings.sampler,
    scheduler: imageSettings.scheduler,
    width: imageSettings.width,
    height: imageSettings.height,
    resolution_preset: detectImageResolutionPreset(imageSettings.width, imageSettings.height),
    seed_mode: imageSettings.seed_mode,
    seed: imageSettings.seed,
  };
}

function applyImageResolutionPresetToDraft(
  draft: SceneImageGenerationDraft,
  presetId: ImageResolutionPresetId,
): SceneImageGenerationDraft {
  const preset = imageResolutionPresets.find((item) => item.id === presetId);
  if (!preset || preset.id === "custom") {
    return {
      ...draft,
      resolution_preset: "custom",
    };
  }
  return {
    ...draft,
    width: preset.width,
    height: preset.height,
    resolution_preset: preset.id,
  };
}

function parsePatternList(value: string) {
  return value
    .split(/[\r\n,;]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function appendPromptSuggestion(currentPrompt: string, suggestion: string) {
  const current = currentPrompt.trim();
  const next = suggestion.trim();
  if (!current) {
    return next;
  }
  if (!next) {
    return current;
  }
  return `${current}\n\n${next}`;
}

function App() {
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [projectScope, setProjectScope] = useState<ProjectScope>("active");
  const [hardware, setHardware] = useState<HardwareProfile | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [projectForm, setProjectForm] = useState<ProjectCreateRequest>(defaultProjectForm);
  const [projectDraft, setProjectDraft] = useState<ProjectDraft | null>(null);
  const [projectDirty, setProjectDirty] = useState(false);
  const [beatBoardDraft, setBeatBoardDraft] = useState<BeatBoard | null>(null);
  const [beatBoardLoading, setBeatBoardLoading] = useState(false);
  const [selectedSceneId, setSelectedSceneId] = useState<string | null>(null);
  const [selectedSequenceId, setSelectedSequenceId] = useState<string | null>(null);
  const [selectedSequenceIds, setSelectedSequenceIds] = useState<string[]>([]);
  const [sequenceFilter, setSequenceFilter] = useState<SequenceReadinessFilter>("all");
  const [batchCameraDirection, setBatchCameraDirection] = useState("");
  const [batchCameraMode, setBatchCameraMode] = useState<SequenceBatchTextMode>("set");
  const [batchActionDirection, setBatchActionDirection] = useState("");
  const [batchActionMode, setBatchActionMode] = useState<SequenceBatchTextMode>("set");
  const [batchIncludeChoice, setBatchIncludeChoice] = useState<"" | "include" | "exclude">("");
  const [sceneDraft, setSceneDraft] = useState<SceneDraft | null>(null);
  const [sceneDirty, setSceneDirty] = useState(false);
  const [sequenceDraft, setSequenceDraft] = useState<SequenceDraft | null>(null);
  const [sequenceDirty, setSequenceDirty] = useState(false);
  const [comfyStartOrder, setComfyStartOrder] = useState<number | null>(null);
  const [activeJob, setActiveJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string>("Movie scripting studio ready.");
  const [loading, setLoading] = useState(false);
  const [workspaceTab, setWorkspaceTab] = useState<WorkspaceTab>("scenario");
  const [assistantFocus, setAssistantFocus] = useState("rewrite");
  const [assistantInstruction, setAssistantInstruction] = useState("");
  const [assistantRewriteScenario, setAssistantRewriteScenario] = useState(true);
  const [assistantLoading, setAssistantLoading] = useState(false);
  const [assistantResult, setAssistantResult] = useState<ScenarioAssistantResponse | null>(null);
  const [modelSettingsDraft, setModelSettingsDraft] = useState<ModelSettings | null>(null);
  const [modelSettingsLoading, setModelSettingsLoading] = useState(false);
  const [mediaGenerationSettingsDraft, setMediaGenerationSettingsDraft] = useState<MediaGenerationSettings | null>(null);
  const [imageModelInventory, setImageModelInventory] = useState<ImageModelInventory | null>(null);
  const [imageModelUploadName, setImageModelUploadName] = useState("");
  const [imageModelUploadBusy, setImageModelUploadBusy] = useState(false);
  const [sceneImageGenerationDraft, setSceneImageGenerationDraft] = useState<SceneImageGenerationDraft | null>(null);
  const [mediaGenerationSettingsLoading, setMediaGenerationSettingsLoading] = useState(false);
  const [mediaGenerationTestResult, setMediaGenerationTestResult] =
    useState<MediaGenerationSettingsTestResponse | null>(null);
  const [mediaDownloadDrafts, setMediaDownloadDrafts] = useState<Record<MediaDownloadTarget, MediaDownloadDraft>>({
    image: defaultMediaDownloadDraft(),
    video: defaultMediaDownloadDraft(),
  });
  const [mediaDownloadStatuses, setMediaDownloadStatuses] = useState<
    Record<MediaDownloadTarget, MediaModelDownloadStatus | null>
  >({
    image: null,
    video: null,
  });
  const [assistantConnectionTestResult, setAssistantConnectionTestResult] = useState<AssistantConnectionTest | null>(null);
  const [autoApproveSceneImages, setAutoApproveSceneImages] = useState(false);
  const [autoApproveSequenceVideos, setAutoApproveSequenceVideos] = useState(false);
  const [projectModelSettingsOverrideDraft, setProjectModelSettingsOverrideDraft] =
    useState<ProjectModelSettingsOverride | null>(null);
  const [projectModelSettingsLoading, setProjectModelSettingsLoading] = useState(false);
  const [settingsTask, setSettingsTask] = useState<PromptTask>("scenario_assistant");
  const [overrideTask, setOverrideTask] = useState<PromptTask>("scenario_assistant");
  const [previewTask, setPreviewTask] = useState<PromptTask>("scenario_assistant");
  const [promptPreviewRunModel, setPromptPreviewRunModel] = useState(false);
  const [promptPreviewLoading, setPromptPreviewLoading] = useState(false);
  const [promptPreviewResult, setPromptPreviewResult] = useState<PromptPreviewResponse | null>(null);

  const projectAutosaveRef = useRef<number | null>(null);
  const sceneAutosaveRef = useRef<number | null>(null);
  const sequenceAutosaveRef = useRef<number | null>(null);

  const scenes = project?.scenes ?? [];
  const beatBoard = beatBoardDraft ?? project?.beat_board ?? null;
  const beatsByAct = groupBeatsByAct(beatBoard);
  const selectedScene = scenes.find((scene) => scene.id === selectedSceneId) ?? null;
  const sequences = selectedScene?.sequences ?? [];
  const filteredSequences = sequences.filter((sequence) => sequenceMatchesFilter(sequence, sequenceFilter));
  const comfyWindows = buildComfyWindows(selectedScene);
  const comfyWindowKey = comfyWindows.map((window) => String(window.startOrder)).join(",");
  const selectedComfyWindow =
    comfyWindows.find((window) => window.startOrder === comfyStartOrder) ?? comfyWindows[0] ?? null;
  const selectedSequence = sequences.find((sequence) => sequence.id === selectedSequenceId) ?? null;
  const selectedImageResolutionPreset = imageResolutionPresets.find(
    (preset) => preset.id === (sceneImageGenerationDraft?.resolution_preset ?? "custom"),
  );
  const imageModelOptions = imageModelInventory?.models ?? [];
  const totalSceneDuration = scenes.reduce((sum, scene) => sum + scene.target_duration_s, 0);
  const totalSequenceCount = scenes.reduce((sum, scene) => sum + scene.sequences.length, 0);
  const selectedSceneSequenceDuration = sequences.reduce((sum, sequence) => sum + sequence.target_duration_s, 0);
  const includedSequences = scenes.flatMap((scene) => scene.sequences).filter((sequence) => sequence.include_in_assembly);
  const uploadedIncludedSequences = includedSequences.filter((sequence) => sequenceVideoAsset(sequence)).length;
  const generatedSceneImageCount = scenes.filter((scene) => scene.generated_image_variants.length > 0).length;
  const approvedSceneImageCount = scenes.filter((scene) => scene.first_image_asset).length;
  const approvedSequenceVideoCount = scenes
    .flatMap((scene) => scene.sequences)
    .filter((sequence) => sequenceVideoAsset(sequence)).length;
  const isArchivedProject = Boolean(project?.archived_at);
  const isProjectEditable = Boolean(project && !isArchivedProject);
  const selectedSceneHasSequences = Boolean(selectedScene && selectedScene.sequences.length > 0);
  const selectedSceneHasContinuityReview = Boolean(selectedScene?.continuity_review);
  const selectedSceneMissingWanOrders = selectedScene
    ? selectedScene.sequences
        .filter((sequence) => !sequence.wan_prompt_text.trim())
        .map((sequence) => sequence.order)
    : [];
  const selectedSequenceSet = new Set(selectedSequenceIds);
  const selectedSequenceCount = selectedSequenceIds.length;
  const availableTasks =
    modelSettingsDraft?.task_catalog ??
    promptTaskOrder.map((task) => ({
      id: task,
      label: task.replace(/_/g, " "),
      variables: [],
    }));
  const activeTaskProfile = modelSettingsDraft?.task_profiles[settingsTask] ?? null;
  const activeTaskCatalog = modelSettingsDraft?.task_catalog.find((item) => item.id === settingsTask) ?? null;
  const activeProjectOverrideTask = projectModelSettingsOverrideDraft?.task_profiles[overrideTask] ?? null;
  const comfyDisabledReason = !selectedScene
    ? "Select a scene to export a Comfy block."
    : !selectedScene.first_image_prompt_text.trim()
      ? "Generate or enter a first-image prompt before exporting."
      : comfyWindows.length === 0
        ? "This scene needs at least 3 consecutive sequences."
        : !selectedComfyWindow
          ? "Choose a 3-sequence block to export."
          : selectedComfyWindow.sequences.some((sequence) => !sequence.wan_prompt_text.trim())
            ? "Every selected sequence needs a Wan 2.2 prompt before export."
            : null;
  const selectedSceneImageDisabledReason = !selectedScene
    ? "Select a scene first."
    : !selectedScene.first_image_prompt_text.trim()
      ? "Generate or enter a first-image prompt before starting image generation."
      : null;
  const selectedSceneWanDisabledReason = !selectedScene
    ? "Select a scene first."
    : !selectedSceneHasSequences
      ? "Generate sequences before refreshing this scene's Wan prompts."
      : null;
  const selectedSequenceVideoDisabledReason = !selectedSequence
    ? "Select a sequence first."
    : !selectedSequence.wan_prompt_text.trim()
      ? "Generate or enter a Wan prompt before starting video generation."
      : !selectedSequence.input_frame_asset
        ? "Approve a scene image or regenerate the upstream sequence first so this shot has an input frame."
        : null;
  const selectedSceneChainDisabledReason = !selectedScene
    ? "Select a scene first."
    : !selectedScene.sequences.length
      ? "Generate sequences before starting a scene video chain."
      : !selectedScene.first_image_asset
        ? "Approve or upload a scene reference image before generating the scene chain."
        : selectedSceneMissingWanOrders.length > 0
          ? `Generate or enter Wan prompts for sequence order(s): ${selectedSceneMissingWanOrders.join(", ")}.`
          : null;

  useEffect(() => {
    void bootstrap();
  }, []);

  useEffect(() => {
    void refreshProjectList(projectScope, project?.id ?? null);
  }, [projectScope]);

  useEffect(() => {
    if (!project) {
      setProjectDraft(null);
      setBeatBoardDraft(null);
      setProjectModelSettingsOverrideDraft(null);
      return;
    }
    if (!projectDirty) {
      setProjectDraft({
        name: project.name,
        scenario_text: project.scenario_text,
        genre: project.genre,
        tone: project.tone,
        target_duration_s: project.target_duration_s,
        style_anchor_text: project.style_anchor?.content ?? "",
      });
    }
    setBeatBoardDraft(cloneValue(project.beat_board));
    setProjectModelSettingsOverrideDraft(cloneValue(project.model_settings_override ?? emptyProjectOverride()));
    if (!selectedSceneId || !project.scenes.some((scene) => scene.id === selectedSceneId)) {
      setSelectedSceneId(project.scenes[0]?.id ?? null);
    }
  }, [project, projectDirty, selectedSceneId]);

  useEffect(() => {
    if (!selectedScene) {
      setSceneDraft(null);
      setSelectedSequenceId(null);
      setSelectedSequenceIds([]);
      return;
    }
    if (!sceneDirty) {
      setSceneDraft({
        id: selectedScene.id,
        order: selectedScene.order,
        title: selectedScene.title,
        target_duration_s: selectedScene.target_duration_s,
        narrative_text: selectedScene.narrative_text,
        duration_locked: selectedScene.duration_locked,
        first_image_prompt_text: selectedScene.first_image_prompt_text,
      });
    }
    if (!selectedSequenceId || !selectedScene.sequences.some((sequence) => sequence.id === selectedSequenceId)) {
      setSelectedSequenceId(selectedScene.sequences[0]?.id ?? null);
    }
    setSelectedSequenceIds((current) => current.filter((sequenceId) => selectedScene.sequences.some((sequence) => sequence.id === sequenceId)));
  }, [selectedScene, sceneDirty, selectedSequenceId]);

  useEffect(() => {
    if (!selectedSequence) {
      setSequenceDraft(null);
      return;
    }
    if (sequenceDirty) {
      return;
    }
    setSequenceDraft({
      id: selectedSequence.id,
      order: selectedSequence.order,
      title: selectedSequence.title,
      target_duration_s: selectedSequence.target_duration_s,
      narrative_text: selectedSequence.narrative_text,
      duration_locked: selectedSequence.duration_locked,
      camera_direction: selectedSequence.camera_direction,
      action_direction: selectedSequence.action_direction,
      wan_prompt_text: selectedSequence.wan_prompt_text,
      trim_in_ms: selectedSequence.trim_in_ms,
      trim_out_ms: selectedSequence.trim_out_ms,
      include_in_assembly: selectedSequence.include_in_assembly,
    });
  }, [selectedSequence, sequenceDirty]);

  useEffect(() => {
    if (comfyWindows.length === 0) {
      if (comfyStartOrder !== null) {
        setComfyStartOrder(null);
      }
      return;
    }
    if (comfyStartOrder === null || !comfyWindows.some((window) => window.startOrder === comfyStartOrder)) {
      setComfyStartOrder(comfyWindows[0].startOrder);
    }
  }, [selectedScene?.id, comfyStartOrder, comfyWindowKey]);

  useEffect(() => {
    if (!projectDirty || !project || !projectDraft) {
      return;
    }
    if (projectAutosaveRef.current !== null) {
      window.clearTimeout(projectAutosaveRef.current);
    }
    projectAutosaveRef.current = window.setTimeout(() => {
      void persistProjectDraft(projectDraft);
    }, 700);

    return () => {
      if (projectAutosaveRef.current !== null) {
        window.clearTimeout(projectAutosaveRef.current);
      }
    };
  }, [projectDirty, projectDraft, project?.id]);

  useEffect(() => {
    if (!sceneDirty || !sceneDraft) {
      return;
    }
    if (sceneAutosaveRef.current !== null) {
      window.clearTimeout(sceneAutosaveRef.current);
    }
    sceneAutosaveRef.current = window.setTimeout(() => {
      void persistSceneDraft(sceneDraft);
    }, 700);

    return () => {
      if (sceneAutosaveRef.current !== null) {
        window.clearTimeout(sceneAutosaveRef.current);
      }
    };
  }, [sceneDirty, sceneDraft]);

  useEffect(() => {
    if (!sequenceDirty || !sequenceDraft) {
      return;
    }
    if (sequenceAutosaveRef.current !== null) {
      window.clearTimeout(sequenceAutosaveRef.current);
    }
    sequenceAutosaveRef.current = window.setTimeout(() => {
      void persistSequenceDraft(sequenceDraft);
    }, 700);

    return () => {
      if (sequenceAutosaveRef.current !== null) {
        window.clearTimeout(sequenceAutosaveRef.current);
      }
    };
  }, [sequenceDirty, sequenceDraft]);

  useEffect(() => {
    if (!activeJob || !project) {
      return;
    }
    if (["succeeded", "failed", "canceled"].includes(activeJob.status)) {
      return;
    }

    const interval = window.setInterval(() => {
      void refreshJob(activeJob.id, project.id);
    }, 1200);

    return () => {
      window.clearInterval(interval);
    };
  }, [activeJob?.id, activeJob?.status, project?.id]);

  useEffect(() => {
    const activeDownloads = (Object.entries(mediaDownloadStatuses) as Array<
      [MediaDownloadTarget, MediaModelDownloadStatus | null]
    >).filter(([, status]) => status && !["succeeded", "failed"].includes(status.status));
    if (!activeDownloads.length) {
      return;
    }

    const interval = window.setInterval(() => {
      activeDownloads.forEach(([target, status]) => {
        if (status) {
          void refreshMediaModelDownloadStatus(target, status.id, false);
        }
      });
    }, 1500);

    return () => {
      window.clearInterval(interval);
    };
  }, [mediaDownloadStatuses.image?.id, mediaDownloadStatuses.image?.status, mediaDownloadStatuses.video?.id, mediaDownloadStatuses.video?.status]);

  async function bootstrap() {
    try {
      setLoading(true);
      const [projectList, hardwareProfile, savedModelSettings, savedMediaSettings, savedImageModels] = await Promise.all([
        listProjects(projectScope),
        getHardware(),
        getModelSettings(),
        getMediaGenerationSettings(),
        listImageModels(),
      ]);
      setProjects(projectList);
      setHardware(hardwareProfile);
      setModelSettingsDraft(savedModelSettings);
      setMediaGenerationSettingsDraft(savedMediaSettings);
      setImageModelInventory(savedImageModels);
      setSceneImageGenerationDraft(buildSceneImageGenerationDraft(savedMediaSettings.image));
      if (projectList.length > 0) {
        await loadProject(projectList[0].id);
      } else {
        setProject(null);
      }
    } catch (caughtError) {
      setError((caughtError as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function refreshImageModelInventory(announce = false) {
    try {
      const inventory = await listImageModels();
      setImageModelInventory(inventory);
      if (announce) {
        setNotice(
          inventory.models.length
            ? `Found ${inventory.models.length} local image model${inventory.models.length === 1 ? "" : "s"}.`
            : "No local image models were found in the configured checkpoint root yet.",
        );
        setError(null);
      }
      return inventory;
    } catch (caughtError) {
      if (announce) {
        setError((caughtError as Error).message);
      }
      return null;
    }
  }

  async function refreshProjectList(scope = projectScope, preferredProjectId: string | null = project?.id ?? null) {
    try {
      const projectList = await listProjects(scope);
      setProjects(projectList);
      const nextSelectedId =
        preferredProjectId && projectList.some((item) => item.id === preferredProjectId)
          ? preferredProjectId
          : projectList[0]?.id ?? null;
      if (!nextSelectedId) {
        setProject(null);
        setProjectDirty(false);
        setSceneDirty(false);
        setSequenceDirty(false);
        return;
      }
      if (project?.id !== nextSelectedId) {
        await loadProject(nextSelectedId);
      }
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function loadProject(projectId: string, preferredSceneId: string | null = null, preferredSequenceId: string | null = null) {
    const [loadedProject, loadedOverride] = await Promise.all([
      getProject(projectId),
      getProjectModelSettings(projectId),
    ]);
    setProject(loadedProject);
    setProjectDirty(false);
    setSceneDirty(false);
    setSequenceDirty(false);
    setAssistantResult(null);
    setProjectModelSettingsOverrideDraft(loadedOverride);
    upsertProjectListItem(loadedProject);
    const nextScene =
      (preferredSceneId ? loadedProject.scenes.find((scene) => scene.id === preferredSceneId) : null) ??
      loadedProject.scenes[0] ??
      null;
    const nextSequence =
      (preferredSequenceId ? nextScene?.sequences.find((sequence) => sequence.id === preferredSequenceId) : null) ??
      nextScene?.sequences[0] ??
      null;
    setSelectedSceneId(nextScene?.id ?? null);
    setSelectedSequenceId(nextSequence?.id ?? null);
  }

  function mergeScene(updatedScene: Scene) {
    setProject((currentProject) => {
      if (!currentProject) {
        return currentProject;
      }
      const nextScenes = currentProject.scenes
        .map((scene) => (scene.id === updatedScene.id ? updatedScene : scene))
        .sort((left, right) => left.order - right.order);
      return {
        ...currentProject,
        scenes: nextScenes,
        updated_at: updatedScene.updated_at,
      };
    });
  }

  function mergeSequence(updatedSequence: Sequence) {
    setProject((currentProject) => {
      if (!currentProject) {
        return currentProject;
      }
      const nextScenes = currentProject.scenes.map((scene) => {
        if (scene.id !== updatedSequence.scene_id) {
          return scene;
        }
        return {
          ...scene,
          sequences: scene.sequences
            .map((sequence) => (sequence.id === updatedSequence.id ? updatedSequence : sequence))
            .sort((left, right) => left.order - right.order),
          updated_at: updatedSequence.updated_at,
        };
      });
      return {
        ...currentProject,
        scenes: nextScenes,
        updated_at: updatedSequence.updated_at,
      };
    });
  }

  function upsertProjectListItem(sourceProject: Project) {
    setProjects((current) => {
      const nextItem = {
        id: sourceProject.id,
        name: sourceProject.name,
        genre: sourceProject.genre,
        tone: sourceProject.tone,
        target_duration_s: sourceProject.target_duration_s,
        scene_count: sourceProject.workflow_version >= 2 ? sourceProject.scenes.length : sourceProject.legacy_sequence_count,
        workflow_version: sourceProject.workflow_version,
        upgrade_available: sourceProject.upgrade_available,
        archived_at: sourceProject.archived_at,
        created_at: sourceProject.created_at,
        updated_at: sourceProject.updated_at,
      };
      const matchesScope =
        projectScope === "all" ||
        (projectScope === "active" ? !nextItem.archived_at : Boolean(nextItem.archived_at));
      const existingIndex = current.findIndex((item) => item.id === sourceProject.id);
      if (!matchesScope) {
        return current.filter((item) => item.id !== sourceProject.id);
      }
      if (existingIndex === -1) {
        return [nextItem, ...current];
      }
      return current.map((item) => (item.id === sourceProject.id ? nextItem : item));
    });
  }

  async function persistProjectDraft(snapshot = projectDraft) {
    if (!project || !snapshot || !isProjectEditable) {
      return;
    }
    try {
      const durationChanged = snapshot.target_duration_s !== project.target_duration_s;
      const savedProject = await updateProject(project.id, snapshot);
      setProjectDirty(false);
      setProject(savedProject);
      upsertProjectListItem(savedProject);
      setNotice(
        durationChanged
          ? "Movie autosaved. Scene durations were rebalanced to match the new movie runtime."
          : "Movie project autosaved.",
      );
      setError(null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function persistSceneDraft(snapshot = sceneDraft) {
    if (!snapshot || !selectedScene || !isProjectEditable) {
      return;
    }
    try {
      const durationChanged = snapshot.target_duration_s !== selectedScene.target_duration_s;
      const lockChanged = snapshot.duration_locked !== selectedScene.duration_locked;
      const orderChanged = snapshot.order !== selectedScene.order;
      const savedScene = await updateScene(snapshot.id, {
        order: snapshot.order,
        title: snapshot.title,
        target_duration_s: snapshot.target_duration_s,
        narrative_text: snapshot.narrative_text,
        duration_locked: snapshot.duration_locked,
        first_image_prompt_text: snapshot.first_image_prompt_text,
      });
      setSceneDirty(false);
      mergeScene(savedScene);
      if (project && (durationChanged || orderChanged)) {
        await loadProject(project.id, snapshot.id, selectedSequenceId);
      }
      setNotice(
        durationChanged
          ? "Scene autosaved. Movie and sequence durations were rebalanced around this scene."
          : lockChanged
            ? `Scene duration lock ${snapshot.duration_locked ? "enabled" : "disabled"}.`
            : "Scene autosaved.",
      );
      setError(null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function persistSequenceDraft(snapshot = sequenceDraft) {
    if (!snapshot || !selectedSequence || !isProjectEditable) {
      return;
    }
    try {
      const durationChanged = snapshot.target_duration_s !== selectedSequence.target_duration_s;
      const lockChanged = snapshot.duration_locked !== selectedSequence.duration_locked;
      const orderChanged = snapshot.order !== selectedSequence.order;
      await updateSequence(snapshot.id, {
        order: snapshot.order,
        title: snapshot.title,
        target_duration_s: snapshot.target_duration_s,
        narrative_text: snapshot.narrative_text,
        duration_locked: snapshot.duration_locked,
        camera_direction: snapshot.camera_direction,
        action_direction: snapshot.action_direction,
      });
      await updateSequenceWanPrompt(snapshot.id, snapshot.wan_prompt_text);
      const savedSequence = await updateSequenceAssembly(snapshot.id, {
        trim_in_ms: snapshot.trim_in_ms,
        trim_out_ms: snapshot.trim_out_ms,
        include_in_assembly: snapshot.include_in_assembly,
      });
      setSequenceDirty(false);
      mergeSequence(savedSequence);
      if (project && (durationChanged || orderChanged)) {
        await loadProject(project.id, selectedSceneId, snapshot.id);
      }
      setNotice(
        durationChanged
          ? "Sequence autosaved. Sibling sequence durations were rebalanced inside the scene."
          : lockChanged
            ? `Sequence duration lock ${snapshot.duration_locked ? "enabled" : "disabled"}.`
            : "Sequence autosaved.",
      );
      setError(null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function refreshJob(jobId: string, projectId: string) {
    try {
      const nextJob = await getJob(jobId);
      startTransition(() => {
        setActiveJob(nextJob);
      });
      if (["succeeded", "failed", "canceled"].includes(nextJob.status)) {
        await loadProject(projectId, selectedSceneId, selectedSequenceId);
        if (nextJob.status === "succeeded") {
          setNotice(
            nextJob.job_type === "continuity_review"
              ? nextJob.result.source === "local_vision"
                ? "Continuity review finished successfully with local vision."
                : "Continuity review finished with the explicit rules-only fallback."
              : nextJob.job_type === "image_generation"
                ? nextJob.result.approved_asset_id
                  ? "Scene image generation finished and the first variant was approved automatically."
                  : "Scene image generation finished. Review the variants and approve the one you want to keep."
                : nextJob.job_type === "video_generation"
                  ? Array.isArray(nextJob.result.approved_variant_ids) && nextJob.result.approved_variant_ids.length > 0
                    ? "Sequence video generation finished and approved the configured variants automatically."
                    : "Sequence video generation finished. Review the variants and approve the clip you want to keep."
                  : nextJob.job_type === "character_image_generation"
                    ? "Character profile image generation finished."
                    : "Rough-cut export finished successfully.",
          );
        }
        if (nextJob.status === "failed") {
          setError(
            nextJob.error_text ??
              (nextJob.job_type === "continuity_review"
                ? "Continuity review failed."
                : nextJob.job_type === "image_generation"
                  ? "Scene image generation failed."
                  : nextJob.job_type === "video_generation"
                    ? "Sequence video generation failed."
                    : "Assembly export failed."),
          );
        }
      }
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function handleCreateProject() {
    try {
      setLoading(true);
      const createdProject = await createProject(projectForm);
      upsertProjectListItem(createdProject);
      setProject(createdProject);
      setProjectDirty(false);
      setSceneDirty(false);
      setSequenceDirty(false);
      setAssistantResult(null);
      setSelectedSceneId(createdProject.scenes[0]?.id ?? null);
      setSelectedSequenceId(createdProject.scenes[0]?.sequences[0]?.id ?? null);
      setWorkspaceTab("scenario");
      setNotice("Movie project created.");
      setError(null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function handleUpgradeProject() {
    if (!project) {
      return;
    }
    try {
      setLoading(true);
      const upgradedProject = await upgradeProjectToV2(project.id);
      setProject(upgradedProject);
      upsertProjectListItem(upgradedProject);
      setSelectedSceneId(upgradedProject.scenes[0]?.id ?? null);
      setSelectedSequenceId(upgradedProject.scenes[0]?.sequences[0]?.id ?? null);
      setWorkspaceTab("scenes");
      setNotice("Legacy project duplicated into a 2.0 project.");
      setError(null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function handleArchiveProject() {
    if (!project || !isProjectEditable) {
      return;
    }
    try {
      await persistProjectDraft();
      await persistSceneDraft();
      await persistSequenceDraft();
      const archivedProject = await archiveProject(project.id);
      setProjectScope("archived");
      setProject(archivedProject);
      upsertProjectListItem(archivedProject);
      setNotice("Project archived. It remains available for review in the archived filter.");
      setError(null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function handleRestoreProject() {
    if (!project || isProjectEditable) {
      return;
    }
    try {
      const restoredProject = await restoreProject(project.id);
      setProjectScope("active");
      setProject(restoredProject);
      upsertProjectListItem(restoredProject);
      setNotice("Project restored and editable again.");
      setError(null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function handleDeleteProject() {
    if (!project || isProjectEditable) {
      return;
    }
    if (!window.confirm(`Permanently delete "${project.name}" and all of its uploaded assets? This cannot be undone.`)) {
      return;
    }
    try {
      const deletingId = project.id;
      await deleteProject(deletingId);
      setProjects((current) => current.filter((item) => item.id !== deletingId));
      setProject(null);
      setProjectDirty(false);
      setSceneDirty(false);
      setSequenceDirty(false);
      setSelectedSceneId(null);
      setSelectedSequenceId(null);
      setAssistantResult(null);
      setNotice("Archived project deleted permanently.");
      setError(null);
      await refreshProjectList(projectScope, null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function handleGenerateBeatBoard() {
    if (!project || !isProjectEditable) {
      return;
    }
    try {
      setBeatBoardLoading(true);
      await persistProjectDraft();
      const nextBeatBoard = await generateBeatBoard(project.id, true);
      setBeatBoardDraft(nextBeatBoard);
      await loadProject(project.id, selectedSceneId, selectedSequenceId);
      setNotice(`Generated ${nextBeatBoard.beats.length} beat-board beats across three acts.`);
      setError(null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    } finally {
      setBeatBoardLoading(false);
    }
  }

  async function handleApplyBeatBoardToScenario() {
    if (!project || !isProjectEditable) {
      return;
    }
    try {
      if (document.activeElement instanceof HTMLElement) {
        document.activeElement.blur();
      }
      const updatedProject = await applyBeatBoardToScenario(project.id);
      setProject(updatedProject);
      upsertProjectListItem(updatedProject);
      setNotice("Beat board applied back into the scenario editor.");
      setError(null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function handleCreateBeat(actIndex: number) {
    if (!project || !isProjectEditable) {
      return;
    }
    try {
      await createBeat(project.id, {
        act_index: actIndex,
        title: `Act ${actIndex} Beat`,
        summary_text: "",
        purpose_text: "",
        source: "manual",
      });
      await loadProject(project.id, selectedSceneId, selectedSequenceId);
      setNotice(`Added a new beat to Act ${actIndex}.`);
      setError(null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function handleSaveBeat(beatId: string, updates: BeatUpdateRequest) {
    if (!project || !isProjectEditable) {
      return;
    }
    try {
      await updateBeat(beatId, updates);
      await loadProject(project.id, selectedSceneId, selectedSequenceId);
      setNotice("Beat card updated.");
      setError(null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function handleDeleteBeat(beatId: string) {
    if (!project || !isProjectEditable) {
      return;
    }
    try {
      await deleteBeat(beatId);
      await loadProject(project.id, selectedSceneId, selectedSequenceId);
      setNotice("Beat removed from the board.");
      setError(null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function handleMoveBeat(beat: BeatCard, direction: "up" | "down") {
    if (!project || !beatBoard || !isProjectEditable) {
      return;
    }
    const beats = [...beatBoard.beats]
      .sort((left, right) => (left.act_index - right.act_index) || (left.order_index - right.order_index))
      .map((item) => ({ ...item }));
    const currentIndex = beats.findIndex((item) => item.id === beat.id);
    if (currentIndex === -1) {
      return;
    }
    const targetIndex = direction === "up" ? currentIndex - 1 : currentIndex + 1;
    if (targetIndex < 0 || targetIndex >= beats.length) {
      return;
    }
    const [moved] = beats.splice(currentIndex, 1);
    beats.splice(targetIndex, 0, moved);
    const reordered: BeatBoardReorderItem[] = [];
    const actCounters = new Map<number, number>([
      [1, 0],
      [2, 0],
      [3, 0],
    ]);
    for (const item of beats) {
      const nextOrder = (actCounters.get(item.act_index) ?? 0) + 1;
      actCounters.set(item.act_index, nextOrder);
      reordered.push({
        beat_id: item.id,
        act_index: item.act_index,
        order_index: nextOrder,
      });
    }
    try {
      const updatedBeatBoard = await reorderBeatBoard(project.id, reordered);
      setBeatBoardDraft(updatedBeatBoard);
      await loadProject(project.id, selectedSceneId, selectedSequenceId);
      setNotice("Beat order updated.");
      setError(null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function handleGenerateScenes(source: "scenario" | "beat_board" = "scenario") {
    if (!project || !isProjectEditable) {
      return;
    }
    try {
      if (document.activeElement instanceof HTMLElement) {
        document.activeElement.blur();
      }
      await persistProjectDraft();
      const updatedProject = await generateScenes(project.id, source);
      setProject(updatedProject);
      upsertProjectListItem(updatedProject);
      setSelectedSceneId(updatedProject.scenes[0]?.id ?? null);
      setSelectedSequenceId(updatedProject.scenes[0]?.sequences[0]?.id ?? null);
      setWorkspaceTab("scenes");
      setNotice(
        source === "beat_board"
          ? `Generated ${updatedProject.scenes.length} movie scenes from the beat board.`
          : `Generated ${updatedProject.scenes.length} movie scenes.`,
      );
      setError(null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function handleGenerateSceneImagePrompts(sceneIds?: string[]) {
    if (!project || !isProjectEditable) {
      return;
    }
    try {
      await persistProjectDraft();
      await persistSceneDraft();
      const updatedProject = await generateSceneImagePrompts(project.id, sceneIds, true);
      setProject(updatedProject);
      upsertProjectListItem(updatedProject);
      setNotice("Scene first-image prompts generated.");
      setError(null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function handleUploadSceneFirstImage(sceneId: string, file: File | null) {
    if (!project || !file || !isProjectEditable) {
      return;
    }
    try {
      const savedScene = await uploadSceneFirstImage(sceneId, file);
      mergeScene(savedScene);
      await loadProject(project.id);
      setNotice("Scene reference image uploaded.");
      setError(null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function handleGenerateSceneImages(sceneId: string) {
    if (!project || !mediaGenerationSettingsDraft || !sceneImageGenerationDraft || !isProjectEditable) {
      return;
    }
    try {
      await persistSceneDraft();
      const job = await generateSceneImages(sceneId, {
        model_name: sceneImageGenerationDraft.model_name,
        variant_count: sceneImageGenerationDraft.variant_count,
        auto_approve: autoApproveSceneImages,
        steps: sceneImageGenerationDraft.steps,
        cfg_scale: sceneImageGenerationDraft.cfg_scale,
        sampler: sceneImageGenerationDraft.sampler,
        scheduler: sceneImageGenerationDraft.scheduler,
        width: sceneImageGenerationDraft.width,
        height: sceneImageGenerationDraft.height,
        seed_mode: sceneImageGenerationDraft.seed_mode,
        seed: sceneImageGenerationDraft.seed,
      });
      setActiveJob(job);
      setWorkspaceTab("images");
      setNotice(
        autoApproveSceneImages
          ? "Scene image generation queued with auto-approve enabled."
          : "Scene image generation queued. Variants will wait for review.",
      );
      setError(null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function handleApproveSceneImage(sceneId: string, assetId: string) {
    if (!project || !isProjectEditable) {
      return;
    }
    try {
      const savedScene = await approveSceneImageVariant(sceneId, assetId);
      mergeScene(savedScene);
      await loadProject(project.id, sceneId, selectedSequenceId);
      setNotice(
        "Generated scene image approved. Downstream sequence inputs were refreshed and any generated clips in this scene may now be stale.",
      );
      setError(null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function handleGenerateSequences(sceneIds?: string[]) {
    if (!project || !isProjectEditable) {
      return;
    }
    try {
      await persistProjectDraft();
      await persistSceneDraft();
      const updatedProject = await generateSequences(project.id, sceneIds, true);
      setProject(updatedProject);
      upsertProjectListItem(updatedProject);
      const nextScene = sceneIds?.[0]
        ? updatedProject.scenes.find((scene) => scene.id === sceneIds[0]) ?? updatedProject.scenes[0]
        : updatedProject.scenes[0];
      setSelectedSceneId(nextScene?.id ?? null);
      setSelectedSequenceId(nextScene?.sequences[0]?.id ?? null);
      setWorkspaceTab("sequences");
      setNotice("Scene sequences generated.");
      setError(null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function handleGenerateWanPrompts(options?: { sceneIds?: string[]; sequenceIds?: string[] }) {
    if (!project || !isProjectEditable) {
      return;
    }
    try {
      await persistProjectDraft();
      await persistSceneDraft();
      await persistSequenceDraft();
      const updatedProject = await generateWanPrompts(project.id, {
        sceneIds: options?.sceneIds,
        sequenceIds: options?.sequenceIds,
        overwriteExisting: true,
      });
      setProject(updatedProject);
      upsertProjectListItem(updatedProject);
      setNotice(
        options?.sequenceIds?.length
          ? `Wan 2.2 prompts refreshed for ${options.sequenceIds.length} selected sequence(s).`
          : "Wan 2.2 sequence prompts generated.",
      );
      setError(null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function handleBatchUpdateSelectedSequences() {
    if (!project || !selectedScene || !isProjectEditable || selectedSequenceIds.length === 0) {
      return;
    }
    try {
      const updatedSequences = await batchUpdateSequences(selectedScene.id, {
        sequence_ids: selectedSequenceIds,
        camera_direction: batchCameraDirection || undefined,
        camera_direction_mode: batchCameraDirection ? batchCameraMode : undefined,
        action_direction: batchActionDirection || undefined,
        action_direction_mode: batchActionDirection ? batchActionMode : undefined,
        include_in_assembly:
          batchIncludeChoice === "include" ? true : batchIncludeChoice === "exclude" ? false : undefined,
      });
      if (updatedSequences.length > 0) {
        await loadProject(project.id, selectedScene.id, selectedSequenceId);
        setNotice(`Updated ${updatedSequences.length} selected sequence(s).`);
        setError(null);
      }
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function handleRunContinuityReview() {
    if (!project || !selectedScene || !isProjectEditable) {
      return;
    }
    try {
      await persistSceneDraft();
      await persistSequenceDraft();
      const job = await startContinuityReview(selectedScene.id);
      setActiveJob(job);
      setNotice(`Continuity review queued for Scene ${selectedScene.order.toString().padStart(2, "0")}.`);
      setError(null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function handleApplyContinuitySuggestion(
    sequenceId: string,
    suggestedPromptFix: string,
    mode: "replace" | "append",
  ) {
    if (!project || !isProjectEditable) {
      return;
    }
    const currentSequence =
      project.scenes.flatMap((scene) => scene.sequences).find((candidate) => candidate.id === sequenceId) ?? null;
    if (!currentSequence) {
      return;
    }
    try {
      const nextPrompt =
        mode === "replace"
          ? suggestedPromptFix.trim()
          : appendPromptSuggestion(currentSequence.wan_prompt_text, suggestedPromptFix);
      const savedSequence = await updateSequenceWanPrompt(sequenceId, nextPrompt);
      mergeSequence(savedSequence);
      if (selectedSequenceId === sequenceId) {
        setSequenceDraft((current) =>
          current
            ? {
                ...current,
                wan_prompt_text: nextPrompt,
              }
            : current,
        );
        setSequenceDirty(false);
      }
      await loadProject(project.id, savedSequence.scene_id, sequenceId);
      setNotice(
        mode === "replace"
          ? "Continuity suggestion replaced the current Wan prompt."
          : "Continuity suggestion was appended to the current Wan prompt.",
      );
      setError(null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function handleRegenerateSuggestedSequence(sequenceId: string) {
    await handleGenerateWanPrompts({ sequenceIds: [sequenceId] });
  }

  async function handleUploadSequenceVideo(sequenceId: string, file: File | null) {
    if (!project || !file || !isProjectEditable) {
      return;
    }
    try {
      const savedSequence = await uploadSequenceVideo(sequenceId, file);
      mergeSequence(savedSequence);
      await loadProject(project.id);
      setNotice(
        "Sequence video uploaded. If this shot feeds later clips, downstream generated videos may now be stale until you regenerate or replace them.",
      );
      setError(null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function handleGenerateSequenceVideo(sequenceId: string) {
    if (!project || !mediaGenerationSettingsDraft || !isProjectEditable) {
      return;
    }
    try {
      await persistSequenceDraft();
      const job = await generateSequenceVideo(sequenceId, {
        model_name: mediaGenerationSettingsDraft.video.model_class,
        auto_approve: autoApproveSequenceVideos,
        seed_mode: mediaGenerationSettingsDraft.video.seed_mode,
        seed: mediaGenerationSettingsDraft.video.seed,
      });
      setActiveJob(job);
      setWorkspaceTab("video");
      setNotice(
        autoApproveSequenceVideos
          ? "Sequence video generation queued with auto-approve enabled."
          : "Sequence video generation queued. Review the generated variant before approving it.",
      );
      setError(null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function handleGenerateSceneVideoChain(sceneId: string) {
    if (!project || !mediaGenerationSettingsDraft || !isProjectEditable) {
      return;
    }
    try {
      await persistSceneDraft();
      await persistSequenceDraft();
      const job = await generateSceneVideoChain(sceneId, {
        model_name: mediaGenerationSettingsDraft.video.model_class,
        auto_approve: autoApproveSequenceVideos,
        seed_mode: mediaGenerationSettingsDraft.video.seed_mode,
        seed: mediaGenerationSettingsDraft.video.seed,
      });
      setActiveJob(job);
      setWorkspaceTab("video");
      setNotice(
        autoApproveSequenceVideos
          ? "Scene video chain queued with auto-approve enabled."
          : "Scene video chain queued. Each generated clip will wait for review before it becomes approved.",
      );
      setError(null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function handleApproveSequenceVideo(sequenceId: string, assetId: string) {
    if (!project || !isProjectEditable) {
      return;
    }
    try {
      const savedSequence = await approveSequenceVideoVariant(sequenceId, assetId);
      mergeSequence(savedSequence);
      await loadProject(project.id, savedSequence.scene_id, sequenceId);
      setNotice(
        "Generated sequence video approved. Later sequences in this scene will use its last frame and may need regeneration if their chain was already built.",
      );
      setError(null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function handleAssemblyExport() {
    if (!project || !isProjectEditable) {
      return;
    }
    try {
      await persistProjectDraft();
      await persistSceneDraft();
      await persistSequenceDraft();
      const job = await startAssemblyExport(project.id);
      setActiveJob(job);
      setNotice("Rough-cut assembly queued.");
      setError(null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  function handleDownloadComfyExtract() {
    if (!selectedScene || !selectedComfyWindow || comfyDisabledReason) {
      return;
    }
    const link = document.createElement("a");
    link.href = comfySceneExtractUrl(selectedScene.id, selectedComfyWindow.startOrder);
    link.rel = "noreferrer";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setNotice(
      `Comfy scene extract prepared for Scene ${selectedScene.order.toString().padStart(2, "0")} / Seq ${selectedComfyWindow.startOrder}-${selectedComfyWindow.endOrder}.`,
    );
    setError(null);
  }

  async function handleRunScenarioAssistant() {
      if (!project || !isProjectEditable) {
        return;
      }
      try {
      await persistProjectDraft();
      setAssistantLoading(true);
      const result = await runScenarioAssistant(project.id, {
        focus: assistantFocus,
        instruction: assistantInstruction,
          rewrite_scenario: assistantRewriteScenario,
          max_suggestions: 4,
        });
        setAssistantResult(result);
        const revisedScenario = result.revised_scenario_text.trim();
        if (
          assistantRewriteScenario &&
          revisedScenario &&
          projectDraft &&
          revisedScenario !== projectDraft.scenario_text.trim()
        ) {
          setProjectDraft((currentDraft) =>
            currentDraft
              ? {
                  ...currentDraft,
                  scenario_text: revisedScenario,
                }
              : currentDraft,
          );
          setProjectDirty(true);
          setNotice("Local story coach finished. The revised scenario is now loaded into the editor and will autosave.");
        } else {
          setNotice("Local story coach finished this pass.");
        }
        setError(null);
      } catch (caughtError) {
        setError((caughtError as Error).message);
      } finally {
        setAssistantLoading(false);
    }
  }

  async function handleSaveModelSettings() {
    if (!modelSettingsDraft) {
      return;
    }
    try {
      setModelSettingsLoading(true);
      const saved = await updateModelSettings(buildModelSettingsPayload(modelSettingsDraft));
      setModelSettingsDraft(saved);
      setNotice("Global model settings saved.");
      setError(null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    } finally {
      setModelSettingsLoading(false);
    }
  }

  async function handleTestModelSettings() {
    if (!modelSettingsDraft) {
      return;
    }
    try {
      setModelSettingsLoading(true);
      const result = await testModelSettingsConnection(buildModelSettingsPayload(modelSettingsDraft));
      setAssistantConnectionTestResult(result);
      setNotice(result.message);
      setError(null);
    } catch (caughtError) {
      setAssistantConnectionTestResult(null);
      setError((caughtError as Error).message);
    } finally {
      setModelSettingsLoading(false);
    }
  }

  async function handleSaveMediaGenerationSettings() {
    if (!mediaGenerationSettingsDraft) {
      return;
    }
    try {
      setMediaGenerationSettingsLoading(true);
      const saved = await updateMediaGenerationSettings(mediaGenerationSettingsDraft);
      setMediaGenerationSettingsDraft(saved);
      setSceneImageGenerationDraft(buildSceneImageGenerationDraft(saved.image));
      await refreshImageModelInventory(false);
      setNotice("Media generation settings saved.");
      setError(null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    } finally {
      setMediaGenerationSettingsLoading(false);
    }
  }

  async function handleTestMediaGenerationRuntime() {
    if (!mediaGenerationSettingsDraft) {
      return;
    }
    try {
      setMediaGenerationSettingsLoading(true);
      const result = await testMediaGenerationSettings(mediaGenerationSettingsDraft);
      setMediaGenerationTestResult(result);
      setNotice(
        result.image.ready && result.video.ready
          ? "Image and video generation runtimes look ready."
          : `${result.image.message} ${result.video.message}`.trim(),
      );
      setError(null);
    } catch (caughtError) {
      setMediaGenerationTestResult(null);
      setError((caughtError as Error).message);
    } finally {
      setMediaGenerationSettingsLoading(false);
    }
  }

  function updateMediaDownloadDraft(target: MediaDownloadTarget, updates: Partial<MediaDownloadDraft>) {
    setMediaDownloadDrafts((current) => ({
      ...current,
      [target]: {
        ...current[target],
        ...updates,
      },
    }));
  }

  async function refreshMediaModelDownloadStatus(
    target: MediaDownloadTarget,
    downloadId: string,
    announceTerminalState = true,
  ) {
    try {
      const nextStatus = await getMediaModelDownload(downloadId);
      setMediaDownloadStatuses((current) => ({ ...current, [target]: nextStatus }));
      if (["succeeded", "failed"].includes(nextStatus.status)) {
        if (nextStatus.status === "succeeded") {
          const refreshedSettings = await getMediaGenerationSettings();
          setMediaGenerationSettingsDraft(refreshedSettings);
          setSceneImageGenerationDraft(buildSceneImageGenerationDraft(refreshedSettings.image));
          if (target === "image") {
            await refreshImageModelInventory(false);
          }
          if (announceTerminalState) {
            setNotice(
              nextStatus.applied_to_settings
                ? `${target === "image" ? "Image" : "Video"} model downloaded and applied to media settings.`
                : `${target === "image" ? "Image" : "Video"} model downloaded successfully.`,
            );
            setError(null);
          }
        } else if (announceTerminalState) {
          setError(nextStatus.error_text ?? `${target === "image" ? "Image" : "Video"} model download failed.`);
        }
      }
    } catch (caughtError) {
      if (announceTerminalState) {
        setError((caughtError as Error).message);
      }
    }
  }

  async function handleStartMediaModelDownload(target: MediaDownloadTarget) {
    const draft = mediaDownloadDrafts[target];
    if (!draft.repo_id.trim()) {
      setError("Enter a Hugging Face repo ID before starting a model download.");
      return;
    }
    try {
      setMediaGenerationSettingsLoading(true);
      const status = await startMediaModelDownload({
        target,
        repo_id: draft.repo_id.trim(),
        revision: draft.revision.trim(),
        filename: draft.filename.trim(),
        include_patterns: parsePatternList(draft.include_patterns),
        ignore_patterns: parsePatternList(draft.ignore_patterns),
        destination_name: draft.destination_name.trim(),
        token: draft.token.trim(),
        apply_to_settings: true,
      });
      setMediaDownloadStatuses((current) => ({ ...current, [target]: status }));
      setNotice(
        `${target === "image" ? "Image" : "Video"} model download queued from Hugging Face. The settings panel will refresh when it finishes.`,
      );
      setError(null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    } finally {
      setMediaGenerationSettingsLoading(false);
    }
  }

  async function handleUploadImageModel(file: File | null) {
    if (!file) {
      return;
    }
    try {
      setImageModelUploadBusy(true);
      const response = await uploadImageModel(file, {
        destination_name: imageModelUploadName.trim(),
        set_default: true,
      });
      setMediaGenerationSettingsDraft(response.settings);
      setSceneImageGenerationDraft(buildSceneImageGenerationDraft(response.settings.image));
      setImageModelInventory(response.inventory);
      setImageModelUploadName("");
      setNotice(`Uploaded ${response.uploaded_model.label} and set it as the active image model.`);
      setError(null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    } finally {
      setImageModelUploadBusy(false);
    }
  }

  async function handlePreviewPrompt() {
    if (!modelSettingsDraft) {
      return;
    }
    try {
      setPromptPreviewLoading(true);
      const result = await testPromptPreview({
        task: previewTask,
        project_id: project?.id,
        scene_id: selectedScene?.id,
        sequence_id: selectedSequence?.id,
        focus: assistantFocus,
        instruction: assistantInstruction,
        rewrite_scenario: assistantRewriteScenario,
        max_suggestions: 4,
        run_model: promptPreviewRunModel,
      });
      setPromptPreviewResult(result);
      setNotice(result.error_text ? "Prompt preview returned a template error." : "Prompt preview refreshed.");
      setError(null);
    } catch (caughtError) {
      setPromptPreviewResult(null);
      setError((caughtError as Error).message);
    } finally {
      setPromptPreviewLoading(false);
    }
  }

  function handleClearPromptPreviewContext() {
    setPromptPreviewResult(null);
    setNotice("LLM prompt preview context cleared.");
  }

  async function handleSaveProjectOverride() {
    if (!project || !projectModelSettingsOverrideDraft || !isProjectEditable) {
      return;
    }
    try {
      setProjectModelSettingsLoading(true);
      const saved = await updateProjectModelSettings(project.id, projectModelSettingsOverrideDraft);
      setProjectModelSettingsOverrideDraft(saved);
      setProject((currentProject) =>
        currentProject
          ? {
              ...currentProject,
              model_settings_override: saved,
            }
          : currentProject,
      );
      setNotice(saved.enabled ? "Project prompt profile override saved." : "Project override disabled.");
      setError(null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    } finally {
      setProjectModelSettingsLoading(false);
    }
  }

  function handleResetProjectOverride() {
    setProjectModelSettingsOverrideDraft(cloneValue(project?.model_settings_override ?? emptyProjectOverride()));
    setNotice("Project override draft reset.");
    setError(null);
  }

  function applyModelPreset(preset: RuntimePreset) {
    if (!modelSettingsDraft) {
      return;
    }
    setModelSettingsDraft({
      ...modelSettingsDraft,
      runtime: cloneValue(runtimePresets[preset]),
    });
    setNotice(`${preset === "gguf" ? "GGUF local server" : preset === "koboldcpp" ? "KoboldCpp" : "Ollama"} preset loaded into Settings.`);
  }

  function handleResetSelectedTask() {
    if (!modelSettingsDraft) {
      return;
    }
    setModelSettingsDraft({
      ...modelSettingsDraft,
      task_profiles: {
        ...modelSettingsDraft.task_profiles,
        [settingsTask]: cloneValue(modelSettingsDraft.defaults.task_profiles[settingsTask]),
      },
    });
    setNotice("Selected task profile reset to defaults.");
    setError(null);
  }

  function handleResetAllModelSettings() {
    if (!modelSettingsDraft) {
      return;
    }
    setModelSettingsDraft({
      ...modelSettingsDraft,
      runtime: cloneValue(modelSettingsDraft.defaults.runtime),
      generation_defaults: cloneValue(modelSettingsDraft.defaults.generation_defaults),
      task_profiles: cloneValue(modelSettingsDraft.defaults.task_profiles),
    });
    setNotice("Global model settings reset to defaults.");
    setError(null);
  }

  function handleExportModelSettings() {
    if (!modelSettingsDraft) {
      return;
    }
    const payload = buildModelSettingsPayload(modelSettingsDraft);
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "movie-scripting-model-settings.json";
    anchor.click();
    URL.revokeObjectURL(url);
    setNotice("Model settings exported.");
  }

  async function handleImportModelSettings(file: File | null) {
    if (!file || !modelSettingsDraft) {
      return;
    }
    try {
      const text = await file.text();
      const parsed = JSON.parse(text) as Pick<ModelSettings, "runtime" | "generation_defaults" | "task_profiles">;
      setModelSettingsDraft({
        ...modelSettingsDraft,
        runtime: cloneValue(parsed.runtime),
        generation_defaults: cloneValue(parsed.generation_defaults),
        task_profiles: cloneValue(parsed.task_profiles),
      });
      setNotice("Imported model settings into the draft editor.");
      setError(null);
    } catch {
      setError("Unable to import this settings file.");
    }
  }

  function applyAssistantScenario() {
      if (!assistantResult || !projectDraft) {
        return;
      }
      setProjectDraft((currentDraft) =>
        currentDraft
          ? {
              ...currentDraft,
              scenario_text: assistantResult.revised_scenario_text,
            }
          : currentDraft,
      );
      setProjectDirty(true);
      setNotice("The revised scenario is now loaded into the editor and will autosave.");
      setError(null);
    }

  async function copyToClipboard(text: string, label: string) {
    try {
      await navigator.clipboard.writeText(text);
      setNotice(`${label} copied.`);
      setError(null);
    } catch {
      setError(`Unable to copy ${label.toLowerCase()} on this browser.`);
    }
  }

  async function handleGenerateCharacters(overwriteExisting: boolean) {
    if (!project) return;
    setLoading(true);
    try {
      await generateCharacters(project.id, overwriteExisting);
      await refreshProjectList(projectScope, project.id);
      setNotice("Characters generated.");
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleAddCharacter() {
    if (!project) return;
    try {
      await createCharacter(project.id, { name: "New Character" });
      await refreshProjectList(projectScope, project.id);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleUpdateCharacter(characterId: string, updates: Partial<Parameters<typeof updateCharacter>[2]>) {
    if (!project) return;
    try {
      await updateCharacter(project.id, characterId, updates);
      await refreshProjectList(projectScope, project.id);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleGenerateCharacterImage(characterId: string, shotType: "portrait" | "cowboyshot" | "fullbody") {
    if (!project) return;
    try {
      const job = await generateCharacterImage(project.id, characterId, shotType);
      setActiveJob(job);
      setNotice(`Character image generation started (${shotType}).`);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleDeleteCharacter(characterId: string) {
    if (!project) return;
    try {
      await deleteCharacter(project.id, characterId);
      await refreshProjectList(projectScope, project.id);
    } catch (e: any) {
      setError(e.message);
    }
  }

  const hasProject = Boolean(project && projectDraft);
  const projectNeedsUpgrade = Boolean(project && project.workflow_version < 2);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-card">
          <p className="eyebrow">Movie 4.0</p>
          <h1>Movie Scripting Tool</h1>
          <p className="lede">
            Develop a 3-5 minute movie scenario, break it into long scenes, split those scenes into short sequences,
            prepare scene image prompts and Wan 2.2 prompts, then assemble a rough cut from approved sequence clips.
          </p>
        </div>

        <section className="panel">
          <div className="panel-header">
            <h2>System</h2>
            {loading ? <span className="badge muted">Loading</span> : null}
          </div>
          {hardware ? (
            <div className="hardware-card">
              <div className="hardware-row">
                <span>GPU</span>
                <strong>{hardware.gpu_name ?? "CPU workflow"}</strong>
              </div>
              <div className="hardware-row">
                <span>CPU Cores</span>
                <strong>{hardware.cpu_cores}</strong>
              </div>
              <div className="hardware-row">
                <span>Story Model</span>
                <strong>{modelSettingsDraft?.runtime.default_model ?? "Not configured"}</strong>
              </div>
              <div className={`badge ${hardware.supported_for_v1 ? "success" : "warning"}`}>
                {hardware.supported_for_v1 ? "GPU ready" : "Local fallback"}
              </div>
              <p className="muted-text">{hardware.notes.join(" ")}</p>
            </div>
          ) : (
            <p className="muted-text">Detecting hardware profile.</p>
          )}
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>New Project</h2>
          </div>
          <label className="field">
            <span>Title</span>
            <input
              value={projectForm.name}
              onChange={(event) => setProjectForm({ ...projectForm, name: event.target.value })}
            />
          </label>
          <label className="field">
            <span>Genre</span>
            <input
              value={projectForm.genre}
              onChange={(event) => setProjectForm({ ...projectForm, genre: event.target.value })}
            />
          </label>
          <label className="field">
            <span>Tone</span>
            <input
              value={projectForm.tone}
              onChange={(event) => setProjectForm({ ...projectForm, tone: event.target.value })}
            />
          </label>
          <label className="field">
            <span>Target Duration (s)</span>
            <input
              type="number"
              min={180}
              max={300}
              value={projectForm.target_duration_s}
              onChange={(event) =>
                setProjectForm({
                  ...projectForm,
                  target_duration_s: Number(event.target.value),
                })
              }
            />
          </label>
          <label className="field">
            <span>Scenario</span>
            <textarea
              rows={7}
              value={projectForm.scenario_text}
              onChange={(event) => setProjectForm({ ...projectForm, scenario_text: event.target.value })}
            />
          </label>
          <button className="primary-button" onClick={() => void handleCreateProject()}>
            Create project
          </button>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>Projects</h2>
            <span className="badge muted">{projects.length}</span>
          </div>
          <div className="token-cloud">
            <button
              className={`pill-button ${projectScope === "active" ? "active" : ""}`}
              onClick={() => setProjectScope("active")}
            >
              Active
            </button>
            <button
              className={`pill-button ${projectScope === "archived" ? "active" : ""}`}
              onClick={() => setProjectScope("archived")}
            >
              Archived
            </button>
            <button
              className={`pill-button ${projectScope === "all" ? "active" : ""}`}
              onClick={() => setProjectScope("all")}
            >
              All
            </button>
          </div>
          <div className="project-list">
            {projects.map((item) => (
              <button
                key={item.id}
                className={`project-chip ${project?.id === item.id ? "active" : ""}`}
                onClick={() => void loadProject(item.id)}
              >
                <strong>{item.name}</strong>
                <span>
                  {item.workflow_version >= 2 ? `${item.scene_count} scenes` : `${item.scene_count} legacy beats`} •{" "}
                  {item.target_duration_s}s
                </span>
                {item.archived_at ? <span className="mini-badge">archived</span> : null}
              </button>
            ))}
          </div>
        </section>
      </aside>

      <main className="workspace">
        <section className="hero-panel">
          <div>
            <p className="eyebrow">Workflow Studio</p>
            <h2>{project?.name ?? "Create or open a movie project"}</h2>
            <p className="muted-text">
                  {hasProject
                ? "Scenario shapes the full movie, Scenes define 30-90 second blocks, Images approves scene references, Sequences defines Wan-ready shots, Video generates or replaces clips, and Settings connects the local AI."
                : "You can configure the local AI in Settings before opening a project, then move from scenario to scenes, images, sequences, and video once a movie project exists."}
            </p>
          </div>
          <div className="job-card">
            <div className="panel-header">
              <h3>Media Queue</h3>
              {activeJob ? <span className={`badge ${statusTone(activeJob.status)}`}>{activeJob.status}</span> : null}
            </div>
            {activeJob ? (
              <>
                <p className="job-title">
                  {activeJob.job_type} #{activeJob.id.slice(0, 8)}
                </p>
                <div className="progress-track">
                  <div className="progress-bar" style={{ width: `${Math.round(activeJob.progress * 100)}%` }} />
                </div>
                <p className="muted-text">
                  {Math.round(activeJob.progress * 100)}% complete
                  {activeJob.error_text ? ` • ${activeJob.error_text}` : ""}
                </p>
              </>
            ) : (
              <p className="muted-text">No active media job. Image generation, video generation, and assembly export appear here.</p>
            )}
          </div>
        </section>

        {error ? <div className="alert error">{error}</div> : null}
        <div className="alert info">{notice}</div>
        {project ? (
          <section className="panel">
            <div className="panel-header">
              <h2>Project Lifecycle</h2>
              {project.archived_at ? (
                <span className="badge warning">Archived</span>
              ) : (
                <span className="badge success">Active</span>
              )}
            </div>
            <p className="muted-text">
              {project.archived_at
                ? "Archived projects stay available for review, download, and restore, but all editing and generation actions are disabled until you restore them."
                : "Archive finished projects to hide them from the default list. Permanent delete is only available after archiving."}
            </p>
            <div className="action-row">
              {project.archived_at ? (
                <>
                  <button className="primary-button" onClick={() => void handleRestoreProject()}>
                    Restore Project
                  </button>
                  <button className="ghost-button" onClick={() => void handleDeleteProject()}>
                    Delete Permanently
                  </button>
                </>
              ) : (
                <button className="ghost-button" onClick={() => void handleArchiveProject()}>
                  Archive Project
                </button>
              )}
            </div>
          </section>
        ) : null}

        <section className="panel">
          <div className="tab-row">
            <button
              className={`tab-button ${workspaceTab === "scenario" ? "active" : ""}`}
              onClick={() => setWorkspaceTab("scenario")}
            >
              Scenario
            </button>
            <button
              className={`tab-button ${workspaceTab === "characters" ? "active" : ""}`}
              onClick={() => setWorkspaceTab("characters")}
              disabled={!project}
            >
              Characters
            </button>
            <button
              className={`tab-button ${workspaceTab === "scenes" ? "active" : ""}`}
              onClick={() => setWorkspaceTab("scenes")}
              disabled={!project}
            >
              Scenes
              {projectOverrideEnabled(project) ? <span className="mini-badge">override</span> : null}
            </button>
            <button
              className={`tab-button ${workspaceTab === "images" ? "active" : ""}`}
              onClick={() => setWorkspaceTab("images")}
              disabled={!project}
            >
              Images
            </button>
            <button
              className={`tab-button ${workspaceTab === "sequences" ? "active" : ""}`}
              onClick={() => setWorkspaceTab("sequences")}
              disabled={!project}
            >
              Sequences
              {projectOverrideEnabled(project) ? <span className="mini-badge">override</span> : null}
            </button>
            <button
              className={`tab-button ${workspaceTab === "video" ? "active" : ""}`}
              onClick={() => setWorkspaceTab("video")}
              disabled={!project}
            >
              Video
            </button>
            <button
              className={`tab-button ${workspaceTab === "settings" ? "active" : ""}`}
              onClick={() => setWorkspaceTab("settings")}
            >
              Settings
            </button>
          </div>
        </section>

        {workspaceTab === "settings" ? (
          <>
            {modelSettingsDraft ? (
              <>
                <section className="settings-grid settings-grid-wide">
                  <div className="panel settings-panel">
                    <div className="panel-header">
                      <h2>Runtime</h2>
                      {assistantConnectionTestResult ? (
                        <span className={`badge ${statusTone(assistantConnectionTestResult.status)}`}>
                          {assistantConnectionTestResult.status}
                        </span>
                      ) : (
                        <span className="badge muted">Not tested</span>
                      )}
                    </div>
                    <p className="muted-text">
                      Configure the shared local model runtime for every LLM-backed stage, then save or test it before
                      editing prompt profiles.
                    </p>
                    <div className="project-grid">
                      <label className="field">
                        <span>Provider</span>
                        <select
                          value={modelSettingsDraft.runtime.provider}
                          onChange={(event) =>
                            setModelSettingsDraft({
                              ...modelSettingsDraft,
                              runtime: {
                                ...modelSettingsDraft.runtime,
                                provider: event.target.value as ModelSettings["runtime"]["provider"],
                              },
                            })
                          }
                        >
                          <option value="ollama">Ollama</option>
                          <option value="openai_compatible">OpenAI-Compatible</option>
                          <option value="koboldcpp">KoboldCpp</option>
                        </select>
                      </label>
                      <label className="field">
                        <span>Default Model</span>
                        <input
                          value={modelSettingsDraft.runtime.default_model}
                          onChange={(event) =>
                            setModelSettingsDraft({
                              ...modelSettingsDraft,
                              runtime: {
                                ...modelSettingsDraft.runtime,
                                default_model: event.target.value,
                              },
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Base URL</span>
                        <input
                          value={modelSettingsDraft.runtime.base_url}
                          onChange={(event) =>
                            setModelSettingsDraft({
                              ...modelSettingsDraft,
                              runtime: {
                                ...modelSettingsDraft.runtime,
                                base_url: event.target.value,
                              },
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Timeout (s)</span>
                        <input
                          type="number"
                          min={5}
                          max={600}
                          value={modelSettingsDraft.runtime.timeout_s}
                          onChange={(event) =>
                            setModelSettingsDraft({
                              ...modelSettingsDraft,
                              runtime: {
                                ...modelSettingsDraft.runtime,
                                timeout_s: Number(event.target.value),
                              },
                            })
                          }
                        />
                      </label>
                      <label className="field scenario-field">
                        <span>API Key</span>
                        <input
                          type="password"
                          value={modelSettingsDraft.runtime.api_key}
                          onChange={(event) =>
                            setModelSettingsDraft({
                              ...modelSettingsDraft,
                              runtime: {
                                ...modelSettingsDraft.runtime,
                                api_key: event.target.value,
                              },
                            })
                          }
                        />
                      </label>
                    </div>
                    <div className="action-row">
                      <button className="primary-button" onClick={() => void handleSaveModelSettings()}>
                        {modelSettingsLoading ? "Working..." : "Save Global Settings"}
                      </button>
                      <button className="ghost-button" onClick={() => void handleTestModelSettings()}>
                        {modelSettingsLoading ? "Working..." : "Test Connection"}
                      </button>
                    </div>
                  </div>

                  <div className="panel settings-guide">
                    <div className="panel-header">
                      <h2>Runtime Presets</h2>
                    </div>
                    <div className="settings-card">
                      <h3>Ollama Localhost</h3>
                      <p className="muted-text">Use this when your local model is exposed through Ollama.</p>
                      <div className="code-chip">http://127.0.0.1:11434</div>
                      <button className="ghost-button" onClick={() => applyModelPreset("ollama")}>
                        Load Ollama Preset
                      </button>
                    </div>
                    <div className="settings-card">
                      <h3>KoboldCpp</h3>
                      <p className="muted-text">
                        Use this for local GGUF inference through KoboldCpp’s OpenAI-style chat endpoint. For
                        continuity review with local vision, launch the matching multimodal projector with
                        <code> --mmproj</code> on the KoboldCpp side.
                      </p>
                      <div className="code-chip">http://127.0.0.1:5001/v1</div>
                      <button className="ghost-button" onClick={() => applyModelPreset("koboldcpp")}>
                        Load KoboldCpp Preset
                      </button>
                    </div>
                    <div className="settings-card">
                      <h3>GGUF Local Server</h3>
                      <p className="muted-text">
                        Use this for Gemma-style GGUF servers such as LM Studio, llama.cpp, or similar OpenAI-compatible backends.
                      </p>
                      <div className="code-chip">http://127.0.0.1:8081/v1</div>
                      <div className="code-chip">gemma-4-e2b-it-q4_k_m</div>
                      <button className="ghost-button" onClick={() => applyModelPreset("gguf")}>
                        Load GGUF Preset
                      </button>
                    </div>
                  </div>
                </section>

                {mediaGenerationSettingsDraft ? (
                  <section className="media-settings-layout">
                    <div className="panel">
                      <div className="panel-header">
                        <h2>Media Generation</h2>
                        <div className="action-row">
                          <button className="primary-button" onClick={() => void handleSaveMediaGenerationSettings()}>
                            {mediaGenerationSettingsLoading ? "Working..." : "Save Media Settings"}
                          </button>
                          <button className="ghost-button" onClick={() => void handleTestMediaGenerationRuntime()}>
                            {mediaGenerationSettingsLoading ? "Working..." : "Test Media Runtime"}
                          </button>
                        </div>
                      </div>
                      <p className="muted-text">
                        Configure the local image and Wan video runtime used by the new Images and Video tabs. Mock mode stays available for Docker smoke tests, while real providers expect local model paths.
                      </p>
                      <div className="media-settings-grid">
                        <div className="settings-card">
                          <div className="panel-header">
                            <h3>Image Generation</h3>
                            <span className={`badge ${statusTone(mediaGenerationTestResult?.image.status ?? "idle")}`}>
                              {mediaGenerationTestResult?.image.status ?? mediaGenerationSettingsDraft.image.provider}
                            </span>
                          </div>
                          <div className="project-grid">
                            <label className="field">
                              <span>Provider</span>
                              <select
                                value={mediaGenerationSettingsDraft.image.provider}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    image: {
                                      ...mediaGenerationSettingsDraft.image,
                                      provider: event.target.value as MediaGenerationSettings["image"]["provider"],
                                    },
                                  })
                                }
                              >
                                <option value="mock">Mock</option>
                                <option value="diffusers">Diffusers (SDXL / Z-image)</option>
                                <option value="comfyui">ComfyUI Server</option>
                              </select>
                            </label>
                            {mediaGenerationSettingsDraft.image.provider === "comfyui" ? (
                              <>
                                <label className="field scenario-field">
                                  <span>ComfyUI Endpoint</span>
                                  <input
                                    value={mediaGenerationSettingsDraft.image.comfy_endpoint}
                                    onChange={(event) =>
                                      setMediaGenerationSettingsDraft({
                                        ...mediaGenerationSettingsDraft,
                                        image: { ...mediaGenerationSettingsDraft.image, comfy_endpoint: event.target.value },
                                      })
                                    }
                                  />
                                </label>
                                <label className="field">
                                  <span>Comfy Timeout</span>
                                  <input
                                    type="number"
                                    min={30}
                                    step={30}
                                    value={mediaGenerationSettingsDraft.image.comfy_timeout_s}
                                    onChange={(event) =>
                                      setMediaGenerationSettingsDraft({
                                        ...mediaGenerationSettingsDraft,
                                        image: {
                                          ...mediaGenerationSettingsDraft.image,
                                          comfy_timeout_s: Number(event.target.value) || 300,
                                        },
                                      })
                                    }
                                  />
                                </label>
                                <label className="field scenario-field">
                                  <span>ComfyUI API Workflow JSON</span>
                                  <textarea
                                    rows={8}
                                    value={mediaGenerationSettingsDraft.image.comfy_workflow_json}
                                    onChange={(event) =>
                                      setMediaGenerationSettingsDraft({
                                        ...mediaGenerationSettingsDraft,
                                        image: {
                                          ...mediaGenerationSettingsDraft.image,
                                          comfy_workflow_json: event.target.value,
                                        },
                                      })
                                    }
                                    placeholder="Leave empty for the built-in txt2img workflow. Placeholders: %prompt%, %negative_prompt%, %width%, %height%, %steps%, %scale%, %sampler%, %scheduler%, %seed%, %model%."
                                  />
                                </label>
                              </>
                            ) : null}
                            <label className="field">
                              <span>Default Model</span>
                              <select
                                value={mediaGenerationSettingsDraft.image.default_model}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    image: { ...mediaGenerationSettingsDraft.image, default_model: event.target.value },
                                  })
                                }
                              >
                                <option value="">Use checkpoint root directly</option>
                                {imageModelOptions.map((model) => (
                                  <option key={model.value} value={model.value}>
                                    {model.label}
                                  </option>
                                ))}
                                {mediaGenerationSettingsDraft.image.default_model &&
                                !imageModelOptions.some(
                                  (model) => model.value === mediaGenerationSettingsDraft.image.default_model,
                                ) ? (
                                  <option value={mediaGenerationSettingsDraft.image.default_model}>
                                    {mediaGenerationSettingsDraft.image.default_model} (manual)
                                  </option>
                                ) : null}
                              </select>
                            </label>
                            <label className="field scenario-field">
                              <span>Checkpoint Root</span>
                              <input
                                value={mediaGenerationSettingsDraft.image.checkpoint_root}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    image: { ...mediaGenerationSettingsDraft.image, checkpoint_root: event.target.value },
                                  })
                                }
                              />
                            </label>
                            <label className="field">
                              <span>VAE Path</span>
                              <input
                                value={mediaGenerationSettingsDraft.image.vae_path}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    image: { ...mediaGenerationSettingsDraft.image, vae_path: event.target.value },
                                  })
                                }
                              />
                            </label>
                            <label className="field">
                              <span>LoRA Directory</span>
                              <input
                                value={mediaGenerationSettingsDraft.image.lora_dir}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    image: { ...mediaGenerationSettingsDraft.image, lora_dir: event.target.value },
                                  })
                                }
                              />
                            </label>
                            <label className="field">
                              <span>Device</span>
                              <select
                                value={mediaGenerationSettingsDraft.image.device}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    image: { ...mediaGenerationSettingsDraft.image, device: event.target.value },
                                  })
                                }
                              >
                                <option value="auto">Auto (prefer CUDA, fall back to CPU)</option>
                                <option value="cuda">CUDA only</option>
                                <option value="cpu">CPU only</option>
                              </select>
                              <small className="muted-text">
                                `auto` prefers CUDA when Docker can see your NVIDIA runtime, otherwise it falls back to CPU.
                              </small>
                            </label>
                            <label className="field">
                              <span>DType</span>
                              <select
                                value={mediaGenerationSettingsDraft.image.dtype}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    image: { ...mediaGenerationSettingsDraft.image, dtype: event.target.value },
                                  })
                                }
                              >
                                <option value="auto">Auto</option>
                                <option value="fp16">FP16</option>
                                <option value="bf16">BF16</option>
                                <option value="fp32">FP32</option>
                              </select>
                              <small className="muted-text">
                                `auto` now resolves to `float32` for CPU runs and for custom single-file CUDA checkpoints, which avoids the black-image decode failures we saw with merged SDXL safetensors.
                              </small>
                            </label>
                            <label className="field">
                              <span>Sampler</span>
                              <select
                                value={mediaGenerationSettingsDraft.image.sampler}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    image: { ...mediaGenerationSettingsDraft.image, sampler: event.target.value },
                                  })
                                }
                              >
                                {imageSamplerOptions.map((option) => (
                                  <option key={option.value} value={option.value}>
                                    {option.label}
                                  </option>
                                ))}
                              </select>
                            </label>
                            <label className="field">
                              <span>Scheduler</span>
                              <select
                                value={mediaGenerationSettingsDraft.image.scheduler}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    image: { ...mediaGenerationSettingsDraft.image, scheduler: event.target.value },
                                  })
                                }
                              >
                                {imageSchedulerOptions.map((option) => (
                                  <option key={option.value} value={option.value}>
                                    {option.label}
                                  </option>
                                ))}
                              </select>
                            </label>
                            <label className="field">
                              <span>Width</span>
                              <input
                                type="number"
                                value={mediaGenerationSettingsDraft.image.width}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    image: { ...mediaGenerationSettingsDraft.image, width: Number(event.target.value) },
                                  })
                                }
                              />
                            </label>
                            <label className="field">
                              <span>Height</span>
                              <input
                                type="number"
                                value={mediaGenerationSettingsDraft.image.height}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    image: { ...mediaGenerationSettingsDraft.image, height: Number(event.target.value) },
                                  })
                                }
                              />
                            </label>
                            <label className="field">
                              <span>Steps</span>
                              <input
                                type="number"
                                value={mediaGenerationSettingsDraft.image.steps}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    image: { ...mediaGenerationSettingsDraft.image, steps: Number(event.target.value) },
                                  })
                                }
                              />
                            </label>
                            <label className="field">
                              <span>CFG</span>
                              <input
                                type="number"
                                step="0.1"
                                value={mediaGenerationSettingsDraft.image.cfg_scale}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    image: { ...mediaGenerationSettingsDraft.image, cfg_scale: Number(event.target.value) },
                                  })
                                }
                              />
                            </label>
                            <label className="field">
                              <span>Variant Count</span>
                              <input
                                type="number"
                                min={1}
                                max={8}
                                value={mediaGenerationSettingsDraft.image.variant_count}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    image: { ...mediaGenerationSettingsDraft.image, variant_count: Number(event.target.value) },
                                  })
                                }
                              />
                            </label>
                            <label className="field">
                              <span>Seed Mode</span>
                              <select
                                value={mediaGenerationSettingsDraft.image.seed_mode}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    image: {
                                      ...mediaGenerationSettingsDraft.image,
                                      seed_mode: event.target.value as MediaGenerationSettings["image"]["seed_mode"],
                                    },
                                  })
                                }
                              >
                                <option value="random">Random</option>
                                <option value="fixed">Fixed</option>
                              </select>
                            </label>
                            <label className="field">
                              <span>Fixed Seed</span>
                              <input
                                type="number"
                                value={mediaGenerationSettingsDraft.image.seed ?? ""}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    image: {
                                      ...mediaGenerationSettingsDraft.image,
                                      seed: event.target.value ? Number(event.target.value) : null,
                                    },
                                  })
                                }
                              />
                            </label>
                            <label className="field scenario-field">
                              <span>Negative Prompt</span>
                              <textarea
                                rows={3}
                                value={mediaGenerationSettingsDraft.image.default_negative_prompt}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    image: {
                                      ...mediaGenerationSettingsDraft.image,
                                      default_negative_prompt: event.target.value,
                                    },
                                  })
                                }
                              />
                            </label>
                          </div>
                          <label className="toggle-row">
                            <input
                              type="checkbox"
                              checked={mediaGenerationSettingsDraft.image.enabled}
                              onChange={(event) =>
                                setMediaGenerationSettingsDraft({
                                  ...mediaGenerationSettingsDraft,
                                  image: { ...mediaGenerationSettingsDraft.image, enabled: event.target.checked },
                                })
                              }
                            />
                            Enable in-app scene image generation
                          </label>
                          <div className="download-panel">
                            <div className="panel-header">
                              <h4>Local Model Library</h4>
                              <div className="action-row">
                                <button
                                  className="ghost-button"
                                  onClick={() => void refreshImageModelInventory(true)}
                                  disabled={imageModelUploadBusy}
                                >
                                  Refresh List
                                </button>
                                <label className={`upload-button ${imageModelUploadBusy ? "disabled-like" : ""}`}>
                                  {imageModelUploadBusy ? "Uploading..." : "Upload Model"}
                                  <input
                                    disabled={imageModelUploadBusy}
                                    type="file"
                                    accept=".safetensors,.ckpt,.pt,.pth,.bin"
                                    onChange={(event) => {
                                      void handleUploadImageModel(event.target.files?.[0] ?? null);
                                      event.currentTarget.value = "";
                                    }}
                                  />
                                </label>
                              </div>
                            </div>
                            <p className="muted-text">
                              Upload single-file SDXL-family checkpoints such as your SDXL-DMD2 and Z-Image Turbo
                              `.safetensors`, then pick them from the model list above.
                            </p>
                            <div className="project-grid">
                              <label className="field">
                                <span>Upload Name (Optional)</span>
                                <input
                                  placeholder="sdxl-dmd2 or z-image-turbo"
                                  value={imageModelUploadName}
                                  onChange={(event) => setImageModelUploadName(event.target.value)}
                                />
                              </label>
                              <div className="field scenario-field">
                                <span>Detected Models</span>
                                <div className="token-cloud">
                                  {imageModelOptions.length ? (
                                    imageModelOptions.map((model) => (
                                      <button
                                        key={model.value}
                                        type="button"
                                        className={`code-chip ${
                                          mediaGenerationSettingsDraft.image.default_model === model.value ? "active-chip" : ""
                                        }`}
                                        onClick={() =>
                                          setMediaGenerationSettingsDraft({
                                            ...mediaGenerationSettingsDraft,
                                            image: {
                                              ...mediaGenerationSettingsDraft.image,
                                              default_model: model.value,
                                            },
                                          })
                                        }
                                      >
                                        {model.label}
                                      </button>
                                    ))
                                  ) : (
                                    <span className="code-chip">No image models detected yet.</span>
                                  )}
                                </div>
                              </div>
                            </div>
                            <p className="helper-text">
                              Root: {imageModelInventory?.root_path ?? mediaGenerationSettingsDraft.image.checkpoint_root}
                            </p>
                          </div>
                          <div className="download-panel">
                            <div className="panel-header">
                              <h4>Download From Hugging Face</h4>
                              <span className="badge muted">SDXL / Z-image</span>
                            </div>
                            <p className="muted-text">
                              Pull a repo snapshot or a single checkpoint file directly into the configured image model area, then auto-apply it to these settings.
                            </p>
                            <div className="project-grid">
                              <label className="field">
                                <span>Repo ID</span>
                                <input
                                  placeholder="stabilityai/stable-diffusion-xl-base-1.0"
                                  value={mediaDownloadDrafts.image.repo_id}
                                  onChange={(event) => updateMediaDownloadDraft("image", { repo_id: event.target.value })}
                                />
                              </label>
                              <label className="field">
                                <span>Revision</span>
                                <input
                                  placeholder="main"
                                  value={mediaDownloadDrafts.image.revision}
                                  onChange={(event) => updateMediaDownloadDraft("image", { revision: event.target.value })}
                                />
                              </label>
                              <label className="field scenario-field">
                                <span>Single Filename (Optional)</span>
                                <input
                                  placeholder="model.safetensors"
                                  value={mediaDownloadDrafts.image.filename}
                                  onChange={(event) => updateMediaDownloadDraft("image", { filename: event.target.value })}
                                />
                              </label>
                              <label className="field">
                                <span>Include Patterns</span>
                                <textarea
                                  rows={2}
                                  placeholder="*.safetensors"
                                  value={mediaDownloadDrafts.image.include_patterns}
                                  onChange={(event) =>
                                    updateMediaDownloadDraft("image", { include_patterns: event.target.value })
                                  }
                                />
                              </label>
                              <label className="field">
                                <span>Ignore Patterns</span>
                                <textarea
                                  rows={2}
                                  placeholder="*.md"
                                  value={mediaDownloadDrafts.image.ignore_patterns}
                                  onChange={(event) =>
                                    updateMediaDownloadDraft("image", { ignore_patterns: event.target.value })
                                  }
                                />
                              </label>
                              <label className="field">
                                <span>Destination Name</span>
                                <input
                                  placeholder="sdxl-base-local"
                                  value={mediaDownloadDrafts.image.destination_name}
                                  onChange={(event) =>
                                    updateMediaDownloadDraft("image", { destination_name: event.target.value })
                                  }
                                />
                              </label>
                              <label className="field scenario-field">
                                <span>HF Token (Optional)</span>
                                <input
                                  type="password"
                                  placeholder="Uses HF_TOKEN env var when left blank"
                                  value={mediaDownloadDrafts.image.token}
                                  onChange={(event) => updateMediaDownloadDraft("image", { token: event.target.value })}
                                />
                              </label>
                            </div>
                            <div className="action-row">
                              <button
                                className="ghost-button"
                                onClick={() => void handleStartMediaModelDownload("image")}
                                disabled={mediaGenerationSettingsLoading || !mediaDownloadDrafts.image.repo_id.trim()}
                              >
                                {mediaDownloadStatuses.image &&
                                ["queued", "running"].includes(mediaDownloadStatuses.image.status)
                                  ? "Downloading..."
                                  : "Download Image Model"}
                              </button>
                            </div>
                            {mediaDownloadStatuses.image ? (
                              <div className="download-status-card">
                                <div className="panel-header">
                                  <h4>Image Download Status</h4>
                                  <span className={`badge ${statusTone(mediaDownloadStatuses.image.status)}`}>
                                    {mediaDownloadStatuses.image.status}
                                  </span>
                                </div>
                                <p className="muted-text">
                                  {Math.round(mediaDownloadStatuses.image.progress * 100)}% • {mediaDownloadStatuses.image.message}
                                </p>
                                {mediaDownloadStatuses.image.downloaded_path ? (
                                  <div className="token-cloud">
                                    <span className="code-chip">{mediaDownloadStatuses.image.downloaded_path}</span>
                                  </div>
                                ) : null}
                                {mediaDownloadStatuses.image.error_text ? (
                                  <p className="assistant-summary">{mediaDownloadStatuses.image.error_text}</p>
                                ) : null}
                              </div>
                            ) : null}
                          </div>
                        </div>

                        <div className="settings-card">
                          <div className="panel-header">
                            <h3>Video Generation</h3>
                            <span className={`badge ${statusTone(mediaGenerationTestResult?.video.status ?? "idle")}`}>
                              {mediaGenerationTestResult?.video.status ?? mediaGenerationSettingsDraft.video.provider}
                            </span>
                          </div>
                          <div className="project-grid">
                            <label className="field">
                              <span>Provider</span>
                              <select
                                value={mediaGenerationSettingsDraft.video.provider}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    video: {
                                      ...mediaGenerationSettingsDraft.video,
                                      provider: event.target.value as MediaGenerationSettings["video"]["provider"],
                                    },
                                  })
                                }
                              >
                                <option value="mock">Mock</option>
                                <option value="lightx2v">LightX2V (Wan)</option>
                              </select>
                            </label>
                            <label className="field">
                              <span>Model Class</span>
                              <input
                                value={mediaGenerationSettingsDraft.video.model_class}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    video: { ...mediaGenerationSettingsDraft.video, model_class: event.target.value },
                                  })
                                }
                              />
                            </label>
                            <label className="field scenario-field">
                              <span>Model Root</span>
                              <input
                                value={mediaGenerationSettingsDraft.video.model_root}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    video: { ...mediaGenerationSettingsDraft.video, model_root: event.target.value },
                                  })
                                }
                              />
                            </label>
                            <label className="field">
                              <span>Encoder Root</span>
                              <input
                                value={mediaGenerationSettingsDraft.video.encoder_root}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    video: { ...mediaGenerationSettingsDraft.video, encoder_root: event.target.value },
                                  })
                                }
                              />
                            </label>
                            <label className="field">
                              <span>VAE Root</span>
                              <input
                                value={mediaGenerationSettingsDraft.video.vae_root}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    video: { ...mediaGenerationSettingsDraft.video, vae_root: event.target.value },
                                  })
                                }
                              />
                            </label>
                            <label className="field">
                              <span>Quantization</span>
                              <input
                                value={mediaGenerationSettingsDraft.video.quantization_preset}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    video: {
                                      ...mediaGenerationSettingsDraft.video,
                                      quantization_preset: event.target.value,
                                    },
                                  })
                                }
                              />
                            </label>
                            <label className="field">
                              <span>Attention Mode</span>
                              <input
                                value={mediaGenerationSettingsDraft.video.attention_mode}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    video: { ...mediaGenerationSettingsDraft.video, attention_mode: event.target.value },
                                  })
                                }
                              />
                            </label>
                            <label className="field">
                              <span>Infer Steps</span>
                              <input
                                type="number"
                                value={mediaGenerationSettingsDraft.video.infer_steps}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    video: { ...mediaGenerationSettingsDraft.video, infer_steps: Number(event.target.value) },
                                  })
                                }
                              />
                            </label>
                            <label className="field">
                              <span>Native Width</span>
                              <input
                                type="number"
                                value={mediaGenerationSettingsDraft.video.native_width}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    video: {
                                      ...mediaGenerationSettingsDraft.video,
                                      native_width: Number(event.target.value),
                                    },
                                  })
                                }
                              />
                            </label>
                            <label className="field">
                              <span>Native Height</span>
                              <input
                                type="number"
                                value={mediaGenerationSettingsDraft.video.native_height}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    video: {
                                      ...mediaGenerationSettingsDraft.video,
                                      native_height: Number(event.target.value),
                                    },
                                  })
                                }
                              />
                            </label>
                            <label className="field">
                              <span>Frames</span>
                              <input
                                type="number"
                                value={mediaGenerationSettingsDraft.video.native_frame_count}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    video: {
                                      ...mediaGenerationSettingsDraft.video,
                                      native_frame_count: Number(event.target.value),
                                    },
                                  })
                                }
                              />
                            </label>
                            <label className="field">
                              <span>Guidance</span>
                              <input
                                type="number"
                                step="0.1"
                                value={mediaGenerationSettingsDraft.video.guidance_scale}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    video: {
                                      ...mediaGenerationSettingsDraft.video,
                                      guidance_scale: Number(event.target.value),
                                    },
                                  })
                                }
                              />
                            </label>
                            <label className="field">
                              <span>Sample Shift</span>
                              <input
                                type="number"
                                step="0.1"
                                value={mediaGenerationSettingsDraft.video.sample_shift}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    video: {
                                      ...mediaGenerationSettingsDraft.video,
                                      sample_shift: Number(event.target.value),
                                    },
                                  })
                                }
                              />
                            </label>
                            <label className="field">
                              <span>Retime Mode</span>
                              <select
                                value={mediaGenerationSettingsDraft.video.retime_mode}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    video: {
                                      ...mediaGenerationSettingsDraft.video,
                                      retime_mode: event.target.value as MediaGenerationSettings["video"]["retime_mode"],
                                    },
                                  })
                                }
                              >
                                <option value="fit_duration">Fit Duration</option>
                                <option value="frame_interpolate_fit">Interpolate And Fit</option>
                                <option value="none">Native Duration</option>
                              </select>
                            </label>
                            <label className="field">
                              <span>Output FPS</span>
                              <input
                                type="number"
                                min={6}
                                max={60}
                                value={mediaGenerationSettingsDraft.video.target_output_fps}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    video: {
                                      ...mediaGenerationSettingsDraft.video,
                                      target_output_fps: Number(event.target.value),
                                    },
                                  })
                                }
                              />
                            </label>
                            <label className="field">
                              <span>Seed Mode</span>
                              <select
                                value={mediaGenerationSettingsDraft.video.seed_mode}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    video: {
                                      ...mediaGenerationSettingsDraft.video,
                                      seed_mode: event.target.value as MediaGenerationSettings["video"]["seed_mode"],
                                    },
                                  })
                                }
                              >
                                <option value="random">Random</option>
                                <option value="fixed">Fixed</option>
                              </select>
                            </label>
                            <label className="field">
                              <span>Fixed Seed</span>
                              <input
                                type="number"
                                value={mediaGenerationSettingsDraft.video.seed ?? ""}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    video: {
                                      ...mediaGenerationSettingsDraft.video,
                                      seed: event.target.value ? Number(event.target.value) : null,
                                    },
                                  })
                                }
                              />
                            </label>
                          </div>
                          <div className="toggle-grid">
                            <label className="toggle-row">
                              <input
                                type="checkbox"
                                checked={mediaGenerationSettingsDraft.video.enabled}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    video: { ...mediaGenerationSettingsDraft.video, enabled: event.target.checked },
                                  })
                                }
                              />
                              Enable in-app Wan video generation
                            </label>
                            <label className="toggle-row">
                              <input
                                type="checkbox"
                                checked={mediaGenerationSettingsDraft.video.cpu_offload}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    video: { ...mediaGenerationSettingsDraft.video, cpu_offload: event.target.checked },
                                  })
                                }
                              />
                              CPU offload
                            </label>
                            <label className="toggle-row">
                              <input
                                type="checkbox"
                                checked={mediaGenerationSettingsDraft.video.text_encoder_offload}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    video: {
                                      ...mediaGenerationSettingsDraft.video,
                                      text_encoder_offload: event.target.checked,
                                    },
                                  })
                                }
                              />
                              Text encoder offload
                            </label>
                            <label className="toggle-row">
                              <input
                                type="checkbox"
                                checked={mediaGenerationSettingsDraft.video.image_encoder_offload}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    video: {
                                      ...mediaGenerationSettingsDraft.video,
                                      image_encoder_offload: event.target.checked,
                                    },
                                  })
                                }
                              />
                              Image encoder offload
                            </label>
                            <label className="toggle-row">
                              <input
                                type="checkbox"
                                checked={mediaGenerationSettingsDraft.video.vae_offload}
                                onChange={(event) =>
                                  setMediaGenerationSettingsDraft({
                                    ...mediaGenerationSettingsDraft,
                                    video: {
                                      ...mediaGenerationSettingsDraft.video,
                                      vae_offload: event.target.checked,
                                    },
                                  })
                                }
                              />
                              VAE offload
                            </label>
                          </div>
                          <div className="download-panel">
                            <div className="panel-header">
                              <h4>Download From Hugging Face</h4>
                              <span className="badge muted">Wan / LightX2V</span>
                            </div>
                            <p className="muted-text">
                              Pull a quantized Wan-compatible model snapshot directly into the configured video model area, then auto-apply it to these settings.
                            </p>
                            <div className="project-grid">
                              <label className="field">
                                <span>Repo ID</span>
                                <input
                                  placeholder="your-org/wan-quant-model"
                                  value={mediaDownloadDrafts.video.repo_id}
                                  onChange={(event) => updateMediaDownloadDraft("video", { repo_id: event.target.value })}
                                />
                              </label>
                              <label className="field">
                                <span>Revision</span>
                                <input
                                  placeholder="main"
                                  value={mediaDownloadDrafts.video.revision}
                                  onChange={(event) => updateMediaDownloadDraft("video", { revision: event.target.value })}
                                />
                              </label>
                              <label className="field scenario-field">
                                <span>Include Patterns</span>
                                <textarea
                                  rows={2}
                                  placeholder="*.json&#10;*.safetensors"
                                  value={mediaDownloadDrafts.video.include_patterns}
                                  onChange={(event) =>
                                    updateMediaDownloadDraft("video", { include_patterns: event.target.value })
                                  }
                                />
                              </label>
                              <label className="field">
                                <span>Ignore Patterns</span>
                                <textarea
                                  rows={2}
                                  placeholder="*.md"
                                  value={mediaDownloadDrafts.video.ignore_patterns}
                                  onChange={(event) =>
                                    updateMediaDownloadDraft("video", { ignore_patterns: event.target.value })
                                  }
                                />
                              </label>
                              <label className="field">
                                <span>Destination Name</span>
                                <input
                                  placeholder="wan22-local"
                                  value={mediaDownloadDrafts.video.destination_name}
                                  onChange={(event) =>
                                    updateMediaDownloadDraft("video", { destination_name: event.target.value })
                                  }
                                />
                              </label>
                              <label className="field scenario-field">
                                <span>HF Token (Optional)</span>
                                <input
                                  type="password"
                                  placeholder="Uses HF_TOKEN env var when left blank"
                                  value={mediaDownloadDrafts.video.token}
                                  onChange={(event) => updateMediaDownloadDraft("video", { token: event.target.value })}
                                />
                              </label>
                            </div>
                            <div className="action-row">
                              <button
                                className="ghost-button"
                                onClick={() => void handleStartMediaModelDownload("video")}
                                disabled={mediaGenerationSettingsLoading || !mediaDownloadDrafts.video.repo_id.trim()}
                              >
                                {mediaDownloadStatuses.video &&
                                ["queued", "running"].includes(mediaDownloadStatuses.video.status)
                                  ? "Downloading..."
                                  : "Download Video Model"}
                              </button>
                            </div>
                            {mediaDownloadStatuses.video ? (
                              <div className="download-status-card">
                                <div className="panel-header">
                                  <h4>Video Download Status</h4>
                                  <span className={`badge ${statusTone(mediaDownloadStatuses.video.status)}`}>
                                    {mediaDownloadStatuses.video.status}
                                  </span>
                                </div>
                                <p className="muted-text">
                                  {Math.round(mediaDownloadStatuses.video.progress * 100)}% • {mediaDownloadStatuses.video.message}
                                </p>
                                {mediaDownloadStatuses.video.downloaded_path ? (
                                  <div className="token-cloud">
                                    <span className="code-chip">{mediaDownloadStatuses.video.downloaded_path}</span>
                                  </div>
                                ) : null}
                                {mediaDownloadStatuses.video.error_text ? (
                                  <p className="assistant-summary">{mediaDownloadStatuses.video.error_text}</p>
                                ) : null}
                              </div>
                            ) : null}
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="panel">
                      <div className="panel-header">
                        <h2>Media Runtime Status</h2>
                        <span className="badge muted">image + video</span>
                      </div>
                      {mediaGenerationTestResult ? (
                        <div className="assistant-columns preview-columns">
                          <div className="assistant-card">
                            <h3>Image Runtime</h3>
                            <p className="assistant-summary">{mediaGenerationTestResult.image.message}</p>
                            <div className="token-cloud">
                              {Object.entries(mediaGenerationTestResult.image.resolved_paths).map(([label, value]) => (
                                <span key={label} className="code-chip">
                                  {label}: {value}
                                </span>
                              ))}
                            </div>
                          </div>
                          <div className="assistant-card">
                            <h3>Video Runtime</h3>
                            <p className="assistant-summary">{mediaGenerationTestResult.video.message}</p>
                            <div className="token-cloud">
                              {Object.entries(mediaGenerationTestResult.video.resolved_paths).map(([label, value]) => (
                                <span key={label} className="code-chip">
                                  {label}: {value}
                                </span>
                              ))}
                            </div>
                          </div>
                          <div className="assistant-card">
                            <h3>Warnings</h3>
                            <ul className="flat-list">
                              {[...mediaGenerationTestResult.image.warnings, ...mediaGenerationTestResult.video.warnings].length ? (
                                [...mediaGenerationTestResult.image.warnings, ...mediaGenerationTestResult.video.warnings].map((warning) => (
                                  <li key={warning}>{warning}</li>
                                ))
                              ) : (
                                <li>No warnings reported.</li>
                              )}
                            </ul>
                          </div>
                        </div>
                      ) : (
                        <p className="muted-text">
                          Run a media runtime test to confirm model paths, optional dependencies, and mock-vs-real provider readiness.
                        </p>
                      )}
                    </div>
                  </section>
                ) : null}

                <section className="settings-grid settings-grid-wide">
                  <div className="panel">
                    <div className="panel-header">
                      <h2>Shared Generation Defaults</h2>
                      <span className="badge muted">all tasks</span>
                    </div>
                    <div className="project-grid">
                      <label className="field">
                        <span>Temperature</span>
                        <input
                          type="number"
                          step="0.05"
                          min={0}
                          max={2}
                          value={modelSettingsDraft.generation_defaults.temperature}
                          onChange={(event) =>
                            setModelSettingsDraft({
                              ...modelSettingsDraft,
                              generation_defaults: {
                                ...modelSettingsDraft.generation_defaults,
                                temperature: Number(event.target.value),
                              },
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Top P</span>
                        <input
                          type="number"
                          step="0.05"
                          min={0}
                          max={1}
                          value={modelSettingsDraft.generation_defaults.top_p}
                          onChange={(event) =>
                            setModelSettingsDraft({
                              ...modelSettingsDraft,
                              generation_defaults: {
                                ...modelSettingsDraft.generation_defaults,
                                top_p: Number(event.target.value),
                              },
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Top K</span>
                        <input
                          type="number"
                          min={0}
                          max={500}
                          value={modelSettingsDraft.generation_defaults.top_k}
                          onChange={(event) =>
                            setModelSettingsDraft({
                              ...modelSettingsDraft,
                              generation_defaults: {
                                ...modelSettingsDraft.generation_defaults,
                                top_k: Number(event.target.value),
                              },
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Min P</span>
                        <input
                          type="number"
                          step="0.01"
                          min={0}
                          max={1}
                          value={modelSettingsDraft.generation_defaults.min_p}
                          onChange={(event) =>
                            setModelSettingsDraft({
                              ...modelSettingsDraft,
                              generation_defaults: {
                                ...modelSettingsDraft.generation_defaults,
                                min_p: Number(event.target.value),
                              },
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Repeat Penalty</span>
                        <input
                          type="number"
                          step="0.05"
                          min={0}
                          max={5}
                          value={modelSettingsDraft.generation_defaults.repeat_penalty}
                          onChange={(event) =>
                            setModelSettingsDraft({
                              ...modelSettingsDraft,
                              generation_defaults: {
                                ...modelSettingsDraft.generation_defaults,
                                repeat_penalty: Number(event.target.value),
                              },
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Max Output Tokens</span>
                        <input
                          type="number"
                          min={64}
                          max={8192}
                          value={modelSettingsDraft.generation_defaults.max_output_tokens}
                          onChange={(event) =>
                            setModelSettingsDraft({
                              ...modelSettingsDraft,
                              generation_defaults: {
                                ...modelSettingsDraft.generation_defaults,
                                max_output_tokens: Number(event.target.value),
                              },
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Seed</span>
                        <input
                          value={modelSettingsDraft.generation_defaults.seed ?? ""}
                          placeholder="optional"
                          onChange={(event) =>
                            setModelSettingsDraft({
                              ...modelSettingsDraft,
                              generation_defaults: {
                                ...modelSettingsDraft.generation_defaults,
                                seed: toOptionalNumber(event.target.value),
                              },
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>JSON Retries</span>
                        <input
                          type="number"
                          min={1}
                          max={6}
                          value={modelSettingsDraft.generation_defaults.json_retries}
                          onChange={(event) =>
                            setModelSettingsDraft({
                              ...modelSettingsDraft,
                              generation_defaults: {
                                ...modelSettingsDraft.generation_defaults,
                                json_retries: Number(event.target.value),
                              },
                            })
                          }
                        />
                      </label>
                      <label className="field scenario-field">
                        <span>Stop Sequences</span>
                        <textarea
                          rows={3}
                          value={modelSettingsDraft.generation_defaults.stop_sequences.join("\n")}
                          placeholder="One stop sequence per line"
                          onChange={(event) =>
                            setModelSettingsDraft({
                              ...modelSettingsDraft,
                              generation_defaults: {
                                ...modelSettingsDraft.generation_defaults,
                                stop_sequences: splitStopSequences(event.target.value),
                              },
                            })
                          }
                        />
                      </label>
                    </div>
                    <div className="toggle-grid">
                      <label className="toggle-row">
                        <input
                          type="checkbox"
                          checked={modelSettingsDraft.generation_defaults.strip_markdown_fences}
                          onChange={(event) =>
                            setModelSettingsDraft({
                              ...modelSettingsDraft,
                              generation_defaults: {
                                ...modelSettingsDraft.generation_defaults,
                                strip_markdown_fences: event.target.checked,
                              },
                            })
                          }
                        />
                        Strip markdown fences before JSON parsing
                      </label>
                      <label className="toggle-row">
                        <input
                          type="checkbox"
                          checked={modelSettingsDraft.generation_defaults.fallback_to_heuristics}
                          onChange={(event) =>
                            setModelSettingsDraft({
                              ...modelSettingsDraft,
                              generation_defaults: {
                                ...modelSettingsDraft.generation_defaults,
                                fallback_to_heuristics: event.target.checked,
                              },
                            })
                          }
                        />
                        Allow deterministic fallback when the runtime is unreachable or invalid
                      </label>
                    </div>
                  </div>

                  <div className="panel">
                    <div className="panel-header">
                      <h2>Task Prompt Profiles</h2>
                      <button className="ghost-button" onClick={handleResetSelectedTask}>
                        Reset Selected Task
                      </button>
                    </div>
                    <div className="focus-row">
                      {availableTasks.map((task) => (
                        <button
                          key={task.id}
                          className={`pill-button ${settingsTask === task.id ? "active" : ""}`}
                          onClick={() => setSettingsTask(task.id)}
                        >
                          {task.label}
                        </button>
                      ))}
                    </div>
                    {activeTaskProfile ? (
                      <>
                        <div className="project-grid">
                          <label className="field">
                            <span>Model Override</span>
                            <input
                              value={activeTaskProfile.model_override ?? ""}
                              placeholder="Uses global default model"
                              onChange={(event) =>
                                setModelSettingsDraft({
                                  ...modelSettingsDraft,
                                  task_profiles: {
                                    ...modelSettingsDraft.task_profiles,
                                    [settingsTask]: {
                                      ...activeTaskProfile,
                                      model_override: toOptionalString(event.target.value),
                                    },
                                  },
                                })
                              }
                            />
                          </label>
                          <label className="field">
                            <span>Temperature Override</span>
                            <input
                              value={activeTaskProfile.temperature_override ?? ""}
                              placeholder="inherit"
                              onChange={(event) =>
                                setModelSettingsDraft({
                                  ...modelSettingsDraft,
                                  task_profiles: {
                                    ...modelSettingsDraft.task_profiles,
                                    [settingsTask]: {
                                      ...activeTaskProfile,
                                      temperature_override: toOptionalNumber(event.target.value),
                                    },
                                  },
                                })
                              }
                            />
                          </label>
                          <label className="field">
                            <span>Top P Override</span>
                            <input
                              value={activeTaskProfile.top_p_override ?? ""}
                              placeholder="inherit"
                              onChange={(event) =>
                                setModelSettingsDraft({
                                  ...modelSettingsDraft,
                                  task_profiles: {
                                    ...modelSettingsDraft.task_profiles,
                                    [settingsTask]: {
                                      ...activeTaskProfile,
                                      top_p_override: toOptionalNumber(event.target.value),
                                    },
                                  },
                                })
                              }
                            />
                          </label>
                          <label className="field">
                            <span>Max Output Tokens Override</span>
                            <input
                              value={activeTaskProfile.max_output_tokens_override ?? ""}
                              placeholder="inherit"
                              onChange={(event) =>
                                setModelSettingsDraft({
                                  ...modelSettingsDraft,
                                  task_profiles: {
                                    ...modelSettingsDraft.task_profiles,
                                    [settingsTask]: {
                                      ...activeTaskProfile,
                                      max_output_tokens_override: toOptionalNumber(event.target.value),
                                    },
                                  },
                                })
                              }
                            />
                          </label>
                          <label className="field scenario-field">
                            <span>System Template</span>
                            <textarea
                              rows={8}
                              value={activeTaskProfile.system_template}
                              onChange={(event) =>
                                setModelSettingsDraft({
                                  ...modelSettingsDraft,
                                  task_profiles: {
                                    ...modelSettingsDraft.task_profiles,
                                    [settingsTask]: {
                                      ...activeTaskProfile,
                                      system_template: event.target.value,
                                    },
                                  },
                                })
                              }
                            />
                          </label>
                          <label className="field scenario-field">
                            <span>User Template</span>
                            <textarea
                              rows={14}
                              value={activeTaskProfile.user_template}
                              onChange={(event) =>
                                setModelSettingsDraft({
                                  ...modelSettingsDraft,
                                  task_profiles: {
                                    ...modelSettingsDraft.task_profiles,
                                    [settingsTask]: {
                                      ...activeTaskProfile,
                                      user_template: event.target.value,
                                    },
                                  },
                                })
                              }
                            />
                          </label>
                        </div>
                        <div className="settings-card">
                          <h3>Variable Reference</h3>
                          {activeTaskCatalog?.variables.length ? (
                            <div className="token-cloud">
                              {activeTaskCatalog.variables.map((token) => (
                                <span key={token} className="code-chip">
                                  {`{{${token}}}`}
                                </span>
                              ))}
                            </div>
                          ) : (
                            <p className="muted-text">No template variables are registered for this task.</p>
                          )}
                        </div>
                      </>
                    ) : null}
                  </div>
                </section>

                <section className="settings-grid settings-grid-wide">
                  <div className="panel">
                    <div className="panel-header">
                      <h2>Preview And Test</h2>
                      <div className="action-row">
                        <button className="primary-button" onClick={() => void handlePreviewPrompt()}>
                          {promptPreviewLoading ? "Working..." : promptPreviewRunModel ? "Render And Run" : "Render Prompt"}
                        </button>
                        <button className="ghost-button" onClick={handleClearPromptPreviewContext} disabled={!promptPreviewResult}>
                          Clear LLM Context
                        </button>
                      </div>
                    </div>
                    <p className="muted-text">
                      Render the effective system and user prompts with the current project context, then optionally run the local model through the active runtime.
                    </p>
                    <div className="project-grid">
                      <label className="field">
                        <span>Task</span>
                        <select value={previewTask} onChange={(event) => setPreviewTask(event.target.value as PromptTask)}>
                          {availableTasks.map((task) => (
                            <option key={task.id} value={task.id}>
                              {task.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="field">
                        <span>Scene Context</span>
                        <input readOnly value={selectedScene ? `${selectedScene.order.toString().padStart(2, "0")} • ${selectedScene.title}` : "No scene selected"} />
                      </label>
                      <label className="field">
                        <span>Sequence Context</span>
                        <input
                          readOnly
                          value={selectedSequence ? `${selectedSequence.order.toString().padStart(2, "0")} • ${selectedSequence.title}` : "No sequence selected"}
                        />
                      </label>
                    </div>
                    <label className="toggle-row">
                      <input
                        type="checkbox"
                        checked={promptPreviewRunModel}
                        onChange={(event) => setPromptPreviewRunModel(event.target.checked)}
                      />
                      Run the model after rendering the prompt
                    </label>
                    {promptPreviewResult ? (
                      <div className="preview-results">
                        <div className="assistant-columns preview-columns">
                          <div className="assistant-card">
                            <h3>Effective Runtime</h3>
                            <ul className="flat-list">
                              <li>Provider: {promptPreviewResult.provider}</li>
                              <li>Model: {promptPreviewResult.effective_model}</li>
                            </ul>
                          </div>
                          <div className="assistant-card">
                            <h3>Parameters</h3>
                            <pre className="code-block">{JSON.stringify(promptPreviewResult.effective_parameters, null, 2)}</pre>
                          </div>
                          <div className="assistant-card">
                            <h3>Status</h3>
                            <p className="muted-text">{promptPreviewResult.error_text ?? "Prompt rendered successfully."}</p>
                          </div>
                        </div>
                        <label className="field">
                          <span>System Prompt</span>
                          <textarea readOnly rows={8} value={promptPreviewResult.system_prompt} />
                        </label>
                        <label className="field">
                          <span>User Prompt</span>
                          <textarea readOnly rows={12} value={promptPreviewResult.user_prompt} />
                        </label>
                        <label className="field">
                          <span>Rendered Variables</span>
                          <textarea readOnly rows={8} value={JSON.stringify(promptPreviewResult.rendered_variables, null, 2)} />
                        </label>
                        {promptPreviewResult.output_text ? (
                          <label className="field">
                            <span>Model Output</span>
                            <textarea readOnly rows={12} value={promptPreviewResult.output_text} />
                          </label>
                        ) : null}
                      </div>
                    ) : (
                      <p className="muted-text">Render a prompt to inspect the exact text and effective model parameters for the selected task.</p>
                    )}
                  </div>

                  <div className="panel">
                    <div className="panel-header">
                      <h2>Import, Export, And Reset</h2>
                    </div>
                    <div className="settings-card">
                      <h3>Export</h3>
                      <p className="muted-text">Download the current runtime, shared defaults, and task prompt profiles as JSON.</p>
                      <button className="ghost-button" onClick={handleExportModelSettings}>
                        Export Settings JSON
                      </button>
                    </div>
                    <div className="settings-card">
                      <h3>Import</h3>
                      <p className="muted-text">Load a previously exported settings file into the editor, then save when you are happy with it.</p>
                      <label className="upload-button">
                        Import Settings JSON
                        <input type="file" accept="application/json" onChange={(event) => void handleImportModelSettings(event.target.files?.[0] ?? null)} />
                      </label>
                    </div>
                    <div className="settings-card">
                      <h3>Reset</h3>
                      <p className="muted-text">Reset the selected task profile or the full settings bundle back to the seeded defaults that ship with the app.</p>
                      <div className="action-row">
                        <button className="ghost-button" onClick={handleResetSelectedTask}>
                          Reset Selected Task
                        </button>
                        <button className="ghost-button" onClick={handleResetAllModelSettings}>
                          Reset All Defaults
                        </button>
                      </div>
                    </div>
                    <div className="settings-card">
                      <h3>Connection Status</h3>
                      {assistantConnectionTestResult ? (
                        <div className="connection-result">
                          <p className="assistant-summary">{assistantConnectionTestResult.message}</p>
                          <ul className="flat-list">
                            <li>Configured URL: {assistantConnectionTestResult.base_url}</li>
                            <li>Resolved URL: {assistantConnectionTestResult.resolved_base_url ?? assistantConnectionTestResult.base_url}</li>
                            <li>Latency: {assistantConnectionTestResult.response_ms ?? 0} ms</li>
                          </ul>
                          <div className="capability-grid">
                            <div className="capability-card">
                              <strong>Text</strong>
                              <span
                                className={`badge ${
                                  assistantConnectionTestResult.capabilities.text ? "success" : "warning"
                                }`}
                              >
                                {assistantConnectionTestResult.capabilities.text ? "ready" : "not ready"}
                              </span>
                            </div>
                            <div className="capability-card">
                              <strong>JSON</strong>
                              <span
                                className={`badge ${
                                  assistantConnectionTestResult.capabilities.json ? "success" : "warning"
                                }`}
                              >
                                {assistantConnectionTestResult.capabilities.json ? "ready" : "not ready"}
                              </span>
                            </div>
                            <div className="capability-card">
                              <strong>Vision</strong>
                              <span
                                className={`badge ${
                                  assistantConnectionTestResult.capabilities.vision ? "success" : "warning"
                                }`}
                              >
                                {assistantConnectionTestResult.capabilities.vision ? "ready" : "fallback"}
                              </span>
                            </div>
                          </div>
                          {assistantConnectionTestResult.vision_message ? (
                            <p
                              className={`runtime-note ${
                                assistantConnectionTestResult.capabilities.vision ? "" : "warning-text"
                              }`}
                            >
                              {assistantConnectionTestResult.vision_message}
                            </p>
                          ) : null}
                          {assistantConnectionTestResult.available_models.length > 0 ? (
                            <div className="token-cloud">
                              {assistantConnectionTestResult.available_models.map((model) => (
                                <span key={model} className="code-chip">
                                  {model}
                                </span>
                              ))}
                            </div>
                          ) : null}
                        </div>
                      ) : (
                        <p className="muted-text">
                          Run a connection test to verify reachability, inspect the models reported by the runtime,
                          and confirm whether multimodal vision is actually ready.
                        </p>
                      )}
                    </div>
                  </div>
                </section>
              </>
            ) : (
              <section className="panel">
                <p className="muted-text">Loading model settings.</p>
              </section>
            )}
          </>
        ) : hasProject && project && projectDraft ? (
          <>
            {projectNeedsUpgrade ? (
              <section className="panel upgrade-panel">
                <div className="panel-header">
                  <h2>Upgrade To Movie 2.0</h2>
                  <span className="badge warning">legacy v1</span>
                </div>
                <p className="muted-text">
                  This project still uses the old flat 5-10 second beat model. Upgrade it to duplicate the project into
                  the new movie-scene-sequence workflow.
                </p>
                <p className="muted-text">Legacy beats ready for conversion: {project.legacy_sequence_count}</p>
                <button className="primary-button" onClick={() => void handleUpgradeProject()}>
                  Upgrade To 2.0
                </button>
              </section>
            ) : null}

            {workspaceTab === "scenario" ? (
              <>
                <section className="panel project-editor">
                  <div className="panel-header">
                    <h2>Scenario Console</h2>
                    <div className="action-row">
                      <button
                        className="ghost-button"
                        onClick={() => void handleRunScenarioAssistant()}
                        disabled={!isProjectEditable}
                      >
                        {assistantLoading ? "Running Coach..." : "Run Local Story Coach"}
                      </button>
                      <button
                        className="primary-button"
                        onClick={() => void handleGenerateScenes("scenario")}
                        disabled={projectNeedsUpgrade || !isProjectEditable}
                      >
                        Generate Scenes From Scenario
                      </button>
                    </div>
                  </div>
                  <p className="muted-text">
                    Editing the movie runtime here rebalances unlocked scene durations across the project while keeping
                    each scene inside the 30-90 second range.
                  </p>

                  <div className="project-grid">
                    <label className="field">
                      <span>Title</span>
                      <input
                        disabled={!isProjectEditable}
                        value={projectDraft.name}
                        onChange={(event) => {
                          setProjectDraft({ ...projectDraft, name: event.target.value });
                          setProjectDirty(true);
                        }}
                      />
                    </label>
                    <label className="field">
                      <span>Genre</span>
                      <input
                        disabled={!isProjectEditable}
                        value={projectDraft.genre}
                        onChange={(event) => {
                          setProjectDraft({ ...projectDraft, genre: event.target.value });
                          setProjectDirty(true);
                        }}
                      />
                    </label>
                    <label className="field">
                      <span>Tone</span>
                      <input
                        disabled={!isProjectEditable}
                        value={projectDraft.tone}
                        onChange={(event) => {
                          setProjectDraft({ ...projectDraft, tone: event.target.value });
                          setProjectDirty(true);
                        }}
                      />
                    </label>
                    <label className="field">
                      <span>Target Duration (s)</span>
                      <input
                        disabled={!isProjectEditable}
                        type="number"
                        min={180}
                        max={300}
                        value={projectDraft.target_duration_s}
                        onChange={(event) => {
                          setProjectDraft({ ...projectDraft, target_duration_s: Number(event.target.value) });
                          setProjectDirty(true);
                        }}
                      />
                    </label>
                    <label className="field scenario-field">
                      <span>Scenario</span>
                      <textarea
                        disabled={!isProjectEditable}
                        rows={12}
                        value={projectDraft.scenario_text}
                        onChange={(event) => {
                          setProjectDraft({ ...projectDraft, scenario_text: event.target.value });
                          setProjectDirty(true);
                        }}
                      />
                    </label>
                  </div>
                </section>

                <section className="panel beat-board-panel">
                  <div className="panel-header">
                    <h2>3-Act Beat Board</h2>
                    <div className="action-row">
                      <span className={`badge ${statusTone(project.beat_board_status)}`}>{project.beat_board_status}</span>
                      <button className="ghost-button" onClick={() => void handleGenerateBeatBoard()} disabled={!isProjectEditable}>
                        {beatBoardLoading ? "Generating..." : "Generate Beat Board"}
                      </button>
                      <button
                        className="ghost-button"
                        onClick={() => void handleApplyBeatBoardToScenario()}
                        disabled={!isProjectEditable || !beatBoard || beatBoard.beats.length === 0}
                      >
                        Apply Beat Board To Scenario
                      </button>
                      <button
                        className="primary-button"
                        onClick={() => void handleGenerateScenes("beat_board")}
                        disabled={!isProjectEditable || !beatBoard || beatBoard.beats.length === 0}
                      >
                        Generate Scenes From Beat Board
                      </button>
                    </div>
                  </div>
                  <p className="muted-text">
                    Build the film in three acts before scene generation. You can edit beats directly, add manual beats,
                    reorder them, and then use the board as the source for scene generation.
                  </p>
                  <div className="beat-board-grid">
                    {[1, 2, 3].map((actIndex) => (
                      <div key={actIndex} className="beat-act-column">
                        <div className="panel-header">
                          <h3>Act {actIndex}</h3>
                          <button
                            className="ghost-button"
                            onClick={() => void handleCreateBeat(actIndex)}
                            disabled={!isProjectEditable}
                          >
                            Add Beat
                          </button>
                        </div>
                        <div className="beat-card-stack">
                          {(beatsByAct.get(actIndex) ?? []).length === 0 ? (
                            <p className="muted-text">No beats in this act yet.</p>
                          ) : (
                            (beatsByAct.get(actIndex) ?? []).map((beat) => (
                              <div key={beat.id} className="settings-card beat-card">
                                <div className="panel-header">
                                  <span className="badge muted">#{beat.order_index}</span>
                                  <div className="action-row">
                                    <button
                                      className="ghost-button"
                                      onClick={() => void handleMoveBeat(beat, "up")}
                                      disabled={!isProjectEditable}
                                    >
                                      Up
                                    </button>
                                    <button
                                      className="ghost-button"
                                      onClick={() => void handleMoveBeat(beat, "down")}
                                      disabled={!isProjectEditable}
                                    >
                                      Down
                                    </button>
                                    <button
                                      className="ghost-button"
                                      onClick={() => void handleDeleteBeat(beat.id)}
                                      disabled={!isProjectEditable}
                                    >
                                      Delete
                                    </button>
                                  </div>
                                </div>
                                <label className="field">
                                  <span>Title</span>
                                  <input
                                    disabled={!isProjectEditable}
                                    value={beat.title}
                                    onChange={(event) =>
                                      setBeatBoardDraft((current) =>
                                        current
                                          ? {
                                              ...current,
                                              beats: current.beats.map((item) =>
                                                item.id === beat.id ? { ...item, title: event.target.value } : item,
                                              ),
                                            }
                                          : current,
                                      )
                                    }
                                    onBlur={(event) => void handleSaveBeat(beat.id, { title: event.target.value })}
                                  />
                                </label>
                                <label className="field">
                                  <span>Summary</span>
                                  <textarea
                                    disabled={!isProjectEditable}
                                    rows={4}
                                    value={beat.summary_text}
                                    onChange={(event) =>
                                      setBeatBoardDraft((current) =>
                                        current
                                          ? {
                                              ...current,
                                              beats: current.beats.map((item) =>
                                                item.id === beat.id ? { ...item, summary_text: event.target.value } : item,
                                              ),
                                            }
                                          : current,
                                      )
                                    }
                                    onBlur={(event) => void handleSaveBeat(beat.id, { summary_text: event.target.value })}
                                  />
                                </label>
                                <label className="field">
                                  <span>Purpose</span>
                                  <textarea
                                    disabled={!isProjectEditable}
                                    rows={3}
                                    value={beat.purpose_text}
                                    onChange={(event) =>
                                      setBeatBoardDraft((current) =>
                                        current
                                          ? {
                                              ...current,
                                              beats: current.beats.map((item) =>
                                                item.id === beat.id ? { ...item, purpose_text: event.target.value } : item,
                                              ),
                                            }
                                          : current,
                                      )
                                    }
                                    onBlur={(event) => void handleSaveBeat(beat.id, { purpose_text: event.target.value })}
                                  />
                                </label>
                                <label className="field compact">
                                  <span>Act</span>
                                  <select
                                    disabled={!isProjectEditable}
                                    value={beat.act_index}
                                    onChange={(event) => void handleSaveBeat(beat.id, { act_index: Number(event.target.value) })}
                                  >
                                    <option value={1}>Act 1</option>
                                    <option value={2}>Act 2</option>
                                    <option value={3}>Act 3</option>
                                  </select>
                                </label>
                              </div>
                            ))
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>

                {projectModelSettingsOverrideDraft ? (
                  <section className="panel project-override-panel">
                    <div className="panel-header">
                      <h2>Project Prompt Profile</h2>
                      <span className={`badge ${projectModelSettingsOverrideDraft.enabled ? "warning" : "muted"}`}>
                        {projectModelSettingsOverrideDraft.enabled ? "override active" : "using global defaults"}
                      </span>
                    </div>
                    <p className="muted-text">
                      Override the prompt profile for this film without changing the global runtime or the other projects in the studio.
                    </p>
                    <label className="toggle-row">
                      <input
                        type="checkbox"
                        disabled={!isProjectEditable}
                        checked={projectModelSettingsOverrideDraft.enabled}
                        onChange={(event) =>
                          setProjectModelSettingsOverrideDraft({
                            ...projectModelSettingsOverrideDraft,
                            enabled: event.target.checked,
                          })
                        }
                      />
                      Use project-specific model settings
                    </label>
                    <div className="project-grid">
                      <label className="field">
                        <span>Default Model Override</span>
                        <input
                          disabled={!isProjectEditable}
                          value={projectModelSettingsOverrideDraft.default_model_override ?? ""}
                          placeholder="inherit global default"
                          onChange={(event) =>
                            setProjectModelSettingsOverrideDraft({
                              ...projectModelSettingsOverrideDraft,
                              default_model_override: toOptionalString(event.target.value),
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Temperature Override</span>
                        <input
                          disabled={!isProjectEditable}
                          value={projectModelSettingsOverrideDraft.generation_defaults_override.temperature ?? ""}
                          placeholder="inherit"
                          onChange={(event) =>
                            setProjectModelSettingsOverrideDraft({
                              ...projectModelSettingsOverrideDraft,
                              generation_defaults_override: {
                                ...projectModelSettingsOverrideDraft.generation_defaults_override,
                                temperature: toOptionalNumber(event.target.value),
                              },
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Top P Override</span>
                        <input
                          disabled={!isProjectEditable}
                          value={projectModelSettingsOverrideDraft.generation_defaults_override.top_p ?? ""}
                          placeholder="inherit"
                          onChange={(event) =>
                            setProjectModelSettingsOverrideDraft({
                              ...projectModelSettingsOverrideDraft,
                              generation_defaults_override: {
                                ...projectModelSettingsOverrideDraft.generation_defaults_override,
                                top_p: toOptionalNumber(event.target.value),
                              },
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Max Tokens Override</span>
                        <input
                          disabled={!isProjectEditable}
                          value={projectModelSettingsOverrideDraft.generation_defaults_override.max_output_tokens ?? ""}
                          placeholder="inherit"
                          onChange={(event) =>
                            setProjectModelSettingsOverrideDraft({
                              ...projectModelSettingsOverrideDraft,
                              generation_defaults_override: {
                                ...projectModelSettingsOverrideDraft.generation_defaults_override,
                                max_output_tokens: toOptionalNumber(event.target.value),
                              },
                            })
                          }
                        />
                      </label>
                    </div>
                    <div className="focus-row">
                      {availableTasks.map((task) => (
                        <button
                          key={task.id}
                          className={`pill-button ${overrideTask === task.id ? "active" : ""}`}
                          onClick={() => setOverrideTask(task.id)}
                          disabled={!isProjectEditable}
                        >
                          {task.label}
                        </button>
                      ))}
                    </div>
                    {activeProjectOverrideTask ? (
                      <div className="project-grid">
                        <label className="field">
                          <span>Task Model Override</span>
                          <input
                            disabled={!isProjectEditable}
                            value={activeProjectOverrideTask.model_override ?? ""}
                            placeholder="inherit"
                            onChange={(event) =>
                              setProjectModelSettingsOverrideDraft({
                                ...projectModelSettingsOverrideDraft,
                                task_profiles: {
                                  ...projectModelSettingsOverrideDraft.task_profiles,
                                  [overrideTask]: {
                                    ...activeProjectOverrideTask,
                                    model_override: toOptionalString(event.target.value),
                                  },
                                },
                              })
                            }
                          />
                        </label>
                        <label className="field">
                          <span>Task Temperature Override</span>
                          <input
                            disabled={!isProjectEditable}
                            value={activeProjectOverrideTask.temperature_override ?? ""}
                            placeholder="inherit"
                            onChange={(event) =>
                              setProjectModelSettingsOverrideDraft({
                                ...projectModelSettingsOverrideDraft,
                                task_profiles: {
                                  ...projectModelSettingsOverrideDraft.task_profiles,
                                  [overrideTask]: {
                                    ...activeProjectOverrideTask,
                                    temperature_override: toOptionalNumber(event.target.value),
                                  },
                                },
                              })
                            }
                          />
                        </label>
                        <label className="field">
                          <span>Task Top P Override</span>
                          <input
                            disabled={!isProjectEditable}
                            value={activeProjectOverrideTask.top_p_override ?? ""}
                            placeholder="inherit"
                            onChange={(event) =>
                              setProjectModelSettingsOverrideDraft({
                                ...projectModelSettingsOverrideDraft,
                                task_profiles: {
                                  ...projectModelSettingsOverrideDraft.task_profiles,
                                  [overrideTask]: {
                                    ...activeProjectOverrideTask,
                                    top_p_override: toOptionalNumber(event.target.value),
                                  },
                                },
                              })
                            }
                          />
                        </label>
                        <label className="field">
                          <span>Task Max Tokens Override</span>
                          <input
                            disabled={!isProjectEditable}
                            value={activeProjectOverrideTask.max_output_tokens_override ?? ""}
                            placeholder="inherit"
                            onChange={(event) =>
                              setProjectModelSettingsOverrideDraft({
                                ...projectModelSettingsOverrideDraft,
                                task_profiles: {
                                  ...projectModelSettingsOverrideDraft.task_profiles,
                                  [overrideTask]: {
                                    ...activeProjectOverrideTask,
                                    max_output_tokens_override: toOptionalNumber(event.target.value),
                                  },
                                },
                              })
                            }
                          />
                        </label>
                        <label className="field scenario-field">
                          <span>Task System Template Override</span>
                          <textarea
                            disabled={!isProjectEditable}
                            rows={6}
                            value={activeProjectOverrideTask.system_template ?? ""}
                            placeholder="inherit the global system template when empty"
                            onChange={(event) =>
                              setProjectModelSettingsOverrideDraft({
                                ...projectModelSettingsOverrideDraft,
                                task_profiles: {
                                  ...projectModelSettingsOverrideDraft.task_profiles,
                                  [overrideTask]: {
                                    ...activeProjectOverrideTask,
                                    system_template: toOptionalString(event.target.value),
                                  },
                                },
                              })
                            }
                          />
                        </label>
                        <label className="field scenario-field">
                          <span>Task User Template Override</span>
                          <textarea
                            disabled={!isProjectEditable}
                            rows={8}
                            value={activeProjectOverrideTask.user_template ?? ""}
                            placeholder="inherit the global user template when empty"
                            onChange={(event) =>
                              setProjectModelSettingsOverrideDraft({
                                ...projectModelSettingsOverrideDraft,
                                task_profiles: {
                                  ...projectModelSettingsOverrideDraft.task_profiles,
                                  [overrideTask]: {
                                    ...activeProjectOverrideTask,
                                    user_template: toOptionalString(event.target.value),
                                  },
                                },
                              })
                            }
                          />
                        </label>
                      </div>
                    ) : null}
                    <div className="action-row">
                      <button
                        className="primary-button"
                        onClick={() => void handleSaveProjectOverride()}
                        disabled={!isProjectEditable}
                      >
                        {projectModelSettingsLoading ? "Working..." : "Save Project Override"}
                      </button>
                      <button className="ghost-button" onClick={handleResetProjectOverride} disabled={!isProjectEditable}>
                        Reset Project Override
                      </button>
                    </div>
                  </section>
                ) : null}

                <section className="assistant-grid">
                  <div className="panel assistant-panel">
                    <div className="panel-header">
                      <h2>Local Story Coach</h2>
                      {assistantResult ? (
                        <span className={`badge ${assistantResult.source === "local_model" ? "success" : "warning"}`}>
                          {assistantResult.source === "local_model" ? "local model" : "fallback"}
                        </span>
                      ) : null}
                    </div>
                    <p className="muted-text">
                      Use the local model configured in Settings to strengthen the 3-5 minute scenario before scene and
                      sequence generation.
                    </p>
                    <div className="focus-row">
                      {scenarioFocusOptions.map((option) => (
                        <button
                          key={option.id}
                          className={`pill-button ${assistantFocus === option.id ? "active" : ""}`}
                          onClick={() => setAssistantFocus(option.id)}
                        >
                          {option.label}
                        </button>
                      ))}
                    </div>
                    <label className="toggle-row assistant-toggle">
                      <input
                        type="checkbox"
                        checked={assistantRewriteScenario}
                        onChange={(event) => setAssistantRewriteScenario(event.target.checked)}
                      />
                      Return a revised movie scenario draft
                    </label>
                    <label className="field">
                      <span>Instruction</span>
                      <textarea
                        rows={4}
                        value={assistantInstruction}
                        placeholder="Example: strengthen the midpoint turn, sharpen the finale, and give each major scene a stronger emotional objective."
                        onChange={(event) => setAssistantInstruction(event.target.value)}
                      />
                    </label>
                    <div className="action-row">
                      <button className="primary-button" onClick={() => void handleRunScenarioAssistant()}>
                        {assistantLoading ? "Running Coach..." : "Ask The Local Model"}
                      </button>
                      <button className="ghost-button" onClick={() => setWorkspaceTab("settings")}>
                        Open Settings
                      </button>
                    </div>
                  </div>

                  <div className="panel assistant-output">
                    <div className="panel-header">
                      <h2>Coach Output</h2>
                      {assistantResult ? (
                        <span className="badge muted">
                          {assistantResult.provider} • {assistantResult.model}
                        </span>
                      ) : null}
                    </div>
                    {assistantResult ? (
                      <div className="assistant-content">
                        <p className="assistant-summary">{assistantResult.summary}</p>
                        <div className="assistant-columns">
                          <div className="assistant-card">
                            <h3>Suggestions</h3>
                            <ul className="flat-list">
                              {assistantResult.suggestions.map((item) => (
                                <li key={item}>{item}</li>
                              ))}
                            </ul>
                          </div>
                          <div className="assistant-card">
                            <h3>Beat Notes</h3>
                            <ul className="flat-list">
                              {assistantResult.beat_notes.map((item) => (
                                <li key={item}>{item}</li>
                              ))}
                            </ul>
                          </div>
                          <div className="assistant-card">
                            <h3>Title Options</h3>
                            <ul className="flat-list">
                              {assistantResult.title_options.map((item) => (
                                <li key={item}>{item}</li>
                              ))}
                            </ul>
                          </div>
                        </div>
                        <label className="field">
                          <span>Revised Scenario</span>
                          <textarea readOnly rows={10} value={assistantResult.revised_scenario_text} />
                        </label>
                        <div className="action-row">
                          <button className="primary-button" onClick={applyAssistantScenario} disabled={!isProjectEditable}>
                            Apply Revised Scenario
                          </button>
                          <button
                            className="ghost-button"
                            onClick={() => void copyToClipboard(assistantResult.revised_scenario_text, "Revised scenario")}
                          >
                            Copy Revised Scenario
                          </button>
                        </div>
                      </div>
                    ) : (
                      <p className="muted-text">
                        Run the local story coach to get a development pass, title ideas, beat notes, and an optional
                        revised scenario draft.
                      </p>
                    )}
                  </div>
                </section>
              </>
            ) : workspaceTab === "characters" ? (
              <>
                <section className="panel workflow-panel">
                  <div className="panel-header">
                    <h2>Project Characters</h2>
                    <span className="badge muted">{project?.characters?.length ?? 0} characters</span>
                    <div className="action-row">
                      <button
                        className="ghost-button"
                        onClick={() => void handleGenerateCharacters(true)}
                        disabled={loading || !isProjectEditable}
                      >
                        {loading ? "Generating..." : "Regenerate Characters"}
                      </button>
                      <button
                        className="primary-button"
                        onClick={() => void handleAddCharacter()}
                        disabled={loading || !isProjectEditable}
                      >
                        Add Character
                      </button>
                    </div>
                  </div>
                </section>
                <div className="character-list" style={{ padding: "1rem" }}>
                  {project?.characters?.length === 0 ? (
                    <div className="panel empty-state">
                      <p className="muted-text">No characters defined. Generate or add characters.</p>
                      <button
                        className="primary-button"
                        onClick={() => void handleGenerateCharacters(false)}
                        disabled={loading || !isProjectEditable}
                        style={{ marginTop: "1rem" }}
                      >
                        {loading ? "Generating..." : "Generate Characters"}
                      </button>
                    </div>
                  ) : (
                    project?.characters?.map((char) => (
                      <CharacterCard
                        key={char.id}
                        character={char}
                        isProjectEditable={isProjectEditable}
                        onUpdate={handleUpdateCharacter}
                        onDelete={handleDeleteCharacter}
                        onGenerateImage={handleGenerateCharacterImage}
                      />
                    ))
                  )}
                </div>
              </>
            ) : workspaceTab === "scenes" ? (
              <>
                <section className="panel workflow-panel">
                  <div className="panel-header">
                    <h2>Scene Breakdown</h2>
                    <div className="action-row">
                      <button className="ghost-button" onClick={() => void handleGenerateScenes()} disabled={!isProjectEditable}>
                        Regenerate Scenes
                      </button>
                      <button
                        className="ghost-button"
                        onClick={() => void handleGenerateSceneImagePrompts()}
                        disabled={!isProjectEditable}
                      >
                        Generate Scene Image Prompts
                      </button>
                      <button className="ghost-button" onClick={() => void handleGenerateSequences()} disabled={!isProjectEditable}>
                        Generate Sequences
                      </button>
                    </div>
                  </div>
                  <p className="muted-text">
                    Build 3-4 major scenes of 30-90 seconds. Each scene gets a first-image prompt and can later receive
                    its own uploaded reference image before sequence refinement.
                  </p>
                </section>

                <section className="overview-grid">
                  <div className="panel package-panel">
                    <div className="panel-header">
                      <h2>Movie Overview</h2>
                      <span className={`badge ${statusTone(project.prompt_package_status)}`}>{project.prompt_package_status}</span>
                    </div>
                    <div className="stat-grid">
                      <div className="stat-card">
                        <span>Scenes</span>
                        <strong>{scenes.length}</strong>
                      </div>
                      <div className="stat-card">
                        <span>Total Scene Runtime</span>
                        <strong>{totalSceneDuration}s</strong>
                      </div>
                      <div className="stat-card">
                        <span>Sequences</span>
                        <strong>{totalSequenceCount}</strong>
                      </div>
                    </div>
                    <label className="field">
                      <span>Style Anchor</span>
                      <textarea
                        disabled={!isProjectEditable}
                        rows={4}
                        value={projectDraft.style_anchor_text}
                        onChange={(event) => {
                          setProjectDraft({ ...projectDraft, style_anchor_text: event.target.value });
                          setProjectDirty(true);
                        }}
                      />
                    </label>
                    <div className="download-row">
                      <a className="ghost-button link-button" href={promptPackageJsonUrl(project.id)} target="_blank" rel="noreferrer">
                        Download JSON
                      </a>
                      <a className="ghost-button link-button" href={promptPackageMarkdownUrl(project.id)} target="_blank" rel="noreferrer">
                        Download Markdown
                      </a>
                    </div>
                  </div>

                  <div className="panel">
                    <div className="panel-header">
                      <h2>Scene Progress</h2>
                      <span className="badge muted">{scenes.length} scenes</span>
                    </div>
                    <div className="flat-list">
                      {scenes.length === 0 ? (
                        <p className="muted-text">Generate scenes from the Scenario tab first.</p>
                      ) : (
                        scenes.map((scene) => (
                          <div key={scene.id} className="timeline-summary">
                            <strong>
                              Scene {scene.order.toString().padStart(2, "0")} • {scene.target_duration_s}s
                            </strong>
                            <span className="muted-text">
                              {scene.duration_locked ? "Locked runtime" : "Unlocked runtime"} •{" "}
                              Prompt {scene.first_image_prompt_text ? "ready" : "missing"} • Image{" "}
                              {scene.first_image_asset ? "uploaded" : "optional"} • {scene.sequences.length} sequences
                            </span>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </section>

                <section className="editor-grid">
                  <div className="panel scene-timeline">
                    <div className="panel-header">
                      <h2>Scenes</h2>
                      <span className="badge muted">{scenes.length}</span>
                    </div>
                    <div className="scene-list">
                      {scenes.map((scene) => (
                        <button
                          key={scene.id}
                          className={`scene-card ${scene.id === selectedSceneId ? "active" : ""}`}
                          onClick={() => setSelectedSceneId(scene.id)}
                        >
                          <div className="scene-card-top">
                            <span className="scene-order">{scene.order.toString().padStart(2, "0")}</span>
                            <span className={`badge ${scene.first_image_asset ? "success" : scene.first_image_prompt_text ? "warning" : "muted"}`}>
                              {scene.first_image_asset ? "image ready" : scene.first_image_prompt_text ? "prompted" : "draft"}
                            </span>
                          </div>
                          <strong>{scene.title}</strong>
                          <p>{scene.narrative_text}</p>
                            <div className="scene-meta">
                              <span>{scene.target_duration_s}s</span>
                              <span>{scene.duration_locked ? "Locked" : "Unlocked"}</span>
                              <span>{scene.sequences.length} sequences</span>
                            </div>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="panel scene-inspector">
                    <div className="panel-header">
                      <h2>Scene Inspector</h2>
                      {sceneDraft ? (
                        <button
                          className="ghost-button"
                          onClick={() => void copyToClipboard(sceneDraft.first_image_prompt_text, "Scene first-image prompt")}
                          disabled={!sceneDraft.first_image_prompt_text}
                        >
                          Copy Scene Prompt
                        </button>
                      ) : null}
                    </div>

                    {sceneDraft && selectedScene ? (
                      <div className="inspector-grid">
                        <label className="field compact">
                          <span>Order</span>
                          <input
                            disabled={!isProjectEditable}
                            type="number"
                            min={1}
                            max={10}
                            value={sceneDraft.order}
                            onChange={(event) => {
                              setSceneDraft({ ...sceneDraft, order: Number(event.target.value) });
                              setSceneDirty(true);
                            }}
                          />
                        </label>
                        <label className="field compact">
                          <span>Duration (s)</span>
                          <input
                            disabled={!isProjectEditable}
                            type="number"
                            min={30}
                            max={90}
                            value={sceneDraft.target_duration_s}
                            onChange={(event) => {
                              setSceneDraft({ ...sceneDraft, target_duration_s: Number(event.target.value) });
                              setSceneDirty(true);
                            }}
                          />
                        </label>
                        <label className="toggle-row">
                          <input
                            type="checkbox"
                            disabled={!isProjectEditable}
                            checked={sceneDraft.duration_locked}
                            onChange={(event) => {
                              setSceneDraft({ ...sceneDraft, duration_locked: event.target.checked });
                              setSceneDirty(true);
                            }}
                          />
                          Lock this scene duration during movie and sequence rebalancing
                        </label>
                        <label className="field">
                          <span>Title</span>
                          <input
                            disabled={!isProjectEditable}
                            value={sceneDraft.title}
                            onChange={(event) => {
                              setSceneDraft({ ...sceneDraft, title: event.target.value });
                              setSceneDirty(true);
                            }}
                          />
                        </label>
                        <label className="field">
                          <span>Narrative Beat</span>
                          <textarea
                            disabled={!isProjectEditable}
                            rows={5}
                            value={sceneDraft.narrative_text}
                            onChange={(event) => {
                              setSceneDraft({ ...sceneDraft, narrative_text: event.target.value });
                              setSceneDirty(true);
                            }}
                          />
                        </label>
                        <label className="field">
                          <span>First Image Prompt</span>
                          <textarea
                            disabled={!isProjectEditable}
                            rows={6}
                            value={sceneDraft.first_image_prompt_text}
                            onChange={(event) => {
                              setSceneDraft({ ...sceneDraft, first_image_prompt_text: event.target.value });
                              setSceneDirty(true);
                            }}
                          />
                        </label>
                        <div className="action-row span-all">
                          <button
                            className="ghost-button"
                            onClick={() => void handleGenerateSceneImagePrompts([selectedScene.id])}
                            disabled={!isProjectEditable}
                          >
                            Regenerate This Scene Prompt
                          </button>
                          <button
                            className="ghost-button"
                            onClick={() => void handleGenerateSequences([selectedScene.id])}
                            disabled={!isProjectEditable}
                          >
                            Generate This Scene’s Sequences
                          </button>
                          <button
                            className="ghost-button"
                            onClick={() => void handleGenerateWanPrompts({ sceneIds: [selectedScene.id] })}
                            disabled={!isProjectEditable || Boolean(selectedSceneWanDisabledReason)}
                          >
                            Refresh This Scene’s Wan Prompts
                          </button>
                          <label className={`upload-button ${!isProjectEditable ? "disabled-like" : ""}`}>
                            Upload Scene Image
                            <input
                              disabled={!isProjectEditable}
                              type="file"
                              accept="image/*"
                              onChange={(event) => void handleUploadSceneFirstImage(selectedScene.id, event.target.files?.[0] ?? null)}
                            />
                          </label>
                        </div>
                        {selectedSceneWanDisabledReason ? (
                          <p className="helper-text warning-text">{selectedSceneWanDisabledReason}</p>
                        ) : null}
                        <div className="preview-panel">
                          <div className="panel-header">
                            <h3>Scene Reference</h3>
                            <span className={`badge ${selectedScene.first_image_asset ? "success" : "muted"}`}>
                              {selectedScene.first_image_asset ? "uploaded" : "optional"}
                            </span>
                          </div>
                          {selectedScene.first_image_asset ? (
                            <>
                              <img src={selectedScene.first_image_asset.asset_url} alt="Scene reference" />
                              <div className="media-meta">
                                <strong>{selectedScene.first_image_asset.original_filename}</strong>
                                <span>{Math.round(selectedScene.first_image_asset.size_bytes / 1024)} KB</span>
                              </div>
                            </>
                          ) : (
                            <p className="muted-text">
                              Upload a scene reference image later if you want stronger continuity refinement. It is not
                              required to generate sequences or Wan prompts.
                            </p>
                          )}
                        </div>
                      </div>
                    ) : (
                      <p className="muted-text">Select a scene to edit its long-form beat and first-image prompt.</p>
                    )}
                  </div>
                </section>
              </>
            ) : workspaceTab === "images" ? (
              <>
                <section className="panel workflow-panel">
                  <div className="panel-header">
                    <h2>Image Studio</h2>
                    <div className="action-row">
                      <button
                        className="ghost-button"
                        onClick={() => void handleGenerateSceneImagePrompts()}
                        disabled={!isProjectEditable}
                      >
                        Refresh Scene Prompts
                      </button>
                      <button
                        className="primary-button"
                        onClick={() => (selectedScene ? void handleGenerateSceneImages(selectedScene.id) : undefined)}
                        disabled={!isProjectEditable || Boolean(selectedSceneImageDisabledReason)}
                      >
                        Generate Selected Scene Image
                      </button>
                    </div>
                  </div>
                  <p className="muted-text">
                    Generate and approve one reference image per scene with SDXL-style local image models, or upload a replacement at any point. Approving a new scene image updates the video chain inputs for that scene.
                  </p>
                  <label className="toggle-row">
                    <input
                      type="checkbox"
                      checked={autoApproveSceneImages}
                      onChange={(event) => setAutoApproveSceneImages(event.target.checked)}
                    />
                    Auto-approve the first generated scene image variant
                  </label>
                  <p className="helper-text">
                    Leave this off to keep review explicit. Generated scene images will stay as variants until you
                    approve one.
                  </p>
                  {selectedSceneImageDisabledReason ? (
                    <p className="helper-text warning-text">{selectedSceneImageDisabledReason}</p>
                  ) : null}
                </section>

                <section className="overview-grid">
                  <div className="panel">
                    <div className="panel-header">
                      <h2>Image Coverage</h2>
                      <span className="badge muted">{scenes.length} scenes</span>
                    </div>
                    <div className="stat-grid">
                      <div className="stat-card">
                        <span>Approved Images</span>
                        <strong>{approvedSceneImageCount}</strong>
                      </div>
                      <div className="stat-card">
                        <span>Generated Scene Sets</span>
                        <strong>{generatedSceneImageCount}</strong>
                      </div>
                      <div className="stat-card">
                        <span>Provider</span>
                        <strong>{mediaGenerationSettingsDraft?.image.provider ?? "--"}</strong>
                      </div>
                    </div>
                    <p className="muted-text">
                      Mock generation is Docker-safe for smoke tests. Switch to `diffusers` in Settings and point to local checkpoints when you are ready for real SDXL or Z-image generation.
                    </p>
                  </div>

                  <div className="panel">
                    <div className="panel-header">
                      <h2>Scene Navigator</h2>
                      <span className="badge muted">{selectedScene ? `Scene ${selectedScene.order.toString().padStart(2, "0")}` : "No scene"}</span>
                    </div>
                    <div className="mini-scene-grid">
                      {scenes.map((scene) => (
                        <button
                          key={scene.id}
                          className={`project-chip ${scene.id === selectedSceneId ? "active" : ""}`}
                          onClick={() => setSelectedSceneId(scene.id)}
                        >
                          <strong>Scene {scene.order.toString().padStart(2, "0")} • {scene.title}</strong>
                          <span>
                            {scene.image_generation_status} • {scene.generated_image_variants.length} variants •{" "}
                            {scene.first_image_asset ? `${scene.first_image_source ?? "approved"} image` : "no approved image"}
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                </section>

                <section className="editor-grid">
                  <div className="panel scene-timeline">
                    <div className="panel-header">
                      <h2>Scene Prompt Queue</h2>
                      <span className="badge muted">{scenes.length}</span>
                    </div>
                    <div className="scene-list">
                      {scenes.map((scene) => (
                        <button
                          key={scene.id}
                          className={`scene-card ${scene.id === selectedSceneId ? "active" : ""}`}
                          onClick={() => setSelectedSceneId(scene.id)}
                        >
                          <div className="scene-card-top">
                            <span className="scene-order">{scene.order.toString().padStart(2, "0")}</span>
                            <span className={`badge ${statusTone(scene.image_generation_status)}`}>
                              {scene.image_generation_status}
                            </span>
                          </div>
                          <strong>{scene.title}</strong>
                          <p>{scene.first_image_prompt_text || "No first-image prompt yet."}</p>
                          <div className="scene-meta">
                            <span>{scene.target_duration_s}s</span>
                            <span>{scene.generated_image_variants.length} variants</span>
                            <span>{scene.first_image_asset ? "approved" : "pending"}</span>
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="panel scene-inspector">
                    <div className="panel-header">
                      <h2>Image Inspector</h2>
                      {selectedScene ? (
                        <button
                          className="ghost-button"
                          onClick={() => void copyToClipboard(selectedScene.first_image_prompt_text, "Scene first-image prompt")}
                          disabled={!selectedScene.first_image_prompt_text.trim()}
                        >
                          Copy Scene Prompt
                        </button>
                      ) : null}
                    </div>
                    {selectedScene ? (
                      <div className="media-stack">
                        <label className="field">
                          <span>Scene Prompt</span>
                          <textarea readOnly rows={6} value={selectedScene.first_image_prompt_text} />
                        </label>
                        {sceneImageGenerationDraft ? (
                          <div className="settings-card">
                            <div className="panel-header">
                              <h3>Generation Controls</h3>
                              <span className="badge muted">
                                {sceneImageGenerationDraft.width}x{sceneImageGenerationDraft.height}
                              </span>
                            </div>
                            <div className="project-grid">
                              <label className="field">
                                <span>Model</span>
                                <select
                                  value={sceneImageGenerationDraft.model_name}
                                  onChange={(event) =>
                                    setSceneImageGenerationDraft({
                                      ...sceneImageGenerationDraft,
                                      model_name: event.target.value,
                                    })
                                  }
                                >
                                  <option value="">Use checkpoint root directly</option>
                                  {imageModelOptions.map((model) => (
                                    <option key={model.value} value={model.value}>
                                      {model.label}
                                    </option>
                                  ))}
                                  {sceneImageGenerationDraft.model_name &&
                                  !imageModelOptions.some((model) => model.value === sceneImageGenerationDraft.model_name) ? (
                                    <option value={sceneImageGenerationDraft.model_name}>
                                      {sceneImageGenerationDraft.model_name} (manual)
                                    </option>
                                  ) : null}
                                </select>
                              </label>
                              <label className="field">
                                <span>Resolution</span>
                                <select
                                  value={sceneImageGenerationDraft.resolution_preset}
                                  onChange={(event) =>
                                    setSceneImageGenerationDraft(
                                      applyImageResolutionPresetToDraft(
                                        sceneImageGenerationDraft,
                                        event.target.value as ImageResolutionPresetId,
                                      ),
                                    )
                                  }
                                >
                                  {imageResolutionPresets.map((preset) => (
                                    <option key={preset.id} value={preset.id}>
                                      {preset.label} • {preset.width}x{preset.height}
                                    </option>
                                  ))}
                                </select>
                              </label>
                              <label className="field compact">
                                <span>Width</span>
                                <input
                                  type="number"
                                  min={256}
                                  max={2048}
                                  value={sceneImageGenerationDraft.width}
                                  onChange={(event) =>
                                    setSceneImageGenerationDraft({
                                      ...sceneImageGenerationDraft,
                                      width: Number(event.target.value),
                                      resolution_preset: "custom",
                                    })
                                  }
                                />
                              </label>
                              <label className="field compact">
                                <span>Height</span>
                                <input
                                  type="number"
                                  min={256}
                                  max={2048}
                                  value={sceneImageGenerationDraft.height}
                                  onChange={(event) =>
                                    setSceneImageGenerationDraft({
                                      ...sceneImageGenerationDraft,
                                      height: Number(event.target.value),
                                      resolution_preset: "custom",
                                    })
                                  }
                                />
                              </label>
                              <label className="field compact">
                                <span>Steps</span>
                                <input
                                  type="number"
                                  min={1}
                                  max={150}
                                  value={sceneImageGenerationDraft.steps}
                                  onChange={(event) =>
                                    setSceneImageGenerationDraft({
                                      ...sceneImageGenerationDraft,
                                      steps: Number(event.target.value),
                                    })
                                  }
                                />
                              </label>
                              <label className="field compact">
                                <span>CFG</span>
                                <input
                                  type="number"
                                  step="0.1"
                                  min={0}
                                  max={30}
                                  value={sceneImageGenerationDraft.cfg_scale}
                                  onChange={(event) =>
                                    setSceneImageGenerationDraft({
                                      ...sceneImageGenerationDraft,
                                      cfg_scale: Number(event.target.value),
                                    })
                                  }
                                />
                              </label>
                              <label className="field">
                                <span>Sampler</span>
                                <select
                                  value={sceneImageGenerationDraft.sampler}
                                  onChange={(event) =>
                                    setSceneImageGenerationDraft({
                                      ...sceneImageGenerationDraft,
                                      sampler: event.target.value,
                                    })
                                  }
                                >
                                  {imageSamplerOptions.map((option) => (
                                    <option key={option.value} value={option.value}>
                                      {option.label}
                                    </option>
                                  ))}
                                </select>
                              </label>
                              <label className="field">
                                <span>Scheduler</span>
                                <select
                                  value={sceneImageGenerationDraft.scheduler}
                                  onChange={(event) =>
                                    setSceneImageGenerationDraft({
                                      ...sceneImageGenerationDraft,
                                      scheduler: event.target.value,
                                    })
                                  }
                                >
                                  {imageSchedulerOptions.map((option) => (
                                    <option key={option.value} value={option.value}>
                                      {option.label}
                                    </option>
                                  ))}
                                </select>
                              </label>
                              <label className="field compact">
                                <span>Variants</span>
                                <input
                                  type="number"
                                  min={1}
                                  max={8}
                                  value={sceneImageGenerationDraft.variant_count}
                                  onChange={(event) =>
                                    setSceneImageGenerationDraft({
                                      ...sceneImageGenerationDraft,
                                      variant_count: Number(event.target.value),
                                    })
                                  }
                                />
                              </label>
                              <label className="field">
                                <span>Seed Mode</span>
                                <select
                                  value={sceneImageGenerationDraft.seed_mode}
                                  onChange={(event) =>
                                    setSceneImageGenerationDraft({
                                      ...sceneImageGenerationDraft,
                                      seed_mode: event.target.value as SceneImageGenerationDraft["seed_mode"],
                                    })
                                  }
                                >
                                  <option value="random">Random</option>
                                  <option value="fixed">Fixed</option>
                                </select>
                              </label>
                              <label className="field compact">
                                <span>Fixed Seed</span>
                                <input
                                  type="number"
                                  value={sceneImageGenerationDraft.seed ?? ""}
                                  onChange={(event) =>
                                    setSceneImageGenerationDraft({
                                      ...sceneImageGenerationDraft,
                                      seed: event.target.value ? Number(event.target.value) : null,
                                    })
                                  }
                                />
                              </label>
                            </div>
                            <p className="helper-text">
                              {selectedImageResolutionPreset?.note ??
                                "Use portrait or landscape presets for movie-style framing, or switch to custom."}
                            </p>
                          </div>
                        ) : null}
                        <div className="action-row">
                          <button
                            className="primary-button"
                            onClick={() => void handleGenerateSceneImages(selectedScene.id)}
                            disabled={!isProjectEditable || Boolean(selectedSceneImageDisabledReason)}
                          >
                            Generate Variants
                          </button>
                          <button
                            className="ghost-button"
                            onClick={() => void handleGenerateSceneImagePrompts([selectedScene.id])}
                            disabled={!isProjectEditable}
                          >
                            Regenerate Prompt
                          </button>
                          <label className={`upload-button ${!isProjectEditable ? "disabled-like" : ""}`}>
                            Upload Scene Image
                            <input
                              disabled={!isProjectEditable}
                              type="file"
                              accept="image/*"
                              onChange={(event) => void handleUploadSceneFirstImage(selectedScene.id, event.target.files?.[0] ?? null)}
                            />
                          </label>
                        </div>
                        {selectedSceneImageDisabledReason ? (
                          <p className="helper-text warning-text">{selectedSceneImageDisabledReason}</p>
                        ) : (
                          <p className="helper-text">
                            Approve a generated image or keep uploading references manually. Approving a new scene
                            image can make downstream generated sequence clips stale until they are regenerated.
                          </p>
                        )}

                        <div className="media-preview-grid">
                          <div className="preview-panel">
                            <div className="panel-header">
                              <h3>Approved Image</h3>
                              <span className={`badge ${selectedScene.first_image_asset ? "success" : "muted"}`}>
                                {selectedScene.first_image_asset ? selectedScene.first_image_source ?? "approved" : "missing"}
                              </span>
                            </div>
                            {selectedScene.first_image_asset ? (
                              <>
                                <img src={selectedScene.first_image_asset.asset_url} alt="Approved scene reference" />
                                <div className="media-meta">
                                  <strong>{selectedScene.first_image_asset.original_filename}</strong>
                                  <span>{Math.round(selectedScene.first_image_asset.size_bytes / 1024)} KB</span>
                                </div>
                              </>
                            ) : (
                              <p className="muted-text">Approve a generated image or upload one manually for this scene.</p>
                            )}
                          </div>

                          <div className="preview-panel">
                            <div className="panel-header">
                              <h3>Generated Variants</h3>
                              <span className="badge muted">{selectedScene.generated_image_variants.length}</span>
                            </div>
                            {selectedScene.generated_image_variants.length > 0 ? (
                              <div className="variant-grid">
                                {selectedScene.generated_image_variants.map((variant) => (
                                  <div key={variant.id} className="variant-card">
                                    {variant.asset ? <img src={variant.asset.asset_url} alt={variant.asset.original_filename} /> : null}
                                    <div className="media-meta">
                                      <strong>{variant.model_name}</strong>
                                      <span>seed {variant.seed ?? "auto"}</span>
                                    </div>
                                    <button
                                      className="ghost-button"
                                      onClick={() => void handleApproveSceneImage(selectedScene.id, variant.id)}
                                      disabled={!isProjectEditable}
                                    >
                                      Approve
                                    </button>
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <p className="muted-text">No generated variants yet for this scene.</p>
                            )}
                          </div>
                        </div>
                      </div>
                    ) : (
                      <p className="muted-text">Select a scene to generate or approve its reference image.</p>
                    )}
                  </div>
                </section>
              </>
            ) : workspaceTab === "sequences" ? (
              <>
                <section className="panel workflow-panel">
                  <div className="panel-header">
                    <h2>Sequence Workflow</h2>
                    <div className="action-row">
                      <button className="ghost-button" onClick={() => void handleGenerateSequences()} disabled={!isProjectEditable}>
                        Regenerate All Sequences
                      </button>
                      <button className="ghost-button" onClick={() => void handleGenerateWanPrompts()} disabled={!isProjectEditable}>
                        Generate All Wan Prompts
                      </button>
                      <button className="primary-button" onClick={() => void handleAssemblyExport()} disabled={!isProjectEditable}>
                        Assemble Rough Cut
                      </button>
                    </div>
                  </div>
                  <p className="muted-text">
                    Each sequence is a 5-10 second shot with its own Wan 2.2 motion/camera prompt. Upload externally
                    generated sequence videos here, then assemble them into a rough cut in story order.
                  </p>
                </section>

                <section className="overview-grid">
                  <div className="panel package-panel">
                    <div className="panel-header">
                      <h2>Sequence Package</h2>
                      <span className="badge muted">{totalSequenceCount} sequences</span>
                    </div>
                    <div className="stat-grid">
                      <div className="stat-card">
                        <span>Included Uploads</span>
                        <strong>
                          {uploadedIncludedSequences}/{includedSequences.length}
                        </strong>
                      </div>
                      <div className="stat-card">
                        <span>Prompt Status</span>
                        <strong>{project.prompt_package_status.replace(/_/g, " ")}</strong>
                      </div>
                      <div className="stat-card">
                        <span>Selected Scene</span>
                        <strong>{selectedScene ? `${selectedScene.order.toString().padStart(2, "0")}` : "--"}</strong>
                      </div>
                      <div className="stat-card">
                        <span>Scene Runtime</span>
                        <strong>{selectedScene ? `${selectedSceneSequenceDuration}/${selectedScene.target_duration_s}s` : "--"}</strong>
                      </div>
                    </div>
                    <div className="download-row">
                      <a className="ghost-button link-button" href={promptPackageJsonUrl(project.id)} target="_blank" rel="noreferrer">
                        Download JSON
                      </a>
                      <a className="ghost-button link-button" href={promptPackageMarkdownUrl(project.id)} target="_blank" rel="noreferrer">
                        Download Markdown
                      </a>
                    </div>
                  </div>

                  <div className="panel">
                    <div className="panel-header">
                      <h2>Scene Navigator</h2>
                      <span className="badge muted">{scenes.length} scenes</span>
                    </div>
                    <div className="mini-scene-grid">
                      {scenes.map((scene) => (
                        <button
                          key={scene.id}
                          className={`project-chip ${scene.id === selectedSceneId ? "active" : ""}`}
                          onClick={() => setSelectedSceneId(scene.id)}
                        >
                          <strong>
                            Scene {scene.order.toString().padStart(2, "0")} • {scene.target_duration_s}s
                          </strong>
                          <span>{scene.sequences.length} sequences</span>
                        </button>
                      ))}
                    </div>
                  </div>
                </section>

                <section className="panel comfy-export-panel">
                  <div className="panel-header">
                    <h2>Comfy Export</h2>
                    <span className={`badge ${comfyDisabledReason ? "warning" : "success"}`}>
                      {comfyDisabledReason ? "blocked" : "ready"}
                    </span>
                  </div>
                  <p className="muted-text">
                    Export one 3-sequence block from the selected scene as a ComfyUI-friendly JSON file with 4 prompt
                    slots: the scene first-image prompt plus sequence 1, 2, and 3 Wan prompts.
                  </p>
                  {selectedScene ? (
                    <div className="comfy-export-grid">
                      <div className="settings-card">
                        <div className="panel-header">
                          <h3>3-Sequence Blocks</h3>
                          <span className="badge muted">
                            Scene {selectedScene.order.toString().padStart(2, "0")}
                          </span>
                        </div>
                        <div className="token-cloud">
                          {comfyWindows.length > 0 ? (
                            comfyWindows.map((window) => (
                              <button
                                key={`${selectedScene.id}-${window.startOrder}`}
                                className={`pill-button ${window.startOrder === selectedComfyWindow?.startOrder ? "active" : ""}`}
                                onClick={() => setComfyStartOrder(window.startOrder)}
                              >
                                Seq {window.startOrder}-{window.endOrder}
                              </button>
                            ))
                          ) : (
                            <span className="muted-text">No valid 3-sequence windows yet.</span>
                          )}
                        </div>
                        <div className="comfy-requirements">
                          <div className="post-card">
                            <h3>Requirements</h3>
                            <ul className="flat-list">
                              <li>
                                First-image prompt:{" "}
                                <strong>{selectedScene.first_image_prompt_text.trim() ? "ready" : "missing"}</strong>
                              </li>
                              <li>
                                Consecutive windows: <strong>{comfyWindows.length}</strong>
                              </li>
                              <li>
                                Selected block prompts:{" "}
                                <strong>
                                  {selectedComfyWindow &&
                                  selectedComfyWindow.sequences.every((sequence) => sequence.wan_prompt_text.trim())
                                    ? "ready"
                                    : "missing"}
                                </strong>
                              </li>
                            </ul>
                          </div>
                        </div>
                        {comfyDisabledReason ? <p className="muted-text">{comfyDisabledReason}</p> : null}
                        <div className="action-row">
                          <button
                            className="primary-button"
                            onClick={handleDownloadComfyExtract}
                            disabled={Boolean(comfyDisabledReason)}
                          >
                            Download Comfy JSON
                          </button>
                        </div>
                      </div>

                      <div className="settings-card">
                        <div className="panel-header">
                          <h3>Prompt Preview</h3>
                          {selectedComfyWindow ? (
                            <span className="badge muted">
                              Seq {selectedComfyWindow.startOrder}-{selectedComfyWindow.endOrder}
                            </span>
                          ) : (
                            <span className="badge muted">No block selected</span>
                          )}
                        </div>
                        <div className="comfy-preview-stack">
                          <div className="preview-panel">
                            <div className="panel-header">
                              <h3>First Image Prompt</h3>
                              <span className={`badge ${selectedScene.first_image_prompt_text.trim() ? "success" : "warning"}`}>
                                {selectedScene.first_image_prompt_text.trim() ? "ready" : "missing"}
                              </span>
                            </div>
                            <p className="muted-text">{selectedScene.first_image_prompt_text || "No first-image prompt yet."}</p>
                          </div>
                          {selectedComfyWindow ? (
                            selectedComfyWindow.sequences.map((sequence, index) => (
                              <div key={sequence.id} className="preview-panel">
                                <div className="panel-header">
                                  <h3>
                                    Sequence {index + 1}: {sequence.title}
                                  </h3>
                                  <span className={`badge ${sequence.wan_prompt_text.trim() ? "success" : "warning"}`}>
                                    {sequence.wan_prompt_text.trim() ? "ready" : "missing"}
                                  </span>
                                </div>
                                <p className="muted-text">{sequence.wan_prompt_text || "No Wan prompt yet."}</p>
                              </div>
                            ))
                          ) : (
                            <p className="muted-text">Choose a valid 3-sequence block to preview the export.</p>
                          )}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <p className="muted-text">Select a scene to prepare a ComfyUI export block.</p>
                  )}
                </section>

                <section className="editor-grid">
                  <div className="panel">
                    <div className="panel-header">
                      <h2>Sequence Batch Editor</h2>
                      <span className="badge muted">{selectedSequenceCount} selected</span>
                    </div>
                    <p className="muted-text">
                      Multi-select sequences inside the current scene, then apply bulk camera or action edits, include
                      or exclude them from assembly, and regenerate Wan prompts only for the selected shots.
                    </p>
                    <div className="project-grid">
                      <label className="field">
                        <span>Filter</span>
                        <select value={sequenceFilter} onChange={(event) => setSequenceFilter(event.target.value as SequenceReadinessFilter)}>
                          <option value="all">All sequences</option>
                          <option value="missing_wan">Missing Wan prompt</option>
                          <option value="ready_external">Ready for external generation</option>
                          <option value="missing_upload">Missing upload</option>
                          <option value="ready_assembly">Ready for assembly</option>
                          <option value="excluded">Excluded</option>
                        </select>
                      </label>
                      <label className="field">
                        <span>Camera Mode</span>
                        <select value={batchCameraMode} onChange={(event) => setBatchCameraMode(event.target.value as SequenceBatchTextMode)}>
                          <option value="set">Set</option>
                          <option value="append">Append</option>
                          <option value="fill_empty">Fill Empty</option>
                        </select>
                      </label>
                      <label className="field">
                        <span>Action Mode</span>
                        <select value={batchActionMode} onChange={(event) => setBatchActionMode(event.target.value as SequenceBatchTextMode)}>
                          <option value="set">Set</option>
                          <option value="append">Append</option>
                          <option value="fill_empty">Fill Empty</option>
                        </select>
                      </label>
                      <label className="field">
                        <span>Assembly</span>
                        <select value={batchIncludeChoice} onChange={(event) => setBatchIncludeChoice(event.target.value as "" | "include" | "exclude")}>
                          <option value="">No change</option>
                          <option value="include">Include selected</option>
                          <option value="exclude">Exclude selected</option>
                        </select>
                      </label>
                      <label className="field scenario-field">
                        <span>Batch Camera Direction</span>
                        <textarea rows={3} value={batchCameraDirection} onChange={(event) => setBatchCameraDirection(event.target.value)} />
                      </label>
                      <label className="field scenario-field">
                        <span>Batch Action Direction</span>
                        <textarea rows={3} value={batchActionDirection} onChange={(event) => setBatchActionDirection(event.target.value)} />
                      </label>
                    </div>
                    <div className="action-row">
                      <button
                        className="ghost-button"
                        onClick={() => setSelectedSequenceIds(filteredSequences.map((sequence) => sequence.id))}
                        disabled={!selectedScene || filteredSequences.length === 0}
                      >
                        Select Visible
                      </button>
                      <button className="ghost-button" onClick={() => setSelectedSequenceIds([])} disabled={selectedSequenceCount === 0}>
                        Clear Selection
                      </button>
                      <button
                        className="ghost-button"
                        onClick={() => void handleBatchUpdateSelectedSequences()}
                        disabled={!isProjectEditable || selectedSequenceCount === 0}
                      >
                        Apply Batch Edit
                      </button>
                      <button
                        className="primary-button"
                        onClick={() => void handleGenerateWanPrompts({ sequenceIds: selectedSequenceIds })}
                        disabled={!isProjectEditable || selectedSequenceCount === 0}
                      >
                        Regenerate Selected Wan Prompts
                      </button>
                    </div>
                  </div>

                  <div className="panel">
                    <div className="panel-header">
                      <h2>Continuity Review</h2>
                      <span className={`badge ${selectedSceneHasContinuityReview ? "success" : "muted"}`}>
                        {selectedSceneHasContinuityReview ? selectedScene?.continuity_review?.source ?? "ready" : "not run"}
                      </span>
                    </div>
                    <p className="muted-text">
                      Compare the scene reference image and approved sequence clips before rough-cut assembly. If a
                      vision-capable runtime is unavailable, the review falls back to a rules-only pass with the same report shape.
                    </p>
                    <div className="action-row">
                      <button
                        className="primary-button"
                        onClick={() => void handleRunContinuityReview()}
                        disabled={!isProjectEditable || !selectedScene}
                      >
                        Run Continuity Review
                      </button>
                    </div>
                    {selectedScene?.continuity_review ? (
                      <div className="continuity-review-stack">
                        <div className="preview-panel">
                          <div className="panel-header">
                            <h3>Summary</h3>
                            <span className="badge muted">{selectedScene.continuity_review.source}</span>
                          </div>
                          <p className="muted-text">{selectedScene.continuity_review.summary_text}</p>
                          {selectedScene.continuity_review.source === "rules_only" ? (
                            <p className="helper-text warning-text">
                              Local vision was not confirmed for this review run, so the report stayed on the explicit
                              rules-only fallback. Test the runtime in Settings to verify that KoboldCpp or your other
                              multimodal backend is actually vision-ready.
                            </p>
                          ) : null}
                        </div>
                        <div className="preview-panel">
                          <div className="panel-header">
                            <h3>Findings</h3>
                            <span className="badge muted">{selectedScene.continuity_review.findings.length}</span>
                          </div>
                          {selectedScene.continuity_review.findings.length > 0 ? (
                            <div className="flat-list">
                              {selectedScene.continuity_review.findings.map((finding, index) => (
                                <div key={`${finding.category}-${finding.sequence_id ?? "scene"}-${index}`} className="timeline-summary">
                                  <strong>
                                    {finding.category} • {finding.severity}
                                  </strong>
                                  <span className="muted-text">{finding.summary_text}</span>
                                  {finding.detail_text ? <span className="muted-text">{finding.detail_text}</span> : null}
                                </div>
                              ))}
                            </div>
                          ) : (
                            <p className="muted-text">No continuity findings were reported for this scene.</p>
                          )}
                        </div>
                        <div className="preview-panel">
                          <div className="panel-header">
                            <h3>Prompt Fix Suggestions</h3>
                            <span className="badge muted">{selectedScene.continuity_review.sequence_suggestions.length}</span>
                          </div>
                          {selectedScene.continuity_review.sequence_suggestions.length > 0 ? (
                            <div className="flat-list">
                              {selectedScene.continuity_review.sequence_suggestions.map((suggestion) => (
                                <div key={suggestion.sequence_id} className="timeline-summary">
                                  <strong>{sequences.find((item) => item.id === suggestion.sequence_id)?.title ?? suggestion.sequence_id}</strong>
                                  <span className="muted-text">{suggestion.suggested_prompt_fix}</span>
                                  <span className="muted-text">{suggestion.rationale}</span>
                                  <div className="action-row">
                                    <button
                                      className="ghost-button"
                                      onClick={() =>
                                        void handleApplyContinuitySuggestion(
                                          suggestion.sequence_id,
                                          suggestion.suggested_prompt_fix,
                                          "replace",
                                        )
                                      }
                                      disabled={!isProjectEditable}
                                    >
                                      Replace Prompt
                                    </button>
                                    <button
                                      className="ghost-button"
                                      onClick={() =>
                                        void handleApplyContinuitySuggestion(
                                          suggestion.sequence_id,
                                          suggestion.suggested_prompt_fix,
                                          "append",
                                        )
                                      }
                                      disabled={!isProjectEditable}
                                    >
                                      Append Suggestion
                                    </button>
                                    <button
                                      className="primary-button"
                                      onClick={() => void handleRegenerateSuggestedSequence(suggestion.sequence_id)}
                                      disabled={!isProjectEditable}
                                    >
                                      Regenerate Wan
                                    </button>
                                  </div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <p className="muted-text">No prompt-fix suggestions are available yet.</p>
                          )}
                        </div>
                      </div>
                    ) : (
                      <p className="muted-text">Run a scene review to persist the latest continuity report here.</p>
                    )}
                  </div>
                </section>

                <section className="editor-grid">
                  <div className="panel scene-timeline">
                    <div className="panel-header">
                      <h2>Sequences</h2>
                      <span className="badge muted">{filteredSequences.length}/{sequences.length}</span>
                    </div>
                    {selectedScene ? (
                      <div className="sequence-list">
                        {filteredSequences.length === 0 ? (
                          <p className="muted-text">No sequences match the current readiness filter.</p>
                        ) : (
                          filteredSequences.map((sequence) => (
                            <div key={sequence.id} className="sequence-row">
                              <label className="sequence-select">
                                <input
                                  type="checkbox"
                                  checked={selectedSequenceSet.has(sequence.id)}
                                  onChange={(event) =>
                                    setSelectedSequenceIds((current) =>
                                      event.target.checked
                                        ? [...new Set([...current, sequence.id])]
                                        : current.filter((item) => item !== sequence.id),
                                    )
                                  }
                                />
                              </label>
                              <button
                                className={`scene-card ${sequence.id === selectedSequenceId ? "active" : ""}`}
                                onClick={() => setSelectedSequenceId(sequence.id)}
                              >
                                <div className="scene-card-top">
                                  <span className="scene-order">{sequence.order.toString().padStart(2, "0")}</span>
                                  <span
                                    className={`badge ${
                                      sequenceVideoAsset(sequence) ? "success" : sequence.wan_prompt_text ? "warning" : "muted"
                                    }`}
                                  >
                                    {sequenceVideoAsset(sequence) ? "approved" : sequence.wan_prompt_text ? "prompted" : "draft"}
                                  </span>
                                </div>
                                <strong>{sequence.title}</strong>
                                <p>{sequence.narrative_text}</p>
                                <div className="scene-meta">
                                  <span>{sequence.target_duration_s}s</span>
                                  <span>{sequence.duration_locked ? "Locked" : "Unlocked"}</span>
                                  <span>{sequence.include_in_assembly ? "In assembly" : "Skipped"}</span>
                                </div>
                              </button>
                            </div>
                          ))
                        )}
                      </div>
                    ) : (
                      <p className="muted-text">Select a scene first to view its sequences.</p>
                    )}
                  </div>

                  <div className="panel scene-inspector">
                    <div className="panel-header">
                      <h2>Sequence Inspector</h2>
                      {sequenceDraft ? (
                        <button
                          className="ghost-button"
                          onClick={() => void copyToClipboard(sequenceDraft.wan_prompt_text, "Wan 2.2 prompt")}
                          disabled={!sequenceDraft.wan_prompt_text}
                        >
                          Copy Wan Prompt
                        </button>
                      ) : null}
                    </div>

                    {sequenceDraft && selectedSequence && selectedScene ? (
                      <div className="inspector-grid">
                        <label className="field compact">
                          <span>Order</span>
                          <input
                            disabled={!isProjectEditable}
                            type="number"
                            min={1}
                            max={200}
                            value={sequenceDraft.order}
                            onChange={(event) => {
                              setSequenceDraft({ ...sequenceDraft, order: Number(event.target.value) });
                              setSequenceDirty(true);
                            }}
                          />
                        </label>
                        <label className="field compact">
                          <span>Duration (s)</span>
                          <input
                            disabled={!isProjectEditable}
                            type="number"
                            min={5}
                            max={10}
                            value={sequenceDraft.target_duration_s}
                            onChange={(event) => {
                              setSequenceDraft({ ...sequenceDraft, target_duration_s: Number(event.target.value) });
                              setSequenceDirty(true);
                            }}
                          />
                        </label>
                        <label className="toggle-row">
                          <input
                            type="checkbox"
                            disabled={!isProjectEditable}
                            checked={sequenceDraft.duration_locked}
                            onChange={(event) => {
                              setSequenceDraft({ ...sequenceDraft, duration_locked: event.target.checked });
                              setSequenceDirty(true);
                            }}
                          />
                          Lock this sequence duration during scene rebalancing
                        </label>
                        <label className="field">
                          <span>Title</span>
                          <input
                            disabled={!isProjectEditable}
                            value={sequenceDraft.title}
                            onChange={(event) => {
                              setSequenceDraft({ ...sequenceDraft, title: event.target.value });
                              setSequenceDirty(true);
                            }}
                          />
                        </label>
                        <label className="field">
                          <span>Narrative Beat</span>
                          <textarea
                            disabled={!isProjectEditable}
                            rows={4}
                            value={sequenceDraft.narrative_text}
                            onChange={(event) => {
                              setSequenceDraft({ ...sequenceDraft, narrative_text: event.target.value });
                              setSequenceDirty(true);
                            }}
                          />
                        </label>
                        <label className="field">
                          <span>Camera Direction</span>
                          <textarea
                            disabled={!isProjectEditable}
                            rows={3}
                            value={sequenceDraft.camera_direction}
                            onChange={(event) => {
                              setSequenceDraft({ ...sequenceDraft, camera_direction: event.target.value });
                              setSequenceDirty(true);
                            }}
                          />
                        </label>
                        <label className="field">
                          <span>Action Direction</span>
                          <textarea
                            disabled={!isProjectEditable}
                            rows={3}
                            value={sequenceDraft.action_direction}
                            onChange={(event) => {
                              setSequenceDraft({ ...sequenceDraft, action_direction: event.target.value });
                              setSequenceDirty(true);
                            }}
                          />
                        </label>
                        <label className="field">
                          <span>Wan 2.2 Prompt</span>
                          <textarea
                            disabled={!isProjectEditable}
                            rows={9}
                            value={sequenceDraft.wan_prompt_text}
                            onChange={(event) => {
                              setSequenceDraft({ ...sequenceDraft, wan_prompt_text: event.target.value });
                              setSequenceDirty(true);
                            }}
                          />
                        </label>
                          <div className="action-row span-all">
                            <button
                              className="ghost-button"
                              onClick={() => void handleGenerateWanPrompts({ sceneIds: [selectedScene.id] })}
                              disabled={!isProjectEditable || Boolean(selectedSceneWanDisabledReason)}
                            >
                              Refresh This Scene’s Wan Prompts
                            </button>
                            <button
                              className="ghost-button"
                              onClick={() => void handleGenerateWanPrompts({ sequenceIds: [selectedSequence.id] })}
                              disabled={!isProjectEditable}
                            >
                              Redo This Wan Prompt
                            </button>
                            <label className={`upload-button ${!isProjectEditable ? "disabled-like" : ""}`}>
                              Upload Sequence Clip
                              <input
                                disabled={!isProjectEditable}
                                type="file"
                              accept="video/*"
                              onChange={(event) => void handleUploadSequenceVideo(selectedSequence.id, event.target.files?.[0] ?? null)}
                            />
                          </label>
                        </div>
                        {selectedSceneWanDisabledReason ? (
                          <p className="helper-text warning-text">{selectedSceneWanDisabledReason}</p>
                        ) : null}
                        <div className="assembly-controls">
                          <label className="field compact">
                            <span>Trim In (ms)</span>
                            <input
                              disabled={!isProjectEditable}
                              type="number"
                              min={0}
                              value={sequenceDraft.trim_in_ms}
                              onChange={(event) => {
                                setSequenceDraft({ ...sequenceDraft, trim_in_ms: Number(event.target.value) });
                                setSequenceDirty(true);
                              }}
                            />
                          </label>
                          <label className="field compact">
                            <span>Trim Out (ms)</span>
                            <input
                              disabled={!isProjectEditable}
                              type="number"
                              min={0}
                              value={sequenceDraft.trim_out_ms}
                              onChange={(event) => {
                                setSequenceDraft({ ...sequenceDraft, trim_out_ms: Number(event.target.value) });
                                setSequenceDirty(true);
                              }}
                            />
                          </label>
                          <label className="toggle-row">
                            <input
                              type="checkbox"
                              disabled={!isProjectEditable}
                              checked={sequenceDraft.include_in_assembly}
                              onChange={(event) => {
                                setSequenceDraft({ ...sequenceDraft, include_in_assembly: event.target.checked });
                                setSequenceDirty(true);
                              }}
                            />
                            Include this sequence in the rough cut
                          </label>
                        </div>
                        <div className="preview-panel">
                          <div className="panel-header">
                            <h3>Approved Sequence Clip</h3>
                            <span className={`badge ${sequenceVideoAsset(selectedSequence) ? "success" : "muted"}`}>
                              {sequenceVideoAsset(selectedSequence) ? "ready" : "missing"}
                            </span>
                          </div>
                          {sequenceVideoAsset(selectedSequence) ? (
                            <>
                              <video controls src={sequenceVideoAsset(selectedSequence)?.asset_url} />
                              <div className="media-meta">
                                <strong>{sequenceVideoAsset(selectedSequence)?.original_filename}</strong>
                                <span>{Math.round((sequenceVideoAsset(selectedSequence)?.size_bytes ?? 0) / 1024)} KB</span>
                              </div>
                            </>
                          ) : (
                            <p className="muted-text">
                              Upload or generate the Wan clip for this sequence when it is ready.
                            </p>
                          )}
                        </div>
                      </div>
                    ) : (
                      <p className="muted-text">Select a sequence to edit its Wan 2.2 prompt and assembly settings.</p>
                    )}
                  </div>
                </section>

                {selectedScene && (
                  <VideoTimeline
                    sequences={sequences}
                    activeSequenceId={selectedSequenceId}
                    onSelectSequence={(id) => setSelectedSequenceId(id)}
                    onUpdateSequenceAssembly={async (id, include, trimInMs, trimOutMs) => {
                      try {
                        const savedSequence = await updateSequenceAssembly(id, {
                          include_in_assembly: include,
                          trim_in_ms: trimInMs,
                          trim_out_ms: trimOutMs,
                        });
                        mergeSequence(savedSequence);
                        if (selectedSequenceId === id) {
                          setSequenceDraft((current) =>
                            current
                              ? {
                                  ...current,
                                  include_in_assembly: include,
                                  trim_in_ms: trimInMs ?? current.trim_in_ms,
                                  trim_out_ms: trimOutMs ?? current.trim_out_ms,
                                }
                              : current,
                          );
                        }
                        setNotice(`Sequence "${savedSequence.title}" ${include ? "included in" : "excluded from"} assembly.`);
                        setError(null);
                      } catch (caughtError) {
                        setError((caughtError as Error).message);
                      }
                    }}
                    onReorderSequences={async (reorderedIds) => {
                      if (!project || !selectedScene) return;
                      try {
                        setLoading(true);
                        await Promise.all(
                          reorderedIds.map((id, index) =>
                            updateSequence(id, { order: index + 1 })
                          )
                        );
                        await loadProject(project.id, selectedScene.id, selectedSequenceId);
                        setNotice("Sequences reordered successfully.");
                        setError(null);
                      } catch (caughtError) {
                        setError((caughtError as Error).message);
                      } finally {
                        setLoading(false);
                      }
                    }}
                  />
                )}

                <section className="panel">
                  <div className="panel-header">
                    <h2>Rough Cut And Postproduction</h2>
                    <span className="badge muted">{project.exports.length} exports</span>
                  </div>
                  <div className="post-grid">
                    <div className="post-card">
                      <h3>Assembly Readiness</h3>
                      <p className="muted-text">
                        Included approved clips: {uploadedIncludedSequences} of {includedSequences.length}.
                      </p>
                      <p className="muted-text">
                        Missing approved clips prevent export, so this panel gives you a quick preflight before you
                        assemble.
                      </p>
                    </div>
                    <div className="post-card">
                      <h3>Continuity Assist</h3>
                      <p className="muted-text">
                        Scene-level continuity review is now available before the final edit, so you can compare the
                        scene reference image and approved sequence clips, then flag identity, costume, location, or
                        lighting drift before assembly.
                      </p>
                    </div>
                  </div>
                  <div className="export-list">
                    {project.exports.length === 0 ? (
                      <p className="muted-text">No rough-cut exports yet.</p>
                    ) : (
                      project.exports.map((asset) => (
                        <a key={asset.id} className="export-card" href={asset.asset_url} target="_blank" rel="noreferrer">
                          <strong>{asset.relative_path.split("/").pop()}</strong>
                          <span>{asset.duration_s ? `${asset.duration_s}s` : "duration pending"}</span>
                        </a>
                      ))
                    )}
                  </div>
                </section>
              </>
            ) : workspaceTab === "video" ? (
              <>
                <section className="panel workflow-panel">
                  <div className="panel-header">
                    <h2>Video Studio</h2>
                    <div className="action-row">
                      <button
                        className="ghost-button"
                        onClick={() => (selectedSequence ? void handleGenerateSequenceVideo(selectedSequence.id) : undefined)}
                        disabled={!isProjectEditable || Boolean(selectedSequenceVideoDisabledReason)}
                      >
                        Generate Selected Sequence
                      </button>
                      <button
                        className="primary-button"
                        onClick={() => (selectedScene ? void handleGenerateSceneVideoChain(selectedScene.id) : undefined)}
                        disabled={!isProjectEditable || Boolean(selectedSceneChainDisabledReason)}
                      >
                        Generate Scene Chain
                      </button>
                    </div>
                  </div>
                  <p className="muted-text">
                    Sequence 1 uses the approved scene image. Every later sequence uses the last frame of the previous approved clip. When an upstream input changes, downstream clips automatically show as stale and ready for regeneration.
                  </p>
                  <label className="toggle-row">
                    <input
                      type="checkbox"
                      checked={autoApproveSequenceVideos}
                      onChange={(event) => setAutoApproveSequenceVideos(event.target.checked)}
                    />
                    Auto-approve the first generated video variant
                  </label>
                  <p className="helper-text">
                    Leave this off to review generated clips before they affect the chain. Approving or replacing an
                    upstream clip can make later generated shots stale.
                  </p>
                  {selectedSceneChainDisabledReason ? (
                    <p className="helper-text warning-text">{selectedSceneChainDisabledReason}</p>
                  ) : null}
                </section>

                <section className="overview-grid">
                  <div className="panel">
                    <div className="panel-header">
                      <h2>Video Coverage</h2>
                      <span className="badge muted">{totalSequenceCount} sequences</span>
                    </div>
                    <div className="stat-grid">
                      <div className="stat-card">
                        <span>Approved Clips</span>
                        <strong>{approvedSequenceVideoCount}</strong>
                      </div>
                      <div className="stat-card">
                        <span>Provider</span>
                        <strong>{mediaGenerationSettingsDraft?.video.provider ?? "--"}</strong>
                      </div>
                      <div className="stat-card">
                        <span>Selected Scene</span>
                        <strong>{selectedScene ? `Scene ${selectedScene.order.toString().padStart(2, "0")}` : "--"}</strong>
                      </div>
                    </div>
                    <p className="muted-text">
                      Mock video generation keeps Docker verification deterministic. Real Wan generation becomes available when `lightx2v` is installed and the configured local model root is valid.
                    </p>
                  </div>

                  <div className="panel">
                    <div className="panel-header">
                      <h2>Scene Navigator</h2>
                      <span className="badge muted">{scenes.length} scenes</span>
                    </div>
                    <div className="mini-scene-grid">
                      {scenes.map((scene) => (
                        <button
                          key={scene.id}
                          className={`project-chip ${scene.id === selectedSceneId ? "active" : ""}`}
                          onClick={() => setSelectedSceneId(scene.id)}
                        >
                          <strong>Scene {scene.order.toString().padStart(2, "0")} • {scene.title}</strong>
                          <span>
                            {scene.sequences.filter((sequence) => sequenceVideoAsset(sequence)).length}/{scene.sequences.length} approved clips
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                </section>

                <section className="editor-grid">
                  <div className="panel scene-timeline">
                    <div className="panel-header">
                      <h2>Scene Chain</h2>
                      <span className="badge muted">{selectedScene ? selectedScene.sequences.length : 0}</span>
                    </div>
                    {selectedScene ? (
                      <div className="scene-list">
                        {selectedScene.sequences.map((sequence) => (
                          <button
                            key={sequence.id}
                            className={`scene-card ${sequence.id === selectedSequenceId ? "active" : ""}`}
                            onClick={() => setSelectedSequenceId(sequence.id)}
                          >
                            <div className="scene-card-top">
                              <span className="scene-order">{sequence.order.toString().padStart(2, "0")}</span>
                              <span className={`badge ${statusTone(sequence.chain_state)}`}>{sequence.chain_state}</span>
                            </div>
                            <strong>{sequence.title}</strong>
                            <p>{sequence.wan_prompt_text || "No Wan prompt yet."}</p>
                            <div className="scene-meta">
                              <span>{sequence.target_duration_s}s</span>
                              <span>{sequenceVideoAsset(sequence) ? "approved" : "pending"}</span>
                              <span>{sequence.generated_video_variants.length} variants</span>
                            </div>
                          </button>
                        ))}
                      </div>
                    ) : (
                      <p className="muted-text">Select a scene to inspect its video chain.</p>
                    )}
                  </div>

                  <div className="panel scene-inspector">
                    <div className="panel-header">
                      <h2>Video Inspector</h2>
                      {selectedSequence ? (
                        <button
                          className="ghost-button"
                          onClick={() => void copyToClipboard(selectedSequence.wan_prompt_text, "Wan 2.2 prompt")}
                          disabled={!selectedSequence.wan_prompt_text.trim()}
                        >
                          Copy Wan Prompt
                        </button>
                      ) : null}
                    </div>
                    {selectedScene && selectedSequence ? (
                      <div className="media-stack">
                        <label className="field">
                          <span>Wan Prompt</span>
                          <textarea readOnly rows={8} value={selectedSequence.wan_prompt_text} />
                        </label>
                          <div className="action-row">
                            <button
                              className="ghost-button"
                              onClick={() => void handleGenerateWanPrompts({ sequenceIds: [selectedSequence.id] })}
                              disabled={!isProjectEditable}
                            >
                              Redo This Wan Prompt
                            </button>
                            <button
                              className="primary-button"
                              onClick={() => void handleGenerateSequenceVideo(selectedSequence.id)}
                              disabled={!isProjectEditable || Boolean(selectedSequenceVideoDisabledReason)}
                            >
                            Generate This Sequence
                          </button>
                          <button
                            className="ghost-button"
                            onClick={() => void handleGenerateSceneVideoChain(selectedScene.id)}
                            disabled={!isProjectEditable || Boolean(selectedSceneChainDisabledReason)}
                          >
                            Regenerate Scene Chain
                          </button>
                          <label className={`upload-button ${!isProjectEditable ? "disabled-like" : ""}`}>
                            Upload Replacement
                            <input
                              disabled={!isProjectEditable}
                              type="file"
                              accept="video/*"
                              onChange={(event) => void handleUploadSequenceVideo(selectedSequence.id, event.target.files?.[0] ?? null)}
                            />
                          </label>
                        </div>
                        {selectedSequenceVideoDisabledReason ? (
                          <p className="helper-text warning-text">{selectedSequenceVideoDisabledReason}</p>
                        ) : selectedSceneChainDisabledReason ? (
                          <p className="helper-text warning-text">{selectedSceneChainDisabledReason}</p>
                        ) : (
                          <p className="helper-text">
                            This sequence uses the current input frame shown below. Regenerating or approving upstream
                            media can mark downstream clips stale until you review them again.
                          </p>
                        )}

                        <div className="media-preview-grid">
                          <div className="preview-panel">
                            <div className="panel-header">
                              <h3>Input Frame</h3>
                              <span className={`badge ${selectedSequence.input_frame_asset ? "success" : "warning"}`}>
                                {selectedSequence.input_frame_asset ? "ready" : "missing"}
                              </span>
                            </div>
                            {selectedSequence.input_frame_asset ? (
                              <img src={selectedSequence.input_frame_asset.asset_url} alt="Video input frame" />
                            ) : (
                              <p className="muted-text">Approve the scene image or upstream clip first.</p>
                            )}
                          </div>

                          <div className="preview-panel">
                            <div className="panel-header">
                              <h3>Approved Clip</h3>
                              <span className={`badge ${sequenceVideoAsset(selectedSequence) ? "success" : "muted"}`}>
                                {sequenceVideoAsset(selectedSequence) ? selectedSequence.approved_video_source ?? "ready" : "missing"}
                              </span>
                            </div>
                            {sequenceVideoAsset(selectedSequence) ? (
                              <>
                                <video controls src={sequenceVideoAsset(selectedSequence)?.asset_url} />
                                <div className="media-meta">
                                  <strong>{sequenceVideoAsset(selectedSequence)?.original_filename}</strong>
                                  <span>{selectedSequence.chain_state}</span>
                                </div>
                              </>
                            ) : (
                              <p className="muted-text">Generate this sequence or upload a replacement clip.</p>
                            )}
                          </div>

                          <div className="preview-panel">
                            <div className="panel-header">
                              <h3>Last Frame</h3>
                              <span className={`badge ${selectedSequence.last_frame_asset ? "success" : "muted"}`}>
                                {selectedSequence.last_frame_asset ? "ready" : "missing"}
                              </span>
                            </div>
                            {selectedSequence.last_frame_asset ? (
                              <img src={selectedSequence.last_frame_asset.asset_url} alt="Sequence last frame" />
                            ) : (
                              <p className="muted-text">The last frame will be extracted after generation or upload.</p>
                            )}
                          </div>
                        </div>

                        <div className="preview-panel">
                          <div className="panel-header">
                            <h3>Generated Variants</h3>
                            <span className="badge muted">{selectedSequence.generated_video_variants.length}</span>
                          </div>
                          {selectedSequence.generated_video_variants.length > 0 ? (
                            <div className="variant-grid">
                              {selectedSequence.generated_video_variants.map((variant) => (
                                <div key={variant.id} className="variant-card">
                                  {variant.asset ? <video controls src={variant.asset.asset_url} /> : null}
                                  <div className="media-meta">
                                    <strong>{variant.model_name}</strong>
                                    <span>{variant.output_duration_s.toFixed(1)}s</span>
                                  </div>
                                  <button
                                    className="ghost-button"
                                    onClick={() => void handleApproveSequenceVideo(selectedSequence.id, variant.id)}
                                    disabled={!isProjectEditable}
                                  >
                                    Approve
                                  </button>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <p className="muted-text">No generated variants yet for this sequence.</p>
                          )}
                        </div>
                      </div>
                    ) : (
                      <p className="muted-text">Select a sequence to inspect its input frame, approved clip, and generated variants.</p>
                    )}
                  </div>
                </section>
              </>
            ) : null}
          </>
        ) : (
          <section className="empty-state panel">
            <h2>No project selected</h2>
            <p>
              Create a movie project to unlock the scenario-writing tab, scene breakdown, image generation, sequence
              prompts, video generation, upload slots, and rough-cut assembly tools. The Settings tab is already
              available so you can connect your local models first.
            </p>
          </section>
        )}
      </main>
    </div>
  );
}

function statusTone(status: string) {
  if (
    status === "succeeded" ||
    status === "ready" ||
    status === "local_model" ||
    status === "generated" ||
    status === "local_vision"
  ) {
    return "success";
  }
  if (status === "failed" || status === "canceled" || status === "error") {
    return "danger";
  }
  if (
    status === "running" ||
    status === "queued" ||
    status === "missing_input" ||
    status === "stale_upstream" ||
    status === "edited" ||
    status === "stale" ||
    status.startsWith("needs_") ||
    status === "needs_upgrade" ||
    status === "fallback" ||
    status === "reachable" ||
    status === "reachable_model_missing" ||
    status === "disabled" ||
    status === "cpu_only" ||
    status === "missing_gpu" ||
    status === "missing_model" ||
    status === "missing_dependency" ||
    status === "unsupported_provider" ||
    status === "rules_only"
  ) {
    return "warning";
  }
  return "muted";
}

export default App;
