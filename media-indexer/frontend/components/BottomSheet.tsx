"use client";

import { ReactNode, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export function BottomSheet({
  open,
  onClose,
  title,
  subtitle,
  children,
  peekable = false,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string | null;
  children: ReactNode;
  /** If true, renders as a peek-able drawer that doesn't block the full screen */
  peekable?: boolean;
}) {
  const [visible, setVisible] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const dragStartY = useRef<number | null>(null);
  const sheetRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (open) {
      requestAnimationFrame(() => setVisible(true));
    } else {
      setVisible(false);
      setExpanded(false);
    }
  }, [open]);

  // Only lock body scroll when fully expanded or not in peekable mode
  useEffect(() => {
    if (open && (!peekable || expanded)) {
      const prev = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      return () => {
        document.body.style.overflow = prev;
      };
    }
  }, [open, peekable, expanded]);

  if (!open || typeof document === "undefined") {
    return null;
  }

  return createPortal(
    <>
      <div
        className="bottom-sheet-backdrop"
        onClick={onClose}
        style={{ opacity: visible ? (peekable && !expanded ? 0 : 1) : 0, pointerEvents: peekable && !expanded ? "none" : "auto" }}
      />
      <div
        ref={sheetRef}
        className={`bottom-sheet ${visible ? "bottom-sheet-open" : ""} ${peekable ? "bottom-sheet-peekable" : ""} ${peekable && expanded ? "bottom-sheet-expanded" : ""}`.trim()}
        onTouchStart={(e) => {
          dragStartY.current = e.touches[0].clientY;
        }}
        onTouchMove={(e) => {
          if (dragStartY.current === null) return;
          const dy = e.touches[0].clientY - dragStartY.current;
          if (dy > 0 && sheetRef.current) {
            sheetRef.current.style.transform = `translateY(${dy}px)`;
          }
        }}
        onTouchEnd={(e) => {
          if (dragStartY.current === null) return;
          const dy = e.changedTouches[0].clientY - dragStartY.current;
          dragStartY.current = null;
          if (sheetRef.current) {
            sheetRef.current.style.transform = "";
          }
          if (dy > 80) {
            if (peekable && expanded) {
              setExpanded(false);
            } else {
              onClose();
            }
          } else if (dy < -40 && peekable && !expanded) {
            setExpanded(true);
          }
        }}
      >
        <div
          className="bottom-sheet-handle"
          onClick={() => peekable && setExpanded((v) => !v)}
          style={peekable ? { cursor: "pointer" } : undefined}
        />
        <div className="stack">
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div>
              <strong style={{ fontSize: "1.05rem" }}>{title}</strong>
              {subtitle ? <p className="subdued" style={{ margin: "0.2rem 0 0" }}>{subtitle}</p> : null}
            </div>
            {peekable && (
              <button
                type="button"
                className="button ghost-button small-button"
                onClick={() => setExpanded((v) => !v)}
                aria-label={expanded ? "Collapse" : "Expand"}
              >
                {expanded ? "▾ Less" : "▴ More"}
              </button>
            )}
          </div>
          {(!peekable || expanded) && children}
        </div>
      </div>
    </>,
    document.body
  );
}
