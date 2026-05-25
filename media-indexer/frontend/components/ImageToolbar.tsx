"use client";

import { useState } from "react";
import { copyImageToClipboard } from "@/lib/clipboard";

export function ImageToolbar({
  contentSrc,
  rotation,
  onRotate,
  viewerContainerRef,
}: {
  contentSrc: string | null;
  rotation: number;
  onRotate: () => void;
  viewerContainerRef?: React.RefObject<HTMLElement | null>;
}) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (!contentSrc) return;
    const ok = await copyImageToClipboard(contentSrc);
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    }
  };

  const handleFullscreen = () => {
    const el = viewerContainerRef?.current ?? document.documentElement;
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else {
      el.requestFullscreen?.();
    }
  };

  const handleOpenOriginal = () => {
    if (contentSrc) {
      window.open(contentSrc, "_blank", "noopener,noreferrer");
    }
  };

  return (
    <div className="image-toolbar">
      <button
        type="button"
        className="image-toolbar-btn"
        title={copied ? "Copied!" : "Copy image to clipboard"}
        onClick={handleCopy}
        disabled={!contentSrc}
      >
        {copied ? "✓" : "⧉"}
      </button>
      <button
        type="button"
        className="image-toolbar-btn"
        title="Open original in new tab"
        onClick={handleOpenOriginal}
        disabled={!contentSrc}
      >
        ↗
      </button>
      <button
        type="button"
        className="image-toolbar-btn"
        title="Toggle fullscreen"
        onClick={handleFullscreen}
      >
        ⤢
      </button>
      <button
        type="button"
        className="image-toolbar-btn"
        title={`Rotate 90° (current: ${rotation}°)`}
        onClick={onRotate}
      >
        ↻
      </button>
    </div>
  );
}
