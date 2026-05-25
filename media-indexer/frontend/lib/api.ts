import {
  AdminHealthResponse,
  AdminSettings,
  ApiTokenCreateResponse,
  ApiTokenSummary,
  AssetBrowseItem,
  AssetBrowseResponse,
  AssetDetail,
  AssetFacesResponse,
  AssetListResponse,
  AuditLogEntry,
  AuthUser,
  ClusteringResultsResponse,
  CollectionDetail,
  CollectionSummary,
  CompareResponse,
  GeoFeatureCollection,
  GroupSummary,
  InboxCompareResponse,
  InboxItem,
  PublicShareResponse,
  RelatedTag,
  ResetResponse,
  ScanJob,
  ScanJobErrorEntry,
  SearchFilters,
  ScheduledScan,
  SimilarAsset,
  SmartAlbumDetail,
  SmartAlbumRule,
  SmartAlbumSummary,
  Source,
  SourceBrowseInspect,
  SourceBrowseResponse,
  SourceTreeResponse,
  SourceUploadResponse,
  TagSuggestion,
  TagCount,
  TagProvidersResponse,
  TagRebuildResponse,
  TagVocabularyEntry,
  TimelineDayBucket,
  TimelineMonthBucket,
  TimelineYearBucket,
  PersonDetail,
  PersonSummary,
  PlatformModule,
  UserRole,
  UserStatus,
  UserSummary,
  WebhookEndpoint,
} from "@/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.status === 204) {
    return undefined as T;
  }
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    throw new Error("Unexpected response from server.");
  }
  return (await response.json()) as T;
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    const body = response.headers.get("content-type")?.includes("application/json")
      ? await response.json()
      : null;
    throw new Error(body?.detail ?? "Request failed.");
  }

  return parseResponse<T>(response);
}

function buildQuery<T extends object>(filters: T): string {
  const params = new URLSearchParams();
  Object.entries(filters as Record<string, string | number | boolean | null | undefined>).forEach(([key, value]) => {
    // Explicitly include boolean false (e.g. flagged=false) — only skip nullish/empty values
    if (value === undefined || value === null || value === "") {
      return;
    }
    params.set(key, String(value));
  });
  const query = params.toString();
  return query ? `?${query}` : "";
}

export function mediaUrl(path: string | null | undefined): string | undefined {
  return path ? `${API_BASE_URL}${path}` : undefined;
}

export function assetImageUrl(id: string, options: { w?: number; h?: number; quality?: number; fmt?: "webp" | "jpeg" } = {}) {
  return `${API_BASE_URL}/assets/${id}/image${buildQuery(options)}`;
}

export function login(username: string, password: string) {
  return apiFetch<AuthUser>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function logout() {
  return apiFetch<void>("/auth/logout", { method: "POST" });
}

export function fetchMe() {
  return apiFetch<AuthUser>("/auth/me");
}

export function changePassword(payload: { current_password: string; new_password: string; confirm_password: string }) {
  return apiFetch<void>("/auth/change-password", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchSources() {
  return apiFetch<Source[]>("/sources");
}

export function fetchSource(id: string) {
  return apiFetch<Source>(`/sources/${id}`);
}

export function createSource(payload: { name: string; root_path: string; type: string }) {
  return apiFetch<Source>("/sources", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchSourceBrowse(id: string, path = "") {
  const query = path ? `?path=${encodeURIComponent(path)}` : "";
  return apiFetch<SourceBrowseResponse>(`/sources/${id}/browse${query}`);
}

export function fetchSourceInspect(id: string, path: string) {
  return apiFetch<SourceBrowseInspect>(`/sources/${id}/browse/inspect?path=${encodeURIComponent(path)}`);
}

export function fetchSourceTree(id: string, path = "") {
  const query = path ? `?path=${encodeURIComponent(path)}` : "";
  return apiFetch<SourceTreeResponse>(`/sources/${id}/tree${query}`);
}

export function deleteSource(id: string) {
  return apiFetch<void>(`/sources/${id}`, { method: "DELETE" });
}

export function triggerScan(id: string, options: { scan_mode?: "basic" | "metadata" | "ai"; path_filter?: string | null } = {}) {
  return apiFetch<ScanJob>(`/sources/${id}/scan`, {
    method: "POST",
    body: JSON.stringify({
      scan_mode: options.scan_mode ?? "basic",
      path_filter: options.path_filter ?? null,
    }),
  });
}

export function fetchScanJobs() {
  return apiFetch<ScanJob[]>("/scan-jobs");
}

export function fetchScanJob(id: string) {
  return apiFetch<ScanJob>(`/scan-jobs/${id}`);
}

export function fetchScanJobErrors(id: string) {
  return apiFetch<ScanJobErrorEntry[]>(`/scan-jobs/${id}/errors`);
}

export function cancelScanJob(id: string) {
  return apiFetch<ScanJob>(`/scan-jobs/${id}/cancel`, { method: "POST" });
}

export function clearFinishedScanJobs() {
  return apiFetch<{ deleted: number }>("/scan-jobs/finished", { method: "DELETE" });
}

export function fetchAssets(filters: SearchFilters = {}) {
  return apiFetch<AssetListResponse>(`/assets${buildQuery(filters)}`);
}

export function fetchAssetBrowse(filters: { source_id?: string; sort?: string; page?: number; page_size?: number; exclude_tags?: string } = {}) {
  const query = buildQuery(filters);
  return apiFetch<AssetBrowseResponse>(`/assets/browse${query}`);
}

export function fetchAsset(id: string) {
  return apiFetch<AssetDetail>(`/assets/${id}`);
}

export function runAssetVisionLlm(id: string) {
  return apiFetch<{ ok: boolean; analysis: string; source: string }>(`/assets/${id}/vision-llm`, { method: "POST" });
}

export function fetchAssetFaces(id: string) {
  return apiFetch<AssetFacesResponse>(`/assets/${id}/faces`);
}

export function fetchSearch(filters: SearchFilters = {}) {
  return apiFetch<AssetListResponse>(`/search${buildQuery(filters)}`);
}

export function fetchNaturalLanguageSearch(q: string, limit = 50) {
  return apiFetch<AssetListResponse>(`/search/nl${buildQuery({ q, limit })}`);
}

export function fetchTags() {
  return apiFetch<TagCount[]>("/tags");
}

export function fetchTagAssets(tag: string, page = 1, pageSize = 24) {
  return apiFetch<AssetListResponse>(`/tags/${encodeURIComponent(tag)}/assets?page=${page}&page_size=${pageSize}`);
}

export function fetchSimilar(id: string, type: "duplicate" | "semantic" | "tag", limit = 50) {
  return apiFetch<SimilarAsset[]>(`/assets/${id}/similar?type=${type}&limit=${limit}`);
}

export function fetchSimilarByImage(id: string, limit = 24) {
  return apiFetch<SimilarAsset[]>(`/assets/${id}/search-similar-by-image?limit=${limit}`);
}

export function bulkAnnotateAssets(payload: {
  asset_ids: string[];
  rating?: number | null;
  review_status?: string | null;
  flagged?: boolean | null;
  note?: string | null;
  tags?: string[] | null;
}) {
  return apiFetch<void>("/assets/bulk-annotate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchCompare(a: string, b: string) {
  return apiFetch<CompareResponse>(`/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`);
}

export function fetchGeoAssets(bbox?: string) {
  return apiFetch<GeoFeatureCollection>(`/assets/geo${buildQuery({ bbox })}`);
}

export function fetchPeople(filters: { q?: string; unnamed_only?: boolean } = {}) {
  return apiFetch<PersonSummary[]>(`/people${buildQuery(filters)}`);
}

export function fetchPerson(id: string) {
  return apiFetch<PersonDetail>(`/people/${id}`);
}

export function fetchPersonAssets(id: string) {
  return apiFetch<AssetBrowseItem[]>(`/people/${id}/assets`);
}

export function updatePerson(id: string, payload: { name?: string | null; cover_face_id?: string | null }) {
  return apiFetch<PersonDetail>(`/people/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function mergePerson(id: string, sourcePersonId: string) {
  return apiFetch<PersonDetail>(`/people/${id}/merge`, {
    method: "POST",
    body: JSON.stringify({ source_person_id: sourcePersonId }),
  });
}

export function reclusterPeople() {
  return apiFetch<{ reassigned_faces: number; created_people: number }>("/people/recluster", {
    method: "POST",
  });
}

export function fetchSmartAlbums() {
  return apiFetch<SmartAlbumSummary[]>("/smart-albums");
}

export function fetchSmartAlbum(id: string) {
  return apiFetch<SmartAlbumDetail>(`/smart-albums/${id}`);
}

export function createSmartAlbum(payload: {
  name: string;
  description?: string | null;
  enabled?: boolean;
  rule: SmartAlbumRule;
}) {
  return apiFetch<SmartAlbumSummary>("/smart-albums", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateSmartAlbum(
  id: string,
  payload: {
    name?: string;
    description?: string | null;
    enabled?: boolean;
    rule?: SmartAlbumRule;
  }
) {
  return apiFetch<SmartAlbumSummary>(`/smart-albums/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteSmartAlbum(id: string) {
  return apiFetch<void>(`/smart-albums/${id}`, { method: "DELETE" });
}

export function syncSmartAlbum(id: string) {
  return apiFetch<SmartAlbumSummary>(`/smart-albums/${id}/sync`, { method: "POST" });
}

export function fetchInbox(status?: string, countOnly = false) {
  return apiFetch<InboxItem[] | { count: number }>(`/inbox${buildQuery({ status, count_only: countOnly })}`);
}

export function fetchInboxCompare(id: string) {
  return apiFetch<InboxCompareResponse>(`/inbox/${id}/compare`);
}

export function approveInboxItem(id: string, targetSourceId?: string) {
  return apiFetch<void>(`/inbox/${id}/approve`, {
    method: "POST",
    body: JSON.stringify({ target_source_id: targetSourceId }),
  });
}

export function rejectInboxItem(id: string) {
  return apiFetch<void>(`/inbox/${id}/reject`, { method: "POST" });
}

export function submitCompareReview(assetIdA: string, assetIdB: string, action: string) {
  return apiFetch<void>("/compare/review", {
    method: "POST",
    body: JSON.stringify({ asset_id_a: assetIdA, asset_id_b: assetIdB, action }),
  });
}

export function resetApplicationData(mode: "index" | "all") {
  return apiFetch<ResetResponse>("/admin/reset", {
    method: "POST",
    body: JSON.stringify({ mode }),
  });
}

export function fetchAdminUsers() {
  return apiFetch<UserSummary[]>("/admin/users");
}

export function fetchModuleRegistry() {
  return apiFetch<PlatformModule[]>("/modules/registry");
}

export function fetchAdminModules() {
  return apiFetch<PlatformModule[]>("/admin/modules");
}

export function fetchAdminModule(moduleId: string) {
  return apiFetch<PlatformModule>(`/admin/modules/${encodeURIComponent(moduleId)}`);
}

export function updateAdminModule(
  moduleId: string,
  payload: { enabled?: boolean; settings_json?: Record<string, unknown> }
) {
  return apiFetch<PlatformModule>(`/admin/modules/${encodeURIComponent(moduleId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function rescanAdminModules() {
  return apiFetch<PlatformModule[]>("/admin/modules/rescan", {
    method: "POST",
  });
}

export function createAdminUser(payload: { username: string; password: string; role: UserRole }) {
  return apiFetch<UserSummary>("/admin/users", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateAdminUser(
  id: string,
  payload: {
    username?: string;
    role?: UserRole;
    status?: UserStatus;
    locked_until?: string | null;
    ban_reason?: string | null;
    group_ids?: string[];
  }
) {
  return apiFetch<UserSummary>(`/admin/users/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteAdminUser(id: string) {
  return apiFetch<void>(`/admin/users/${id}`, { method: "DELETE" });
}

export function fetchGroups() {
  return apiFetch<GroupSummary[]>("/admin/groups");
}

// Aliases used by /admin/groups and /admin/users pages
export const fetchAdminGroups = fetchGroups;

export function createGroup(payload: { name: string; description: string; permissions: Record<string, unknown> }) {
  return apiFetch<GroupSummary>("/admin/groups", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export const createAdminGroup = createGroup;

export function updateGroup(id: string, payload: { name?: string; description?: string; permissions?: Record<string, unknown> }) {
  return apiFetch<GroupSummary>(`/admin/groups/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export const updateAdminGroup = updateGroup;

export function deleteGroup(id: string) {
  return apiFetch<void>(`/admin/groups/${id}`, { method: "DELETE" });
}

export const deleteAdminGroup = deleteGroup;

export function resetAdminUserPassword(id: string, newPassword: string) {
  return apiFetch<void>(`/admin/users/${id}/password`, {
    method: "POST",
    body: JSON.stringify({ new_password: newPassword }),
  });
}

export function fetchAuditLogs(limit = 50) {
  return apiFetch<AuditLogEntry[]>(`/admin/audit-logs?limit=${limit}`);
}

export function fetchAdminSettings() {
  return apiFetch<AdminSettings>("/admin/settings");
}

export function fetchAdminHealth() {
  return apiFetch<AdminHealthResponse>("/admin/health");
}

export function fetchSchedules() {
  return apiFetch<ScheduledScan[]>("/admin/schedules");
}

export function createSchedule(payload: { source_id: string; cron_expression: string; enabled?: boolean }) {
  return apiFetch<ScheduledScan>("/admin/schedules", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateSchedule(id: string, payload: { cron_expression?: string; enabled?: boolean }) {
  return apiFetch<ScheduledScan>(`/admin/schedules/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteSchedule(id: string) {
  return apiFetch<void>(`/admin/schedules/${id}`, { method: "DELETE" });
}

export function fetchWebhookEvents() {
  return apiFetch<string[]>("/admin/webhook-events");
}

export function fetchWebhooks() {
  return apiFetch<WebhookEndpoint[]>("/admin/webhooks");
}

export function createWebhook(payload: { url: string; secret: string; events: string[]; enabled?: boolean }) {
  return apiFetch<WebhookEndpoint>("/admin/webhooks", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateWebhook(id: string, payload: { url?: string; secret?: string; events?: string[]; enabled?: boolean }) {
  return apiFetch<WebhookEndpoint>(`/admin/webhooks/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteWebhook(id: string) {
  return apiFetch<void>(`/admin/webhooks/${id}`, { method: "DELETE" });
}

export function testWebhook(id: string) {
  return apiFetch<void>(`/admin/webhooks/${id}/test`, { method: "POST" });
}

export function fetchApiTokens() {
  return apiFetch<ApiTokenSummary[]>("/admin/api-tokens");
}

export function createApiToken(payload: { name: string; expires_at?: string | null }) {
  return apiFetch<ApiTokenCreateResponse>("/admin/api-tokens", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function revokeApiToken(id: string) {
  return apiFetch<void>(`/admin/api-tokens/${id}`, { method: "DELETE" });
}

export function updateAdminSettings(payload: AdminSettings) {
  return apiFetch<AdminSettings>("/admin/settings", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function rebuildTagSimilarity() {
  return apiFetch<{ rebuilt_assets: number; rebuilt_links: number }>("/admin/settings/rebuild-tag-similarity", {
    method: "POST",
  });
}

export async function restoreBackup(file: File, options: { dryRun?: boolean; confirm?: string } = {}) {
  const query = buildQuery({
    dry_run: options.dryRun ?? false,
    confirm: options.confirm ?? "",
  });
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${API_BASE_URL}/admin/restore${query}`, {
    method: "POST",
    credentials: "include",
    body: formData,
  });
  if (!response.ok) {
    const body = response.headers.get("content-type")?.includes("application/json")
      ? await response.json()
      : null;
    throw new Error(body?.detail ?? "Restore failed.");
  }
  return parseResponse<Record<string, unknown>>(response);
}

export function purgeDeepzoom() {
  return apiFetch<{ deleted_tile_directories: number; deleted_manifests: number }>("/admin/purge-deepzoom", {
    method: "POST",
  });
}

export function reindexSearch() {
  return apiFetch<{ rebuilt_assets: number }>("/admin/reindex-search", {
    method: "POST",
  });
}

export function fetchCollections() {
  return apiFetch<CollectionSummary[]>("/collections");
}

export function createCollection(payload: { name: string; description: string }) {
  return apiFetch<CollectionSummary>("/collections", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchCollection(id: string, page = 1, pageSize = 36) {
  return apiFetch<CollectionDetail>(`/collections/${id}?page=${page}&page_size=${pageSize}`);
}

export function updateCollection(id: string, payload: { name?: string; description?: string }) {
  return apiFetch<CollectionSummary>(`/collections/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteCollection(id: string) {
  return apiFetch<void>(`/collections/${id}`, { method: "DELETE" });
}

export function addAssetsToCollection(id: string, assetIds: string[]) {
  return apiFetch<CollectionDetail>(`/collections/${id}/assets`, {
    method: "POST",
    body: JSON.stringify({ asset_ids: assetIds }),
  });
}

export function addSearchResultsToCollection(
  id: string,
  payload: {
    q?: string;
    media_type?: string;
    caption?: string;
    ocr_text?: string;
    camera_make?: string;
    camera_model?: string;
    year?: number;
    width_min?: number;
    width_max?: number;
    height_min?: number;
    height_max?: number;
    duration_min?: number;
    duration_max?: number;
    tags?: string[];
    auto_tags?: string[];
  }
) {
  return apiFetch<CollectionDetail>(`/collections/${id}/search-results`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function removeAssetFromCollection(id: string, assetId: string) {
  return apiFetch<void>(`/collections/${id}/assets/${assetId}`, { method: "DELETE" });
}

export async function uploadToSource(id: string, files: File[], folder = "") {
  const formData = new FormData();
  if (folder.trim()) {
    formData.append("folder", folder.trim());
  }
  files.forEach((file) => formData.append("files", file));

  const response = await fetch(`${API_BASE_URL}/sources/${id}/upload`, {
    method: "POST",
    credentials: "include",
    body: formData,
  });
  if (!response.ok) {
    const body = response.headers.get("content-type")?.includes("application/json")
      ? await response.json()
      : null;
    throw new Error(body?.detail ?? "Upload failed.");
  }
  return parseResponse<SourceUploadResponse>(response);
}

/** M4 — Auth-aware workflow download; avoids 401 on JWT setups */
export async function downloadWorkflow(assetId: string, filename: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/assets/${assetId}/workflow/download`, {
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error("Workflow download failed.");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename.endsWith(".json") ? filename : `${filename}_workflow.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export async function downloadWorkflowFromFile(assetId: string, filename: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/assets/${assetId}/workflow/extract-from-file`, {
    credentials: "include",
  });
  if (!response.ok) {
    const body = response.headers.get("content-type")?.includes("application/json")
      ? await response.json()
      : null;
    throw new Error(body?.detail ?? "No workflow found in file.");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename.endsWith(".json") ? filename : `${filename}_workflow.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// --- Feature 1: Timeline ---
export function fetchTimelineYears(sourceId?: string) {
  return apiFetch<TimelineYearBucket[]>("/timeline/years" + buildQuery({ source_id: sourceId }));
}
export function fetchTimelineMonths(year: number, sourceId?: string) {
  return apiFetch<TimelineMonthBucket[]>("/timeline/months" + buildQuery({ year, source_id: sourceId }));
}
export function fetchTimelineDays(year: number, month: number, sourceId?: string) {
  return apiFetch<TimelineDayBucket[]>("/timeline/days" + buildQuery({ year, month, source_id: sourceId }));
}
export function fetchTimelineAssets(year: number, month?: number, day?: number, page: number = 1) {
  const limit = 50;
  const offset = (page - 1) * limit;
  return apiFetch<AssetListResponse>("/timeline/assets" + buildQuery({ year, month, day, limit, offset }));
}

// --- Feature 2: Clustering ---
export function triggerClustering(k: number, minSize: number) {
  return apiFetch<{ job_id: string }>("/admin/clustering/suggest", {
    method: "POST",
    body: JSON.stringify({ k, min_size: minSize }),
  });
}
export function fetchClusteringResults(jobId: string) {
  return apiFetch<ClusteringResultsResponse>(`/admin/clustering/results/${jobId}`);
}
export function acceptClusterProposals(proposals: Array<{ label: string; asset_ids: string[] }>) {
  return apiFetch<{ created_collections: number }>("/admin/clustering/accept", {
    method: "POST",
    body: JSON.stringify({ proposals }),
  });
}

// --- Feature 4: Tag Vocabulary ---
export function fetchTagVocabulary() {
  return apiFetch<TagVocabularyEntry[]>("/tags/vocabulary");
}
export function createTagVocabularyEntry(payload: { tag: string; description?: string; clip_prompt: string; enabled?: boolean }) {
  return apiFetch<TagVocabularyEntry>("/tags/vocabulary", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchTagSuggestions(assetId: string) {
  return apiFetch<TagSuggestion[]>(`/tags/suggestions/asset/${assetId}`);
}

export function submitTagSuggestionAction(suggestionId: number, action: "accept" | "reject") {
  return apiFetch<{ status: string }>("/tags/suggestions/action", {
    method: "POST",
    body: JSON.stringify({ suggestion_id: suggestionId, action }),
  });
}

export function fetchTagProviders() {
  return apiFetch<TagProvidersResponse>("/tags/providers");
}

export function preloadTagProviders() {
  return apiFetch<TagProvidersResponse>("/tags/providers/preload", {
    method: "POST",
  });
}

export function rebuildTags(payload: {
  scope?: "all" | "source" | "asset";
  source_id?: string;
  asset_id?: string;
  provider?: "wd_vit_v3" | "deepghs_wd_embeddings" | "clip_vocab";
  compare_mode?: boolean;
}) {
  return apiFetch<TagRebuildResponse>("/tags/rebuild", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchRelatedTags(tag: string, limit = 12) {
  return apiFetch<RelatedTag[]>(`/tags/related?tag=${encodeURIComponent(tag)}&limit=${limit}`);
}

export function fetchPublicShare(id: string) {
  return apiFetch<PublicShareResponse>(`/share/${id}`);
}

