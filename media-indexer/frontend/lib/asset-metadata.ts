"use client";

import { BrowseIndexState } from "@/lib/types";

export function metadataLabel(value: unknown, fallback = "n/a") {
  return typeof value === "string" || typeof value === "number" ? String(value) : fallback;
}

export function numericMetadata(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}

export function stringMetadata(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

export function promptTagsFromMetadata(normalized: Record<string, unknown>, limit = 6): string[] {
  const promptTags = normalized.prompt_tags;
  if (!Array.isArray(promptTags)) {
    return [];
  }
  return promptTags.filter((value): value is string => typeof value === "string" && value.trim().length > 0).slice(0, limit);
}

export function promptTagStringFromMetadata(normalized: Record<string, unknown>): string | null {
  const value = normalized.prompt_tag_string;
  return typeof value === "string" && value.trim() ? value : null;
}

export function metadataVersion(normalized: Record<string, unknown>): number {
  const value = normalized.metadata_version;
  return typeof value === "number" ? value : 0;
}

export function formatBytes(value: number | null) {
  if (value === null) return "n/a";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 * 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  return `${(value / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

export function formatDate(value: string | null) {
  if (!value) return "n/a";
  return new Date(value).toLocaleString();
}

export function browseIndexStateLabel(state: BrowseIndexState | null) {
  switch (state) {
    case "indexed":
      return "Indexed";
    case "metadata_refresh_pending":
      return "Metadata Refresh Pending";
    case "processing":
      return "Processing";
    case "live_browse":
      return "Live Browse";
    default:
      return null;
  }
}
