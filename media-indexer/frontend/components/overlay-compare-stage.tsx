"use client";

import { useEffect, useState } from "react";

import { ViewerViewport } from "@/components/interactive-image-stage";
import { useImageStage } from "@/components/use-image-stage";

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

export function OverlayCompareStage({
  baseSrc,
  overlaySrc,
  baseAlt,
  overlayAlt,
  baseLabel,
  overlayLabel,
  sliderPosition,
  onSliderPositionChange,
  viewport,
  onViewportChange,
  onFitScaleChange,
  onImageFrameChange,
}: {
  baseSrc: string;
  overlaySrc: string;
  baseAlt: string;
  overlayAlt: string;
  baseLabel: string;
  overlayLabel: string;
  sliderPosition: number;
  onSliderPositionChange?: (next: number) => void;
  viewport: ViewerViewport;
  onViewportChange: (next: ViewerViewport) => void;
  onFitScaleChange?: (fitScale: number) => void;
  onImageFrameChange?: (next: { left: number; top: number; width: number; height: number }) => void;
}) {
  const [sliderDragging, setSliderDragging] = useState(false);
  const { stageRef, frame, dragging, imageTransform, setNaturalSize, stageProps } = useImageStage({
    viewport,
    onViewportChange,
    onFitScaleChange,
  });
  const dividerPosition = clamp(sliderPosition, 0, 100);
  const dividerX = frame.scaledWidth ? frame.imageLeft + (frame.scaledWidth * dividerPosition) / 100 : 0;

  useEffect(() => {
    onImageFrameChange?.({
      left: frame.visibleLeft,
      top: frame.visibleTop,
      width: frame.visibleWidth,
      height: frame.visibleHeight,
    });
  }, [frame.visibleHeight, frame.visibleLeft, frame.visibleTop, frame.visibleWidth, onImageFrameChange]);

  const updateSliderPosition = (clientX: number) => {
    if (!stageRef.current || !onSliderPositionChange) {
      return;
    }
    if (!frame.scaledWidth) {
      onSliderPositionChange(50);
      return;
    }
    const rect = stageRef.current.getBoundingClientRect();
    const stageX = clientX - rect.left;
    const percentage = ((stageX - frame.imageLeft) / frame.scaledWidth) * 100;
    onSliderPositionChange(clamp(percentage, 0, 100));
  };

  return (
    <div
      ref={stageRef}
      className={`interactive-image-stage overlay-compare-stage ${dragging ? "interactive-image-stage-dragging" : ""}`.trim()}
      {...stageProps}
    >
      <img
        src={baseSrc}
        alt={baseAlt}
        draggable={false}
        onLoad={(event) => {
          setNaturalSize(event.currentTarget.naturalWidth, event.currentTarget.naturalHeight, "max");
        }}
        style={{ transform: imageTransform }}
      />
      <img
        src={overlaySrc}
        alt={overlayAlt}
        draggable={false}
        className="overlay-compare-image"
        onLoad={(event) => {
          setNaturalSize(event.currentTarget.naturalWidth, event.currentTarget.naturalHeight, "max");
        }}
        style={{
          transform: imageTransform,
          clipPath: `inset(0 0 0 ${clamp(sliderPosition, 0, 100)}%)`,
        }}
      />
      <button
        type="button"
        className={`overlay-compare-divider-hitbox ${sliderDragging ? "overlay-compare-divider-hitbox-dragging" : ""}`}
        style={{ left: dividerX }}
        onPointerDown={(event) => {
          event.stopPropagation();
          event.preventDefault();
          event.currentTarget.setPointerCapture(event.pointerId);
          setSliderDragging(true);
          updateSliderPosition(event.clientX);
        }}
        onPointerMove={(event) => {
          if (!sliderDragging) {
            return;
          }
          event.stopPropagation();
          event.preventDefault();
          updateSliderPosition(event.clientX);
        }}
        onPointerUp={(event) => {
          if (event.currentTarget.hasPointerCapture(event.pointerId)) {
            event.currentTarget.releasePointerCapture(event.pointerId);
          }
          setSliderDragging(false);
          updateSliderPosition(event.clientX);
        }}
        onPointerCancel={(event) => {
          if (event.currentTarget.hasPointerCapture(event.pointerId)) {
            event.currentTarget.releasePointerCapture(event.pointerId);
          }
          setSliderDragging(false);
        }}
      >
        <span className="overlay-compare-divider-line" style={{ top: frame.visibleTop, height: frame.visibleHeight }} />
        <span className="overlay-compare-handle" style={{ top: frame.visibleTop + frame.visibleHeight / 2 }} />
      </button>
      <span className="overlay-compare-label overlay-compare-label-left">{baseLabel}</span>
      <span className="overlay-compare-label overlay-compare-label-right">{overlayLabel}</span>
    </div>
  );
}
