import React, { useState, useRef, useEffect } from "react";
import { ZoomIn, ZoomOut, Maximize2, RotateCw, Copy, Check, ExternalLink } from "lucide-react";

interface DeepZoomViewerProps {
  src: string;
  alt: string;
  onScaleChange?: (scale: number) => void;
  compact?: boolean;
}

export function DeepZoomViewer({ src, alt, onScaleChange, compact = false }: DeepZoomViewerProps) {
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [rotation, setRotation] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const [copied, setCopied] = useState(false);
  const dragStart = useRef({ x: 0, y: 0 });
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Reset viewport on image source change
    setScale(1);
    setOffset({ x: 0, y: 0 });
    setRotation(0);
  }, [src]);

  const handleZoomIn = () => {
    const next = Math.min(4, scale + 0.25);
    setScale(next);
    onScaleChange?.(next);
  };

  const handleZoomOut = () => {
    const next = Math.max(0.25, scale - 0.25);
    setScale(next);
    onScaleChange?.(next);
  };

  const handleReset = () => {
    setScale(1);
    setOffset({ x: 0, y: 0 });
    setRotation(0);
    onScaleChange?.(1);
  };

  const handleRotate = () => {
    setRotation((r) => (r + 90) % 360);
  };

  const handleCopy = async () => {
    try {
      const response = await fetch(src);
      const blob = await response.blob();
      await navigator.clipboard.write([
        new ClipboardItem({ [blob.type]: blob })
      ]);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (e) {
      console.error("Clipboard write failed: copying URL instead");
      await navigator.clipboard.writeText(window.location.origin + src);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleToggleFullscreen = () => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen().catch(err => console.error(err));
    } else {
      document.exitFullscreen();
    }
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    if (scale === 1) return; // Only drag when zoomed in
    setIsDragging(true);
    dragStart.current = { x: e.clientX - offset.x, y: e.clientY - offset.y };
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging) return;
    setOffset({
      x: e.clientX - dragStart.current.x,
      y: e.clientY - dragStart.current.y
    });
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const next = Math.min(4, Math.max(0.25, scale - e.deltaY * 0.003));
    setScale(next);
    onScaleChange?.(next);
  };

  return (
    <div 
      ref={containerRef}
      onWheel={handleWheel}
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        background: "#08080a",
        borderRadius: compact ? "0" : "8px",
        overflow: "hidden",
        display: "flex",
        alignItems: compact ? "stretch" : "center",
        justifyContent: "center",
        cursor: scale > 1 ? (isDragging ? "grabbing" : "grab") : "default",
        userSelect: "none"
      }}
    >
      <div
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        style={{
          transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale}) rotate(${rotation}deg)`,
          transition: isDragging ? "none" : "transform 0.2s cubic-bezier(0.16, 1, 0.3, 1)",
          transformOrigin: "center center",
          width: compact ? "100%" : undefined,
          height: compact ? "100%" : undefined,
          minWidth: 0,
          minHeight: 0,
          maxWidth: "100%",
          maxHeight: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center"
        }}
      >
        <img 
          src={src} 
          alt={alt} 
          style={{ 
            width: compact ? "100%" : undefined,
            height: compact ? "100%" : undefined,
            maxWidth: "100%", 
            maxHeight: compact ? "100%" : "80vh", 
            objectFit: "contain",
            pointerEvents: "none",
            display: "block"
          }} 
        />
      </div>

      {/* Floating Toolbar */}
      <div 
        style={{
          position: "absolute",
          bottom: compact ? "calc(0.65rem + env(safe-area-inset-bottom))" : "1.5rem",
          left: compact ? "0.65rem" : "50%",
          right: compact ? "0.65rem" : undefined,
          transform: compact ? "none" : "translateX(-50%)",
          display: "flex",
          flexWrap: compact ? "wrap" : "nowrap",
          gap: "0.25rem",
          alignItems: "center",
          justifyContent: "center",
          maxWidth: compact ? "calc(100% - 1.3rem)" : undefined,
          overflowX: compact ? "auto" : undefined,
          background: "rgba(15, 15, 20, 0.75)",
          backdropFilter: "blur(12px)",
          border: "1px solid rgba(255, 255, 255, 0.08)",
          padding: compact ? "0.3rem" : "0.4rem 0.8rem",
          borderRadius: compact ? "12px" : "9999px",
          boxShadow: "0 10px 30px rgba(0, 0, 0, 0.5)",
          zIndex: 10,
          color: "#fff"
        }}
      >
        <button 
          onClick={handleZoomOut}
          style={{ background: "none", border: "none", color: "#ccc", cursor: "pointer", display: "flex", padding: compact ? "0.35rem" : "0.4rem", borderRadius: "50%" }}
          title="Zoom Out"
        >
          <ZoomOut size={15} />
        </button>
        <span style={{ fontSize: "0.8rem", minWidth: compact ? "2.1rem" : "2.5rem", textAlign: "center", fontWeight: 600 }}>
          {Math.round(scale * 100)}%
        </span>
        <button 
          onClick={handleZoomIn}
          style={{ background: "none", border: "none", color: "#ccc", cursor: "pointer", display: "flex", padding: compact ? "0.35rem" : "0.4rem", borderRadius: "50%" }}
          title="Zoom In"
        >
          <ZoomIn size={15} />
        </button>
        <span style={{ width: "1px", height: "14px", background: "rgba(255, 255, 255, 0.15)", margin: compact ? "0 0.15rem" : "0 0.4rem" }} />
        <button 
          onClick={handleReset}
          style={{ background: "none", border: "none", color: "#ccc", cursor: "pointer", fontSize: "0.75rem", fontWeight: 600, padding: compact ? "0.3rem 0.4rem" : "0.3rem 0.6rem", borderRadius: "4px" }}
        >
          Reset
        </button>
        <button 
          onClick={handleRotate}
          style={{ background: "none", border: "none", color: "#ccc", cursor: "pointer", display: "flex", padding: compact ? "0.35rem" : "0.4rem", borderRadius: "50%" }}
          title="Rotate 90°"
        >
          <RotateCw size={15} />
        </button>
        <button 
          onClick={handleCopy}
          style={{ background: "none", border: "none", color: copied ? "var(--accent)" : "#ccc", cursor: "pointer", display: "flex", padding: compact ? "0.35rem" : "0.4rem", borderRadius: "50%" }}
          title="Copy Image to Clipboard"
        >
          {copied ? <Check size={15} /> : <Copy size={15} />}
        </button>
        <button 
          onClick={() => window.open(src, "_blank")}
          style={{ background: "none", border: "none", color: "#ccc", cursor: "pointer", display: "flex", padding: compact ? "0.35rem" : "0.4rem", borderRadius: "50%" }}
          title="Open in New Tab"
        >
          <ExternalLink size={15} />
        </button>
        <button 
          onClick={handleToggleFullscreen}
          style={{ background: "none", border: "none", color: "#ccc", cursor: "pointer", display: "flex", padding: compact ? "0.35rem" : "0.4rem", borderRadius: "50%" }}
          title="Toggle Fullscreen"
        >
          <Maximize2 size={15} />
        </button>
      </div>
    </div>
  );
}
