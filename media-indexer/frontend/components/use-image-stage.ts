"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { ViewerViewport } from "@/components/interactive-image-stage";

interface ImageStageSize {
  width: number;
  height: number;
}

interface ImageStageFrame {
  scaledWidth: number;
  scaledHeight: number;
  imageLeft: number;
  imageTop: number;
  imageRight: number;
  imageBottom: number;
  visibleLeft: number;
  visibleTop: number;
  visibleWidth: number;
  visibleHeight: number;
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function distanceBetween(left: PointerEvent, right: PointerEvent) {
  return Math.hypot(right.clientX - left.clientX, right.clientY - left.clientY);
}

function midpointWithinStage(left: PointerEvent, right: PointerEvent, rect: DOMRect) {
  return {
    x: (left.clientX + right.clientX) / 2 - rect.left,
    y: (left.clientY + right.clientY) / 2 - rect.top,
  };
}

function zoomAroundPoint(viewport: ViewerViewport, nextZoom: number, point: { x: number; y: number }, width: number, height: number) {
  const ratio = nextZoom / viewport.zoom;
  const centerX = width / 2;
  const centerY = height / 2;
  return {
    zoom: nextZoom,
    offsetX: viewport.offsetX * ratio + (point.x - centerX) * (1 - ratio),
    offsetY: viewport.offsetY * ratio + (point.y - centerY) * (1 - ratio),
  };
}

function sameViewport(left: ViewerViewport, right: ViewerViewport) {
  return (
    Math.abs(left.zoom - right.zoom) < 0.0001 &&
    Math.abs(left.offsetX - right.offsetX) < 0.5 &&
    Math.abs(left.offsetY - right.offsetY) < 0.5
  );
}

export function useImageStage({
  viewport,
  onViewportChange,
  onFitScaleChange,
}: {
  viewport: ViewerViewport;
  onViewportChange: (next: ViewerViewport) => void;
  onFitScaleChange?: (fitScale: number) => void;
}) {
  const stageRef = useRef<HTMLDivElement | null>(null);
  const [naturalSize, setNaturalSizeState] = useState<ImageStageSize>({ width: 0, height: 0 });
  const [stageSize, setStageSize] = useState<ImageStageSize>({ width: 0, height: 0 });
  const [dragging, setDragging] = useState(false);
  const pointersRef = useRef<Map<number, PointerEvent>>(new Map());
  const panStartRef = useRef<{ pointerId: number; originX: number; originY: number; viewport: ViewerViewport } | null>(null);
  const pinchStartRef = useRef<{ distance: number; viewport: ViewerViewport } | null>(null);
  const lastTapRef = useRef<{ time: number; x: number; y: number } | null>(null);

  const fitScale =
    naturalSize.width && naturalSize.height && stageSize.width && stageSize.height
      ? Math.min(stageSize.width / naturalSize.width, stageSize.height / naturalSize.height, 1)
      : 1;
  const maxZoom = Math.max(12, fitScale > 0 ? 1 / fitScale : 12);

  const clampViewport = useCallback(
    (next: ViewerViewport): ViewerViewport => {
      const zoom = clamp(next.zoom, 1, maxZoom);
      if (zoom <= 1 || !naturalSize.width || !naturalSize.height || !stageSize.width || !stageSize.height) {
        return { zoom: 1, offsetX: 0, offsetY: 0 };
      }

      const scaledWidth = naturalSize.width * fitScale * zoom;
      const scaledHeight = naturalSize.height * fitScale * zoom;
      const maxOffsetX = Math.max(0, (scaledWidth - stageSize.width) / 2);
      const maxOffsetY = Math.max(0, (scaledHeight - stageSize.height) / 2);
      return {
        zoom,
        offsetX: clamp(next.offsetX, -maxOffsetX, maxOffsetX),
        offsetY: clamp(next.offsetY, -maxOffsetY, maxOffsetY),
      };
    },
    [fitScale, maxZoom, naturalSize.height, naturalSize.width, stageSize.height, stageSize.width]
  );

  const updateViewport = useCallback(
    (next: ViewerViewport) => {
      onViewportChange(clampViewport(next));
    },
    [clampViewport, onViewportChange]
  );

  useEffect(() => {
    onFitScaleChange?.(fitScale);
  }, [fitScale, onFitScaleChange]);

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) {
      return;
    }
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) {
        return;
      }
      setStageSize({
        width: entry.contentRect.width,
        height: entry.contentRect.height,
      });
    });
    observer.observe(stage);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const clamped = clampViewport(viewport);
    if (!sameViewport(clamped, viewport)) {
      onViewportChange(clamped);
    }
  }, [clampViewport, onViewportChange, viewport]);

  const setNaturalSize = useCallback((width: number, height: number, mode: "replace" | "max" = "replace") => {
    if (!width || !height) {
      return;
    }
    setNaturalSizeState((current) =>
      mode === "max"
        ? {
            width: Math.max(current.width, width),
            height: Math.max(current.height, height),
          }
        : { width, height }
    );
  }, []);

  const handleZoom = useCallback(
    (nextZoom: number, point?: { x: number; y: number }) => {
      const clampedZoom = clamp(nextZoom, 1, maxZoom);
      if (clampedZoom <= 1) {
        onViewportChange({ zoom: 1, offsetX: 0, offsetY: 0 });
        return;
      }
      const focalPoint = point ?? { x: stageSize.width / 2, y: stageSize.height / 2 };
      updateViewport(zoomAroundPoint(viewport, clampedZoom, focalPoint, stageSize.width, stageSize.height));
    },
    [maxZoom, onViewportChange, stageSize.height, stageSize.width, updateViewport, viewport]
  );

  const frame: ImageStageFrame = (() => {
    const scaledWidth = naturalSize.width * fitScale * viewport.zoom;
    const scaledHeight = naturalSize.height * fitScale * viewport.zoom;
    const imageLeft = stageSize.width / 2 - scaledWidth / 2 + viewport.offsetX;
    const imageTop = stageSize.height / 2 - scaledHeight / 2 + viewport.offsetY;
    const imageRight = imageLeft + scaledWidth;
    const imageBottom = imageTop + scaledHeight;
    const visibleLeft = clamp(imageLeft, 0, stageSize.width);
    const visibleTop = clamp(imageTop, 0, stageSize.height);
    const visibleRight = clamp(imageRight, 0, stageSize.width);
    const visibleBottom = clamp(imageBottom, 0, stageSize.height);
    return {
      scaledWidth,
      scaledHeight,
      imageLeft,
      imageTop,
      imageRight,
      imageBottom,
      visibleLeft,
      visibleTop,
      visibleWidth: Math.max(0, visibleRight - visibleLeft),
      visibleHeight: Math.max(0, visibleBottom - visibleTop),
    };
  })();

  return {
    stageRef,
    naturalSize,
    stageSize,
    fitScale,
    maxZoom,
    frame,
    dragging,
    imageTransform: `translate(calc(-50% + ${viewport.offsetX}px), calc(-50% + ${viewport.offsetY}px)) scale(${fitScale * viewport.zoom})`,
    setNaturalSize,
    setDragging,
    handleZoom,
    stageProps: {
      onDoubleClick: (event: React.MouseEvent<HTMLDivElement>) => {
        const rect = event.currentTarget.getBoundingClientRect();
        const point = { x: event.clientX - rect.left, y: event.clientY - rect.top };
        handleZoom(viewport.zoom >= 2.5 ? 1 : viewport.zoom * 2, point);
      },
      onPointerDown: (event: React.PointerEvent<HTMLDivElement>) => {
        pointersRef.current.set(event.pointerId, event.nativeEvent);
        event.currentTarget.setPointerCapture(event.pointerId);

        if (pointersRef.current.size >= 2) {
          const pointers = Array.from(pointersRef.current.values());
          pinchStartRef.current = {
            distance: distanceBetween(pointers[0], pointers[1]),
            viewport,
          };
          panStartRef.current = null;
          return;
        }

        if (viewport.zoom <= 1) {
          return;
        }

        panStartRef.current = {
          pointerId: event.pointerId,
          originX: event.clientX,
          originY: event.clientY,
          viewport,
        };
        setDragging(true);
      },
      onPointerMove: (event: React.PointerEvent<HTMLDivElement>) => {
        if (!stageRef.current) {
          return;
        }
        pointersRef.current.set(event.pointerId, event.nativeEvent);
        const rect = stageRef.current.getBoundingClientRect();

        if (pointersRef.current.size >= 2 && pinchStartRef.current) {
          const pointers = Array.from(pointersRef.current.values());
          const nextDistance = distanceBetween(pointers[0], pointers[1]);
          if (!pinchStartRef.current.distance) {
            return;
          }
          const midpoint = midpointWithinStage(pointers[0], pointers[1], rect);
          const nextZoom = pinchStartRef.current.viewport.zoom * (nextDistance / pinchStartRef.current.distance);
          handleZoom(nextZoom, midpoint);
          return;
        }

        if (!panStartRef.current || panStartRef.current.pointerId !== event.pointerId) {
          return;
        }

        updateViewport({
          zoom: viewport.zoom,
          offsetX: panStartRef.current.viewport.offsetX + (event.clientX - panStartRef.current.originX),
          offsetY: panStartRef.current.viewport.offsetY + (event.clientY - panStartRef.current.originY),
        });
      },
      onPointerUp: (event: React.PointerEvent<HTMLDivElement>) => {
        pointersRef.current.delete(event.pointerId);
        if (event.currentTarget.hasPointerCapture(event.pointerId)) {
          event.currentTarget.releasePointerCapture(event.pointerId);
        }
        if (pointersRef.current.size < 2) {
          pinchStartRef.current = null;
        }
        if (panStartRef.current?.pointerId === event.pointerId) {
          panStartRef.current = null;
        }
        setDragging(false);

        if (event.pointerType === "touch" && stageRef.current) {
          const rect = stageRef.current.getBoundingClientRect();
          const point = { x: event.clientX - rect.left, y: event.clientY - rect.top };
          const now = Date.now();
          const lastTap = lastTapRef.current;
          if (
            lastTap &&
            now - lastTap.time < 280 &&
            Math.abs(lastTap.x - point.x) < 24 &&
            Math.abs(lastTap.y - point.y) < 24
          ) {
            handleZoom(viewport.zoom >= 2.5 ? 1 : viewport.zoom * 2, point);
            lastTapRef.current = null;
          } else {
            lastTapRef.current = { time: now, x: point.x, y: point.y };
          }
        }
      },
      onPointerCancel: (event: React.PointerEvent<HTMLDivElement>) => {
        pointersRef.current.delete(event.pointerId);
        if (event.currentTarget.hasPointerCapture(event.pointerId)) {
          event.currentTarget.releasePointerCapture(event.pointerId);
        }
        if (panStartRef.current?.pointerId === event.pointerId) {
          panStartRef.current = null;
        }
        if (pointersRef.current.size < 2) {
          pinchStartRef.current = null;
        }
        setDragging(false);
      },
      onWheel: (event: React.WheelEvent<HTMLDivElement>) => {
        event.preventDefault();
        const rect = event.currentTarget.getBoundingClientRect();
        handleZoom(viewport.zoom + (event.deltaY < 0 ? 0.18 : -0.18), {
          x: event.clientX - rect.left,
          y: event.clientY - rect.top,
        });
      },
    },
  };
}
