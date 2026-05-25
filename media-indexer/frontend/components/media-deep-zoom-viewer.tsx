"use client";

import { type ReactNode, forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function isMobileViewport() {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  return window.matchMedia("(max-width: 900px), (pointer: coarse)").matches;
}

export interface DeepZoomViewportState {
  imageZoom: number;
  centerX: number;
  centerY: number;
}

export interface MediaDeepZoomViewerHandle {
  fit: () => void;
  actualSize: () => void;
  zoomIn: () => void;
  zoomOut: () => void;
  toggleNavigator: (visible?: boolean) => void;
  getViewer: () => any;
}

export interface MediaDeepZoomSource {
  previewSrc?: string | null;
  fullSrc?: string | null;
  deepzoomUrl?: string | null;
}

export interface DeepZoomOverlay {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  label?: string | null;
}

function readViewportState(viewer: any): DeepZoomViewportState | null {
  const item = viewer?.world?.getItemAt?.(0);
  if (!item || !viewer?.viewport) {
    return null;
  }
  const size = item.getContentSize?.();
  if (!size?.x || !size?.y) {
    return null;
  }
  const center = viewer.viewport.viewportToImageCoordinates(viewer.viewport.getCenter(true));
  return {
    imageZoom: viewer.viewport.viewportToImageZoom(viewer.viewport.getZoom(true)),
    centerX: clamp(center.x / size.x, 0, 1),
    centerY: clamp(center.y / size.y, 0, 1),
  };
}

function setNavigatorVisibility(viewer: any, visible: boolean) {
  if (!viewer?.navigator) {
    return;
  }
  if (typeof viewer.navigator.setVisible === "function") {
    viewer.navigator.setVisible(visible);
    return;
  }
  if (viewer.navigator.element) {
    viewer.navigator.element.style.display = visible ? "" : "none";
  }
}

function applyViewportState(viewer: any, state: DeepZoomViewportState, syncPan = true) {
  const item = viewer?.world?.getItemAt?.(0);
  if (!item || !viewer?.viewport) {
    return;
  }
  const size = item.getContentSize?.();
  if (!size?.x || !size?.y) {
    return;
  }
  const viewportZoom = viewer.viewport.imageToViewportZoom(Math.max(0.01, state.imageZoom));
  viewer.viewport.zoomTo(viewportZoom, undefined, true);
  if (syncPan) {
    const targetPoint = viewer.viewport.imageToViewportCoordinates(size.x * state.centerX, size.y * state.centerY);
    viewer.viewport.panTo(targetPoint, true);
  }
}

function fitViewer(viewer: any) {
  viewer?.viewport?.goHome?.(true);
}

function actualSizeViewer(viewer: any) {
  if (!viewer?.viewport) {
    return;
  }
  const homeBounds = viewer.viewport.getHomeBounds?.();
  const homeCenter = typeof homeBounds?.getCenter === "function" ? homeBounds.getCenter() : undefined;
  if (homeCenter) {
    viewer.viewport.panTo(homeCenter, true);
  }
  viewer.viewport.zoomTo(viewer.viewport.imageToViewportZoom(1), undefined, true);
}

function currentScalePercent(viewer: any) {
  if (!viewer?.viewport) {
    return 100;
  }
  return Math.max(1, Math.round(viewer.viewport.viewportToImageZoom(viewer.viewport.getZoom(true)) * 100));
}

export const MediaDeepZoomStage = forwardRef<
  MediaDeepZoomViewerHandle,
  {
    source: MediaDeepZoomSource;
    alt: string;
    className?: string;
    navigatorVisible?: boolean;
    interactionsEnabled?: boolean;
    defaultMode?: "auto" | "native" | "fit";
    syncedViewportState?: DeepZoomViewportState | null;
    syncPan?: boolean;
    onScalePercentChange?: (value: number) => void;
    onViewportStateChange?: (state: DeepZoomViewportState) => void;
    onSourceReady?: () => void;
    children?: ReactNode;
    overlays?: DeepZoomOverlay[];
  }
>(
  (
    {
      source,
      alt,
      className = "",
      navigatorVisible = true,
      interactionsEnabled = true,
      defaultMode = "auto",
      syncedViewportState = null,
      syncPan = true,
      onScalePercentChange,
      onViewportStateChange,
      onSourceReady,
      children,
      overlays = [],
    },
    ref
  ) => {
    const containerRef = useRef<HTMLDivElement | null>(null);
    const viewerRef = useRef<any>(null);
    const currentSourceTokenRef = useRef(0);
    const pendingRestoreStateRef = useRef<{ token: number; state: DeepZoomViewportState } | null>(null);
    const emitFrameRef = useRef<number | null>(null);
    const overlayElementsRef = useRef<HTMLElement[]>([]);
    const syncSuppressRef = useRef(false);
    const previousSourceKeyRef = useRef("");
    const lastInteractionModeRef = useRef<"fit" | "native" | null>(null);
    const lastAppliedExternalRef = useRef<DeepZoomViewportState | null>(null);
    const navigatorVisibleRef = useRef(navigatorVisible);
    const [ready, setReady] = useState(false);

    const defaultModeRef = useRef(defaultMode);
    useEffect(() => {
      defaultModeRef.current = defaultMode;
    }, [defaultMode]);

    const sourceKey = useMemo(
      () => [source.deepzoomUrl ?? "", source.previewSrc ?? "", source.fullSrc ?? ""].join("|"),
      [source.deepzoomUrl, source.previewSrc, source.fullSrc]
    );
    const overlaysKey = useMemo(() => JSON.stringify(overlays), [overlays]);

    const clearOverlays = (viewer: any) => {
      for (const element of overlayElementsRef.current) {
        try {
          viewer?.removeOverlay?.(element);
        } catch {}
      }
      overlayElementsRef.current = [];
    };

    const renderOverlays = (viewer: any) => {
      clearOverlays(viewer);
      if (!overlays.length) {
        return;
      }
      const item = viewer?.world?.getItemAt?.(0);
      if (!item || !viewer?.viewport) {
        return;
      }
      for (const overlay of overlays) {
        const element = document.createElement("div");
        element.style.border = "2px solid rgba(255, 94, 91, 0.95)";
        element.style.borderRadius = "12px";
        element.style.boxShadow = "0 0 0 1px rgba(16, 18, 24, 0.45)";
        element.style.background = "rgba(255, 94, 91, 0.06)";
        element.style.pointerEvents = "none";
        element.style.position = "relative";
        if (overlay.label) {
          const badge = document.createElement("span");
          badge.textContent = overlay.label;
          badge.style.position = "absolute";
          badge.style.top = "-1.6rem";
          badge.style.left = "0";
          badge.style.padding = "0.2rem 0.45rem";
          badge.style.borderRadius = "999px";
          badge.style.background = "rgba(255, 94, 91, 0.96)";
          badge.style.color = "#fff";
          badge.style.fontSize = "0.72rem";
          badge.style.whiteSpace = "nowrap";
          badge.style.fontWeight = "600";
          element.appendChild(badge);
        }
        viewer.addOverlay({
          element,
          location: viewer.viewport.imageToViewportRectangle(overlay.x, overlay.y, overlay.width, overlay.height),
        });
        overlayElementsRef.current.push(element);
      }
    };

    const emitViewerState = () => {
      const viewer = viewerRef.current;
      if (!viewer) {
        return;
      }
      const scalePercent = currentScalePercent(viewer);
      onScalePercentChange?.(scalePercent);
      if (syncSuppressRef.current) {
        return;
      }
      const state = readViewportState(viewer);
      if (state) {
        onViewportStateChange?.(state);
      }
    };

    const scheduleEmitViewerState = () => {
      if (emitFrameRef.current !== null) {
        return;
      }
      emitFrameRef.current = window.requestAnimationFrame(() => {
        emitFrameRef.current = null;
        emitViewerState();
      });
    };

    const applyDefaultMode = (viewer: any) => {
      const mode = defaultModeRef.current;
      const resolvedMode = mode === "auto" ? (isMobileViewport() ? "fit" : "native") : mode;
      if (resolvedMode === "native") {
        actualSizeViewer(viewer);
        lastInteractionModeRef.current = "native";
      } else {
        fitViewer(viewer);
        lastInteractionModeRef.current = "fit";
      }
    };

    const toggleFitActual = () => {
      const viewer = viewerRef.current;
      if (!viewer) {
        return;
      }
      if (lastInteractionModeRef.current === "native") {
        fitViewer(viewer);
        lastInteractionModeRef.current = "fit";
      } else {
        actualSizeViewer(viewer);
        lastInteractionModeRef.current = "native";
      }
      scheduleEmitViewerState();
    };

    useImperativeHandle(
      ref,
      () => ({
        fit: () => {
          const viewer = viewerRef.current;
          if (!viewer) {
            return;
          }
          fitViewer(viewer);
          lastInteractionModeRef.current = "fit";
          scheduleEmitViewerState();
        },
        actualSize: () => {
          const viewer = viewerRef.current;
          if (!viewer) {
            return;
          }
          actualSizeViewer(viewer);
          lastInteractionModeRef.current = "native";
          scheduleEmitViewerState();
        },
        zoomIn: () => {
          const viewer = viewerRef.current;
          viewer?.viewport?.zoomBy?.(1.2);
          viewer?.viewport?.applyConstraints?.();
          lastInteractionModeRef.current = null;
          scheduleEmitViewerState();
        },
        zoomOut: () => {
          const viewer = viewerRef.current;
          viewer?.viewport?.zoomBy?.(1 / 1.2);
          viewer?.viewport?.applyConstraints?.();
          lastInteractionModeRef.current = null;
          scheduleEmitViewerState();
        },
        toggleNavigator: (visible?: boolean) => {
          const viewer = viewerRef.current;
          if (!viewer) {
            return;
          }
          const nextVisible = visible ?? !navigatorVisibleRef.current;
          navigatorVisibleRef.current = nextVisible;
          setNavigatorVisibility(viewer, nextVisible);
        },
        getViewer: () => viewerRef.current,
      }),
      []
    );

    useEffect(() => {
      navigatorVisibleRef.current = navigatorVisible;
      if (viewerRef.current) {
        setNavigatorVisibility(viewerRef.current, navigatorVisible);
      }
    }, [navigatorVisible]);

    useEffect(() => {
      if (!ready || !viewerRef.current) {
        return;
      }
      viewerRef.current.setMouseNavEnabled(Boolean(interactionsEnabled));
    }, [interactionsEnabled, ready]);

    useEffect(() => {
      let active = true;

      const init = async () => {
        if (!containerRef.current) {
          return;
        }
        const module = await import("openseadragon");
        if (!active || !containerRef.current) {
          return;
        }
        const OpenSeadragon = module.default ?? module;
        const viewer = OpenSeadragon({
          element: containerRef.current,
          showNavigator: true,
          showNavigationControl: false,
          showHomeControl: false,
          showZoomControl: false,
          showFullPageControl: false,
          showRotationControl: false,
          showReferenceStrip: false,
          animationTime: 0.25,
          blendTime: 0.08,
          constrainDuringPan: true,
          visibilityRatio: 1,
          springStiffness: 8,
          maxZoomPixelRatio: 3.5,
          minZoomImageRatio: 0.1, // Allow fitting large images
          gestureSettingsMouse: {
            clickToZoom: false,
            dblClickToZoom: false,
            scrollToZoom: true,
            pinchToZoom: true,
            flickEnabled: true,
          },
          gestureSettingsTouch: {
            clickToZoom: false,
            dblClickToZoom: false,
            pinchToZoom: true,
            flickEnabled: true,
          },
        });
        viewerRef.current = viewer;
        setNavigatorVisibility(viewer, navigatorVisibleRef.current);
        viewer.setMouseNavEnabled(Boolean(interactionsEnabled));

        viewer.addHandler("open", () => {
          const pendingRestore = pendingRestoreStateRef.current;
          if (pendingRestore && pendingRestore.token === currentSourceTokenRef.current) {
            syncSuppressRef.current = true;
            applyViewportState(viewer, pendingRestore.state, true);
            pendingRestoreStateRef.current = null;
            window.requestAnimationFrame(() => {
              syncSuppressRef.current = false;
              scheduleEmitViewerState();
            });
          } else {
            // Use requestAnimationFrame to ensure the container size is settled
            window.requestAnimationFrame(() => {
              applyDefaultMode(viewer);
              scheduleEmitViewerState();
            });
          }
          onSourceReady?.();
        });
        viewer.addHandler("animation", scheduleEmitViewerState);
        viewer.addHandler("resize", scheduleEmitViewerState);
        viewer.addHandler("canvas-double-click", (event: any) => {
          event.preventDefaultAction = true;
          toggleFitActual();
        });
        viewer.addHandler("canvas-drag", () => {
          lastInteractionModeRef.current = null;
        });
        viewer.addHandler("canvas-scroll", () => {
          lastInteractionModeRef.current = null;
        });

        setReady(true);
      };

      void init();

      return () => {
        active = false;
        if (emitFrameRef.current !== null) {
          window.cancelAnimationFrame(emitFrameRef.current);
          emitFrameRef.current = null;
        }
        clearOverlays(viewerRef.current);
        viewerRef.current?.destroy?.();
        viewerRef.current = null;
      };
    }, []);

    useEffect(() => {
      const viewer = viewerRef.current;
      if (!ready || !viewer) {
        return;
      }
      if (previousSourceKeyRef.current === sourceKey) {
        return;
      }
      previousSourceKeyRef.current = sourceKey;
      currentSourceTokenRef.current += 1;
      const token = currentSourceTokenRef.current;
      pendingRestoreStateRef.current = null;

      if (!source.deepzoomUrl && !source.previewSrc && !source.fullSrc) {
        viewer.close?.();
        return;
      }

      const openWith = (url: string) => {
        viewer.open({
          type: "image",
          url,
        });
      };

      if (source.deepzoomUrl) {
        viewer.open(source.deepzoomUrl);
        return;
      }

      const initialUrl = source.previewSrc ?? source.fullSrc;
      const fullUrl = source.fullSrc ?? source.previewSrc;
      if (initialUrl) {
        openWith(initialUrl);
      }

      if (initialUrl && fullUrl && initialUrl !== fullUrl) {
        const preloadImage = new Image();
        preloadImage.decoding = "async";
        preloadImage.onload = () => {
          if (currentSourceTokenRef.current !== token || !viewerRef.current) {
            return;
          }
          const currentState = readViewportState(viewerRef.current);
          if (currentState) {
            pendingRestoreStateRef.current = { token, state: currentState };
          }
          openWith(fullUrl);
        };
        preloadImage.src = fullUrl;
      }
    }, [ready, source.deepzoomUrl, source.previewSrc, source.fullSrc, sourceKey]);

    useEffect(() => {
      if (!ready || !viewerRef.current) {
        return;
      }
      const viewer = viewerRef.current;
      const apply = () => renderOverlays(viewer);
      apply();
      viewer.addHandler("open", apply);
      return () => {
        viewer.removeHandler?.("open", apply);
        clearOverlays(viewer);
      };
    }, [ready, overlaysKey, sourceKey]);

    useEffect(() => {
      if (!ready || !viewerRef.current || !syncedViewportState) {
        return;
      }
      const currentState = readViewportState(viewerRef.current);
      const previousExternal = lastAppliedExternalRef.current;
      if (
        previousExternal &&
        Math.abs(previousExternal.imageZoom - syncedViewportState.imageZoom) < 0.0001 &&
        Math.abs(previousExternal.centerX - syncedViewportState.centerX) < 0.0001 &&
        Math.abs(previousExternal.centerY - syncedViewportState.centerY) < 0.0001
      ) {
        return;
      }
      if (
        currentState &&
        Math.abs(currentState.imageZoom - syncedViewportState.imageZoom) < 0.0001 &&
        Math.abs(currentState.centerX - syncedViewportState.centerX) < 0.0001 &&
        Math.abs(currentState.centerY - syncedViewportState.centerY) < 0.0001
      ) {
        return;
      }
      lastAppliedExternalRef.current = syncedViewportState;
      syncSuppressRef.current = true;
      applyViewportState(viewerRef.current, syncedViewportState, syncPan);
      window.requestAnimationFrame(() => {
        syncSuppressRef.current = false;
        scheduleEmitViewerState();
      });
    }, [ready, syncPan, syncedViewportState?.centerX, syncedViewportState?.centerY, syncedViewportState?.imageZoom]);

    return (
      <div className={`deepzoom-stage-shell ${className}`.trim()} aria-label={alt}>
        <div ref={containerRef} className="deepzoom-stage" />
        {children}
      </div>
    );
  }
);

MediaDeepZoomStage.displayName = "MediaDeepZoomStage";

export const MediaDeepZoomViewer = forwardRef<
  MediaDeepZoomViewerHandle,
  {
    source: MediaDeepZoomSource;
    alt: string;
    className?: string;
    defaultMode?: "auto" | "native" | "fit";
    overlays?: DeepZoomOverlay[];
  }
>(({ source, alt, className = "", defaultMode = "auto", overlays = [] }, ref) => {
  const stageRef = useRef<MediaDeepZoomViewerHandle | null>(null);
  const [scalePercent, setScalePercent] = useState(100);
  const [navigatorVisible, setNavigatorVisible] = useState(true);

  useEffect(() => {
    setNavigatorVisible(!isMobileViewport());
  }, []);

  useImperativeHandle(
    ref,
    () => ({
      fit: () => stageRef.current?.fit(),
      actualSize: () => stageRef.current?.actualSize(),
      zoomIn: () => stageRef.current?.zoomIn(),
      zoomOut: () => stageRef.current?.zoomOut(),
      toggleNavigator: (visible?: boolean) => {
        const nextVisible = visible ?? !navigatorVisible;
        setNavigatorVisible(nextVisible);
        stageRef.current?.toggleNavigator(nextVisible);
      },
      getViewer: () => stageRef.current?.getViewer() ?? null,
    }),
    [navigatorVisible]
  );

  return (
    <div className={`zoomable-viewer ${className}`.trim()}>
      <div className="zoomable-toolbar">
        <button type="button" className="button ghost-button small-button" onClick={() => stageRef.current?.fit()}>
          Fit
        </button>
        <button type="button" className="button ghost-button small-button" onClick={() => stageRef.current?.actualSize()}>
          100%
        </button>
        <button type="button" className="button subtle-button small-button" onClick={() => stageRef.current?.zoomOut()}>
          -
        </button>
        <button type="button" className="button subtle-button small-button" onClick={() => stageRef.current?.zoomIn()}>
          +
        </button>
        <button
          type="button"
          className={`button small-button ${navigatorVisible ? "" : "ghost-button"}`}
          onClick={() => {
            const nextVisible = !navigatorVisible;
            setNavigatorVisible(nextVisible);
            stageRef.current?.toggleNavigator(nextVisible);
          }}
        >
          Navigator
        </button>
        <span className="pill">{scalePercent}%</span>
      </div>
      <MediaDeepZoomStage
        ref={stageRef}
        source={source}
        alt={alt}
        defaultMode={defaultMode}
        navigatorVisible={navigatorVisible}
        onScalePercentChange={setScalePercent}
        overlays={overlays}
      />
    </div>
  );
});

MediaDeepZoomViewer.displayName = "MediaDeepZoomViewer";
