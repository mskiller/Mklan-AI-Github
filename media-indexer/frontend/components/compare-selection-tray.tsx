"use client";

import Link from "next/link";

export interface TrayItem {
  id: string;
  name: string;
  previewUrl?: string | null;
}

export function CompareSelectionTray({
  selectionMode,
  selectedItems,
  selectedCount: selectedCountProp,
  compareHref,
  onToggleSelectionMode,
  onClearSelection,
  onRemoveItem,
  hint,
  canAddToCollection = false,
  onAddToCollection,
}: {
  selectionMode: boolean;
  /** New API: full item list with optional thumbnails */
  selectedItems?: TrayItem[];
  /** Legacy API: pass a bare count when you don't have item objects */
  selectedCount?: number;
  compareHref: string | null;
  onToggleSelectionMode: () => void;
  onClearSelection: () => void;
  onRemoveItem?: (id: string) => void;
  hint: string;
  canAddToCollection?: boolean;
  onAddToCollection?: () => void;
}) {
  // Support both old (selectedCount) and new (selectedItems) callers
  const items = selectedItems ?? [];
  const selectedCount = selectedCountProp ?? items.length;

  return (
    <section className="compare-tray panel">
      <div>
        <p className="eyebrow">Compare Tray</p>
        <h2>{selectedCount} selected</h2>
        <p className="subdued">{hint}</p>
      </div>

      {/* Staged thumbnails — only shown when caller passes selectedItems */}
      {items.length > 0 ? (
        <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap" }}>
          {items.map((item) => (
            <div
              key={item.id}
              style={{
                position: "relative",
                width: 64,
                height: 64,
                borderRadius: 10,
                overflow: "hidden",
                border: "1px solid var(--border)",
                background: "var(--bg-alt)",
                flexShrink: 0,
              }}
            >
              {item.previewUrl ? (
                <img
                  src={item.previewUrl}
                  alt={item.name}
                  style={{ width: "100%", height: "100%", objectFit: "cover" }}
                />
              ) : (
                <div
                  style={{
                    width: "100%",
                    height: "100%",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: "0.65rem",
                    color: "var(--muted)",
                    padding: "0.2rem",
                    textAlign: "center",
                    wordBreak: "break-all",
                  }}
                >
                  {item.name}
                </div>
              )}
              {onRemoveItem ? (
                <button
                  type="button"
                  aria-label={`Remove ${item.name}`}
                  onClick={() => onRemoveItem(item.id)}
                  style={{
                    position: "absolute",
                    top: 2,
                    right: 2,
                    width: 18,
                    height: 18,
                    borderRadius: "50%",
                    background: "rgba(7,16,20,0.82)",
                    border: "1px solid rgba(255,255,255,0.12)",
                    color: "var(--text)",
                    fontSize: "0.65rem",
                    lineHeight: 1,
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  ✕
                </button>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}

      <div className="card-actions">
        <button className={`button small-button ${selectionMode ? "" : "ghost-button"}`} type="button" onClick={onToggleSelectionMode}>
          {selectionMode ? "Exit Selection Mode" : "Select for Compare"}
        </button>
        <button className="button ghost-button small-button" type="button" onClick={onClearSelection} disabled={!selectedCount}>
          Clear Selection
        </button>
        {canAddToCollection && onAddToCollection ? (
          <button className="button subtle-button small-button" type="button" onClick={onAddToCollection} disabled={!selectedCount}>
            Add Selected to Collection
          </button>
        ) : null}
        {compareHref ? (
          <Link href={compareHref} className="button small-button">
            {selectedCount === 2 ? "Compare Now →" : "Compare Selected"}
          </Link>
        ) : null}
      </div>
    </section>
  );
}
