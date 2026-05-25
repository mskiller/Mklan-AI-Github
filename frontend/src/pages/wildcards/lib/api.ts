import type {
  DuplicateGroup,
  EntryItem,
  ExportPlan,
  Health,
  LlmJobItem,
  LlmSuggestResponse,
  PromptComposeResponse,
  ScanStatus,
  ScanSummary,
  TaxonomyResponse,
  TagItem,
  WildcardDetail,
  WildcardListItem
} from "../types/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/wildcards/api${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `${response.status} ${response.statusText}`);
  }

  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/health"),
  scan: (mode: "incremental" | "reset" = "reset") =>
    request<{ running: boolean; message: string } | ScanSummary>("/import/scan", { method: "POST", body: JSON.stringify({ mode, reset: mode === "reset", background: true }) }),
  scanStatus: () => request<ScanStatus>("/import/status"),
  wildcards: (params: { search?: string; tag?: string; tag_polarity?: string; kind?: string; category?: string; prompt_mode?: string; limit?: number }) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== "") query.set(key, String(value));
    });
    return request<WildcardListItem[]>(`/wildcards?${query}`);
  },
  wildcard: (id: number) => request<WildcardDetail>(`/wildcards/${id}`),
  patchEntry: (id: number, staged_text: string) =>
    request<EntryItem>(`/entries/${id}`, { method: "PATCH", body: JSON.stringify({ staged_text }) }),
  tags: (search = "", category = "", tag_polarity = "all") => request<{ tags: TagItem[] }>(`/tags?${new URLSearchParams({ search, category, tag_polarity })}`),
  categories: () => request<{ categories: Array<{ category: string; usage_count: number }> }>("/categories"),
  promptModes: () => request<{ modes: Array<{ prompt_mode: string; entry_count: number; file_count: number; wildcard_count: number }> }>("/prompt-modes"),
  duplicates: () => request<{ groups: DuplicateGroup[] }>("/duplicates"),
  composePrompt: (body: {
    positive_tags: string[];
    negative_tags: string[];
    wildcard_refs: string[];
    model_profile: string;
    quality_preset: string;
    preset: string;
    prompt_mode: "danbooru_tags" | "sdxl_natural";
    slots: Record<string, string[]>;
    sdxl?: Record<string, string>;
  }) => request<PromptComposeResponse>("/prompts/compose", { method: "POST", body: JSON.stringify(body) }),
  cleanupPreview: (text: string) =>
    request<{ normalized_lines: string[]; duplicate_lines: string[]; case_conflicts: string[][]; prose_candidates: string[] }>("/cleanup/preview", {
      method: "POST",
      body: JSON.stringify({ text })
    }),
  promptRecipes: () => request<{ recipes: Array<Record<string, unknown>> }>("/prompt-recipes"),
  savePromptRecipe: (body: { name: string; preset: string; slots: Record<string, string[]>; negative_tags: string[]; wildcard_refs: string[] }) =>
    request<{ id: number; updated_at: string }>("/prompt-recipes", { method: "POST", body: JSON.stringify(body) }),
  tagOverrides: () => request<{ overrides: Array<Record<string, unknown>> }>("/tag-overrides"),
  saveTagOverride: (body: { tag: string; canonical_tag?: string; category?: string; is_ignored: boolean }) =>
    request<{ tag: string; updated_at: string }>("/tag-overrides", { method: "POST", body: JSON.stringify(body) }),
  llmSuggest: (body: { task: string; text: string; endpoint: string; model: string; prompt_mode: "danbooru_tags" | "sdxl_natural" }) =>
    request<LlmSuggestResponse>("/llm/suggest", { method: "POST", body: JSON.stringify(body) }),
  llmTest: (body: { task: string; text: string; endpoint: string; model: string; prompt_mode: "danbooru_tags" | "sdxl_natural" }) =>
    request<LlmSuggestResponse>("/llm/test", { method: "POST", body: JSON.stringify(body) }),
  createLlmJob: (body: { task: string; text: string; endpoint: string; model: string; prompt_mode: "danbooru_tags" | "sdxl_natural" }) =>
    request<LlmJobItem>("/llm/jobs", { method: "POST", body: JSON.stringify(body) }),
  llmJobs: () => request<LlmJobItem[]>("/llm/jobs"),
  cancelLlmJob: (id: number) => request<LlmJobItem>(`/llm/jobs/${id}/cancel`, { method: "POST" }),
  taxonomy: () => request<TaxonomyResponse>("/taxonomy"),
  updateTaxonomy: (body: { category?: string; keywords?: string[]; rules?: Record<string, string[]> }) =>
    request<{ updated_at: string; keyword_count: number }>("/taxonomy", { method: "PATCH", body: JSON.stringify(body) }),
  reindexTaxonomy: () => request<{ running: boolean; message: string } | ScanSummary>("/taxonomy/reindex", { method: "POST" }),
  exportDryRun: (body: { format: string; target_root?: string; overwrite: boolean; prompt_mode: string }) =>
    request<ExportPlan>("/export/dry-run", { method: "POST", body: JSON.stringify(body) }),
  exportRun: (body: { format: string; target_root?: string; overwrite: boolean; prompt_mode: string }) =>
    request<ExportPlan>("/export/run", { method: "POST", body: JSON.stringify(body) })
};
