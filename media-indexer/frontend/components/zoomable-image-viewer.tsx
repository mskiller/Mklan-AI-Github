"use client";

import { forwardRef } from "react";

import {
  DeepZoomOverlay,
  MediaDeepZoomSource,
  MediaDeepZoomViewer,
  MediaDeepZoomViewerHandle,
} from "@/components/media-deep-zoom-viewer";

export interface ZoomableImageViewerHandle extends MediaDeepZoomViewerHandle {}

export const ZoomableImageViewer = forwardRef<
  ZoomableImageViewerHandle,
  {
    src?: string | null;
    previewSrc?: string | null;
    contentSrc?: string | null;
    deepzoomUrl?: string | null;
    alt: string;
    defaultMode?: "auto" | "native" | "fit";
    overlays?: DeepZoomOverlay[];
  }
>(({ src, previewSrc, contentSrc, deepzoomUrl, alt, defaultMode = "auto", overlays = [] }, ref) => {
  const source: MediaDeepZoomSource = {
    previewSrc: previewSrc ?? src ?? contentSrc ?? null,
    fullSrc: contentSrc ?? src ?? previewSrc ?? null,
    deepzoomUrl: deepzoomUrl ?? null,
  };
  return <MediaDeepZoomViewer ref={ref} source={source} alt={alt} defaultMode={defaultMode} overlays={overlays} />;
});

ZoomableImageViewer.displayName = "ZoomableImageViewer";
