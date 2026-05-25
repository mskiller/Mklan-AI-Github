"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { bulkAnnotateAssets, mediaUrl } from "@/lib/api";
import { formatBytes, metadataLabel, promptTagsFromMetadata } from "@/lib/asset-metadata";
import { BlurhashPlaceholder } from "@/components/blurhash-placeholder";
import { TagFilterChip } from "@/components/tag-filter-chip";
import { AssetSummary } from "@/lib/types";

export function AssetCard({
  asset,
  selected,
  onSelect,
  selectionMode,
  statusBadge,
  contextBadges = [],
  onAddToCollection,
  onRemoveFromCollection,
  bulkSelected,
  onBulkToggle,
  onDownloadWorkflow,
  onTagged,
}: {
  asset: AssetSummary;
  selected?: boolean;
  onSelect?: (asset: AssetSummary) => void;
  selectionMode?: boolean;
  statusBadge?: string | null;
  contextBadges?: string[];
  onAddToCollection?: (asset: AssetSummary) => void;
  onRemoveFromCollection?: (asset: AssetSummary) => void;
  bulkSelected?: boolean;
  onBulkToggle?: () => void;
  onDownloadWorkflow?: () => void;
  onTagged?: (assetId: string) => void;
}) {
  const router = useRouter();
  const longPressTimer = useRef<number | null>(null);
  const longPressTriggered = useRef(false);
  const preview = mediaUrl(asset.preview_url);
  const [loaded, setLoaded] = useState(false);
  const [menuPos, setMenuPos] = useState<{ x: number; y: number } | null>(null);
  const width = metadataLabel(asset.normalized_metadata.width);
  const height = metadataLabel(asset.normalized_metadata.height);
  const supportsCompareSelect = Boolean(onSelect) && asset.media_type === "image";
  const promptTags = promptTagsFromMetadata(asset.normalized_metadata, 4);
  const compareButtonLabel = selected ? "Selected" : "Select";

  useEffect(() => {
    setLoaded(false);
  }, [preview]);

  const handlePreviewClick = (event: React.MouseEvent<HTMLButtonElement>) => {
    if (longPressTriggered.current) {
      longPressTriggered.current = false;
      event.preventDefault();
      return;
    }
    // If in bulk mode (onBulkToggle provided) or ctrl-clicking in bulk context
    if (onBulkToggle && (event.ctrlKey || event.metaKey || bulkSelected !== undefined)) {
      event.preventDefault();
      onBulkToggle();
      return;
    }
    // Compare selection
    if ((selectionMode || event.ctrlKey || event.metaKey) && supportsCompareSelect) {
      event.preventDefault();
      onSelect?.(asset);
      return;
    }
    router.push(`/assets/${asset.id}`);
  };

  const handleTagAction = async (tag: string) => {
    setMenuPos(null);
    try {
      await bulkAnnotateAssets({ asset_ids: [asset.id], tags: [tag] });
      onTagged?.(asset.id);
    } catch (e) {
      console.error("Tagging failed", e);
    }
  };

  const handleCustomTag = async () => {
    const tag = window.prompt("Enter tag name to add:");
    if (tag && tag.trim()) {
      await handleTagAction(tag.trim().toLowerCase());
    }
  };

  return (
    <article 
      className={`asset-card ${selected ? "asset-card-selected" : ""} ${bulkSelected ? "asset-card-bulk-selected" : ""}`}
      onContextMenu={(e) => {
        e.preventDefault();
        setMenuPos({ x: e.clientX, y: e.clientY });
      }}
    >
      {menuPos && typeof document !== "undefined" && createPortal(
        <div 
          className="gallery-context-menu gallery-context-menu-open"
          style={{
            position: "fixed",
            left: menuPos.x,
            top: menuPos.y,
            zIndex: 10000,
          }}
          onBlur={() => setMenuPos(null)}
          onMouseLeave={() => setMenuPos(null)}
        >
          <button className="button context-action-btn" onClick={() => handleTagAction("nsfw")}>🔞 Tag NSFW</button>
          <button className="button context-action-btn" onClick={handleCustomTag}>🏷️ Add Tag...</button>
          {onDownloadWorkflow && (
            <button 
              className="button context-action-btn" 
              onClick={() => { setMenuPos(null); onDownloadWorkflow(); }}
            >
              ⬇ Download Workflow JSON
            </button>
          )}
          <button className="button context-action-btn" onClick={() => setMenuPos(null)}>Cancel</button>
        </div>,
        document.body
      )}
      {onBulkToggle && (
        <button
          type="button"
          className={`gallery-select-badge gallery-select-badge-visible ${bulkSelected ? "gallery-select-badge-selected" : ""}`}
          style={{ top: "2.2rem" }}
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); onBulkToggle(); }}
        >
          {bulkSelected ? "✓ Bulk" : "+ Bulk"}
        </button>
      )}
      <div className="asset-preview-shell">
        {supportsCompareSelect ? (
          <button
            type="button"
            className={`selection-toggle ${selected ? "selection-toggle-selected" : ""}`}
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              onSelect?.(asset);
            }}
            title={selectionMode ? "Tap to select." : "Tap to select."}
          >
            {compareButtonLabel}
          </button>
        ) : null}
        {statusBadge ? <span className="asset-status-badge">{statusBadge}</span> : null}
        <button
          type="button"
          className="asset-preview"
          onClick={handlePreviewClick}
          onTouchStart={() => {
            if (!supportsCompareSelect || selectionMode) {
              return;
            }
            longPressTriggered.current = false;
            if (longPressTimer.current) {
              window.clearTimeout(longPressTimer.current);
            }
            longPressTimer.current = window.setTimeout(() => {
              longPressTriggered.current = true;
              onSelect?.(asset);
            }, 450);
          }}
          onTouchEnd={() => {
            if (longPressTimer.current) {
              window.clearTimeout(longPressTimer.current);
              longPressTimer.current = null;
            }
          }}
          onTouchCancel={() => {
            if (longPressTimer.current) {
              window.clearTimeout(longPressTimer.current);
              longPressTimer.current = null;
            }
          }}
          title={
            selectionMode && supportsCompareSelect
              ? "Tap to select."
              : supportsCompareSelect
                ? "Click to open. Ctrl/Cmd-click or long-press to select."
                : "Click to open."
          }
        >
          {preview ? (
            <>
              {!loaded && asset.blur_hash ? <BlurhashPlaceholder hash={asset.blur_hash} className="asset-card-blurhash" /> : null}
              <img src={preview} alt={asset.filename} style={{ opacity: loaded ? 1 : 0 }} onLoad={() => setLoaded(true)} />
            </>
          ) : <div className="asset-placeholder">{asset.media_type}</div>}
        </button>
      </div>
      <div className="asset-body">
        <div className="asset-card-topline">
          <div>
            <p className="asset-name">{asset.filename}</p>
            <p className="subdued">{asset.relative_path}</p>
          </div>
          <span className="pill">{asset.media_type}</span>
        </div>
        <div className="asset-meta">
          <span>{width} x {height}</span>
          <span>{formatBytes(asset.size_bytes)}</span>
        </div>
        <div className="chip-row">
          {contextBadges.map((badge) => (
            <span key={badge} className="chip chip-accent">
              {badge}
            </span>
          ))}
          {promptTags.map((tag) => (
            <TagFilterChip key={tag} tag={tag} prompt className="chip chip-prompt buttonless" />
          ))}
          {!promptTags.length ? asset.tags.slice(0, 3).map((tag) => (
            <TagFilterChip key={tag} tag={tag} className="chip buttonless" />
          )) : null}
          {supportsCompareSelect && !selectionMode ? <span className="chip">Ctrl/Cmd-click to compare</span> : null}
        </div>
        <div className="card-actions">
          <Link href={`/assets/${asset.id}`} className="button small-button">
            Open Detail
          </Link>
          {onAddToCollection ? (
            <button type="button" className="button ghost-button" onClick={() => onAddToCollection(asset)}>
              Add to Collection
            </button>
          ) : null}
          {onRemoveFromCollection ? (
            <button type="button" className="button ghost-button small-button" style={{ color: "var(--error, #e05)" }} onClick={() => onRemoveFromCollection(asset)}>
              Remove
            </button>
          ) : null}
          <Link href={`/assets/${asset.id}/similar`} className="button subtle-button">
            Similar
          </Link>
        </div>
      </div>
    </article>
  );
}
