"use client";

import { useState } from "react";
import { bulkAnnotateAssets } from "@/lib/api";
import { ReviewStatus } from "@/lib/types";

export function BulkActionBar({
  selectedIds,
  onClear,
  onDone,
}: {
  selectedIds: string[];
  onClear: () => void;
  onDone: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const act = async (payload: {
    rating?: number | null;
    review_status?: ReviewStatus;
    flagged?: boolean;
    tags?: string[];
  }) => {
    if (!selectedIds.length) return;
    setBusy(true);
    setError(null);
    try {
      await bulkAnnotateAssets({ asset_ids: selectedIds, ...payload });
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Bulk action failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="bulk-action-bar">
      <span className="subdued">{selectedIds.length} selected</span>
      {error && <span className="error-inline">{error}</span>}
      <div className="chip-row">
        <button className="button small-button" disabled={busy} onClick={() => act({ review_status: "approved" })}>✅ Approve</button>
        <button className="button small-button" disabled={busy} onClick={() => act({ review_status: "rejected" })}>❌ Reject</button>
        <button className="button small-button" disabled={busy} onClick={() => act({ review_status: "favorite" })}>⭐ Favorite</button>
        <button className="button ghost-button small-button" disabled={busy} onClick={() => act({ review_status: "unreviewed" })}>○ Unreviewed</button>
        <button className="button ghost-button small-button" disabled={busy} onClick={() => act({ flagged: true })}>🚩 Flag</button>
        <button className="button ghost-button small-button" disabled={busy} onClick={() => act({ rating: 5 })}>★★★★★</button>
        <button className="button ghost-button small-button" disabled={busy} onClick={() => act({ rating: 4 })}>★★★★</button>
        <button className="button ghost-button small-button" disabled={busy} onClick={() => act({ rating: 3 })}>★★★</button>
        <button className="button ghost-button small-button" disabled={busy} onClick={() => act({ rating: null })}>Clear Rating</button>
        <div className="vertical-divider" />
        <button className="button small-button" style={{ backgroundColor: "#8b0000" }} disabled={busy} onClick={() => act({ tags: ["nsfw"] })}>🔞 NSFW</button>
        <button 
          className="button ghost-button small-button" 
          disabled={busy} 
          onClick={() => {
            const tag = window.prompt("Enter tag name to add:");
            if (tag && tag.trim()) {
              void act({ tags: [tag.trim()] });
            }
          }}
        >
          🏷️ Add Tag...
        </button>
      </div>
      <button className="button subtle-button small-button" disabled={busy} onClick={onClear}>Clear Selection</button>
    </div>
  );
}
