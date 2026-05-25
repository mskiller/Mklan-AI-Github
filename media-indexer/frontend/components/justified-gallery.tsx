"use client";

import { ReactNode, useEffect, useMemo, useRef, useState } from "react";

interface JustifiedGalleryRowItem {
  key: string;
  width: number;
  ratio: number;
  content: ReactNode;
}

export interface JustifiedGalleryItem {
  key: string;
  ratio: number;
  content: ReactNode;
}

function buildRows(items: JustifiedGalleryItem[], containerWidth: number, targetRowHeight: number, gap: number) {
  if (!containerWidth || !items.length) {
    return [];
  }

  const rows: Array<{ key: string; height: number; items: JustifiedGalleryRowItem[] }> = [];
  let currentRow: JustifiedGalleryItem[] = [];
  let currentRatioSum = 0;

  const pushRow = (rowItems: JustifiedGalleryItem[], ratioSum: number, fillWidth: boolean) => {
    if (!rowItems.length || ratioSum <= 0) {
      return;
    }
    const availableWidth = Math.max(containerWidth - gap * Math.max(0, rowItems.length - 1), 1);
    const fittedHeight = availableWidth / ratioSum;
    const height = fillWidth
      ? Math.max(120, Math.min(targetRowHeight * 1.24, fittedHeight))
      : Math.max(120, Math.min(targetRowHeight, fittedHeight));
    rows.push({
      key: rowItems.map((item) => item.key).join(":"),
      height,
      items: rowItems.map((item) => ({
        key: item.key,
        ratio: item.ratio,
        width: item.ratio * height,
        content: item.content,
      })),
    });
  };

  for (const item of items) {
    currentRow.push(item);
    currentRatioSum += item.ratio;
    const projectedWidth = currentRatioSum * targetRowHeight + gap * Math.max(0, currentRow.length - 1);
    if (projectedWidth >= containerWidth && currentRow.length > 1) {
      pushRow(currentRow, currentRatioSum, true);
      currentRow = [];
      currentRatioSum = 0;
    }
  }

  pushRow(currentRow, currentRatioSum, false);
  return rows;
}

export function JustifiedGallery({
  items,
  targetRowHeight = 248,
  gap = 12,
  className = "",
}: {
  items: JustifiedGalleryItem[];
  targetRowHeight?: number;
  gap?: number;
  className?: string;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [containerWidth, setContainerWidth] = useState(0);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) {
      return;
    }
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) {
        return;
      }
      setContainerWidth(entry.contentRect.width);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const rows = useMemo(
    () => buildRows(items, containerWidth, targetRowHeight, gap),
    [containerWidth, gap, items, targetRowHeight]
  );

  return (
    <div ref={containerRef} className={`justified-gallery ${className}`.trim()} style={{ minWidth: 0, overflow: "hidden" }}>
      {rows.map((row) => (
        <div key={row.key} className="justified-gallery-row" style={{ gap: `${gap}px`, minHeight: `${row.height}px` }}>
          {row.items.map((item) => (
            <div key={item.key} className="justified-gallery-item" style={{ width: `${item.width}px`, height: `${row.height}px` }}>
              {item.content}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
