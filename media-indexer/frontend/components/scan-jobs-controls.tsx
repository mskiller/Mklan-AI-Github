"use client";

import { useState } from "react";

/**
 * Provides a "Clear Done Jobs" button for the Scan Jobs page.
 *
 * Usage in your scan-jobs page:
 *
 *   import { ScanJobsControls } from "@/components/scan-jobs-controls";
 *
 *   <ScanJobsControls onCleared={refetch} />
 *
 * The component calls DELETE /api/scan-jobs/done (adjust the endpoint to match
 * your actual backend route for bulk-deleting completed jobs).
 */
export function ScanJobsControls({ onCleared }: { onCleared?: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const handleClearDone = async () => {
    if (!window.confirm("Remove all completed and failed jobs from the list?")) return;
    setBusy(true);
    setError(null);
    setSuccess(false);
    try {
      const res = await fetch("/api/scan-jobs/done", { method: "DELETE" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`);
      }
      setSuccess(true);
      setTimeout(() => setSuccess(false), 2500);
      onCleared?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to clear jobs.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
      <button
        type="button"
        className="button ghost-button small-button"
        onClick={handleClearDone}
        disabled={busy}
      >
        {busy ? "Clearing…" : "🗑 Clear Done Jobs"}
      </button>
      {success && <span className="subdued" style={{ fontSize: "0.85rem" }}>✓ Cleared</span>}
      {error && <span style={{ fontSize: "0.85rem", color: "var(--error, #e05)" }}>{error}</span>}
    </div>
  );
}
