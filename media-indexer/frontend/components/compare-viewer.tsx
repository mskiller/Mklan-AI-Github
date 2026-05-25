"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { mediaUrl } from "@/lib/api";
import { metadataLabel, promptTagsFromMetadata } from "@/lib/asset-metadata";
import { CompareResponse } from "@/lib/types";
import {
  DeepZoomViewportState,
  MediaDeepZoomStage,
  MediaDeepZoomViewerHandle,
} from "@/components/media-deep-zoom-viewer";
import { TagFilterChip } from "@/components/tag-filter-chip";

const DEFAULT_VIEWPORT: DeepZoomViewportState = {
  imageZoom: 1,
  centerX: 0.5,
  centerY: 0.5,
};

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

export function CompareViewer({ comparison }: { comparison: CompareResponse }) {
  const leftViewerRef = useRef<MediaDeepZoomViewerHandle | null>(null);
  const rightViewerRef = useRef<MediaDeepZoomViewerHandle | null>(null);
  const overlayBaseRef = useRef<MediaDeepZoomViewerHandle | null>(null);
  const [sharedZoom, setSharedZoom] = useState(DEFAULT_VIEWPORT.imageZoom);
  const [splitCenters, setSplitCenters] = useState<Record<"left" | "right", Pick<DeepZoomViewportState, "centerX" | "centerY">>>({
    left: { centerX: 0.5, centerY: 0.5 },
    right: { centerX: 0.5, centerY: 0.5 },
  });
  const [overlayViewport, setOverlayViewport] = useState<DeepZoomViewportState>(DEFAULT_VIEWPORT);
  const [scalePercent, setScalePercent] = useState(100);
  const [syncPan, setSyncPan] = useState(false);
  const [swapSides, setSwapSides] = useState(false);
  const [showPromptDiff, setShowPromptDiff] = useState(true);
  const [viewMode, setViewMode] = useState<"overlay" | "split">("overlay");
  const [overlaySplit, setOverlaySplit] = useState(50);
  const [navigatorVisible, setNavigatorVisible] = useState(true);
  const [peekMode, setPeekMode] = useState<"base" | null>(null);

  const panes = swapSides
    ? [
        { key: "left" as const, asset: comparison.asset_b },
        { key: "right" as const, asset: comparison.asset_a },
      ]
    : [
        { key: "left" as const, asset: comparison.asset_a },
        { key: "right" as const, asset: comparison.asset_b },
      ];
  const leftOnlyPromptTags = swapSides ? comparison.right_only_prompt_tags : comparison.left_only_prompt_tags;
  const rightOnlyPromptTags = swapSides ? comparison.left_only_prompt_tags : comparison.right_only_prompt_tags;
  const leftAsset = panes[0].asset;
  const rightAsset = panes[1].asset;
  const overlayClipPercent = peekMode === "base" ? 100 : overlaySplit;
  const splitViewportLeft: DeepZoomViewportState = useMemo(
    () => ({ imageZoom: sharedZoom, ...splitCenters.left }),
    [sharedZoom, splitCenters.left]
  );
  const splitViewportRight: DeepZoomViewportState = useMemo(
    () => ({ imageZoom: sharedZoom, ...(syncPan ? splitCenters.left : splitCenters.right) }),
    [sharedZoom, splitCenters.left, splitCenters.right, syncPan]
  );

  useEffect(() => {
    setNavigatorVisible(
      typeof window === "undefined" || typeof window.matchMedia !== "function"
        ? true
        : !window.matchMedia("(max-width: 900px), (pointer: coarse)").matches
    );
  }, []);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === " ") {
        setPeekMode("base");
      }
      if (event.key === "0") {
        event.preventDefault();
        if (viewMode === "overlay") {
          overlayBaseRef.current?.fit();
        } else {
          leftViewerRef.current?.fit();
          rightViewerRef.current?.fit();
        }
      }
      if (event.key === "1") {
        event.preventDefault();
        if (viewMode === "overlay") {
          overlayBaseRef.current?.actualSize();
        } else {
          leftViewerRef.current?.actualSize();
          rightViewerRef.current?.actualSize();
        }
      }
    };
    const handleKeyUp = (event: KeyboardEvent) => {
      if (event.key === " ") {
        setPeekMode(null);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
    };
  }, [viewMode]);

  const resetView = () => {
    setSharedZoom(1);
    setSplitCenters({
      left: { centerX: 0.5, centerY: 0.5 },
      right: { centerX: 0.5, centerY: 0.5 },
    });
    setOverlayViewport(DEFAULT_VIEWPORT);
    if (viewMode === "overlay") {
      overlayBaseRef.current?.fit();
    } else {
      leftViewerRef.current?.fit();
      rightViewerRef.current?.fit();
    }
  };

  const updateSplitViewport = (key: "left" | "right", next: DeepZoomViewportState) => {
    setSharedZoom(next.imageZoom);
    setScalePercent(Math.max(1, Math.round(next.imageZoom * 100)));
    setSplitCenters((current) => {
      if (syncPan) {
        return {
          left: { centerX: next.centerX, centerY: next.centerY },
          right: { centerX: next.centerX, centerY: next.centerY },
        };
      }
      return {
        ...current,
        [key]: { centerX: next.centerX, centerY: next.centerY },
      };
    });
  };

  return (
    <div className="compare-layout">
      <div className="compare-toolbar panel">
        <div className="compare-toolbar-actions">
          <button
            type="button"
            className={`button small-button ${viewMode === "overlay" ? "" : "ghost-button"}`}
            onClick={() => setViewMode("overlay")}
          >
            Overlay
          </button>
          <button
            type="button"
            className={`button small-button ${viewMode === "split" ? "" : "ghost-button"}`}
            onClick={() => setViewMode("split")}
          >
            Side by Side
          </button>
          <button
            type="button"
            className="button subtle-button"
            onClick={() => {
              if (viewMode === "overlay") {
                overlayBaseRef.current?.zoomOut();
              } else {
                leftViewerRef.current?.zoomOut();
                rightViewerRef.current?.zoomOut();
              }
            }}
          >
            Zoom Out
          </button>
          <button type="button" className="button ghost-button small-button" onClick={resetView}>
            Fit
          </button>
          {viewMode === "split" ? (
            <button type="button" className={`button small-button ${syncPan ? "" : "ghost-button"}`} onClick={() => setSyncPan((value) => !value)}>
              {syncPan ? "Sync Pan On" : "Sync Pan Off"}
            </button>
          ) : null}
          <button
            type="button"
            className={`button small-button ${navigatorVisible ? "" : "ghost-button"}`}
            onClick={() => setNavigatorVisible((value) => !value)}
          >
            Navigator
          </button>
          <button type="button" className="button ghost-button small-button" onClick={() => setSwapSides((value) => !value)}>
            Swap Sides
          </button>
          <button
            type="button"
            className="button ghost-button small-button"
            onClick={() => {
              if (viewMode === "overlay") {
                overlayBaseRef.current?.actualSize();
              } else {
                leftViewerRef.current?.actualSize();
                rightViewerRef.current?.actualSize();
              }
            }}
          >
            100%
          </button>
          <button type="button" className={`button small-button ${showPromptDiff ? "" : "ghost-button"}`} onClick={() => setShowPromptDiff((value) => !value)}>
            {showPromptDiff ? "Hide Prompt Diff" : "Show Prompt Diff"}
          </button>
          <button
            type="button"
            className="button ghost-button small-button"
            onPointerDown={() => setPeekMode("base")}
            onPointerUp={() => setPeekMode(null)}
            onPointerLeave={() => setPeekMode(null)}
            onPointerCancel={() => setPeekMode(null)}
          >
            Hold A/B Peek
          </button>
          <button
            type="button"
            className="button subtle-button"
            onClick={() => {
              if (viewMode === "overlay") {
                overlayBaseRef.current?.zoomIn();
              } else {
                leftViewerRef.current?.zoomIn();
                rightViewerRef.current?.zoomIn();
              }
            }}
          >
            Zoom In
          </button>
          <span className="pill">{scalePercent}%</span>
        </div>
        <p className="subdued">
          pHash distance: {comparison.phash_distance ?? "n/a"} · semantic similarity:{" "}
          {comparison.semantic_similarity !== null ? comparison.semantic_similarity.toFixed(3) : "n/a"}
          {" "}· shared prompt tags: {comparison.prompt_tag_overlap}
        </p>
      </div>
      {viewMode === "overlay" ? (
        <section className="compare-pane compare-overlay-panel panel">
          <div className="compare-pane-header">
            <div>
              <h3>{leftAsset.filename}</h3>
              <p className="subdued">
                Left side · {metadataLabel(leftAsset.normalized_metadata.width)} x {metadataLabel(leftAsset.normalized_metadata.height)}
              </p>
            </div>
            <span className="pill">vs</span>
            <div className="compare-pane-meta-right">
              <h3>{rightAsset.filename}</h3>
              <p className="subdued">
                Right side · {metadataLabel(rightAsset.normalized_metadata.width)} x {metadataLabel(rightAsset.normalized_metadata.height)}
              </p>
            </div>
          </div>
          <div className="compare-image-frame compare-image-frame-overlay compare-deepzoom-overlay">
            <MediaDeepZoomStage
              ref={overlayBaseRef}
              className="compare-deepzoom-stage compare-deepzoom-stage-base"
              source={{
                previewSrc: mediaUrl(leftAsset.preview_url) ?? mediaUrl(leftAsset.content_url),
                fullSrc: mediaUrl(leftAsset.content_url),
                deepzoomUrl: mediaUrl(leftAsset.deepzoom_url),
              }}
              alt={leftAsset.filename}
              navigatorVisible={navigatorVisible}
              syncedViewportState={overlayViewport}
              onScalePercentChange={setScalePercent}
              onViewportStateChange={(next) => {
                setOverlayViewport(next);
                setScalePercent(Math.max(1, Math.round(next.imageZoom * 100)));
              }}
            />
            <div className="compare-overlay-top-layer" style={{ clipPath: `inset(0 0 0 ${overlayClipPercent}%)` }}>
              <MediaDeepZoomStage
                source={{
                  previewSrc: mediaUrl(rightAsset.preview_url) ?? mediaUrl(rightAsset.content_url),
                  fullSrc: mediaUrl(rightAsset.content_url),
                  deepzoomUrl: mediaUrl(rightAsset.deepzoom_url),
                }}
                alt={rightAsset.filename}
                navigatorVisible={false}
                interactionsEnabled={false}
                syncedViewportState={overlayViewport}
              />
            </div>
            <div className="compare-overlay-slider-line" style={{ left: `${overlayClipPercent}%` }}>
              <button
                type="button"
                className="compare-overlay-slider-handle"
                aria-label="Adjust overlay split"
                onPointerDown={(event) => {
                  const container = event.currentTarget.closest(".compare-image-frame");
                  if (!container) {
                    return;
                  }
                  const updatePosition = (clientX: number) => {
                    const rect = (container as HTMLDivElement).getBoundingClientRect();
                    const next = ((clientX - rect.left) / rect.width) * 100;
                    setOverlaySplit(clamp(next, 0, 100));
                  };
                  updatePosition(event.clientX);
                  event.currentTarget.setPointerCapture(event.pointerId);
                  const move = (moveEvent: PointerEvent) => updatePosition(moveEvent.clientX);
                  const up = (upEvent: PointerEvent) => {
                    updatePosition(upEvent.clientX);
                    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
                      event.currentTarget.releasePointerCapture(event.pointerId);
                    }
                    event.currentTarget.removeEventListener("pointermove", move);
                    event.currentTarget.removeEventListener("pointerup", up);
                    event.currentTarget.removeEventListener("pointercancel", cancel);
                  };
                  const cancel = () => {
                    event.currentTarget.removeEventListener("pointermove", move);
                    event.currentTarget.removeEventListener("pointerup", up);
                    event.currentTarget.removeEventListener("pointercancel", cancel);
                  };
                  event.currentTarget.addEventListener("pointermove", move);
                  event.currentTarget.addEventListener("pointerup", up);
                  event.currentTarget.addEventListener("pointercancel", cancel);
                }}
              >
                <span className="compare-overlay-slider-grip" />
              </button>
            </div>
          </div>
          <div className="compare-slider-row">
            <span className="chip chip-prompt">{leftAsset.filename}</span>
            <input
              type="range"
              min={0}
              max={100}
              value={overlaySplit}
              onChange={(event) => setOverlaySplit(Number(event.target.value))}
              className="compare-slider"
            />
            <span className="chip chip-accent">{rightAsset.filename}</span>
          </div>
          <div className="compare-overlay-details">
            <div className="chip-row">
              {promptTagsFromMetadata(leftAsset.normalized_metadata, 5).map((tag) => (
                <TagFilterChip key={`${leftAsset.id}-${tag}`} tag={tag} prompt className="chip chip-prompt buttonless" />
              ))}
            </div>
            <div className="chip-row compare-overlay-chip-row-right">
              {promptTagsFromMetadata(rightAsset.normalized_metadata, 5).map((tag) => (
                <TagFilterChip key={`${rightAsset.id}-${tag}`} tag={tag} prompt className="chip chip-accent buttonless" />
              ))}
            </div>
          </div>
        </section>
      ) : (
        <div className="compare-stage">
          {panes.map(({ key, asset }) => (
            <div
              key={asset.id}
              className="compare-pane panel"
            >
              <div className="compare-pane-header">
                <div>
                  <h3>{asset.filename}</h3>
                  <p className="subdued">
                    {metadataLabel(asset.normalized_metadata.width)} x {metadataLabel(asset.normalized_metadata.height)}
                  </p>
                </div>
              </div>
              <div className="compare-image-frame">
                <MediaDeepZoomStage
                  ref={key === "left" ? leftViewerRef : rightViewerRef}
                  source={{
                    previewSrc: mediaUrl(asset.preview_url) ?? mediaUrl(asset.content_url),
                    fullSrc: mediaUrl(asset.content_url),
                    deepzoomUrl: mediaUrl(asset.deepzoom_url),
                  }}
                  alt={asset.filename}
                  navigatorVisible={navigatorVisible}
                  syncedViewportState={key === "left" ? splitViewportLeft : splitViewportRight}
                  syncPan={key === "right" ? syncPan : true}
                  onScalePercentChange={setScalePercent}
                  onViewportStateChange={(next) => updateSplitViewport(key, next)}
                />
              </div>
              <div className="chip-row">
                {promptTagsFromMetadata(asset.normalized_metadata, 5).map((tag) => (
                  <TagFilterChip key={`${asset.id}-${tag}`} tag={tag} prompt className="chip chip-prompt buttonless" />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
      {showPromptDiff ? (
        <section className="panel stack">
          <div className="row-between">
            <div>
              <p className="eyebrow">Prompt Tags</p>
              <h2>Shared and unique prompt phrases</h2>
            </div>
            <span className="pill">{comparison.prompt_tag_overlap} shared</span>
          </div>
          <div className="metadata-grid">
            <div className="metadata-row">
              <strong>Shared</strong>
              <div className="chip-row compare-chip-row">
                {comparison.shared_prompt_tags.length
                  ? comparison.shared_prompt_tags.map((tag) => (
                      <TagFilterChip key={`shared-${tag}`} tag={tag} className="chip chip-accent buttonless" />
                    ))
                  : <span className="subdued">No shared prompt tags.</span>}
              </div>
            </div>
            <div className="metadata-row">
              <strong>Left Only</strong>
              <div className="chip-row compare-chip-row">
                {leftOnlyPromptTags.length
                  ? leftOnlyPromptTags.map((tag) => (
                      <TagFilterChip key={`left-${tag}`} tag={tag} className="chip buttonless" />
                    ))
                  : <span className="subdued">No left-only prompt tags.</span>}
              </div>
            </div>
            <div className="metadata-row">
              <strong>Right Only</strong>
              <div className="chip-row compare-chip-row">
                {rightOnlyPromptTags.length
                  ? rightOnlyPromptTags.map((tag) => (
                      <TagFilterChip key={`right-${tag}`} tag={tag} className="chip buttonless" />
                    ))
                  : <span className="subdued">No right-only prompt tags.</span>}
              </div>
            </div>
          </div>
        </section>
      ) : null}
    </div>
  );
}
