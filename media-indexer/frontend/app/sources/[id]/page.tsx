"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { CompareSelectionTray } from "@/components/compare-selection-tray";
import { CollectionPickerModal } from "@/components/collection-picker-modal";
import { GalleryTile } from "@/components/gallery-tile";
import { ImageExplorerOverlay } from "@/components/image-explorer-overlay";
import { JustifiedGallery } from "@/components/justified-gallery";
import { useModuleRegistry } from "@/components/module-registry-provider";
import { useDeviceMode } from "@/hooks/use-device-mode";
import {
  addAssetsToCollection,
  bulkAnnotateAssets,
  cancelScanJob,
  createSource,
  fetchCollections,
  fetchScanJobs,
  fetchSource,
  fetchSourceBrowse,
  fetchSourceInspect,
  mediaUrl,
  runAssetVisionLlm,
  triggerScan,
} from "@/lib/api";
import { browseIndexStateLabel, formatBytes, formatDate } from "@/lib/asset-metadata";
import { copyTextToClipboard } from "@/lib/clipboard";
import { CollectionSummary, ScanJob, Source, SourceBrowseEntry, SourceBrowseInspect, SourceBrowseResponse } from "@/lib/types";

const BROWSE_PAGE_SIZE = 24;
type BrowseSortMode = "name" | "date" | "size";
type BrowseDisplayMode = "gallery" | "explorer";
type ScanMode = "basic" | "metadata" | "ai";

function findActiveJob(source: Source, jobs: ScanJob[]): ScanJob | null {
  return (
    jobs.find(
      (job) =>
        job.source_id === source.id &&
        (job.status === "queued" ||
          job.status === "running" ||
          (job.status === "cancelled" && source.status === "scanning"))
    ) ?? null
  );
}

function compareBrowseEntries(left: SourceBrowseEntry, right: SourceBrowseEntry, sortMode: BrowseSortMode) {
  if (sortMode === "date") {
    const leftTime = left.modified_at ? new Date(left.modified_at).getTime() : 0;
    const rightTime = right.modified_at ? new Date(right.modified_at).getTime() : 0;
    return rightTime - leftTime || left.name.localeCompare(right.name);
  }
  if (sortMode === "size") {
    const leftSize = left.size_bytes ?? -1;
    const rightSize = right.size_bytes ?? -1;
    return rightSize - leftSize || left.name.localeCompare(right.name);
  }
  return left.name.localeCompare(right.name);
}

function SourceBrowsePageContent() {
  const { user } = useAuth();
  const { isModuleEnabled } = useModuleRegistry();
  const deviceMode = useDeviceMode();
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const currentPath = searchParams.get("path") ?? "";

  const [source, setSource] = useState<Source | null>(null);
  const [browse, setBrowse] = useState<SourceBrowseResponse | null>(null);
  const [activeJob, setActiveJob] = useState<ScanJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [visibleFileCount, setVisibleFileCount] = useState(BROWSE_PAGE_SIZE);
  const [scanSubmitting, setScanSubmitting] = useState(false);
  const [sourceCreating, setSourceCreating] = useState(false);
  const [sortMode, setSortMode] = useState<BrowseSortMode>("name");
  const [displayMode, setDisplayMode] = useState<BrowseDisplayMode>("gallery");
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedAssets, setSelectedAssets] = useState<Array<{ id: string; name: string }>>([]);
  const [explorerIndex, setExplorerIndex] = useState<number | null>(null);
  const [controlsOpen, setControlsOpen] = useState(false);
  const [inspectCache, setInspectCache] = useState<Record<string, SourceBrowseInspect>>({});
  const [imageSizes, setImageSizes] = useState<Record<string, { width: number; height: number }>>({});
  const [collections, setCollections] = useState<CollectionSummary[]>([]);
  const [collectionModalOpen, setCollectionModalOpen] = useState(false);
  const [collectionBusy, setCollectionBusy] = useState(false);
  const [pendingCollectionAssetIds, setPendingCollectionAssetIds] = useState<string[]>([]);
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const collectionsEnabled = isModuleEnabled("collections");

  const load = async (silent = false) => {
    if (!silent) {
      setLoading(true);
    }
    setError(null);
    try {
      const [nextSource, nextBrowse, jobs] = await Promise.all([
        fetchSource(params.id),
        fetchSourceBrowse(params.id, currentPath),
        fetchScanJobs(),
      ]);
      setSource(nextSource);
      setBrowse(nextBrowse);
      setActiveJob(findActiveJob(nextSource, jobs));
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Unable to browse this source.");
    } finally {
      if (!silent) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    setVisibleFileCount(BROWSE_PAGE_SIZE);
    void load();
    const interval = window.setInterval(() => {
      void load(true);
    }, 5000);
    return () => window.clearInterval(interval);
  }, [params.id, currentPath]);

  useEffect(() => {
    if (!user?.capabilities.can_manage_collections || !collectionsEnabled) {
      return;
    }
    const loadCollections = async () => {
      try {
        setCollections(await fetchCollections());
      } catch {
        setCollections([]);
      }
    };
    void loadCollections();
  }, [user?.capabilities.can_manage_collections, collectionsEnabled]);

  const openPath = (nextPath: string) => {
    const href = nextPath ? `/sources/${params.id}?path=${encodeURIComponent(nextPath)}` : `/sources/${params.id}`;
    router.push(href);
    setControlsOpen(false);
  };

  const directories = (browse?.entries.filter((entry) => entry.entry_type === "directory") ?? []).sort((left, right) =>
    compareBrowseEntries(left, right, sortMode === "size" ? "name" : sortMode)
  );
  const files = (browse?.entries.filter((entry) => entry.entry_type === "file" && entry.media_type === "image") ?? []).sort((left, right) =>
    compareBrowseEntries(left, right, sortMode)
  );
  const visibleFiles = files.slice(0, visibleFileCount);
  const hasMoreFiles = visibleFileCount < files.length;
  const parentPath = browse?.parent_path ?? null;
  const cancellationPending = activeJob?.status === "cancelled" && source?.status === "scanning";
  const compareHref = selectedAssets.length === 2 ? `/compare?a=${selectedAssets[0].id}&b=${selectedAssets[1].id}` : null;
  const selectedAssetIds = useMemo(() => selectedAssets.map((item) => item.id), [selectedAssets]);
  const explorerItems = useMemo(
    () =>
      visibleFiles.map((entry) => {
        const inspect = inspectCache[entry.relative_path];
        const previewSrc = mediaUrl(inspect?.preview_url ?? entry.preview_url);
        const contentSrc = mediaUrl(inspect?.content_url ?? entry.content_url);
        const dimensions =
          inspect?.width && inspect?.height
            ? `${inspect.width} x ${inspect.height}`
            : imageSizes[entry.relative_path]
              ? `${imageSizes[entry.relative_path].width} x ${imageSizes[entry.relative_path].height}`
              : null;
        return {
          key: entry.relative_path,
          title: entry.name,
          subtitle: [dimensions, inspect?.generator].filter(Boolean).join(" · ") || undefined,
          promptExcerpt: inspect?.prompt_excerpt,
          promptTags: inspect?.prompt_tags ?? [],
          statusBadge: browseIndexStateLabel(inspect?.index_state ?? entry.index_state),
          previewSrc,
          contentSrc,
          deepzoomUrl: mediaUrl(inspect?.deepzoom_url ?? null),
          detailHref: entry.indexed_asset_id ? `/assets/${entry.indexed_asset_id}` : null,
          similarHref: entry.indexed_asset_id ? `/assets/${entry.indexed_asset_id}/similar` : null,
          sourceContext: entry.relative_path,
          metadataSummary: [
            ...(dimensions ? [{ label: "Dimensions", value: dimensions }] : []),
            ...(entry.modified_at ? [{ label: "Modified", value: formatDate(entry.modified_at) }] : []),
            ...(entry.size_bytes !== null ? [{ label: "Size", value: formatBytes(entry.size_bytes) }] : []),
          ],
        };
      }),
    [imageSizes, inspectCache, visibleFiles]
  );

  useEffect(() => {
    if (displayMode === "explorer" && visibleFiles.length && explorerIndex === null) {
      setExplorerIndex(0);
    }
    if (displayMode === "gallery" && explorerIndex !== null) {
      setExplorerIndex(null);
    }
  }, [displayMode, explorerIndex, visibleFiles.length]);

  const ensureInspect = async (entry: SourceBrowseEntry) => {
    if (inspectCache[entry.relative_path] || entry.entry_type !== "file" || entry.media_type !== "image") {
      return;
    }
    try {
      const payload = await fetchSourceInspect(params.id, entry.relative_path);
      setInspectCache((current) => ({ ...current, [entry.relative_path]: payload }));
    } catch {
          setInspectCache((current) => ({
            ...current,
            [entry.relative_path]: {
              source_id: params.id,
              relative_path: entry.relative_path,
              indexed_asset_id: entry.indexed_asset_id,
              index_state: entry.index_state,
              preview_url: entry.preview_url,
              content_url: entry.content_url,
              blur_hash: null,
              deepzoom_available: false,
              deepzoom_url: null,
              width: null,
              height: null,
              generator: null,
          prompt_excerpt: null,
          prompt_tags: [],
          prompt_tag_string: null,
          annotation: null,
        },
      }));
    }
  };

  const copyText = async (value: string | null | undefined) => {
    if (!value) {
      return;
    }
    try {
      const success = await copyTextToClipboard(value);
      if (!success) {
        throw new Error("copy_failed");
      }
      setMessage("Copied to clipboard.");
    } catch {
      setError("Clipboard access failed.");
    }
  };

  const queueScan = async (scan_mode: ScanMode, path_filter: string | null = null) => {
    setScanSubmitting(true);
    setMessage(null);
    setError(null);
    try {
      const job = await triggerScan(params.id, { scan_mode, path_filter });
      const scope = path_filter ? ` for ${path_filter}` : "";
      setMessage(`${scan_mode.toUpperCase()} scan queued${scope}: ${job.id}`);
      setActiveJob(job);
      await load(true);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Unable to queue scan.");
    } finally {
      setScanSubmitting(false);
    }
  };

  const openCollectionPicker = (assetIds: string[]) => {
    if (!assetIds.length) {
      return;
    }
    setPendingCollectionAssetIds(assetIds);
    setCollectionModalOpen(true);
  };

  const annotateEntry = async (entry: SourceBrowseEntry, tag: string) => {
    if (!entry.indexed_asset_id) {
      setError("This image must be indexed before tags can be added.");
      return;
    }
    setError(null);
    setMessage(null);
    try {
      await bulkAnnotateAssets({ asset_ids: [entry.indexed_asset_id], tags: [tag] });
      setMessage(`Tag "${tag}" added to ${entry.name}.`);
      await load(true);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Unable to update tags.");
    }
  };

  const runVisionLlmForEntry = async (entry: SourceBrowseEntry) => {
    if (!entry.indexed_asset_id) {
      setError("This image must be indexed before Vision LLM analysis can run.");
      return;
    }
    setError(null);
    setMessage(null);
    setScanSubmitting(true);
    try {
      await runAssetVisionLlm(entry.indexed_asset_id);
      setMessage(`Vision LLM analysis saved for ${entry.name}.`);
      await load(true);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Vision LLM analysis failed.");
    } finally {
      setScanSubmitting(false);
    }
  };

  useEffect(() => {
    const target = sentinelRef.current;
    if (!target || !hasMoreFiles || loading) {
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          setVisibleFileCount((current) => Math.min(current + BROWSE_PAGE_SIZE, files.length));
        }
      },
      { rootMargin: "800px 0px" }
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [files.length, hasMoreFiles, loading]);

  useEffect(() => {
    if (explorerIndex === null) {
      return;
    }
    if (!visibleFiles.length) {
      setExplorerIndex(null);
      return;
    }
    if (explorerIndex >= visibleFiles.length) {
      setExplorerIndex(visibleFiles.length - 1);
    }
  }, [explorerIndex, visibleFiles.length]);

  const toggleEntrySelection = (entry: SourceBrowseEntry) => {
    const assetId = entry.indexed_asset_id;
    if (!assetId || entry.media_type !== "image") {
      return;
    }
    setSelectedAssets((current) => {
      const exists = current.some((item) => item.id === assetId);
      if (exists) {
        return current.filter((item) => item.id !== assetId);
      }
      const next = { id: assetId, name: entry.name };
      if (current.length === 2) {
        return [current[1], next];
      }
      return [...current, next];
    });
  };

  return (
    <AppShell
      title={source ? `Browse ${source.name}` : "Browse Source"}
      description="Live folder browsing stays image-first here, while Search handles indexed metadata, tags, and prompt filters."
      actions={
        <div className="page-actions">
          <Link href="/browse-indexed" className="button subtle-button small-button">
            Browse Indexed
          </Link>
          <Link href="/search" className="button subtle-button small-button">
            Open Search
          </Link>
          {/* v1.6 — File Explorer link */}
          <Link href={`/sources/${params.id}/explorer`} className="button ghost-button small-button">
            📁 File Explorer
          </Link>
          <button className="button ghost-button small-button mobile-control-button" type="button" onClick={() => setControlsOpen(true)}>
            Controls
          </button>
          {user?.capabilities.can_run_scans ? (
            <button
              className="button"
              type="button"
              disabled={scanSubmitting || Boolean(activeJob) || source?.status === "scanning"}
              onClick={() => void queueScan("basic", currentPath || null)}
            >
              {activeJob ? "Scan Running" : scanSubmitting ? "Starting Scan..." : "Quick Index Files"}
            </button>
          ) : null}
          {user?.capabilities.can_run_scans ? (
            <button
              className="button ghost-button small-button"
              type="button"
              disabled={scanSubmitting || Boolean(activeJob) || source?.status === "scanning"}
              onClick={() => void queueScan("metadata", currentPath || null)}
            >
              Parse Metadata
            </button>
          ) : null}
        </div>
      }
    >
      <button
        type="button"
        aria-label="Close browse controls"
        className={`search-overlay ${controlsOpen ? "search-overlay-visible" : ""}`}
        onClick={() => setControlsOpen(false)}
      />
      <CollectionPickerModal
        open={collectionModalOpen}
        collections={collections}
        busy={collectionBusy}
        onClose={() => setCollectionModalOpen(false)}
        onConfirm={async (collectionId) => {
          setCollectionBusy(true);
          setError(null);
          setMessage(null);
          try {
            await addAssetsToCollection(collectionId, pendingCollectionAssetIds);
            setMessage("Assets added to collection.");
            setCollectionModalOpen(false);
            setPendingCollectionAssetIds([]);
          } catch (nextError) {
            setError(nextError instanceof Error ? nextError.message : "Unable to add to collection.");
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
        onActiveIndexChange={(next) => {
          const entry = visibleFiles[next];
          if (entry) {
            void ensureInspect(entry);
          }
          setExplorerIndex(next);
        }}
        renderActions={(item) => {
          const entry = visibleFiles.find((candidate) => candidate.relative_path === item.key);
          if (!entry) {
            return null;
          }
          const indexedAssetId = entry.indexed_asset_id;
          const selected = indexedAssetId ? selectedAssets.some((candidate) => candidate.id === indexedAssetId) : false;
          const compareTarget = selectedAssets.find((candidate) => candidate.id !== indexedAssetId);
          const inspect = inspectCache[entry.relative_path];
          const content = mediaUrl(inspect?.content_url ?? entry.content_url);
          return (
            <>
              {indexedAssetId ? (
                <div className="card-actions">
                  <button type="button" className="button small-button" onClick={() => toggleEntrySelection(entry)}>
                    {selected ? "Deselect for Compare" : "Stage for Compare"}
                  </button>
                  {compareTarget ? (
                    <button
                      type="button"
                      className="button ghost-button small-button"
                      onClick={() => router.push(`/compare?a=${compareTarget.id}&b=${indexedAssetId}`)}
                    >
                      Compare with Selected
                    </button>
                  ) : null}
                </div>
              ) : null}
              <div className="card-actions">
                {user?.capabilities.can_manage_collections && collectionsEnabled && indexedAssetId ? (
                  <button
                    type="button"
                    className="button subtle-button small-button"
                    onClick={() => openCollectionPicker([indexedAssetId])}
                  >
                    Add to Collection
                  </button>
                ) : null}
                <button
                  type="button"
                  className="button ghost-button small-button"
                  disabled={!inspect?.prompt_tag_string}
                  onClick={() => void copyText(inspect?.prompt_tag_string)}
                >
                  Copy Danbooru Tags
                </button>
              </div>
              <div className="card-actions">
                <button
                  type="button"
                  className="button ghost-button small-button"
                  disabled={!content}
                  onClick={() => {
                    if (content) {
                      window.open(content, "_blank", "noopener,noreferrer");
                    }
                  }}
                >
                  Open Original File
                </button>
                {user?.capabilities.can_run_scans ? (
                  <>
                    <button
                      type="button"
                      className="button ghost-button small-button"
                      disabled={scanSubmitting || Boolean(activeJob)}
                      onClick={() => void queueScan("metadata", entry.relative_path)}
                    >
                      Parse Metadata
                    </button>
                    <button
                      type="button"
                      className="button ghost-button small-button"
                      disabled={scanSubmitting || Boolean(activeJob)}
                      onClick={() => void queueScan("ai", entry.relative_path)}
                    >
                      Interrogate Image
                    </button>
                  </>
                ) : null}
              </div>
            </>
          );
        }}
      />
      <section className="panel stack">
        <div className="row-between">
          <div>
            <p className="eyebrow">Source Root</p>
            <h2>{browse?.current_path || "Root"}</h2>
            <p className="subdued">{source?.display_root_path ?? "Loading source details..."}</p>
          </div>
          <span className="pill">{source?.status ?? "loading"}</span>
        </div>
        {browse ? (
          <div className="chip-row">
            <span className="chip">{files.length} files</span>
            <span className="chip">{directories.length} folders</span>
            <span className="chip">{browse.current_path || "root"}</span>
          </div>
        ) : null}
        {browse ? (
          <div className="breadcrumb-row">
            {browse.breadcrumbs.map((breadcrumb) => (
              <button
                key={`${breadcrumb.label}-${breadcrumb.path}`}
                className="chip buttonless"
                type="button"
                onClick={() => openPath(breadcrumb.path)}
              >
                {breadcrumb.label}
              </button>
            ))}
          </div>
        ) : null}
        <div className="card-actions">
          <Link href="/sources" className="button ghost-button small-button">
            Back to Sources
          </Link>
          {parentPath !== null ? (
            <button className="button ghost-button small-button" type="button" onClick={() => openPath(parentPath)}>
              Up One Level
            </button>
          ) : null}
          {user?.capabilities.can_manage_sources && source && currentPath && source.root_path ? (
            <button
              className="button subtle-button small-button"
              type="button"
              disabled={sourceCreating}
              onClick={async () => {
                const sourceRootPath = source.root_path;
                if (!sourceRootPath) {
                  return;
                }
                const suggestedName = currentPath.split("/").filter(Boolean).at(-1) ?? "subsource";
                const name = window.prompt("New source name", suggestedName)?.trim();
                if (!name) {
                  return;
                }

                setSourceCreating(true);
                setError(null);
                setMessage(null);
                try {
                  const rootPath = `${sourceRootPath.replace(/\/$/, "")}/${currentPath}`;
                  const created = await createSource({
                    name,
                    root_path: rootPath,
                    type: "mounted_fs",
                  });
                  setMessage(`Created source ${created.name}.`);
                  router.push(`/sources/${created.id}`);
                } catch (nextError) {
                  setError(nextError instanceof Error ? nextError.message : "Unable to create a source from this folder.");
                } finally {
                  setSourceCreating(false);
                }
              }}
            >
              {sourceCreating ? "Creating Source..." : "Create Source From Folder"}
            </button>
          ) : null}
          {message ? (
            <Link href="/scan-jobs" className="button subtle-button small-button">
              Open Scan Jobs
            </Link>
          ) : null}
        </div>
        {message ? <p className="subdued">{message}</p> : null}
      </section>

      {activeJob ? (
        <section className="panel stack">
          <div className="row-between">
            <div>
              <p className="eyebrow">Active Scan</p>
              <h2>
                {cancellationPending
                  ? "Stopping this scan"
                  : activeJob.status === "running"
                    ? "Scanning this source"
                    : "Queued for scan"}
              </h2>
              <p className="subdued">
                {cancellationPending
                  ? "Cancellation requested. Waiting for the worker to stop cleanly."
                  : activeJob.message ?? "Worker is processing files in this root."}
              </p>
            </div>
            <span className="pill">{activeJob.progress}%</span>
          </div>
          <div className="progress-track">
            <div className="progress-bar" style={{ width: `${activeJob.progress}%` }} />
          </div>
          <div className="chip-row">
            <span className="chip">Scanned {activeJob.scanned_count}</span>
            <span className="chip">New {activeJob.new_count}</span>
            <span className="chip">Updated {activeJob.updated_count}</span>
            <span className="chip">Deleted {activeJob.deleted_count}</span>
            <span className="chip">Errors {activeJob.error_count}</span>
          </div>
          <div className="card-actions">
            <Link href={`/scan-jobs/${activeJob.id}`} className="button subtle-button small-button">
              Open Scan Job
            </Link>
            {!cancellationPending && user?.capabilities.can_run_scans ? (
              <button
                className="button ghost-button small-button"
                type="button"
                onClick={async () => {
                  setError(null);
                  setMessage(null);
                  try {
                    const cancelled = await cancelScanJob(activeJob.id);
                    setMessage(`Cancelled scan job ${cancelled.id}.`);
                    await load(true);
                  } catch (nextError) {
                    setError(nextError instanceof Error ? nextError.message : "Unable to cancel scan job.");
                  }
                }}
              >
                Cancel Scan
              </button>
            ) : null}
          </div>
        </section>
      ) : null}

      {error ? <section className="panel empty-state">{error}</section> : null}
      {loading ? <section className="panel empty-state">Loading source folder…</section> : null}

      {!loading && browse ? (
        <>
          <CompareSelectionTray
            selectionMode={selectionMode}
            selectedCount={selectedAssets.length}
            compareHref={compareHref}
            onToggleSelectionMode={() => setSelectionMode((value) => !value)}
            onClearSelection={() => setSelectedAssets([])}
            hint="Tap opens the image. Right click on desktop or long-press on phone for gallery actions and collection shortcuts."
            canAddToCollection={Boolean(user?.capabilities.can_manage_collections) && collectionsEnabled}
            onAddToCollection={user?.capabilities.can_manage_collections && collectionsEnabled ? () => openCollectionPicker(selectedAssetIds) : undefined}
          />
          <section className={`panel stack browse-controls-panel ${controlsOpen ? "browse-controls-panel-open" : ""}`}>
            <div className="row-between">
              <div>
                <p className="eyebrow">Browse Controls</p>
                <h2>Source gallery</h2>
              </div>
              <button className="button ghost-button small-button search-sidebar-close" type="button" onClick={() => setControlsOpen(false)}>
                Close
              </button>
            </div>
            <div className="row-between">
              <div className="chip-row">
                <span className="chip">Folders first</span>
                <span className="chip">{sortMode === "name" ? "A-Z" : sortMode === "date" ? "Newest first" : "Largest first"}</span>
              </div>
              <div className="chip-row">
                <span className="chip">{selectionMode ? "Selection on" : "Tap opens"}</span>
              </div>
            </div>
            <div className="card-actions browse-rail-actions">
              <button className="button subtle-button small-button" type="button" onClick={() => void load()}>
                Refresh
              </button>
              <button className={`button small-button ${displayMode === "gallery" ? "" : "ghost-button"}`} type="button" onClick={() => setDisplayMode("gallery")}>
                Gallery
              </button>
              <button
                className={`button small-button ${displayMode === "explorer" ? "" : "ghost-button"}`}
                type="button"
                onClick={() => setDisplayMode("explorer")}
                disabled={!files.length}
              >
                Explorer
              </button>
              {parentPath !== null ? (
                <button className="button ghost-button small-button" type="button" onClick={() => openPath(parentPath)}>
                  Up
                </button>
              ) : null}
              <button className={`button small-button ${selectionMode ? "" : "ghost-button"}`} type="button" onClick={() => setSelectionMode((value) => !value)}>
                {selectionMode ? "Selection On" : "Selection Off"}
              </button>
            </div>
            <div className="browse-toolbar">
              <div className="browse-toolbar-group">
                <span className="subdued">Sort</span>
                <div className="chip-row">
                  <button className={`button small-button ${sortMode === "name" ? "" : "ghost-button"}`} type="button" onClick={() => setSortMode("name")}>
                    Name
                  </button>
                  <button className={`button small-button ${sortMode === "date" ? "" : "ghost-button"}`} type="button" onClick={() => setSortMode("date")}>
                    Date
                  </button>
                  <button className={`button small-button ${sortMode === "size" ? "" : "ghost-button"}`} type="button" onClick={() => setSortMode("size")}>
                    Size
                  </button>
                </div>
              </div>
            </div>
          </section>

          <section className="browse-section stack">
            <div className="row-between">
              <div>
                <p className="eyebrow">Folders</p>
                <h2>{directories.length} subfolders</h2>
              </div>
            </div>
            {directories.length ? (
              <div className="folder-pill-row">
                {directories.map((entry) => (
                  <button key={entry.relative_path} className="folder-pill" type="button" onClick={() => openPath(entry.relative_path)}>
                    {entry.name}
                  </button>
                ))}
              </div>
            ) : (
              <div className="panel empty-state">No subfolders in this location.</div>
            )}
          </section>

          <section className="stack browse-section">
            <div className="row-between">
              <div>
                <p className="eyebrow">Image Gallery</p>
                <h2>{files.length} visible images</h2>
              </div>
              <div className="chip-row">
                <span className="chip">Live browse</span>
                <span className="chip">Indexed when ready</span>
                <span className="chip">
                  Showing {visibleFiles.length} of {files.length}
                </span>
              </div>
            </div>
            {files.length ? (
              <>
                <JustifiedGallery
                  className="gallery-surface"
                  targetRowHeight={deviceMode === "mobile" ? 168 : 248}
                  gap={deviceMode === "mobile" ? 8 : 12}
                  items={visibleFiles.map((entry, index) => {
                    const preview = mediaUrl(inspectCache[entry.relative_path]?.preview_url ?? entry.preview_url);
                    const content = mediaUrl(inspectCache[entry.relative_path]?.content_url ?? entry.content_url);
                    const inspect = inspectCache[entry.relative_path];
                    const canSelect = Boolean(entry.indexed_asset_id);
                    const selected = entry.indexed_asset_id ? selectedAssets.some((item) => item.id === entry.indexed_asset_id) : false;
                    const stateLabel = browseIndexStateLabel(inspect?.index_state ?? entry.index_state);
                    const measuredSize = imageSizes[entry.relative_path];
                    const subtitleParts = [
                      inspect?.width && inspect?.height
                        ? `${inspect.width} x ${inspect.height}`
                        : measuredSize
                          ? `${measuredSize.width} x ${measuredSize.height}`
                          : null,
                      inspect?.generator ?? null,
                    ].filter((value): value is string => Boolean(value));
                    const compareTarget = selectedAssets.find((item) => item.id !== entry.indexed_asset_id);
                    const ratio =
                      inspect?.width && inspect?.height
                        ? inspect.width / inspect.height
                        : measuredSize
                          ? measuredSize.width / measuredSize.height
                          : 1;

                    return {
                      key: entry.relative_path,
                      ratio,
                      content: (
                        <GalleryTile
                          key={entry.relative_path}
                          className="gallery-tile-justified"
                          tileStyle={{ height: "100%" }}
                          imageButtonStyle={{ height: "100%", aspectRatio: "auto" }}
                          imageSrc={preview}
                          alt={entry.name}
                          title={entry.name}
                          subtitle={subtitleParts.join(" · ") || undefined}
                          promptExcerpt={inspect?.prompt_excerpt}
                          promptTags={inspect?.prompt_tags ?? []}
                          statusBadge={stateLabel}
                          selected={selected}
                          selectionMode={selectionMode}
                          onInspect={() => void ensureInspect(entry)}
                          onImageLoad={(size) => {
                            setImageSizes((current) =>
                              current[entry.relative_path]?.width === size.width && current[entry.relative_path]?.height === size.height
                                ? current
                                : { ...current, [entry.relative_path]: size }
                            );
                          }}
                          onOpen={() => {
                            void ensureInspect(entry);
                            setExplorerIndex(index);
                          }}
                          onToggleSelect={canSelect ? () => toggleEntrySelection(entry) : undefined}
                          menuActions={[
                            {
                              label: "Open Explorer",
                              onSelect: () => {
                                void ensureInspect(entry);
                                setExplorerIndex(index);
                              },
                            },
                            ...(entry.indexed_asset_id
                              ? [{
                                  label: "Open Image Details",
                                  onSelect: () => router.push(`/assets/${entry.indexed_asset_id}`),
                                  variant: "subtle" as const,
                                }]
                              : []),
                            ...(entry.indexed_asset_id
                              ? [{
                                  label: "Open Similar",
                                  onSelect: () => router.push(`/assets/${entry.indexed_asset_id}/similar`),
                                  variant: "subtle" as const,
                                }]
                              : []),
                            ...(canSelect
                              ? [{
                                  label: selected ? "Remove from Selection" : "Add to Selection",
                                  onSelect: () => toggleEntrySelection(entry),
                                  variant: "ghost" as const,
                                }]
                              : []),
                            ...(canSelect && compareTarget && entry.indexed_asset_id
                              ? [{
                                  label: "Compare with Selected",
                                  onSelect: () => router.push(`/compare?a=${compareTarget.id}&b=${entry.indexed_asset_id}`),
                                  variant: "subtle" as const,
                                }]
                              : []),
                            ...(user?.capabilities.can_manage_collections && collectionsEnabled && entry.indexed_asset_id
                              ? [{
                                  label: "Add to Collection",
                                  onSelect: () => openCollectionPicker([entry.indexed_asset_id!]),
                                  variant: "subtle" as const,
                                }]
                              : []),
                            ...(entry.indexed_asset_id
                              ? [{
                                  label: "Add NSFW Tag",
                                  onSelect: () => void annotateEntry(entry, "nsfw"),
                                  variant: "ghost" as const,
                                }]
                              : []),
                            {
                              label: "Copy Danbooru Tags",
                              onSelect: () => void copyText(inspect?.prompt_tag_string),
                              variant: "ghost" as const,
                              disabled: !inspect?.prompt_tag_string,
                            },
                            {
                              label: "Open Original File",
                              onSelect: () => {
                                if (content) {
                                  window.open(content, "_blank", "noopener,noreferrer");
                                }
                              },
                              variant: "ghost" as const,
                              disabled: !content,
                            },
                            ...(user?.capabilities.can_run_scans
                              ? [
                                  {
                                    label: "Scan Metadata",
                                    onSelect: () => void queueScan("metadata", entry.relative_path),
                                    variant: "ghost" as const,
                                    disabled: scanSubmitting || Boolean(activeJob),
                                  },
                                  ...(entry.indexed_asset_id
                                    ? [{
                                        label: "Scan with Vision LLM (KoboldCpp)",
                                        onSelect: () => void runVisionLlmForEntry(entry),
                                        variant: "ghost" as const,
                                        disabled: scanSubmitting,
                                      }]
                                    : []),
                                  {
                                    label: "Run CLIP / AI Enrichment",
                                    onSelect: () => void queueScan("ai", entry.relative_path),
                                    variant: "ghost" as const,
                                    disabled: scanSubmitting || Boolean(activeJob),
                                  },
                                ]
                              : []),
                          ]}
                        />
                      ),
                    };
                  })}
                />
                <section className="panel stack">
                  <div className="row-between">
                    <p className="subdued">
                      Showing {visibleFiles.length} of {files.length} images in this folder
                    </p>
                    {hasMoreFiles ? <p className="subdued">Scroll for more…</p> : <p className="subdued">End of folder.</p>}
                  </div>
                  <div ref={sentinelRef} className="infinite-sentinel" />
                </section>
              </>
            ) : (
              <section className="panel empty-state">No supported images in this folder yet.</section>
            )}
          </section>
        </>
      ) : null}
    </AppShell>
  );
}

export default function SourceBrowsePage() {
  return (
    <Suspense
      fallback={
        <AppShell title="Browse Source" description="Inspect approved folders directly while indexing is still catching up.">
          <section className="panel empty-state">Loading source folder…</section>
        </AppShell>
      }
    >
      <SourceBrowsePageContent />
    </Suspense>
  );
}
