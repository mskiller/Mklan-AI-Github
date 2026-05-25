import type {
  AssistantConnectionTest,
  AssemblyUpdateRequest,
  BeatBoard,
  BeatBoardReorderItem,
  BeatCard,
  BeatUpdateRequest,
  CharacterCreateRequest,
  CharacterGenerateRequest,
  CharacterUpdateRequest,
  ContinuityReview,
  CreateBeatRequest,
  HardwareProfile,
  ImageModelInventory,
  ImageModelUploadResponse,
  Job,
  MediaModelDownloadRequest,
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
  PromptPreviewRequest,
  PromptPreviewResponse,
  ProjectUpdateRequest,
  PromptPackage,
  ScenarioAssistantRequest,
  ScenarioAssistantResponse,
  Scene,
  SceneImageGenerationRequest,
  SequenceBatchUpdateRequest,
  SceneUpdateRequest,
  Sequence,
  SequenceUpdateRequest,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/movie";

function buildUrl(path: string) {
  return `${API_BASE}${path}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers ?? {});
  const isFormData = init?.body instanceof FormData;
  if (!isFormData && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(buildUrl(path), {
    ...init,
    headers,
  });

  if (!response.ok) {
    let message = response.statusText;
    try {
      const payload = await response.json();
      message = payload.detail ?? message;
    } catch {
      // Keep HTTP status message.
    }
    throw new Error(message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export function promptPackageJsonUrl(projectId: string) {
  return buildUrl(`/projects/${projectId}/prompt-package.json`);
}

export function promptPackageMarkdownUrl(projectId: string) {
  return buildUrl(`/projects/${projectId}/prompt-package.md`);
}

export function comfySceneExtractUrl(sceneId: string, startOrder: number) {
  return buildUrl(`/scenes/${sceneId}/comfy-extract.json?start_order=${startOrder}`);
}

export function listProjects(scope: ProjectScope = "active") {
  return request<ProjectListItem[]>(`/projects?scope=${scope}`);
}

export function getProject(projectId: string) {
  return request<Project>(`/projects/${projectId}`);
}

export function createProject(payload: ProjectCreateRequest) {
  return request<Project>("/projects", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateProject(projectId: string, payload: ProjectUpdateRequest) {
  return request<Project>(`/projects/${projectId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function archiveProject(projectId: string) {
  return request<Project>(`/projects/${projectId}/archive`, {
    method: "POST",
  });
}

export function restoreProject(projectId: string) {
  return request<Project>(`/projects/${projectId}/restore`, {
    method: "POST",
  });
}

export function deleteProject(projectId: string) {
  return request<void>(`/projects/${projectId}`, {
    method: "DELETE",
  });
}

export function upgradeProjectToV2(projectId: string) {
  return request<Project>(`/projects/${projectId}/upgrade-to-v2`, {
    method: "POST",
  });
}

export function generateScenes(projectId: string, source: "scenario" | "beat_board" = "scenario") {
  return request<Project>(`/projects/${projectId}/scenes/generate`, {
    method: "POST",
    body: JSON.stringify({ replace_existing: true, source }),
  });
}

export function getBeatBoard(projectId: string) {
  return request<BeatBoard>(`/projects/${projectId}/beat-board`);
}

export function listCharacters(projectId: string) {
  return request<ProjectCharacter[]>(`/projects/${projectId}/characters`);
}

export function generateCharacters(projectId: string, overwriteExisting = true) {
  return request<ProjectCharacter[]>(`/projects/${projectId}/characters/generate`, {
    method: "POST",
    body: JSON.stringify({ overwrite_existing: overwriteExisting }),
  });
}

export function createCharacter(projectId: string, payload: CharacterCreateRequest) {
  return request<ProjectCharacter>(`/projects/${projectId}/characters`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateCharacter(projectId: string, characterId: string, payload: CharacterUpdateRequest) {
  return request<ProjectCharacter>(`/projects/${projectId}/characters/${characterId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteCharacter(projectId: string, characterId: string) {
  return request<void>(`/projects/${projectId}/characters/${characterId}`, {
    method: "DELETE",
  });
}

export function generateCharacterImage(projectId: string, characterId: string, shotType: "portrait" | "cowboyshot" | "fullbody") {
  return request<Job>(`/projects/${projectId}/characters/${characterId}/images/generate`, {
    method: "POST",
    body: JSON.stringify({ shot_type: shotType }),
  });
}

export function generateBeatBoard(projectId: string, overwriteExisting = true) {
  return request<BeatBoard>(`/projects/${projectId}/beat-board/generate`, {
    method: "POST",
    body: JSON.stringify({ overwrite_existing: overwriteExisting }),
  });
}

export function reorderBeatBoard(projectId: string, beats: BeatBoardReorderItem[]) {
  return request<BeatBoard>(`/projects/${projectId}/beat-board/reorder`, {
    method: "POST",
    body: JSON.stringify({ beats }),
  });
}

export function applyBeatBoardToScenario(projectId: string) {
  return request<Project>(`/projects/${projectId}/beat-board/apply-to-scenario`, {
    method: "POST",
  });
}

export function createBeat(projectId: string, payload: CreateBeatRequest) {
  return request<BeatCard>(`/projects/${projectId}/beats`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateBeat(beatId: string, payload: BeatUpdateRequest) {
  return request<BeatCard>(`/beats/${beatId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteBeat(beatId: string) {
  return request<void>(`/beats/${beatId}`, {
    method: "DELETE",
  });
}

export function generateSceneImagePrompts(projectId: string, sceneIds?: string[], overwriteExisting = true) {
  return request<Project>(`/projects/${projectId}/scene-image-prompts/generate`, {
    method: "POST",
    body: JSON.stringify({ scene_ids: sceneIds, overwrite_existing: overwriteExisting }),
  });
}

export function uploadSceneFirstImage(sceneId: string, file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return request<Scene>(`/scenes/${sceneId}/first-image`, {
    method: "POST",
    body: formData,
  });
}

export function generateSceneImages(sceneId: string, payload?: SceneImageGenerationRequest) {
  return request<Job>(`/scenes/${sceneId}/images/generate`, {
    method: "POST",
    body: JSON.stringify(payload ?? {}),
  });
}

export function approveSceneImageVariant(sceneId: string, assetId: string) {
  return request<Scene>(`/scenes/${sceneId}/images/${assetId}/approve`, {
    method: "POST",
  });
}

export function generateSequences(projectId: string, sceneIds?: string[], overwriteExisting = true) {
  return request<Project>(`/projects/${projectId}/sequences/generate`, {
    method: "POST",
    body: JSON.stringify({ scene_ids: sceneIds, overwrite_existing: overwriteExisting }),
  });
}

export function generateWanPrompts(
  projectId: string,
  options?: { sceneIds?: string[]; sequenceIds?: string[]; overwriteExisting?: boolean },
) {
  return request<Project>(`/projects/${projectId}/wan-prompts/generate`, {
    method: "POST",
    body: JSON.stringify({
      scene_ids: options?.sceneIds,
      sequence_ids: options?.sequenceIds,
      overwrite_existing: options?.overwriteExisting ?? true,
    }),
  });
}

export function updateScene(sceneId: string, payload: SceneUpdateRequest) {
  return request<Scene>(`/scenes/${sceneId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function updateSequence(sequenceId: string, payload: SequenceUpdateRequest) {
  return request<Sequence>(`/sequences/${sequenceId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function updateSequenceWanPrompt(sequenceId: string, wanPromptText: string) {
  return request<Sequence>(`/sequences/${sequenceId}/wan-prompt`, {
    method: "PATCH",
    body: JSON.stringify({ wan_prompt_text: wanPromptText }),
  });
}

export function batchUpdateSequences(sceneId: string, payload: SequenceBatchUpdateRequest) {
  return request<Sequence[]>(`/scenes/${sceneId}/sequences/batch`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function uploadSequenceVideo(sequenceId: string, file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return request<Sequence>(`/sequences/${sequenceId}/video`, {
    method: "POST",
    body: formData,
  });
}

export function generateSequenceVideo(
  sequenceId: string,
  payload?: {
    model_name?: string;
    auto_approve?: boolean;
    seed_mode?: "random" | "fixed";
    seed?: number | null;
  },
) {
  return request<Job>(`/sequences/${sequenceId}/video/generate`, {
    method: "POST",
    body: JSON.stringify(payload ?? {}),
  });
}

export function generateSceneVideoChain(
  sceneId: string,
  payload?: {
    model_name?: string;
    auto_approve?: boolean;
    seed_mode?: "random" | "fixed";
    seed?: number | null;
  },
) {
  return request<Job>(`/scenes/${sceneId}/video/generate-chain`, {
    method: "POST",
    body: JSON.stringify(payload ?? {}),
  });
}

export function approveSequenceVideoVariant(sequenceId: string, assetId: string) {
  return request<Sequence>(`/sequences/${sequenceId}/videos/${assetId}/approve`, {
    method: "POST",
  });
}

export function updateSequenceAssembly(sequenceId: string, payload: AssemblyUpdateRequest) {
  return request<Sequence>(`/sequences/${sequenceId}/assembly`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function getPromptPackage(projectId: string) {
  return request<PromptPackage>(`/projects/${projectId}/prompt-package`);
}

export function startAssemblyExport(projectId: string) {
  return request<Job>(`/projects/${projectId}/assembly/export`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function getJob(jobId: string) {
  return request<Job>(`/jobs/${jobId}`);
}

export function startContinuityReview(sceneId: string) {
  return request<Job>(`/scenes/${sceneId}/continuity-review`, {
    method: "POST",
  });
}

export function getContinuityReview(sceneId: string) {
  return request<ContinuityReview>(`/scenes/${sceneId}/continuity-review`);
}

export function runScenarioAssistant(projectId: string, payload: ScenarioAssistantRequest) {
  return request<ScenarioAssistantResponse>(`/projects/${projectId}/scenario-assistant`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getHardware() {
  return request<HardwareProfile>("/system/hardware");
}

export function getModelSettings() {
  return request<ModelSettings>("/system/model-settings");
}

export function getMediaGenerationSettings() {
  return request<MediaGenerationSettings>("/system/media-generation-settings");
}

export function listImageModels() {
  return request<ImageModelInventory>("/system/media-generation/image-models");
}

export function uploadImageModel(file: File, options?: { destination_name?: string; set_default?: boolean }) {
  const formData = new FormData();
  formData.append("file", file);
  if (options?.destination_name) {
    formData.append("destination_name", options.destination_name);
  }
  formData.append("set_default", options?.set_default === false ? "false" : "true");
  return request<ImageModelUploadResponse>("/system/media-generation/image-models/upload", {
    method: "POST",
    body: formData,
  });
}

export function updateMediaGenerationSettings(payload: MediaGenerationSettings) {
  return request<MediaGenerationSettings>("/system/media-generation-settings", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function testMediaGenerationSettings(payload?: MediaGenerationSettings) {
  return request<MediaGenerationSettingsTestResponse>("/system/media-generation-settings/test", {
    method: "POST",
    body: payload ? JSON.stringify(payload) : undefined,
  });
}

export function startMediaModelDownload(payload: MediaModelDownloadRequest) {
  return request<MediaModelDownloadStatus>("/system/media-generation/downloads", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getMediaModelDownload(downloadId: string) {
  return request<MediaModelDownloadStatus>(`/system/media-generation/downloads/${downloadId}`);
}

export function updateModelSettings(payload: Pick<ModelSettings, "runtime" | "generation_defaults" | "task_profiles">) {
  return request<ModelSettings>("/system/model-settings", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function testModelSettingsConnection(
  payload: Pick<ModelSettings, "runtime" | "generation_defaults" | "task_profiles">,
) {
  return request<AssistantConnectionTest>("/system/model-settings/test-connection", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function testPromptPreview(payload: PromptPreviewRequest) {
  return request<PromptPreviewResponse>("/system/model-settings/test-prompt", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getProjectModelSettings(projectId: string) {
  return request<ProjectModelSettingsOverride>(`/projects/${projectId}/model-settings`);
}

export function updateProjectModelSettings(projectId: string, payload: ProjectModelSettingsOverride) {
  return request<ProjectModelSettingsOverride>(`/projects/${projectId}/model-settings`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}
