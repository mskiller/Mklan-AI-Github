export type ScanSummary = {
  source_root: string;
  scan_mode: "incremental" | "reset";
  files_seen: number;
  files_indexed: number;
  files_skipped: number;
  files_changed: number;
  entries_indexed: number;
  txt_files: number;
  yaml_files: number;
  total_mb: number;
  warnings: string[];
};

export type ScanStatus = {
  running: boolean;
  started_at: string | null;
  finished_at: string | null;
  summary: ScanSummary | null;
  error: string | null;
};

export type Health = {
  ok: boolean;
  db_path: string;
  source_root_exists: boolean;
  files: number;
  entries: number;
  last_scan: { summary_json: string; created_at: string } | null;
};

export type WildcardListItem = {
  id: number;
  wildcard_path: string;
  relative_path: string;
  extension: string;
  size_bytes: number;
  entry_count: number;
  prompt_count: number;
  duplicate_count: number;
  unresolved_refs: number;
  categories: string[];
  prompt_modes: Record<string, number>;
  updated_at: string;
};

export type EntryItem = {
  id: number;
  source_file_id: number;
  wildcard_path: string;
  item_index: number;
  raw_text: string;
  staged_text: string | null;
  effective_text: string;
  normalized_text: string;
  kind: string;
  prompt_mode: string;
  tags: string[];
  positive_tags: string[];
  negative_tags: string[];
  all_extracted_tags: string[];
  prompt_parts: Record<string, unknown>;
  tag_categories: string[];
  refs: string[];
  warnings: string[];
  is_dirty: boolean;
};

export type WildcardDetail = {
  file: Record<string, unknown>;
  entries: EntryItem[];
  refs: string[];
  unresolved_refs: string[];
  warnings: string[];
};

export type TagItem = {
  tag: string;
  usage_count: number;
};

export type DuplicateGroup = {
  type: "exact_file" | "normalized_entry" | "path_collision" | string;
  key: string;
  count: number;
  items: string[];
};

export type PromptComposeResponse = {
  positive: string;
  negative: string;
  wildcard_prompt: string;
  model_profile: string;
  preset: string;
  prompt_mode: string;
  slot_order: string[];
  unresolved_refs: string[];
};

export type LlmSuggestResponse = {
  ok: boolean;
  endpoint_used: string;
  suggestion: string;
  raw: unknown | null;
  error: string | null;
};

export type LlmJobItem = {
  id: number;
  task: string;
  prompt_mode: string;
  endpoint: string;
  model: string;
  input_text: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  suggestion: string;
  error: string | null;
  endpoint_used: string | null;
  created_at: string;
  updated_at: string;
  accepted_at: string | null;
  rejected_at: string | null;
  cancelled_at: string | null;
};

export type TaxonomyResponse = {
  rules: Record<string, string[]>;
  disabled: Record<string, string[]>;
  version: string | null;
  updated_at: string | null;
  fallback_categories: string[];
};

export type ExportPlan = {
  target_root: string;
  format: string;
  created: string[];
  changed: string[];
  skipped: string[];
  conflicts: string[];
  manifest_path: string | null;
  unresolved_refs: string[];
};
