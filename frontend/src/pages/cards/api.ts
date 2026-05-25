import type {
  AssistantConnectionTest,
  Character,
  CharacterCreateRequest,
  CharacterUpdateRequest,
  CompatibilityReport,
  GMCardProfile,
  GeneratedImagePrompt,
  HardwareProfile,
  ImageCandidate,
  ImageShotFormat,
  ImageModelInventory,
  ImageModelUploadResponse,
  LoreEntry,
  LoreEntryCreateRequest,
  LoreEntryUpdateRequest,
  MediaGenerationSettings,
  MediaGenerationSettingsTestResponse,
  ModelSettings,
  Project,
  ProjectCreateRequest,
  ProjectListItem,
  ProjectModelSettingsOverride,
  ProjectScope,
  ProjectUpdateRequest,
  PromptPreviewRequest,
  PromptPreviewResponse,
  SillyTavernStatus,
  SillyTavernSyncResponse,
  UserProfile,
  UserProfileUpdateRequest,
} from "./types";

const API_BASE = import.meta.env.VITE_CARDS_API_BASE_URL ?? "/cards";

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
      // keep status text
    }
    throw new Error(message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export function characterExportJsonUrl(projectId: string, characterId: string) {
  return buildUrl(`/projects/${projectId}/characters/${characterId}/export.json`);
}

export function characterExportImageUrl(projectId: string, characterId: string, format: "png" | "webp") {
  return buildUrl(`/projects/${projectId}/characters/${characterId}/export.image?image_format=${format}`);
}

export function gmCardExportJsonUrl(projectId: string) {
  return buildUrl(`/projects/${projectId}/gm-card/export.json`);
}

export function gmCardExportImageUrl(projectId: string, format: "png" | "webp") {
  return buildUrl(`/projects/${projectId}/gm-card/export.image?image_format=${format}`);
}

export function lorebookExportUrl(projectId: string) {
  return buildUrl(`/projects/${projectId}/lorebook.json`);
}

export function userExportUrl(projectId: string) {
  return buildUrl(`/projects/${projectId}/user-export.json`);
}

export function personaCardExportJsonUrl(projectId: string) {
  return buildUrl(`/projects/${projectId}/persona-card/export.json`);
}

export function personaCardExportImageUrl(projectId: string, format: "png" | "webp") {
  return buildUrl(`/projects/${projectId}/persona-card/export.image?image_format=${format}`);
}

export function bundleExportUrl(projectId: string) {
  return buildUrl(`/projects/${projectId}/export-bundle.json`);
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

export function getGmCard(projectId: string) {
  return request<GMCardProfile>(`/projects/${projectId}/gm-card`);
}

export function updateGmCard(projectId: string, payload: Partial<GMCardProfile>) {
  return request<GMCardProfile>(`/projects/${projectId}/gm-card`, {
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

export function listCharacters(projectId: string) {
  return request<Character[]>(`/projects/${projectId}/characters`);
}

export function createCharacter(projectId: string, payload: CharacterCreateRequest) {
  return request<Character>(`/projects/${projectId}/characters`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateCharacter(projectId: string, characterId: string, payload: CharacterUpdateRequest) {
  return request<Character>(`/projects/${projectId}/characters/${characterId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteCharacter(projectId: string, characterId: string) {
  return request<void>(`/projects/${projectId}/characters/${characterId}`, {
    method: "DELETE",
  });
}

export function generateCharacterImage(
  projectId: string,
  characterId: string,
  format: ImageShotFormat,
  options?: { instruction?: string; prompt?: string; negative_prompt?: string },
) {
  return request<Character>(`/projects/${projectId}/characters/${characterId}/images/generate`, {
    method: "POST",
    body: JSON.stringify({
      format,
      instruction: options?.instruction ?? "",
      prompt: options?.prompt ?? "",
      negative_prompt: options?.negative_prompt ?? "",
    }),
  });
}

export function generateScenarioImage(projectId: string, options?: { instruction?: string; prompt?: string; negative_prompt?: string }) {
  return request<Project>(`/projects/${projectId}/images/scenario/generate`, {
    method: "POST",
    body: JSON.stringify({
      instruction: options?.instruction ?? "",
      prompt: options?.prompt ?? "",
      negative_prompt: options?.negative_prompt ?? "",
    }),
  });
}

export function listLoreEntries(projectId: string) {
  return request<LoreEntry[]>(`/projects/${projectId}/lore-entries`);
}

export function createLoreEntry(projectId: string, payload: LoreEntryCreateRequest) {
  return request<LoreEntry>(`/projects/${projectId}/lore-entries`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateLoreEntry(projectId: string, loreId: string, payload: LoreEntryUpdateRequest) {
  return request<LoreEntry>(`/projects/${projectId}/lore-entries/${loreId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteLoreEntry(projectId: string, loreId: string) {
  return request<void>(`/projects/${projectId}/lore-entries/${loreId}`, {
    method: "DELETE",
  });
}

export function generateLoreImage(projectId: string, loreId: string, options?: { instruction?: string; prompt?: string; negative_prompt?: string }) {
  return request<LoreEntry>(`/projects/${projectId}/lore-entries/${loreId}/image/generate`, {
    method: "POST",
    body: JSON.stringify({
      instruction: options?.instruction ?? "",
      prompt: options?.prompt ?? "",
      negative_prompt: options?.negative_prompt ?? "",
    }),
  });
}

export function getUserProfile(projectId: string) {
  return request<UserProfile>(`/projects/${projectId}/user-profile`);
}

export function updateUserProfile(projectId: string, payload: UserProfileUpdateRequest) {
  return request<UserProfile>(`/projects/${projectId}/user-profile`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function generateUserImage(
  projectId: string,
  format: ImageShotFormat,
  options?: { instruction?: string; prompt?: string; negative_prompt?: string },
) {
  return request<UserProfile>(`/projects/${projectId}/user-profile/images/generate`, {
    method: "POST",
    body: JSON.stringify({
      format,
      instruction: options?.instruction ?? "",
      prompt: options?.prompt ?? "",
      negative_prompt: options?.negative_prompt ?? "",
    }),
  });
}

export function generateScenarioImagePrompt(projectId: string, instruction = "") {
  return request<GeneratedImagePrompt>(`/projects/${projectId}/images/scenario/prompt`, {
    method: "POST",
    body: JSON.stringify({ instruction }),
  });
}

export function generateCharacterImagePrompt(
  projectId: string,
  characterId: string,
  format: ImageShotFormat,
  instruction = "",
) {
  return request<GeneratedImagePrompt>(`/projects/${projectId}/characters/${characterId}/images/prompt`, {
    method: "POST",
    body: JSON.stringify({ format, instruction }),
  });
}

export function generateLoreImagePrompt(projectId: string, loreId: string, instruction = "") {
  return request<GeneratedImagePrompt>(`/projects/${projectId}/lore-entries/${loreId}/image/prompt`, {
    method: "POST",
    body: JSON.stringify({ instruction }),
  });
}

export function generateUserImagePrompt(projectId: string, format: ImageShotFormat, instruction = "") {
  return request<GeneratedImagePrompt>(`/projects/${projectId}/user-profile/images/prompt`, {
    method: "POST",
    body: JSON.stringify({ format, instruction }),
  });
}

export function listImageCandidates(
  projectId: string,
  filters: {
    owner_type?: "scenario" | "character" | "lore" | "user";
    owner_id?: string;
    image_slot?: string;
    limit?: number;
  },
) {
  const params = new URLSearchParams();
  if (filters.owner_type) params.set("owner_type", filters.owner_type);
  if (filters.owner_id) params.set("owner_id", filters.owner_id);
  if (filters.image_slot) params.set("image_slot", filters.image_slot);
  if (filters.limit) params.set("limit", String(filters.limit));
  const query = params.toString();
  return request<ImageCandidate[]>(`/projects/${projectId}/image-candidates${query ? `?${query}` : ""}`);
}

export function approveImageCandidate(projectId: string, candidateId: string) {
  return request<ImageCandidate>(`/projects/${projectId}/image-candidates/${candidateId}/approve`, {
    method: "POST",
  });
}

export function generateScenario(projectId: string, instruction = "") {
  return request<Project>(`/projects/${projectId}/generate/scenario`, {
    method: "POST",
    body: JSON.stringify({ instruction }),
  });
}

export function generateCharacters(projectId: string, options?: { overwriteExisting?: boolean; targetCount?: number; instruction?: string }) {
  return request<Project>(`/projects/${projectId}/generate/characters`, {
    method: "POST",
    body: JSON.stringify({
      overwrite_existing: options?.overwriteExisting ?? true,
      target_count: options?.targetCount ?? 5,
      instruction: options?.instruction ?? "",
    }),
  });
}

export function generateLore(projectId: string, options?: { overwriteExisting?: boolean; instruction?: string }) {
  return request<Project>(`/projects/${projectId}/generate/lore`, {
    method: "POST",
    body: JSON.stringify({
      overwrite_existing: options?.overwriteExisting ?? true,
      instruction: options?.instruction ?? "",
    }),
  });
}

export function generateUser(projectId: string, instruction = "") {
  return request<Project>(`/projects/${projectId}/generate/user`, {
    method: "POST",
    body: JSON.stringify({ instruction }),
  });
}

export function generateGmCard(projectId: string, instruction = "") {
  return request<Project>(`/projects/${projectId}/generate/gm-card`, {
    method: "POST",
    body: JSON.stringify({ instruction }),
  });
}

export function generateAll(
  projectId: string,
  options?: {
    overwriteCharacters?: boolean;
    overwriteLore?: boolean;
    targetCount?: number;
    instruction?: string;
  },
) {
  return request<Project>(`/projects/${projectId}/generate/all`, {
    method: "POST",
    body: JSON.stringify({
      overwrite_characters: options?.overwriteCharacters ?? true,
      overwrite_lore: options?.overwriteLore ?? true,
      target_count: options?.targetCount,
      instruction: options?.instruction ?? "",
    }),
  });
}

export function getHardware() {
  return request<HardwareProfile>("/system/hardware");
}

export function getSillyTavernStatus() {
  return request<SillyTavernStatus>("/system/sillytavern");
}

export function syncProjectToSillyTavern(projectId: string) {
  return request<SillyTavernSyncResponse>(`/projects/${projectId}/sillytavern/sync`, {
    method: "POST",
  });
}

export function inspectCompatibility(projectId: string) {
  return request<CompatibilityReport>(`/projects/${projectId}/compatibility`);
}

export function getModelSettings() {
  return request<ModelSettings>("/system/model-settings");
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

export function getMediaGenerationSettings() {
  return request<MediaGenerationSettings>("/system/media-generation-settings");
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
