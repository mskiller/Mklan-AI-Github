"use client";

import { useEffect, useRef, useState } from "react";

import { useImageStage } from "@/components/use-image-stage";

export interface ViewerViewport {
  zoom: number;
  offsetX: number;
  offsetY: number;
}

export function InteractiveImageStage({
  src,
  alt,
  viewport,
  onViewportChange,
  onFitScaleChange,
  className = "",
}: {
  src: string;
  alt: string;
  viewport: ViewerViewport;
  onViewportChange: (next: ViewerViewport) => void;
  onFitScaleChange?: (fitScale: number) => void;
  className?: string;
}) {
  const stageShellRef = useRef<HTMLDivElement | null>(null);
  const [shellSize, setShellSize] = useState({ width: 0, height: 0 });
  const { stageRef, naturalSize, stageSize, fitScale, dragging, imageTransform, setNaturalSize, stageProps } = useImageStage({
    viewport,
    onViewportChange,
    onFitScaleChange,
  });

  useEffect(() => {
    const shell = stageShellRef.current;
    if (!shell) {
      return;
    }
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) {
        return;
      }
      setShellSize({
        width: entry.contentRect.width,
        height: entry.contentRect.height,
      });
    });
    observer.observe(shell);
    return () => observer.disconnect();
  }, []);

  const availableWidth = shellSize.width || stageSize.width;
  const fitHeight = naturalSize.height * fitScale;
  const unconstrainedFitScale =
    naturalSize.width && naturalSize.height && availableWidth && stageSize.height
      ? Math.min(availableWidth / naturalSize.width, stageSize.height / naturalSize.height, 1)
      : 1;
  const unconstrainedFitWidth = naturalSize.width * unconstrainedFitScale;
  const stageStyle =
    viewport.zoom <= 1.01 &&
    availableWidth > 0 &&
    fitHeight > 0 &&
    unconstrainedFitWidth > 0 &&
    unconstrainedFitWidth < availableWidth - 96
      ? {
          maxWidth: `${Math.ceil(Math.min(availableWidth, unconstrainedFitWidth + 72))}px`,
          marginInline: "auto",
        }
      : undefined;

  return (
    <div ref={stageShellRef} className="interactive-image-stage-shell" style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
      <div
        ref={stageRef}
        className={`interactive-image-stage ${dragging ? "interactive-image-stage-dragging" : ""} ${className}`.trim()}
        style={{ ...stageStyle, flex: 1, minHeight: 0 }}
        {...stageProps}
      >
        <img
          src={src}
          alt={alt}
          draggable={false}
          onLoad={(event) => {
            setNaturalSize(event.currentTarget.naturalWidth, event.currentTarget.naturalHeight);
          }}
          style={{ transform: imageTransform }}
        />
      </div>
    </div>
  );
}
