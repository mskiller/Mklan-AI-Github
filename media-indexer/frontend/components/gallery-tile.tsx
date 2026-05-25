"use client";

import { CSSProperties, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { BlurhashPlaceholder } from "@/components/blurhash-placeholder";
import { TagFilterChip } from "@/components/tag-filter-chip";
import { BottomSheet } from "@/components/BottomSheet";
import { useDeviceMode } from "@/hooks/use-device-mode";

export interface GalleryTileAction {
  label: string;
  onSelect: () => void;
  variant?: "primary" | "subtle" | "ghost" | "danger";
  disabled?: boolean;
}

export function GalleryTile({
  imageSrc,
  blurHash,
  alt,
  title,
  subtitle,
  promptExcerpt,
  promptTags,
  statusBadge,
  selected,
  selectionMode,
  onOpen,
  onInspect,
  onToggleSelect,
  menuActions,
  className = "",
  tileStyle,
  imageButtonStyle,
  onImageLoad,
  workflowAvailable,
}: {
  imageSrc: string | null | undefined;
  blurHash?: string | null;
  alt: string;
  title: string;
  subtitle?: string | null;
  promptExcerpt?: string | null;
  promptTags: string[];
  statusBadge?: string | null;
  selected?: boolean;
  selectionMode?: boolean;
  onOpen: () => void;
  onInspect?: () => void;
  onToggleSelect?: () => void;
  menuActions: GalleryTileAction[];
  className?: string;
  tileStyle?: CSSProperties;
  imageButtonStyle?: CSSProperties;
  onImageLoad?: (size: { width: number; height: number }) => void;
  workflowAvailable?: boolean;
}) {
  const [menuPos, setMenuPos] = useState<{ x: number; y: number } | null>(null);
  const menuOpen = menuPos !== null;
  const [loaded, setLoaded] = useState(false);
  const [isInspecting, setIsInspecting] = useState(false);
  const [bottomSheetOpen, setBottomSheetOpen] = useState(false);
  const longPressTimer = useRef<number | null>(null);
  const longPressTriggered = useRef(false);
  const tileRef = useRef<HTMLElement | null>(null);
  const deviceMode = useDeviceMode();
  const isMobile = deviceMode === "mobile";
  const desktopMenuStyle = (() => {
    if (!menuPos || typeof window === "undefined") {
      return undefined;
    }
    const width = 288;
    const estimatedHeight = Math.min(520, menuActions.length * 38 + 18);
    const left = Math.max(8, Math.min(menuPos.x, window.innerWidth - width - 8));
    const top = Math.max(8, Math.min(menuPos.y, window.innerHeight - estimatedHeight - 8));
    return {
      left,
      top,
      width,
      maxHeight: `calc(100vh - ${top + 8}px)`,
    } satisfies CSSProperties;
  })();

  useEffect(() => {
    setLoaded(false);
  }, [imageSrc]);

  useEffect(() => {
    if (!menuOpen) {
      return;
    }
    const handlePointerDown = (event: PointerEvent) => {
      // Don't close if clicking inside the tile itself
      if (tileRef.current?.contains(event.target as Node)) {
        return;
      }
      // Don't close if clicking inside the context menu portal
      if ((event.target as Element).closest?.(".gallery-context-menu")) {
        return;
      }
      setMenuPos(null);
    };
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [menuOpen]);

  const triggerInspect = () => {
    onInspect?.();
  };

  const triggerMenuAction = (action: GalleryTileAction) => {
    if (action.disabled) {
      return;
    }
    setMenuPos(null);
    setBottomSheetOpen(false);
    action.onSelect();
  };

  return (
    <article
      ref={tileRef}
      className={`gallery-tile ${selected ? "gallery-tile-selected" : ""} ${className}`.trim()}
      style={tileStyle}
      data-inspecting={isInspecting || menuOpen ? "true" : undefined}
      onMouseEnter={() => {
        setIsInspecting(true);
        triggerInspect();
      }}
      onMouseLeave={() => setIsInspecting(false)}
      onContextMenu={(event) => {
        event.preventDefault();
        triggerInspect();
        setMenuPos({ x: event.clientX, y: event.clientY });
      }}
    >
      {statusBadge ? <span className="gallery-status-badge">{statusBadge}</span> : null}
      {onToggleSelect ? (
        <button
          type="button"
          className={`gallery-select-badge ${selected ? "gallery-select-badge-selected" : ""} ${selectionMode ? "gallery-select-badge-visible" : ""}`}
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            onToggleSelect();
          }}
        >
          {selected ? "Selected" : "Select"}
        </button>
      ) : null}
      <div className="gallery-image-shell">
        <button
          type="button"
          className="gallery-image-button"
          style={imageButtonStyle}
          onClick={(event) => {
            if (longPressTriggered.current) {
              longPressTriggered.current = false;
              event.preventDefault();
              return;
            }
            if ((event.ctrlKey || event.metaKey || selectionMode) && onToggleSelect) {
              event.preventDefault();
              onToggleSelect();
              return;
            }
            onOpen();
          }}
          onTouchStart={(event) => {
            // Do NOT call triggerInspect() here — that blocks tap-to-open on mobile
            longPressTriggered.current = false;
            if (longPressTimer.current) {
              window.clearTimeout(longPressTimer.current);
            }
            const touch = event.touches[0];
            longPressTimer.current = window.setTimeout(() => {
              longPressTriggered.current = true;
              triggerInspect();
              if (isMobile) {
                setBottomSheetOpen(true);
              } else {
                setMenuPos({ x: touch.clientX, y: touch.clientY });
              }
            }, 420);
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
        >
          {imageSrc ? (
            <>
              {!loaded && blurHash ? (
                <BlurhashPlaceholder hash={blurHash} className="gallery-blurhash" />
              ) : null}
              {!loaded && !blurHash ? (
                <div className="gallery-blurhash-missing" />
              ) : null}
              <img
                src={imageSrc}
                alt={alt}
                loading="lazy"
                className={!loaded ? "gallery-img-loading" : ""}
                style={{ opacity: loaded ? 1 : 0 }}
                onLoad={(event) => {
                  setLoaded(true);
                  onImageLoad?.({
                    width: event.currentTarget.naturalWidth,
                    height: event.currentTarget.naturalHeight,
                  });
                }}
              />
            </>
          ) : (
            <div className="asset-placeholder">image</div>
          )}
        </button>
        {workflowAvailable && (
          <span
            className="gallery-workflow-badge"
            title="Workflow embedded"
            aria-label="Workflow available"
          >
            ⚡
          </span>
        )}
        {/* Lightweight overlay — filename + badge + max 3 tags; pointer-events: none always */}
        <div className={`gallery-overlay ${menuOpen ? "gallery-overlay-visible" : ""}`}>
          <div className="gallery-overlay-top">
            <strong>{title}</strong>
            {subtitle ? <span>{subtitle}</span> : null}
          </div>
          {promptTags.length ? (
            <div className="chip-row gallery-overlay-tags">
              {promptTags.slice(0, 3).map((tag) => (
                <TagFilterChip key={tag} tag={tag} prompt className="chip chip-prompt buttonless" />
              ))}
            </div>
          ) : null}
        </div>
      </div>

      {/* Mobile: slide-up bottom sheet on long-press */}
      {isMobile ? (
        <BottomSheet open={bottomSheetOpen} onClose={() => setBottomSheetOpen(false)} title={title} subtitle={subtitle}>
          <div className="stack">
            {menuActions.map((action) => (
              <button
                key={action.label}
                type="button"
                className={`button small-button ${
                  action.variant === "subtle"
                    ? "subtle-button"
                    : action.variant === "ghost"
                      ? "ghost-button"
                      : action.variant === "danger"
                        ? "danger-button"
                        : ""
                }`.trim()}
                disabled={action.disabled}
                onClick={() => triggerMenuAction(action)}
              >
                {action.label}
              </button>
            ))}
          </div>
        </BottomSheet>
      ) : null}

      {/* Desktop: portal context menu on right-click */}
      {!isMobile && menuOpen && menuPos && typeof document !== "undefined"
        ? createPortal(
            <div
              className="gallery-context-menu gallery-context-menu-desktop gallery-context-menu-open"
              role="menu"
              style={desktopMenuStyle}
            >
              {menuActions.map((action) => (
                <button
                  key={action.label}
                  type="button"
                  className="button context-action-btn"
                  disabled={action.disabled}
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    triggerMenuAction(action);
                  }}
                >
                  {action.label}
                </button>
              ))}
            </div>,
            document.body
          )
        : null}
    </article>
  );
}
