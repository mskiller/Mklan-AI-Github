"use client";

import { useEffect, useMemo, useState } from "react";
import { fetchTagSuggestions, submitTagSuggestionAction } from "@/lib/api";
import { useToast } from "@/components/use-toast";
import { TagSuggestion } from "@/lib/types";

const GROUP_LABELS: Record<string, string> = {
  rating: "Rating",
  general: "General",
  meta: "Meta",
  character: "Character",
  copyright: "Copyright",
  curated: "Curated",
};

const GROUP_ORDER = ["rating", "general", "meta", "character", "copyright", "curated"];

export function TagSuggestionReview({ assetId, onChanged }: { assetId: string; onChanged?: () => void | Promise<void> }) {
  const [suggestions, setSuggestions] = useState<TagSuggestion[]>([]);
  const { push } = useToast();

  useEffect(() => {
    void loadSuggestions();
  }, [assetId]);

  const loadSuggestions = async () => {
    try {
      const res = await fetchTagSuggestions(assetId);
      setSuggestions(res);
    } catch (e) {
      console.error(e);
    }
  };

  const handleAction = async (id: number, action: "accept" | "reject") => {
    try {
      await submitTagSuggestionAction(id, action);
      setSuggestions((prev) => prev.filter((s) => s.id !== id));
      await onChanged?.();
      push(action === "accept" ? "Tag added!" : "Suggestion dismissed", "success");
    } catch (e) {
      push("Failed to process suggestion", "error");
    }
  };

  const groupedSuggestions = useMemo(() => {
    const groups = new Map<string, TagSuggestion[]>();
    suggestions.forEach((suggestion) => {
      const key = suggestion.tag_group ?? "general";
      const current = groups.get(key) ?? [];
      current.push(suggestion);
      groups.set(key, current);
    });
    const orderedGroups = [
      ...GROUP_ORDER.filter((group) => groups.has(group)),
      ...Array.from(groups.keys()).filter((group) => !GROUP_ORDER.includes(group)),
    ];
    return orderedGroups.map((group) => ({
      group,
      items: groups.get(group) ?? [],
    }));
  }, [suggestions]);

  if (suggestions.length === 0) return null;

  return (
    <div className="tag-suggestion-section" style={{ marginTop: "1rem", padding: "1rem", background: "rgba(var(--accent-rgb), 0.05)", borderRadius: "var(--radius-md)", border: "1px dashed var(--accent)" }}>
      <p className="eyebrow" style={{ color: "var(--accent)" }}>✨ AI Tag Suggestions</p>
      <div className="stack" style={{ marginTop: "0.75rem", gap: "0.85rem" }}>
        {groupedSuggestions.map(({ group, items }) => (
          <div key={group} className="stack" style={{ gap: "0.45rem" }}>
            <div className="row-between">
              <strong>{GROUP_LABELS[group] ?? group}</strong>
              <span className="subdued small">{items.length} suggestions</span>
            </div>
            <div className="tag-cloud">
              {items.map((s) => (
                <div key={s.id} className="tag-suggestion-chip" style={{ display: "flex", alignItems: "center", gap: "0.5rem", background: "var(--bg-paper)", padding: "0.35rem 0.6rem", borderRadius: "var(--radius-sm)", border: "1px solid var(--divider)" }}>
                  <span style={{ fontWeight: 600 }}>{s.tag}</span>
                  <span className="subdued small">{(s.confidence * 100).toFixed(0)}%</span>
                  {s.source_model ? <span className="chip buttonless">{s.source_model}</span> : null}
                  <div style={{ display: "flex", gap: "0.25rem" }}>
                    <button
                      className="button accent-button small-button"
                      style={{ padding: "0 0.25rem", minWidth: "1.5rem" }}
                      onClick={() => handleAction(s.id, "accept")}
                      title="Accept"
                    >
                      ✓
                    </button>
                    <button
                      className="button subtle-button small-button"
                      style={{ padding: "0 0.25rem", minWidth: "1.5rem" }}
                      onClick={() => handleAction(s.id, "reject")}
                      title="Dismiss"
                    >
                      ✕
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
