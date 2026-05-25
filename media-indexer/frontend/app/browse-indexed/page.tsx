"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { BulkActionBar } from "@/components/bulk-action-bar";
import { CompareSelectionTray } from "@/components/compare-selection-tray";
import { CollectionPickerModal } from "@/components/collection-picker-modal";
import { GalleryTile } from "@/components/gallery-tile";
import { ImageExplorerOverlay } from "@/components/image-explorer-overlay";
import { JustifiedGallery } from "@/components/justified-gallery";
import { useAuth } from "@/components/auth-provider";
import { useModuleRegistry } from "@/components/module-registry-provider";
import { useSettings } from "@/components/settings-provider";
import { useDeviceMode } from "@/hooks/use-device-mode";
import {
  addAssetsToCollection,
  bulkAnnotateAssets,
  downloadWorkflow,
  fetchAssetBrowse,
  fetchCollections,
  fetchScanJobs,
  fetchSources,
  fetchTags,
  mediaUrl,
  runAssetVisionLlm,
  triggerScan,
} from "@/lib/api";
import { formatBytes, formatDate } from "@/lib/asset-metadata";
import { sourceFolderBrowseHref } from "@/lib/browse-links";
import { copyTextToClipboard } from "@/lib/clipboard";
import { AssetBrowseItem, CollectionSummary, Source, TagCount } from "@/lib/types";

type BrowseSortMode = "modified_at" | "created_at" | "filename";
type BrowseDisplayMode = "gallery" | "explorer";
type FilterScope = "only_indexed" | "has_workflow" | "has_prompt" | null;

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";

export default function BrowseIndexedPage() {
  const router = useRouter();
  const { user } = useAuth();
  const { isModuleEnabled } = useModuleRegistry();
  const { nsfwVisible } = useSettings();
  const deviceMode = useDeviceMode();
  const [sources, setSources] = useState<Source[]>([]);
  const [collections, setCollections] = useState<CollectionSummary[]>([]);
  const [items, setItems] = useState<AssetBrowseItem[]>([]);
  const [total, setTotal] = useState(0);
  const [sourceId, setSourceId] = useState("");
  const [sortMode, setSortMode] = useState<BrowseSortMode>("modified_at");
  const [displayMode, setDisplayMode] = useState<BrowseDisplayMode>("gallery");
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [actionBusyId, setActionBusyId] = useState<string | null>(null);
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedAssets, setSelectedAssets] = useState<Array<{ id: string; name: string; previewUrl?: string | null }>>([]);
  const [bulkMode, setBulkMode] = useState(false);
  const [bulkSelectedIds, setBulkSelectedIds] = useState<string[]>([]);
  const [explorerIndex, setExplorerIndex] = useState<number | null>(null);
  const [collectionModalOpen, setCollectionModalOpen] = useState(false);
  const [collectionBusy, setCollectionBusy] = useState(false);
  const [pendingCollectionAssetIds, setPendingCollectionAssetIds] = useState<string[]>([]);
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  // M2 — SSE scan progress
  const [scanProgress, setScanProgress] = useState<{ processed: number; total: number } | null>(null);
  const [activeScanJobId, setActiveScanJobId] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  // M5.5 — Tag frequency panel
  const [topTags, setTopTags] = useState<TagCount[]>([]);
  const [tagsOpen, setTagsOpen] = useState(true);
  const [tagFilter, setTagFilter] = useState<string | null>(null);

  // M5.7 — Filter scopes
  const [filterScope, setFilterScope] = useState<FilterScope>(null);
  const collectionsEnabled = isModuleEnabled("collections");

  useEffect(() => {
    const loadStatic = async () => {
      try {
        const [nextSources, nextCollections, nextTags] = await Promise.all([
          fetchSources(),
          user?.capabilities.can_manage_collections && collectionsEnabled ? fetchCollections() : Promise.resolve([]),
          fetchTags(),
        ]);
        setSources(nextSources);
        setCollections(nextCollections);
        setTopTags(nextTags.slice(0, 20));
      } catch {
        setSources([]);
        setCollections([]);
      }
    };
    void loadStatic();
  }, [user?.capabilities.can_manage_collections, collectionsEnabled]);

  // M2 — Detect active scan jobs on mount / sourceId change
  useEffect(() => {
    const detectScan = async () => {
      try {
        const jobs = await fetchScanJobs();
        const active = jobs.find(
          (j) =>
            (j.status === "queued" || j.status === "running") &&
            (sourceId ? j.source_id === sourceId : true)
        );
        setActiveScanJobId(active?.id ?? null);
      } catch {
        setActiveScanJobId(null);
      }
    };
    void detectScan();
  }, [sourceId]);

  // M2 — Open SSE stream when activeScanJobId is set
  useEffect(() => {
    if (!activeScanJobId) {
      setScanProgress(null);
      return;
    }
    // Close any existing stream
    eventSourceRef.current?.close();
    const es = new EventSource(`${API_BASE_URL}/scan-jobs/${activeScanJobId}/stream`, { withCredentials: true });
    eventSourceRef.current = es;

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as { status: string; processed: number; total: number };
        setScanProgress({ processed: data.processed, total: data.total });
        if (data.status === "completed" || data.status === "failed" || data.status === "cancelled") {
          es.close();
          setActiveScanJobId(null);
          setScanProgress(null);
          // Reload gallery
          setPage(1);
        }
      } catch {
        // ignore parse errors
      }
    };
    es.onerror = () => {
      es.close();
      setActiveScanJobId(null);
      setScanProgress(null);
    };

    return () => es.close();
  }, [activeScanJobId]);

  const load = async () => {
    setLoading(true);
    setError(null);
    setPage(1);
    setSelectedAssets([]);
    try {
      const response = await fetchAssetBrowse({
        source_id: sourceId || undefined,
        sort: sortMode,
        page: 1,
        page_size: 36,
        exclude_tags: !nsfwVisible ? "nsfw" : undefined,
      });
      setItems(response.items);
      setTotal(response.total);
      setHasMore(response.page * response.page_size < response.total);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Unable to load indexed browse.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [sourceId, sortMode, nsfwVisible]);

  useEffect(() => {
    if (page === 1) {
      return;
    }
    const loadMore = async () => {
      setLoadingMore(true);
      try {
        const response = await fetchAssetBrowse({
          source_id: sourceId || undefined,
          sort: sortMode,
          page,
          page_size: 36,
          exclude_tags: !nsfwVisible ? "nsfw" : undefined,
        });
        setItems((current) => [...current, ...response.items]);
        setTotal(response.total);
        setHasMore(response.page * response.page_size < response.total);
      } catch (nextError) {
        setError(nextError instanceof Error ? nextError.message : "Unable to load more indexed images.");
      } finally {
        setLoadingMore(false);
      }
    };
    void loadMore();
  }, [page, sourceId, sortMode]);

  useEffect(() => {
    const target = sentinelRef.current;
    if (!target || !hasMore || loading || loadingMore) {
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          setPage((current) => current + 1);
        }
      },
      { rootMargin: "900px 0px" }
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [hasMore, loading, loadingMore, items.length]);

  // M5.5 — Apply tag filter + scope filter client-side
  const displayItems = useMemo(() => {
    let filtered = items;
    if (tagFilter) {
      filtered = filtered.filter((item) => item.prompt_tags.includes(tagFilter));
    }
    if (filterScope === "has_workflow") {
      filtered = filtered.filter((item) => item.workflow_export_available);
    } else if (filterScope === "has_prompt") {
      filtered = filtered.filter((item) => Boolean(item.prompt_excerpt));
    }
    return filtered;
  }, [items, tagFilter, filterScope]);

  const toggleSelection = (assetId: string, name: string, previewUrl?: string | null) => {
    setSelectedAssets((current) => {
      const exists = current.some((item) => item.id === assetId);
      if (exists) {
        return current.filter((item) => item.id !== assetId);
      }
      const next = { id: assetId, name, previewUrl };
      if (current.length === 2) {
        return [current[1], next];
      }
      return [...current, next];
    });
  };

  const removeSelection = (id: string) => {
    setSelectedAssets((current) => current.filter((item) => item.id !== id));
  };

  const compareHref = selectedAssets.length === 2 ? `/compare?a=${selectedAssets[0].id}&b=${selectedAssets[1].id}` : null;

  const annotateWithTag = async (assetId: string, tag: string) => {
    setActionBusyId(assetId);
    setError(null);
    setMessage(null);
    try {
      await bulkAnnotateAssets({ asset_ids: [assetId], tags: [tag] });
      setMessage(`Tag "${tag}" added.`);
      await load();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Unable to update tags.");
    } finally {
      setActionBusyId(null);
    }
  };

  const queueAssetScan = async (item: AssetBrowseItem, scanMode: "metadata" | "ai") => {
    setActionBusyId(item.id);
    setError(null);
    setMessage(null);
    try {
      const job = await triggerScan(item.source_id, { scan_mode: scanMode, path_filter: item.relative_path });
      setActiveScanJobId(job.id);
      setMessage(`${scanMode === "metadata" ? "Metadata" : "AI"} scan queued for ${item.filename}.`);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Unable to queue scan.");
    } finally {
      setActionBusyId(null);
    }
  };

  const runVisionLlmForItem = async (item: AssetBrowseItem) => {
    setActionBusyId(item.id);
    setError(null);
    setMessage(null);
    try {
      await runAssetVisionLlm(item.id);
      setMessage(`Vision LLM analysis saved for ${item.filename}.`);
      await load();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Vision LLM analysis failed.");
    } finally {
      setActionBusyId(null);
    }
  };

  const explorerItems = useMemo(
    () =>
      displayItems.map((item) => ({
        key: item.id,
        title: item.filename,
        subtitle: [item.source_name, item.generator].filter(Boolean).join(" · ") || undefined,
        promptExcerpt: item.prompt_excerpt,
        promptTags: item.prompt_tags,
        previewSrc: mediaUrl(item.preview_url) ?? null,
        contentSrc: mediaUrl(item.content_url) ?? null,
        deepzoomUrl: mediaUrl(item.deepzoom_url) ?? null,
        detailHref: `/assets/${item.id}`,
        similarHref: `/assets/${item.id}/similar`,
        sourceContext: item.relative_path,
        workflowAvailable: item.workflow_export_available,
        metadataSummary: [
          ...(item.width && item.height ? [{ label: "Dimensions", value: `${item.width} x ${item.height}` }] : []),
          { label: "Modified", value: formatDate(item.modified_at) },
          { label: "Size", value: formatBytes(item.size_bytes) },
        ],
      })),
    [displayItems]
  );

  // Auto-select first item when entering Explorer mode
  const prevDisplayModeRef = useRef<BrowseDisplayMode>(displayMode);
  useEffect(() => {
    const prev = prevDisplayModeRef.current;
    prevDisplayModeRef.current = displayMode;
    if (displayMode === "explorer" && displayItems.length && explorerIndex === null) {
      setExplorerIndex(0);
    }
    // Only clear the overlay when the user explicitly switches FROM explorer BACK TO gallery,
    // not on every explorerIndex change (which caused clicks to open+close in the same cycle).
    if (prev === "explorer" && displayMode === "gallery") {
      setExplorerIndex(null);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [displayMode, displayItems.length]); // intentionally excludes explorerIndex

  useEffect(() => {
    if (explorerIndex === null) {
      return;
    }
    if (!explorerItems.length) {
      setExplorerIndex(null);
      return;
    }
    if (explorerIndex >= explorerItems.length) {
      setExplorerIndex(explorerItems.length - 1);
    }
  }, [explorerIndex, explorerItems.length]);

  return (
    <AppShell
      title="Browse Indexed"
      description="Gallery-first exploration of already indexed images. Search stays separate for dense filters and metadata work."
      actions={
        <div className="page-actions">
          <Link href="/sources" className="button subtle-button small-button">
            Open Sources
          </Link>
          <Link href="/search" className="button ghost-button small-button">
            Open Search
          </Link>
        </div>
      }
    >
      <CollectionPickerModal
        open={collectionModalOpen}
        collections={collections}
        busy={collectionBusy}
        onClose={() => setCollectionModalOpen(false)}
        onConfirm={async (collectionId) => {
          setCollectionBusy(true);
          setError(null);
          try {
            await addAssetsToCollection(collectionId, pendingCollectionAssetIds);
            setCollectionModalOpen(false);
          } catch (nextError) {
            setError(nextError instanceof Error ? nextError.message : "Unable to add assets to collection.");
          } finally {
            setCollectionBusy(false);
          }
        }}
      />
      <ImageExplorerOverlay
        open={explorerIndex !== null}
        items={explorerItems}
        activeIndex={explorerIndex ?? 0}
        onClose={() => {
          setExplorerIndex(null);
          if (displayMode === "explorer") {
            setDisplayMode("gallery");
          }
        }}
        onActiveIndexChange={(next) => setExplorerIndex(next)}
        renderActions={(item) => {
          const sourceItem = displayItems.find((entry) => entry.id === item.key);
          if (!sourceItem) {
            return null;
          }
          const selected = selectedAssets.some((entry) => entry.id === sourceItem.id);
          const compareTarget = selectedAssets.find((entry) => entry.id !== sourceItem.id);
          return (
            <>
              <div className="card-actions">
                <button type="button" className="button small-button" onClick={() => toggleSelection(sourceItem.id, sourceItem.filename, mediaUrl(sourceItem.preview_url))}>
                  {selected ? "Deselect for Compare" : "Stage for Compare"}
                </button>
                {compareTarget ? (
                  <button
                    type="button"
                    className="button ghost-button small-button"
                    onClick={() => router.push(`/compare?a=${compareTarget.id}&b=${sourceItem.id}`)}
                  >
                    Compare with Selected
                  </button>
                ) : null}
              </div>
              <div className="card-actions">
                {user?.capabilities.can_manage_collections && collectionsEnabled ? (
                  <button
                    type="button"
                    className="button subtle-button small-button"
                    onClick={() => {
                      setPendingCollectionAssetIds([sourceItem.id]);
                      setCollectionModalOpen(true);
                    }}
                  >
                    Add to Collection
                  </button>
                ) : null}
                <button
                  type="button"
                  className="button ghost-button small-button"
                  disabled={!sourceItem.prompt_tag_string}
                  onClick={async () => {
                    if (sourceItem.prompt_tag_string) {
                      await copyTextToClipboard(sourceItem.prompt_tag_string);
                    }
                  }}
                >
                  Copy Danbooru Tags
                </button>
              </div>
              {/* M4 — Generation Tools group */}
              {sourceItem.workflow_export_available ? (
                <div>
                  <p className="eyebrow" style={{ marginBottom: "0.4rem" }}>Generation Tools</p>
                  <div className="card-actions">
                    <button
                      type="button"
                      className="button ghost-button small-button"
                      onClick={() => void downloadWorkflow(sourceItem.id, sourceItem.filename)}
                    >
                      Download Workflow JSON
                    </button>
                  </div>
                </div>
              ) : null}
              <div className="card-actions">
                <button
                  type="button"
                  className="button ghost-button small-button"
                  onClick={() => window.open(mediaUrl(sourceItem.content_url) ?? sourceItem.content_url, "_blank", "noopener,noreferrer")}
                >
                  Open Original File
                </button>
                <Link href={sourceFolderBrowseHref(sourceItem.source_id, sourceItem.relative_path)} className="button ghost-button small-button">
                  Open Live Folder
                </Link>
              </div>
            </>
          );
        }}
      />
      {bulkMode && bulkSelectedIds.length > 0 && (
        <BulkActionBar
          selectedIds={bulkSelectedIds}
          onClear={() => setBulkSelectedIds([])}
          onDone={() => {
            setBulkSelectedIds([]);
            setBulkMode(false);
            void load();
          }}
        />
      )}
      <CompareSelectionTray
        selectionMode={selectionMode}
        selectedItems={selectedAssets.map((a) => ({ id: a.id, name: a.name, previewUrl: a.previewUrl }))}
        compareHref={compareHref}
        onToggleSelectionMode={() => setSelectionMode((value) => !value)}
        onClearSelection={() => setSelectedAssets([])}
        onRemoveItem={removeSelection}
        hint="This page is for visual browsing only. Hover or long-press for prompt tags, quick actions, and collection shortcuts."
        canAddToCollection={Boolean(user?.capabilities.can_manage_collections) && collectionsEnabled}
        onAddToCollection={
          user?.capabilities.can_manage_collections && collectionsEnabled
            ? () => {
                setPendingCollectionAssetIds(selectedAssets.map((item) => item.id));
                setCollectionModalOpen(true);
              }
            : undefined
        }
      />
      {!selectionMode && (
        <div style={{ padding: "0.5rem 1rem" }}>
          <button
            type="button"
            className={`button small-button ${bulkMode ? "" : "ghost-button"}`}
            onClick={() => { setBulkMode((v) => !v); setBulkSelectedIds([]); }}
          >
            {bulkMode ? `Bulk Mode (${bulkSelectedIds.length} selected)` : "Bulk Curate"}
          </button>
        </div>
      )}
      <section className="gallery-layout">
        <aside className="panel stack gallery-sidebar">
          <div>
            <p className="eyebrow">Indexed Controls</p>
            <h2>Gallery filters</h2>
          </div>
          <label className="field">
            <span>Source</span>
            <select value={sourceId} onChange={(event) => setSourceId(event.target.value)}>
              <option value="">All sources</option>
              {sources.map((source) => (
                <option key={source.id} value={source.id}>
                  {source.name}
                </option>
              ))}
            </select>
          </label>
          <div className="browse-toolbar-group">
            <span className="subdued">Mode</span>
            <div className="chip-row gallery-filter-chip-row">
              <button className={`button small-button ${displayMode === "gallery" ? "" : "ghost-button"}`} type="button" onClick={() => setDisplayMode("gallery")}>
                Gallery
              </button>
              <button
                className={`button small-button ${displayMode === "explorer" ? "" : "ghost-button"}`}
                type="button"
                onClick={() => setDisplayMode("explorer")}
                disabled={!displayItems.length}
              >
                Explorer
              </button>
            </div>
          </div>
          <div className="browse-toolbar-group">
            <span className="subdued">Sort</span>
            <div className="chip-row gallery-filter-chip-row">
              <button className={`button small-button ${sortMode === "modified_at" ? "" : "ghost-button"}`} type="button" onClick={() => setSortMode("modified_at")}>
                Modified
              </button>
              <button className={`button small-button ${sortMode === "created_at" ? "" : "ghost-button"}`} type="button" onClick={() => setSortMode("created_at")}>
                Created
              </button>
              <button className={`button small-button ${sortMode === "filename" ? "" : "ghost-button"}`} type="button" onClick={() => setSortMode("filename")}>
                Name
              </button>
            </div>
          </div>

          {/* M5.7 — Filter scopes */}
          <div className="browse-toolbar-group">
            <span className="subdued">Quick filters</span>
            <div className="filter-scope-group">
              {([
                ["has_workflow", "Has workflow"],
                ["has_prompt", "Has prompt"],
              ] as const).map(([scope, label]) => (
                <button
                  key={scope}
                  type="button"
                  className={`button small-button ${filterScope === scope ? "" : "ghost-button"}`}
                  onClick={() => setFilterScope(filterScope === scope ? null : scope)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* M2 — Scan progress bar */}
          {scanProgress ? (
            <div className="scan-progress">
              <span>Scanning… {scanProgress.processed} / {scanProgress.total || "?"}</span>
              <div className="scan-progress-bar">
                <div
                  className="scan-progress-bar-inner"
                  style={{
                    width: scanProgress.total
                      ? `${Math.min(100, (scanProgress.processed / scanProgress.total) * 100).toFixed(1)}%`
                      : "0%",
                  }}
                />
              </div>
            </div>
          ) : null}

          <div className="chip-row">
            <span className="chip">{total} indexed images</span>
            {sourceId ? <span className="chip">Filtered source</span> : null}
            {tagFilter ? (
              <button
                type="button"
                className="chip"
                style={{ cursor: "pointer" }}
                onClick={() => setTagFilter(null)}
              >
                #{tagFilter} ✕
              </button>
            ) : null}
          </div>

          {/* M5.5 — Top tags panel */}
          {topTags.length > 0 ? (
            <div className="tag-frequency-panel">
              <button type="button" className="browse-collapsible" onClick={() => setTagsOpen((v) => !v)}>
                <span>Top tags</span>
                <span>{tagsOpen ? "▲" : "▼"}</span>
              </button>
              {tagsOpen ? (
                <div className="tag-frequency-chips">
                  {topTags.map((tc) => {
                    const minSize = 0.75;
                    const maxSize = 1.15;
                    const maxCount = topTags[0]?.count ?? 1;
                    const size = minSize + ((tc.count / maxCount) * (maxSize - minSize));
                    return (
                      <button
                        key={tc.tag}
                        type="button"
                        className={`tag-freq-chip ${tagFilter === tc.tag ? "tag-freq-chip-active" : ""}`}
                        style={{ fontSize: `${size.toFixed(2)}rem` }}
                        onClick={() => setTagFilter(tagFilter === tc.tag ? null : tc.tag)}
                        title={`${tc.count} images`}
                      >
                        {tc.tag}
                      </button>
                    );
                  })}
                </div>
              ) : null}
            </div>
          ) : null}
        </aside>
        <section className="stack">
          {error ? <section className="panel empty-state">{error}</section> : null}
          {message ? <section className="panel info-banner">{message}</section> : null}
          {loading ? <section className="panel empty-state">Loading indexed gallery…</section> : null}
          <JustifiedGallery
            className="gallery-surface"
            targetRowHeight={deviceMode === "mobile" ? 168 : 248}
            gap={deviceMode === "mobile" ? 8 : 12}
            items={displayItems.map((item, index) => {
              const selected = selectedAssets.some((entry) => entry.id === item.id);
              const compareTarget = selectedAssets.find((entry) => entry.id !== item.id);
              return {
                key: item.id,
                ratio: item.width && item.height ? item.width / item.height : 1,
                content: (
                  <GalleryTile
                    key={item.id}
                    className="gallery-tile-justified"
                    tileStyle={{ height: "100%" }}
                    imageButtonStyle={{ height: "100%", aspectRatio: "auto" }}
                    imageSrc={mediaUrl(item.preview_url) ?? null}
                    blurHash={item.blur_hash}
                    alt={item.filename}
                    title={item.filename}
                    subtitle={[item.source_name, item.generator].filter(Boolean).join(" · ") || undefined}
                    promptExcerpt={item.prompt_excerpt}
                    promptTags={item.prompt_tags}
                    selected={selected}
                    selectionMode={bulkMode || selectedAssets.length > 0}
                    workflowAvailable={item.workflow_export_available}
                    onOpen={() => setExplorerIndex(index)}
                    onToggleSelect={() => {
                      if (bulkMode) {
                        setBulkSelectedIds((ids) => ids.includes(item.id) ? ids.filter((x) => x !== item.id) : [...ids, item.id]);
                      } else {
                        toggleSelection(item.id, item.filename, mediaUrl(item.preview_url));
                      }
                    }}
                    menuActions={[
                      { label: "Open Explorer", onSelect: () => setExplorerIndex(index) },
                      { label: "Open Image Details", onSelect: () => router.push(`/assets/${item.id}`), variant: "subtle" },
                      { label: "Open Similar", onSelect: () => router.push(`/assets/${item.id}/similar`), variant: "subtle" },
                      ...(item.workflow_export_available
                        ? [
                            {
                              label: "Download Workflow JSON",
                              onSelect: () => void downloadWorkflow(item.id, item.filename),
                              variant: "ghost" as const,
                            },
                          ]
                        : []),
                      { 
                        label: bulkMode 
                          ? (bulkSelectedIds.includes(item.id) ? "Remove from Bulk" : "Add to Bulk")
                          : (selected ? "Remove from Selection" : "Add to Selection"), 
                        onSelect: () => {
                          if (bulkMode) {
                            setBulkSelectedIds((ids) => ids.includes(item.id) ? ids.filter((x) => x !== item.id) : [...ids, item.id]);
                          } else {
                            toggleSelection(item.id, item.filename, mediaUrl(item.preview_url));
                          }
                        }, 
                        variant: "ghost" 
                      },
                      {
                        label: "Scan Metadata",
                        onSelect: () => void queueAssetScan(item, "metadata"),
                        variant: "ghost",
                        disabled: Boolean(activeScanJobId) || actionBusyId === item.id,
                      },
                      {
                        label: "Scan with Vision LLM (KoboldCpp)",
                        onSelect: () => void runVisionLlmForItem(item),
                        variant: "ghost",
                        disabled: actionBusyId === item.id,
                      },
                      {
                        label: "Run CLIP / AI Enrichment",
                        onSelect: () => void queueAssetScan(item, "ai"),
                        variant: "ghost",
                        disabled: Boolean(activeScanJobId) || actionBusyId === item.id,
                      },
                      ...(compareTarget
                        ? [{ label: "Compare with Selected", onSelect: () => router.push(`/compare?a=${compareTarget.id}&b=${item.id}`), variant: "subtle" as const }]
                        : []),
                      ...(user?.capabilities.can_manage_collections && collectionsEnabled
                        ? [{ label: "Add to Collection", onSelect: () => { setPendingCollectionAssetIds([item.id]); setCollectionModalOpen(true); }, variant: "subtle" as const }]
                        : []),
                      {
                        label: "Copy Danbooru Tags",
                        onSelect: async () => {
                          if (item.prompt_tag_string) {
                            await copyTextToClipboard(item.prompt_tag_string);
                          }
                        },
                        variant: "ghost",
                        disabled: !item.prompt_tag_string,
                      },
                      {
                        label: "Add Tag...",
                        onSelect: () => {
                          const tag = window.prompt("Enter tag name to add:");
                          if (tag && tag.trim()) {
                            void bulkAnnotateAssets({ asset_ids: [item.id], tags: [tag.trim()] }).then(() => void load());
                          }
                        },
                        variant: "ghost",
                      },
                      {
                        label: "Add NSFW Tag",
                        onSelect: () => void annotateWithTag(item.id, "nsfw"),
                        variant: "ghost",
                        disabled: actionBusyId === item.id,
                      },
                      {
                        label: "Open Live Folder",
                        onSelect: () => router.push(sourceFolderBrowseHref(item.source_id, item.relative_path)),
                        variant: "ghost",
                      },
                      {
                        label: "Open Original File",
                        onSelect: () => window.open(mediaUrl(item.content_url) ?? item.content_url, "_blank", "noopener,noreferrer"),
                        variant: "ghost",
                      },
                    ]}
                  />
                ),
              };
            })}
          />
          {!loading ? (
            <section className="panel stack">
              <div className="row-between">
                <p className="subdued">Showing {displayItems.length} of {total} indexed images</p>
                {loadingMore ? <p className="subdued">Loading more…</p> : null}
              </div>
              <div ref={sentinelRef} className="infinite-sentinel" />
            </section>
          ) : null}
        </section>
      </section>
    </AppShell>
  );
}
