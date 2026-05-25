import { SearchFilterFormState } from "@/lib/types";

type SearchParamReader = Pick<URLSearchParams, "get">;

export const DEFAULT_SEARCH_FILTERS: SearchFilterFormState = {
  q: "",
  media_type: "",
  caption: "",
  ocr_text: "",
  camera_make: "",
  camera_model: "",
  year: "",
  width_min: "",
  width_max: "",
  height_min: "",
  height_max: "",
  duration_min: "",
  duration_max: "",
  has_gps: false,
  tags: "",
  auto_tags: "",
  min_rating: "",
  review_status: "",
  flagged: false,
  // v1.6: use modified_at as default so the page shows ALL images on open with no query.
  // "relevance" with an empty query returns 0 results on the backend.
  sort: "modified_at",
};

const FILTER_KEYS = Object.keys(DEFAULT_SEARCH_FILTERS) as Array<keyof SearchFilterFormState>;

export function parseTagList(rawValue: string): string[] {
  const seen = new Set<string>();
  return rawValue
    .split(",")
    .map((value) => value.trim())
    .filter((value) => {
      const normalized = value.toLowerCase();
      if (!normalized || seen.has(normalized)) {
        return false;
      }
      seen.add(normalized);
      return true;
    });
}

export function appendTagFilter(rawValue: string, tag: string): string {
  return parseTagList([...parseTagList(rawValue), tag].join(",")).join(",");
}

export function removeTagFilter(rawValue: string, tag: string): string {
  return parseTagList(rawValue)
    .filter((value) => value.toLowerCase() !== tag.toLowerCase())
    .join(",");
}

export function parseSearchFilterState(searchParams: SearchParamReader): SearchFilterFormState {
  const next = { ...DEFAULT_SEARCH_FILTERS };
  FILTER_KEYS.forEach((key) => {
    const value = searchParams.get(key);
    if (value !== null) {
      if (key === "sort") {
        if (
          value === "relevance" ||
          value === "created_at" ||
          value === "modified_at" ||
          value === "filename" ||
          value === "rating" ||
          value === "review_status"
        ) {
          next.sort = value;
        }
        return;
      }
      if (key === "flagged") {
        next.flagged = value === "true";
        return;
      }
      if (key === "has_gps") {
        next.has_gps = value === "true";
        return;
      }
      next[key] = value;
    }
  });
  next.tags = parseTagList(next.tags).join(",");
  next.auto_tags = parseTagList(next.auto_tags).join(",");
  return next;
}

export function buildSearchQuery(filters: SearchFilterFormState): string {
  const params = new URLSearchParams();
  FILTER_KEYS.forEach((key) => {
    const value = filters[key];
    if (key === "flagged" || key === "has_gps") {
      if (filters[key]) {
        params.set(key, "true");
      }
      return;
    }
    if (value) {
      params.set(key, key === "tags" || key === "auto_tags" ? parseTagList(String(value)).join(",") : String(value));
    }
  });
  return params.toString();
}
