"use client";

import { ReactNode, useEffect, useMemo, useRef, useState } from "react";


function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}


export function VirtualizedGallery<T>({
  items,
  renderItem,
  itemMinWidth = 240,
  itemHeight = 300,
  gap = 12,
  overscanRows = 3,
  className = "",
}: {
  items: T[];
  renderItem: (item: T, index: number) => ReactNode;
  itemMinWidth?: number;
  itemHeight?: number;
  gap?: number;
  overscanRows?: number;
  className?: string;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(0);
  const [height, setHeight] = useState(0);
  const [scrollTop, setScrollTop] = useState(0);

  useEffect(() => {
    const node = containerRef.current;
    if (!node) {
      return;
    }
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) {
        return;
      }
      setWidth(entry.contentRect.width);
      setHeight(entry.contentRect.height);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const columns = useMemo(() => {
    if (!width) {
      return 1;
    }
    return Math.max(1, Math.floor((width + gap) / (itemMinWidth + gap)));
  }, [gap, itemMinWidth, width]);

  const itemWidth = useMemo(() => {
    return Math.max(180, (width - gap * Math.max(0, columns - 1)) / columns);
  }, [columns, gap, width]);

  const rowHeight = itemHeight + gap;
  const totalRows = Math.ceil(items.length / columns);
  const totalHeight = totalRows * rowHeight;

  const startRow = clamp(Math.floor(scrollTop / rowHeight) - overscanRows, 0, totalRows);
  const endRow = clamp(Math.ceil((scrollTop + height) / rowHeight) + overscanRows, 0, totalRows);

  const visibleItems = useMemo(() => {
    const next: Array<{ item: T; index: number; row: number; column: number }> = [];
    for (let row = startRow; row < endRow; row += 1) {
      for (let column = 0; column < columns; column += 1) {
        const index = row * columns + column;
        const item = items[index];
        if (item === undefined) {
          continue;
        }
        next.push({ item, index, row, column });
      }
    }
    return next;
  }, [columns, endRow, items, startRow]);

  return (
    <div
      ref={containerRef}
      className={`virtualized-gallery ${className}`.trim()}
      onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
    >
      <div className="virtualized-gallery-surface" style={{ height: `${Math.max(totalHeight, height)}px` }}>
        {visibleItems.map(({ item, index, row, column }) => (
          <div
            key={index}
            className="virtualized-gallery-item"
            style={{
              width: `${itemWidth}px`,
              height: `${itemHeight}px`,
              left: `${column * (itemWidth + gap)}px`,
              top: `${row * rowHeight}px`,
            }}
          >
            {renderItem(item, index)}
          </div>
        ))}
      </div>
    </div>
  );
}
