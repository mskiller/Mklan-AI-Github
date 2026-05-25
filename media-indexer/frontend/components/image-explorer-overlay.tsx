"use client";

import Link from "next/link";
import { ReactNode, useCallback, useEffect, useRef, useState } from "react";

import { TagFilterChip } from "@/components/tag-filter-chip";
import { MediaDeepZoomStage, MediaDeepZoomViewerHandle } from "@/components/media-deep-zoom-viewer";
import { fetchAssetFaces, mediaUrl } from "@/lib/api";
import { copyImageToClipboard } from "@/lib/clipboard";
import { copyTextToClipboard } from "@/lib/clipboard";
import { downloadWorkflow } from "@/lib/api";
import { AssetFacesResponse } from "@/lib/types";

export interface ExplorerMetadataEntry {
  label: string;
  value: string;
}

export interface ExplorerItem {
  key: string;
  title: string;
  subtitle?: string | null;
  promptExcerpt?: string | null;
  promptTags: string[];
  statusBadge?: string | null;
  previewSrc: string | null | undefined;
  contentSrc: string | null | undefined;
  deepzoomUrl?: string | null | undefined;
  detailHref?: string | null;
  similarHref?: string | null;
  sourceContext?: string | null;
  metadataSummary?: ExplorerMetadataEntry[];
  workflowAvailable?: boolean;
}

export function ImageExplorerOverlay({
  open,
  items,
  activeIndex,
  onClose,
  onActiveIndexChange,
  renderActions,
}: {
  open: boolean;
  items: ExplorerItem[];
  activeIndex: number;
  onClose: () => void;
  onActiveIndexChange: (next: number) => void;
  renderActions?: (item: ExplorerItem) => ReactNode;
}) {
  const viewerRef = useRef<MediaDeepZoomViewerHandle | null>(null);
  const viewerContainerRef = useRef<HTMLDivElement | null>(null);
  const filmstripRef = useRef<HTMLDivElement | null>(null);
  const forceFitOnNextSourceRef = useRef(true);
  const currentItem = items[activeIndex] ?? null;
  const touchRef = useRef<{ x: number; y: number } | null>(null);
  const [metaPanelOpen, setMetaPanelOpen] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const [rotation, setRotation] = useState(0);
  const [scalePercent, setScalePercent] = useState(100);
  const [navigatorVisible, setNavigatorVisible] = useState(true);
  const [copied, setCopied] = useState(false);
  const [toolbarVisible, setToolbarVisible] = useState(true);
  const [showFaceBoxes, setShowFaceBoxes] = useState(false);
  const [faceData, setFaceData] = useState<Record<string, AssetFacesResponse>>({});
  const [zoomMode, setZoomMode] = useState<"fit" | "native">("fit");

  // Reset rotation when item changes
  useEffect(() => {
    setRotation(0);
  }, [activeIndex]);

  useEffect(() => {
    if (!open) return;
    setMetaPanelOpen(false);
    setShowHelp(false);
    setCopied(false);
    setZoomMode("fit");
    forceFitOnNextSourceRef.current = true;
  }, [open, activeIndex]);

  useEffect(() => {
    if (!open || !currentItem?.key || faceData[currentItem.key]) {
      return;
    }
    let cancelled = false;
    void fetchAssetFaces(currentItem.key)
      .then((payload) => {
        if (!cancelled) {
          setFaceData((current) => ({ ...current, [currentItem.key]: payload }));
        }
      })
      .catch(() => {
        if (!cancelled) {
          setFaceData((current) => ({
            ...current,
            [currentItem.key]: { enabled: false, image_width: null, image_height: null, items: [] },
          }));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [open, currentItem?.key, faceData]);

  const currentFaceData = currentItem?.key ? faceData[currentItem.key] : undefined;
  const currentOverlays =
    showFaceBoxes && currentFaceData?.enabled && currentFaceData.image_width && currentFaceData.image_height
      ? currentFaceData.items.map((face) => ({
          id: face.id,
          x: face.bbox_x1,
          y: face.bbox_y1,
          width: face.bbox_x2 - face.bbox_x1,
          height: face.bbox_y2 - face.bbox_y1,
          label: face.person?.name ?? "Face",
        }))
      : [];

  // Scroll active filmstrip item into view
  useEffect(() => {
    if (!open) return;
    const strip = filmstripRef.current;
    if (!strip) return;
    const active = strip.querySelector('.explorer-filmstrip-item-active') as HTMLElement | null;
    if (active) {
      active.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
    }
  }, [open, activeIndex]);

  // Horizontal wheel scroll on filmstrip
  useEffect(() => {
    const strip = filmstripRef.current;
    if (!strip) return;
    const handleWheel = (e: WheelEvent) => {
      if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
        e.preventDefault();
        strip.scrollLeft += e.deltaY;
      }
    };
    strip.addEventListener('wheel', handleWheel, { passive: false });
    return () => strip.removeEventListener('wheel', handleWheel);
  }, [open]);

  const handleCopyImage = useCallback(async () => {
    if (!currentItem?.contentSrc) return;
    const ok = await copyImageToClipboard(currentItem.contentSrc);
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    }
  }, [currentItem?.contentSrc]);

  const handleOpenOriginal = useCallback(() => {
    if (currentItem?.contentSrc) {
      window.open(currentItem.contentSrc, '_blank', 'noopener,noreferrer');
    }
  }, [currentItem?.contentSrc]);

  const handleFullscreen = useCallback(() => {
    const el = viewerContainerRef.current ?? document.documentElement;
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else {
      el.requestFullscreen?.();
    }
  }, []);

  useEffect(() => {
    if (!open) {
      return;
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      // Don't intercept when user is typing in an input
      if (
        document.activeElement instanceof HTMLInputElement ||
        document.activeElement instanceof HTMLTextAreaElement
      ) {
        return;
      }

      switch (event.key) {
        case "Escape":
          event.preventDefault();
          if (showHelp) { setShowHelp(false); return; }
          onClose();
          return;
        case "ArrowLeft":
        case "ArrowUp":
          event.preventDefault();
          onActiveIndexChange(Math.max(0, activeIndex - 1));
          return;
        case "ArrowRight":
        case "ArrowDown":
          event.preventDefault();
          onActiveIndexChange(Math.min(items.length - 1, activeIndex + 1));
          return;
        case "PageDown":
          event.preventDefault();
          onActiveIndexChange(Math.min(items.length - 1, activeIndex + 10));
          return;
        case "PageUp":
          event.preventDefault();
          onActiveIndexChange(Math.max(0, activeIndex - 10));
          return;
        case "0":
          event.preventDefault();
          viewerRef.current?.fit();
          setZoomMode("fit");
          return;
        case "1":
          event.preventDefault();
          viewerRef.current?.actualSize();
          setZoomMode("native");
          return;
        case "c":
        case "C":
          event.preventDefault();
          if (currentItem?.promptTags.length) {
            void copyTextToClipboard(currentItem.promptTags.join(", "));
          }
          return;
        case "w":
        case "W":
        case "d":
        case "D":
          event.preventDefault();
          if (currentItem?.workflowAvailable && currentItem.key) {
            void downloadWorkflow(currentItem.key, currentItem.title);
          }
          return;
        case "?":
          event.preventDefault();
          setShowHelp((v) => !v);
          return;
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [activeIndex, items.length, onActiveIndexChange, onClose, open, currentItem, showHelp]);

  if (!open || !currentItem) {
    return null;
  }

  return (
    <>
      <button type="button" className="explorer-scrim" aria-label="Close explorer" onClick={onClose} />
      <section className="explorer-overlay">
        <div className="explorer-header">
          <div className="stack explorer-header-title">
            <p className="eyebrow">Explorer</p>
            <h2>{currentItem.title}</h2>
            {currentItem.subtitle ? <p className="subdued">{currentItem.subtitle}</p> : null}
          </div>
          <div className="explorer-header-actions">
            <button type="button" className="button ghost-button small-button" onClick={() => onActiveIndexChange(Math.max(0, activeIndex - 1))} disabled={activeIndex === 0} title="Previous">
              <span className="explorer-btn-icon" aria-hidden="true">◀</span>
              <span className="explorer-btn-label">Previous</span>
            </button>
            <button
              type="button"
              className="button ghost-button small-button"
              onClick={() => onActiveIndexChange(Math.min(items.length - 1, activeIndex + 1))}
              disabled={activeIndex >= items.length - 1}
              title="Next"
            >
              <span className="explorer-btn-icon" aria-hidden="true">▶</span>
              <span className="explorer-btn-label">Next</span>
            </button>
            <button type="button" className="button ghost-button small-button" onClick={() => setShowHelp((v) => !v)} title="Keyboard shortcuts">
              ?
            </button>
            {currentFaceData?.enabled && currentFaceData.items.length ? (
              <button
                type="button"
                className={`button ghost-button small-button ${showFaceBoxes ? "image-toolbar-btn-active" : ""}`}
                onClick={() => setShowFaceBoxes((value) => !value)}
                title="Toggle face boxes"
              >
                Faces
              </button>
            ) : null}
            <button type="button" className="button ghost-button small-button explorer-meta-toggle" onClick={() => setMetaPanelOpen((v) => !v)} title="Toggle info panel">
              <span className="explorer-btn-icon" aria-hidden="true">ℹ</span>
              <span className="explorer-btn-label">{metaPanelOpen ? "Hide" : "Info"}</span>
            </button>
            <button type="button" className="button small-button" onClick={onClose} title="Close">
              <span className="explorer-btn-icon" aria-hidden="true">✕</span>
              <span className="explorer-btn-label">Close</span>
            </button>
          </div>
        </div>

        {/* Keyboard help panel */}
        {showHelp ? (
          <div className="panel" style={{ padding: "0.75rem 1rem", marginBottom: "0.5rem" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.84rem" }}>
              <tbody>
                {[
                  ["← / →  or  ↑ / ↓", "Previous / Next image"],
                  ["Page Up / Page Down", "Jump ±10 images"],
                  ["C", "Copy Danbooru tags"],
                  ["D / W", "Download workflow (if available)"],
                  ["0", "Fit image to viewer"],
                  ["1", "Actual size"],
                  ["?", "Toggle this help panel"],
                  ["Esc", "Close explorer"],
                ].map(([key, desc]) => (
                  <tr key={key} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td style={{ padding: "0.3rem 0.6rem 0.3rem 0", fontFamily: "var(--font-mono)", color: "var(--accent)" }}>{key}</td>
                    <td style={{ padding: "0.3rem 0", color: "var(--muted)" }}>{desc}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}

        <div
          className="explorer-body"
          onTouchStart={(e) => {
            touchRef.current = { x: e.touches[0].clientX, y: e.touches[0].clientY };
          }}
          onTouchEnd={(e) => {
            if (!touchRef.current) return;
            const dx = e.changedTouches[0].clientX - touchRef.current.x;
            const dy = e.changedTouches[0].clientY - touchRef.current.y;
            touchRef.current = null;
            if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 50) {
              if (dx < 0) {
                onActiveIndexChange(Math.min(items.length - 1, activeIndex + 1));
              } else {
                onActiveIndexChange(Math.max(0, activeIndex - 1));
              }
            } else if (dy < -60 && Math.abs(dy) > Math.abs(dx)) {
              setMetaPanelOpen(true);
            } else if (dy > 60 && Math.abs(dy) > Math.abs(dx)) {
              setMetaPanelOpen(false);
            }
          }}
          onDoubleClick={(e) => {
            (viewerRef.current as any)?.zoomToPoint?.(e.clientX, e.clientY, 2.5);
          }}
        >
          <div className="panel explorer-viewer-panel" ref={viewerContainerRef}>
            {currentItem.contentSrc ? (
              <div style={{ transform: `rotate(${rotation}deg)`, transition: "transform 0.22s ease", height: "100%", width: "100%", position: "relative" }}>
                <MediaDeepZoomStage
                  ref={viewerRef}
                  source={{
                    previewSrc: currentItem.previewSrc ?? currentItem.contentSrc ?? null,
                    fullSrc: currentItem.contentSrc ?? currentItem.previewSrc ?? null,
                    deepzoomUrl: currentItem.deepzoomUrl ?? null,
                  }}
                  alt={currentItem.title}
                  defaultMode={zoomMode}
                  navigatorVisible={navigatorVisible}
                  onScalePercentChange={setScalePercent}
                  onSourceReady={() => {
                    if (!forceFitOnNextSourceRef.current) {
                      return;
                    }
                    forceFitOnNextSourceRef.current = false;
                    viewerRef.current?.fit();
                    setZoomMode("fit");
                  }}
                  overlays={currentOverlays}
                />
              </div>
            ) : (
              <div className="explorer-viewer-empty">No image available.</div>
            )}
            {/* Floating compact toolbar */}
            <div
              className={`explorer-floating-toolbar ${toolbarVisible ? '' : 'explorer-floating-toolbar-hidden'}`}
              onMouseEnter={() => setToolbarVisible(true)}
            >
              <button type="button" className={`image-toolbar-btn ${zoomMode === 'fit' ? 'image-toolbar-btn-active' : ''}`} title="Fit" onClick={() => { viewerRef.current?.fit(); setZoomMode("fit"); }}>⊞</button>
              <button type="button" className="image-toolbar-btn" title="Zoom out" onClick={() => { viewerRef.current?.zoomOut(); setZoomMode("native"); }}>−</button>
              <span className="explorer-toolbar-scale">{scalePercent}%</span>
              <button type="button" className="image-toolbar-btn" title="Zoom in" onClick={() => { viewerRef.current?.zoomIn(); setZoomMode("native"); }}>+</button>
              <span className="explorer-toolbar-sep" />
              <button type="button" className={`image-toolbar-btn ${zoomMode === 'native' && scalePercent === 100 ? 'image-toolbar-btn-active' : ''}`} title="Actual size (100%)" onClick={() => { viewerRef.current?.actualSize(); setZoomMode("native"); }}>1</button>
              <button type="button" className="image-toolbar-btn" title={copied ? 'Copied!' : 'Copy image'} onClick={handleCopyImage} disabled={!currentItem.contentSrc}>{copied ? '✓' : '⧉'}</button>
              <button type="button" className="image-toolbar-btn" title="Open original" onClick={handleOpenOriginal} disabled={!currentItem.contentSrc}>↗</button>
              <button type="button" className="image-toolbar-btn" title="Fullscreen" onClick={handleFullscreen}>⤢</button>
              <button type="button" className="image-toolbar-btn" title={`Rotate (${rotation}°)`} onClick={() => setRotation((r) => (r + 90) % 360)}>↻</button>
              <button
                type="button"
                className={`image-toolbar-btn ${navigatorVisible ? 'image-toolbar-btn-active' : ''}`}
                title="Toggle navigator"
                onClick={() => {
                  const next = !navigatorVisible;
                  setNavigatorVisible(next);
                  viewerRef.current?.toggleNavigator(next);
                }}
              >🗺</button>
            </div>
          </div>
          <aside className={`panel stack explorer-inspector ${metaPanelOpen ? "explorer-inspector-open" : ""}`}>
            <div className="row-between">
              <div>
                <p className="eyebrow">Inspector</p>
                <h3>{currentItem.title}</h3>
              </div>
              {currentItem.statusBadge ? <span className="pill">{currentItem.statusBadge}</span> : null}
            </div>
            {currentItem.sourceContext ? <p className="subdued">{currentItem.sourceContext}</p> : null}
            {currentItem.promptExcerpt ? (
              <div className="stack">
                <strong>Prompt</strong>
                <p className="subdued">{currentItem.promptExcerpt}</p>
              </div>
            ) : null}
            {currentItem.promptTags.length ? (
              <div className="stack">
                <strong>Tags</strong>
                <div className="chip-row">
                  {currentItem.promptTags.map((tag) => (
                    <TagFilterChip key={`${currentItem.key}-${tag}`} tag={tag} prompt className="chip chip-prompt buttonless" />
                  ))}
                </div>
              </div>
            ) : null}
            {currentItem.metadataSummary?.length ? (
              <div className="metadata-grid explorer-metadata-grid">
                {currentItem.metadataSummary.map((entry) => (
                  <div key={`${currentItem.key}-${entry.label}`} className="metadata-row">
                    <strong>{entry.label}</strong>
                    <div className="subdued">{entry.value}</div>
                  </div>
                ))}
              </div>
            ) : null}
            {currentFaceData?.items.length ? (
              <div className="stack">
                <strong>Detected Faces</strong>
                <div className="similarity-scroll">
                  {currentFaceData.items.map((face) => (
                    <div key={face.id} className="panel" style={{ minWidth: "132px", padding: "0.45rem" }}>
                      {face.crop_preview_url ? (
                        <img
                          src={mediaUrl(face.crop_preview_url)}
                          alt={face.person?.name ?? "Face crop"}
                          style={{ width: "120px", height: "120px", objectFit: "cover", borderRadius: "0.8rem" }}
                        />
                      ) : null}
                      <div style={{ marginTop: "0.35rem" }}>
                        <strong>{face.person?.name ?? "Unnamed person"}</strong>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
            {renderActions ? <div className="stack">{renderActions(currentItem)}</div> : null}
            <div className="card-actions">
              {currentItem.detailHref ? (
                <Link href={currentItem.detailHref} className="button subtle-button small-button">
                  Open Detail
                </Link>
              ) : null}
              {currentItem.similarHref ? (
                <Link href={currentItem.similarHref} className="button ghost-button small-button">
                  Open Similar
                </Link>
              ) : null}
            </div>
          </aside>
        </div>
        <div className="explorer-filmstrip" ref={filmstripRef}>
          {items.map((item, index) => (
            <button
              key={item.key}
              type="button"
              className={`explorer-filmstrip-item ${index === activeIndex ? "explorer-filmstrip-item-active" : ""}`}
              onClick={() => onActiveIndexChange(index)}
            >
              {item.previewSrc ? <img src={item.previewSrc} alt={item.title} loading="lazy" /> : <span>{item.title}</span>}
            </button>
          ))}
        </div>
      </section>
    </>
  );
}
