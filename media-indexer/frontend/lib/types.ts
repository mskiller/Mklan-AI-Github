export type MediaType = "image" | "video" | "unknown";
export type MatchType = "duplicate" | "semantic" | "tag";
export type SortField = "relevance" | "created_at" | "modified_at" | "filename" | "rating" | "review_status";
export type BrowseIndexState = "indexed" | "metadata_refresh_pending" | "processing" | "live_browse";
export type UserRole = "admin" | "curator" | "guest";
export type UserStatus = "active" | "disabled" | "locked" | "banned";
export type ReviewStatus = "unreviewed" | "approved" | "rejected" | "favorite";

export interface AssetAnnotation {
  id: string | null;
  user_id: string | null;
  rating: number | null;
  review_status: ReviewStatus;
  note: string | null;
  flagged: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface AuthCapabilities {
  can_manage_sources: boolean;
  can_run_scans: boolean;
  can_review_compare: boolean;
  can_reset: boolean;
  can_manage_users: boolean;
  can_manage_collections: boolean;
  can_upload_assets: boolean;
  can_view_admin: boolean;
  allowed_source_ids: string[] | "all";
}

export interface AuthUser {
  authenticated: boolean;
  id: string;
  username: string;
  role: UserRole;
  capabilities: AuthCapabilities;
}

export interface Source {
  id: string;
  name: string;
  type: string;
  root_path: string | null;
  display_root_path: string;
  status: string;
  last_scan_at: string | null;
  created_at: string;
}

export interface SourceTreeFileEntry {
  name: string;
  relative_path: string;
  indexed: boolean;
}

export interface SourceTreeResponse {
  path: string;
  dirs: string[];
  files: SourceTreeFileEntry[];
}

export interface SourceBreadcrumb {
  label: string;
  path: string;
}

export interface SourceBrowseEntry {
  name: string;
  relative_path: string;
  entry_type: "directory" | "file";
  media_type: MediaType | null;
  mime_type: string | null;
  size_bytes: number | null;
  modified_at: string | null;
  indexed_asset_id: string | null;
  index_state: BrowseIndexState | null;
  preview_url: string | null;
  content_url: string | null;
}

export interface SourceBrowseResponse {
  source_id: string;
  current_path: string;
  parent_path: string | null;
  breadcrumbs: SourceBreadcrumb[];
  entries: SourceBrowseEntry[];
}

export interface ScanJob {
  id: string;
  source_id: string;
  status: string;
  scan_mode: "basic" | "metadata" | "ai" | string;
  path_filter: string | null;
  progress: number;
  scanned_count: number;
  new_count: number;
  updated_count: number;
  deleted_count: number;
  error_count: number;
  message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface ScanJobErrorEntry {
  path: string;
  error: string;
  at: string;
}

export interface ResetResponse {
  deleted_assets: number;
  deleted_scan_jobs: number;
  deleted_sources: number;
  deleted_audit_logs: number;
}

export interface UserSummary {
  id: string;
  username: string;
  role: UserRole;
  status: UserStatus;
  locked_until: string | null;
  ban_reason: string | null;
  group_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface GroupSummary {
  id: string;
  name: string;
  description: string;
  permissions: Record<string, unknown>;
  created_at: string;
}

export interface AuditLogEntry {
  id: string;
  actor: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  details: Record<string, unknown>;
  created_at: string;
}

export interface AssetSummary {
  id: string;
  source_id: string;
  relative_path: string;
  filename: string;
  extension: string;
  media_type: MediaType;
  mime_type: string;
  size_bytes: number;
  modified_at: string;
  created_at: string | null;
  indexed_at: string;
  preview_url: string | null;
  content_url: string;
  blur_hash: string | null;
  deepzoom_available: boolean;
  deepzoom_url: string | null;
  tags: string[];
  normalized_metadata: Record<string, unknown>;
  caption: string | null;
  caption_source: string | null;
  ocr_text: string | null;
  ocr_confidence: number | null;
  annotation: AssetAnnotation | null;
  workflow_export_available: boolean;
  waveform_url: string | null;
  video_keyframes: string[] | null;
}

export interface AssetDetail extends AssetSummary {
  raw_metadata: Record<string, unknown>;
  source_name: string;
  workflow_export_available: boolean;
  workflow_export_url: string | null;
  visual_workflow_json?: {
    nodes: any[];
    edges: any[];
  } | null;
  visual_workflow_confidence?: number | null;
  visual_workflow_updated_at?: string | null;
}

export interface AssetFacePerson {
  id: string;
  name: string | null;
}

export interface AssetFace {
  id: string;
  asset_id: string;
  bbox_x1: number;
  bbox_y1: number;
  bbox_x2: number;
  bbox_y2: number;
  det_score: number;
  crop_preview_url: string | null;
  person: AssetFacePerson | null;
}

export interface AssetFacesResponse {
  enabled: boolean;
  image_width: number | null;
  image_height: number | null;
  items: AssetFace[];
}

export interface AssetListResponse {
  items: AssetSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface TagCount {
  tag: string;
  count: number;
}

export interface SimilarAsset {
  asset: AssetSummary;
  match_type: MatchType;
  distance: number;
  score: number;
  prompt_tag_overlap: number;
  shared_prompt_tags: string[];
}

export interface AssetBrowseItem {
  id: string;
  source_id: string;
  source_name: string;
  filename: string;
  relative_path: string;
  preview_url: string | null;
  content_url: string;
  blur_hash: string | null;
  deepzoom_available: boolean;
  deepzoom_url: string | null;
  width: number | null;
  height: number | null;
  modified_at: string;
  created_at: string | null;
  size_bytes: number;
  generator: string | null;
  prompt_excerpt: string | null;
  prompt_tags: string[];
  prompt_tag_string: string | null;
  caption: string | null;
  ocr_text: string | null;
  annotation: AssetAnnotation | null;
  workflow_export_available: boolean;
  media_type: MediaType;
  waveform_url: string | null;
  video_keyframes: string[] | null;
}

export interface AssetBrowseResponse {
  items: AssetBrowseItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface TimelineYearBucket {
  year: number;
  count: number;
}

export interface TimelineMonthBucket {
  month: number;
  count: number;
}

export interface TimelineDayBucket {
  day: number;
  count: number;
}

export interface TagVocabularyEntry {
  id: number;
  tag: string;
  description: string | null;
  clip_prompt: string;
  enabled: boolean;
}

export interface TagSuggestion {
  id: number;
  asset_id: string;
  tag: string;
  tag_group: string | null;
  confidence: number;
  source_model: string | null;
  rank: number | null;
  raw_score: number | null;
  threshold_used: number | null;
  source_payload: Record<string, unknown> | null;
  status: string;
  created_at: string;
}

export interface TagProviderStatus {
  key: string;
  label: string;
  status: string;
  device: string;
  source_model: string;
  warm: boolean;
  detail: string | null;
}

export interface TagProvidersResponse {
  providers: TagProviderStatus[];
}

export interface TagRebuildResponse {
  processed_assets: number;
  created_suggestions: number;
}

export interface RelatedTag {
  tag: string;
  score: number;
  group: string;
  source_model: string;
}

export interface ClusterProposal {
  centroid_id: string;
  cover_asset_ids: string[];
  asset_ids: string[];
  size: number;
  suggested_label: string;
}

export interface ClusteringPendingStatus {
  status: "processing";
}

export interface ClusteringErrorStatus {
  status: "error";
  message: string;
}

export type ClusteringResultsResponse = ClusterProposal[] | ClusteringPendingStatus | ClusteringErrorStatus;

export interface PublicShareItem {
  id: string;
  filename: string;
  size_bytes: number;
  preview_url: string | null;
  content_url: string | null;
}

export interface PublicShareResponse {
  type: "asset" | "collection";
  label: string;
  item: PublicShareItem | null;
  items: PublicShareItem[];
  allow_download: boolean;
}

export interface SourceBrowseInspect {
  source_id: string;
  relative_path: string;
  indexed_asset_id: string | null;
  index_state: BrowseIndexState | null;
  preview_url: string | null;
  content_url: string | null;
  blur_hash: string | null;
  deepzoom_available: boolean;
  deepzoom_url: string | null;
  width: number | null;
  height: number | null;
  generator: string | null;
  prompt_excerpt: string | null;
  prompt_tags: string[];
  prompt_tag_string: string | null;
  annotation: AssetAnnotation | null;
}

export interface SourceUploadResponse {
  source_id: string;
  folder: string;
  uploaded_files: string[];
  scan_job_id: string | null;
}

export interface HealthDbStats {
  connected: boolean;
  pool_size: number;
  checked_out: number;
}

export interface HealthWorkerQueueStats {
  pending_jobs: number;
  running_jobs: number;
}

export interface HealthDiskSource {
  source_id: string;
  name: string;
  path: string;
  free_gb: number;
  total_gb: number;
}

export interface HealthDiskStats {
  sources: HealthDiskSource[];
  previews_gb: number;
}

export interface HealthModelState {
  loaded: boolean;
  model_id?: string | null;
}

export interface ScheduledScan {
  id: string;
  source_id: string;
  source_name: string;
  cron_expression: string;
  enabled: boolean;
  last_triggered_at: string | null;
  last_job_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface AdminHealthResponse {
  status: string;
  db: HealthDbStats;
  worker_queue: HealthWorkerQueueStats;
  disk: HealthDiskStats;
  models: Record<string, HealthModelState>;
  schedules: Array<{
    schedule_id: string;
    source_id: string;
    source_name: string;
    cron_expression: string;
    enabled: boolean;
    last_run: string | null;
    last_job_id: string | null;
    status: string;
  }>;
}

export interface WebhookEndpoint {
  id: string;
  url: string;
  events: string[];
  enabled: boolean;
  created_at: string;
  last_delivered_at: string | null;
  last_status_code: number | null;
}

export interface ApiTokenSummary {
  id: string;
  name: string;
  token_prefix: string;
  created_by: string;
  expires_at: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

export interface ApiTokenCreateResponse {
  token: string;
  item: ApiTokenSummary;
}

export interface GeoFeatureCollection {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    geometry: {
      type: "Point";
      coordinates: [number, number];
    };
    properties: {
      id: string;
      thumbnail_url: string | null;
      filename: string;
      taken_at: string | null;
    };
  }>;
}

export interface InboxItem {
  id: string;
  filename: string;
  inbox_path: string;
  file_size: number;
  phash: string | null;
  clip_distance_min: number | null;
  nearest_asset_id: string | null;
  status: string;
  target_source_id: string | null;
  target_source_name: string | null;
  created_at: string;
  reviewed_at: string | null;
  reviewed_by: string | null;
  error_message: string | null;
  thumbnail_url: string | null;
}

export interface InboxCompareResponse {
  item: InboxItem;
  nearest_asset: AssetSummary | null;
}

export interface CollectionSummary {
  id: string;
  name: string;
  description: string;
  created_by: string;
  asset_count: number;
  created_at: string;
  updated_at: string;
}

export interface CollectionDetail extends CollectionSummary {
  items: AssetBrowseItem[];
  page: number;
  page_size: number;
  total: number;
}

export interface PersonSummary {
  id: string;
  name: string | null;
  cover_face_url: string | null;
  face_count: number;
  asset_count: number;
  created_at: string;
}

export interface PersonDetail extends PersonSummary {
  faces: AssetFace[];
  items: AssetBrowseItem[];
}

export interface SmartAlbumRule {
  media_type?: MediaType | null;
  source_ids: string[];
  tags_any: string[];
  auto_tags_any: string[];
  people_ids: string[];
  review_status?: ReviewStatus | null;
  min_rating?: number | null;
  flagged?: boolean | null;
  has_gps?: boolean | null;
  date_from?: string | null;
  date_to?: string | null;
}

export interface SmartAlbumSummary {
  id: string;
  name: string;
  description: string | null;
  owner_id: string;
  enabled: boolean;
  last_synced_at: string | null;
  asset_count: number;
  cover_asset_id: string | null;
  source: string;
  status: string;
  degraded_reason: string | null;
  created_at: string;
  updated_at: string;
  rule: SmartAlbumRule;
}

export interface SmartAlbumDetail extends SmartAlbumSummary {
  items: AssetBrowseItem[];
  suggested: boolean;
}

export interface AdminSettings {
  tag_similarity_threshold_percent: number;
  max_thumbnail_size: number;
  duplicate_phash_threshold: number;
  semantic_similarity_threshold: number;
  semantic_neighbor_limit: number;
  clip_enabled: boolean;
  preview_cache_max_mb: number;
  worker_poll_interval_seconds: number;
}

export interface CompareAsset {
  id: string;
  filename: string;
  preview_url: string | null;
  content_url: string;
  deepzoom_available: boolean;
  deepzoom_url: string | null;
  size_bytes: number;
  created_at: string | null;
  modified_at: string;
  normalized_metadata: Record<string, unknown>;
  tags: string[];
}

export interface CompareDiffEntry {
  field: string;
  left: string | number | null;
  right: string | number | null;
}

export interface CompareResponse {
  asset_a: CompareAsset;
  asset_b: CompareAsset;
  phash_distance: number | null;
  semantic_similarity: number | null;
  prompt_tag_overlap: number;
  shared_prompt_tags: string[];
  left_only_prompt_tags: string[];
  right_only_prompt_tags: string[];
  metadata_diff: CompareDiffEntry[];
}

export interface SearchFilters {
  q?: string;
  media_type?: string;
  caption?: string;
  ocr_text?: string;
  camera_make?: string;
  camera_model?: string;
  year?: string;
  width_min?: string;
  width_max?: string;
  height_min?: string;
  height_max?: string;
  duration_min?: string;
  duration_max?: string;
  has_gps?: boolean;
  tags?: string;
  auto_tags?: string;
  exclude_tags?: string;
  min_rating?: number;
  review_status?: ReviewStatus;
  flagged?: boolean;
  sort?: SortField;
  page?: number;
  page_size?: number;
}

export interface SearchFilterFormState {
  q: string;
  media_type: string;
  caption: string;
  ocr_text: string;
  camera_make: string;
  camera_model: string;
  year: string;
  width_min: string;
  width_max: string;
  height_min: string;
  height_max: string;
  duration_min: string;
  duration_max: string;
  has_gps: boolean;
  tags: string;
  auto_tags: string;
  min_rating: string;
  review_status: string;
  flagged: boolean;
  sort: SortField;
}

export interface ModuleSettingFieldRead {
  key: string;
  label: string;
  type: "boolean" | "string" | "integer" | "number";
  description: string | null;
  default: unknown;
}

export interface PlatformModule {
  module_id: string;
  name: string;
  kind: string;
  version: string;
  description: string | null;
  platform_api_version: string;
  source_ref: string | null;
  enabled: boolean;
  status: string;
  error: string | null;
  permissions: string[];
  dependencies: string[];
  backend_entrypoint: string | null;
  worker_entrypoint: string | null;
  frontend_entrypoint: string | null;
  backend_migrations: string | null;
  api_mount: string | null;
  user_mount: string | null;
  admin_mount: string | null;
  nav_label: string | null;
  nav_href: string | null;
  nav_order: number;
  admin_nav_label: string | null;
  admin_nav_href: string | null;
  admin_nav_order: number;
  user_visible: boolean;
  admin_visible: boolean;
  settings_schema: ModuleSettingFieldRead[];
  settings_json: Record<string, unknown>;
  manifest_path: string | null;
  installed_at: string;
  updated_at: string;
}
