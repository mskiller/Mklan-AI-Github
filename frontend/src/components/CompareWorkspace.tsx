import React, { useState, useRef, useEffect } from "react";
import { X, GitCompare, ZoomIn, ZoomOut, Layers, BarChart2 } from "lucide-react";

interface CompareMeta {
  prompt?: string;
  negative_prompt?: string;
  steps?: number;
  cfg_scale?: number;
  sampler_name?: string;
  scheduler?: string;
  width?: number;
  height?: number;
}

interface GalleryImage {
  name: string;
  url: string;
  metadata: CompareMeta;
  id?: string;
}

interface CompareWorkspaceProps {
  images: [GalleryImage, GalleryImage];
  onClose: () => void;
}

export function CompareWorkspace({ images, onClose }: CompareWorkspaceProps) {
  const [mode, setMode] = useState<"side" | "slider">("side");
  const [sliderPos, setSliderPos] = useState(50);
  const [syncZoom, setSyncZoom] = useState(1);
  const [syncPan, setSyncPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const dragStart = useRef({ x: 0, y: 0 });
  
  const [imgA, imgB] = images;

  // AI-Assisted Metrics
  const [compareData, setCompareData] = useState<any | null>(null);
  const [loadingMetrics, setLoadingMetrics] = useState(false);

  useEffect(() => {
    if (imgA.id && imgB.id) {
      setLoadingMetrics(true);
      fetch(`/api/media/compare?a=${imgA.id}&b=${imgB.id}`)
        .then(res => res.ok ? res.json() : null)
        .then(data => {
          if (data) setCompareData(data);
        })
        .catch(err => console.error("Compare fetch failed", err))
        .finally(() => setLoadingMetrics(false));
    }
  }, [imgA.id, imgB.id]);

  const tagsA = imgA.metadata.prompt ? imgA.metadata.prompt.split(",").map(t => t.trim()).filter(Boolean) : [];
  const tagsB = imgB.metadata.prompt ? imgB.metadata.prompt.split(",").map(t => t.trim()).filter(Boolean) : [];

  const sharedTags = compareData ? compareData.shared_prompt_tags : tagsA.filter(t => tagsB.includes(t));
  const uniqueA = compareData ? compareData.left_only_prompt_tags : tagsA.filter(t => !tagsB.includes(t));
  const uniqueB = compareData ? compareData.right_only_prompt_tags : tagsB.filter(t => !tagsA.includes(t));

  const handleMouseDown = (e: React.MouseEvent) => {
    if (syncZoom === 1) return;
    setIsDragging(true);
    dragStart.current = { x: e.clientX - syncPan.x, y: e.clientY - syncPan.y };
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging) return;
    setSyncPan({
      x: e.clientX - dragStart.current.x,
      y: e.clientY - dragStart.current.y
    });
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  const handleZoomIn = () => setSyncZoom(z => Math.min(4, z + 0.25));
  const handleZoomOut = () => setSyncZoom(z => Math.max(0.5, z - 0.25));
  const handleReset = () => {
    setSyncZoom(1);
    setSyncPan({ x: 0, y: 0 });
  };

  return (
    <div 
      className="panel form-panel"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "1.5rem",
        background: "var(--bg-main)",
        border: "1px solid var(--border-color)",
        borderRadius: "12px",
        padding: "1.5rem",
        position: "relative",
        overflow: "hidden"
      }}
    >
      {/* Top Toolbar */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--border-color)", paddingBottom: "1rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <GitCompare size={18} color="var(--accent)" />
          <h2 style={{ fontSize: "1.1rem", margin: 0, fontWeight: 700 }}>Dual Sync Image Comparer</h2>
        </div>
        <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
          <div style={{ display: "flex", background: "var(--bg-secondary)", borderRadius: "6px", padding: "0.2rem" }}>
            <button 
              onClick={() => setMode("side")}
              style={{
                background: mode === "side" ? "var(--accent)" : "none",
                color: mode === "side" ? "#fff" : "var(--text-secondary)",
                border: "none",
                borderRadius: "4px",
                padding: "0.35rem 0.75rem",
                fontSize: "0.8rem",
                cursor: "pointer",
                fontWeight: 600
              }}
            >
              Side-by-Side
            </button>
            <button 
              onClick={() => setMode("slider")}
              style={{
                background: mode === "slider" ? "var(--accent)" : "none",
                color: mode === "slider" ? "#fff" : "var(--text-secondary)",
                border: "none",
                borderRadius: "4px",
                padding: "0.35rem 0.75rem",
                fontSize: "0.8rem",
                cursor: "pointer",
                fontWeight: 600
              }}
            >
              Slider Split
            </button>
          </div>

          <span style={{ width: "1px", height: "16px", background: "var(--border-color)" }} />

          {/* Sync Zoom Toolbar */}
          <div style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}>
            <button onClick={handleZoomOut} style={{ background: "none", border: "none", color: "var(--text-secondary)", cursor: "pointer", padding: "0.3rem" }} title="Zoom Out"><ZoomOut size={14} /></button>
            <span style={{ fontSize: "0.75rem", minWidth: "2.2rem", textAlign: "center", fontWeight: 700 }}>{Math.round(syncZoom * 100)}%</span>
            <button onClick={handleZoomIn} style={{ background: "none", border: "none", color: "var(--text-secondary)", cursor: "pointer", padding: "0.3rem" }} title="Zoom In"><ZoomIn size={14} /></button>
            <button onClick={handleReset} style={{ background: "none", border: "none", color: "var(--text-secondary)", fontSize: "0.7rem", fontWeight: 600, cursor: "pointer", padding: "0.25rem 0.5rem" }}>Reset</button>
          </div>

          <span style={{ width: "1px", height: "16px", background: "var(--border-color)" }} />

          <button 
            className="icon-button" 
            onClick={onClose}
            style={{ padding: "0.4rem 0.8rem", background: "rgba(239, 68, 68, 0.1)", color: "#ef4444", border: "none", borderRadius: "6px", cursor: "pointer", fontSize: "0.8rem", display: "flex", alignItems: "center", gap: "0.3rem" }}
          >
            <X size={14} /> Close Compare
          </button>
        </div>
      </div>

      {/* Main comparison viewport */}
      {mode === "side" ? (
        <div 
          style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
        >
          {/* Panel A */}
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", overflow: "hidden" }}>
            <div 
              style={{ 
                aspectRatio: "1/1", 
                background: "#08080a", 
                borderRadius: "8px", 
                border: "1px solid var(--border-color)",
                overflow: "hidden",
                position: "relative"
              }}
            >
              <div
                style={{
                  transform: `translate(${syncPan.x}px, ${syncPan.y}px) scale(${syncZoom})`,
                  width: "100%",
                  height: "100%",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  transition: isDragging ? "none" : "transform 0.15s cubic-bezier(0.16, 1, 0.3, 1)"
                }}
              >
                <img src={imgA.url} alt={imgA.name} style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain", pointerEvents: "none" }} />
              </div>
              <div style={{ position: "absolute", top: "0.5rem", left: "0.5rem", background: "rgba(0,0,0,0.7)", padding: "0.25rem 0.5rem", borderRadius: "4px", fontSize: "0.7rem", fontWeight: 700 }}>Image A</div>
            </div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", background: "var(--bg-secondary)", padding: "0.5rem 0.75rem", borderRadius: "6px" }}>
              <strong>A:</strong> {imgA.metadata.prompt || "No prompt meta"}
            </div>
          </div>

          {/* Panel B */}
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", overflow: "hidden" }}>
            <div 
              style={{ 
                aspectRatio: "1/1", 
                background: "#08080a", 
                borderRadius: "8px", 
                border: "1px solid var(--border-color)",
                overflow: "hidden",
                position: "relative"
              }}
            >
              <div
                style={{
                  transform: `translate(${syncPan.x}px, ${syncPan.y}px) scale(${syncZoom})`,
                  width: "100%",
                  height: "100%",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  transition: isDragging ? "none" : "transform 0.15s cubic-bezier(0.16, 1, 0.3, 1)"
                }}
              >
                <img src={imgB.url} alt={imgB.name} style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain", pointerEvents: "none" }} />
              </div>
              <div style={{ position: "absolute", top: "0.5rem", left: "0.5rem", background: "rgba(0,0,0,0.7)", padding: "0.25rem 0.5rem", borderRadius: "4px", fontSize: "0.7rem", fontWeight: 700 }}>Image B</div>
            </div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", background: "var(--bg-secondary)", padding: "0.5rem 0.75rem", borderRadius: "6px" }}>
              <strong>B:</strong> {imgB.metadata.prompt || "No prompt meta"}
            </div>
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <div 
            style={{ 
              position: "relative", 
              width: "100%", 
              aspectRatio: "16/9", 
              maxHeight: "55vh",
              background: "#000", 
              borderRadius: "8px", 
              overflow: "hidden",
              userSelect: "none",
              border: "1px solid var(--border-color)"
            }}
          >
            {/* Image A (Base) */}
            <img src={imgA.url} alt={imgA.name} style={{ width: "100%", height: "100%", objectFit: "contain", display: "block" }} />
            {/* Image B (Overlay) */}
            <div style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", clipPath: `inset(0 ${100 - sliderPos}% 0 0)` }}>
              <img src={imgB.url} alt={imgB.name} style={{ width: "100%", height: "100%", objectFit: "contain", display: "block" }} />
            </div>
            {/* Splitter Line overlay bar */}
            <div style={{ position: "absolute", top: 0, bottom: 0, left: `${sliderPos}%`, transform: "translateX(-50%)", width: "3px", height: "100%", background: "var(--accent)", boxShadow: "0 0 10px rgba(0,0,0,0.5)", pointerEvents: "none" }} />
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "1rem", background: "var(--bg-secondary)", padding: "0.75rem 1rem", borderRadius: "8px", border: "1px solid var(--border-color)" }}>
            <span style={{ fontSize: "0.75rem", fontWeight: 700 }}>Image A (Left)</span>
            <input 
              type="range" 
              min="0" 
              max="100" 
              value={sliderPos} 
              onChange={(e) => setSliderPos(Number(e.target.value))} 
              style={{ flex: 1, accentColor: "var(--accent)" }} 
            />
            <span style={{ fontSize: "0.75rem", fontWeight: 700 }}>Image B (Right)</span>
          </div>
        </div>
      )}

      {/* AI Metrics Sidebar / Overlay if available */}
      {compareData && (
        <div style={{ display: "flex", gap: "1rem", background: "rgba(99,102,241,0.05)", border: "1px solid rgba(99,102,241,0.2)", borderRadius: "8px", padding: "1rem", alignItems: "center", justifyContent: "space-around" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <BarChart2 size={18} color="var(--accent)" />
            <span style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--text-main)" }}>AI Metrics:</span>
          </div>
          {compareData.semantic_similarity !== null && (
            <div style={{ fontSize: "0.8rem" }}>
              <span style={{ color: "var(--text-secondary)" }}>Semantic Similarity:</span>{" "}
              <strong style={{ color: "var(--accent)" }}>{(compareData.semantic_similarity * 100).toFixed(1)}%</strong>
            </div>
          )}
          {compareData.phash_distance !== null && (
            <div style={{ fontSize: "0.8rem" }}>
              <span style={{ color: "var(--text-secondary)" }}>Perceptual Difference:</span>{" "}
              <strong style={{ color: compareData.phash_distance <= 4 ? "#10b981" : "#ef4444" }}>
                {compareData.phash_distance} (Hash Distance)
              </strong>
            </div>
          )}
        </div>
      )}

      {/* Dynamic Prompt Diffing highlights panel */}
      <div 
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "1rem",
          background: "var(--bg-secondary)",
          border: "1px solid var(--border-color)",
          borderRadius: "8px",
          padding: "1rem"
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
          <Layers size={14} color="var(--accent)" />
          <h3 style={{ margin: 0, fontSize: "0.85rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em" }}>Interactive Prompt Diff Explorer</h3>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "1rem" }}>
          {/* Left unique */}
          <div>
            <div style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--accent)", marginBottom: "0.4rem" }}>A Only (Left unique)</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.3rem", maxHeight: "100px", overflowY: "auto" }}>
              {uniqueA.length > 0 ? (
                uniqueA.map((t: string, i: number) => (
                  <span key={i} style={{ fontSize: "0.7rem", padding: "0.15rem 0.4rem", background: "rgba(99, 102, 241, 0.08)", border: "1px solid rgba(99, 102, 241, 0.15)", borderRadius: "4px", color: "var(--accent)" }}>{t}</span>
                ))
              ) : (
                <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontStyle: "italic" }}>None</span>
              )}
            </div>
          </div>

          {/* Shared overlap */}
          <div>
            <div style={{ fontSize: "0.75rem", fontWeight: 600, color: "#10b981", marginBottom: "0.4rem" }}>Shared Overlap ({sharedTags.length})</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.3rem", maxHeight: "100px", overflowY: "auto" }}>
              {sharedTags.length > 0 ? (
                sharedTags.map((t: string, i: number) => (
                  <span key={i} style={{ fontSize: "0.7rem", padding: "0.15rem 0.4rem", background: "rgba(16, 185, 129, 0.08)", border: "1px solid rgba(16, 185, 129, 0.15)", borderRadius: "4px", color: "#10b981" }}>{t}</span>
                ))
              ) : (
                <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontStyle: "italic" }}>No overlapping tags</span>
              )}
            </div>
          </div>

          {/* Right unique */}
          <div>
            <div style={{ fontSize: "0.75rem", fontWeight: 600, color: "#f59e0b", marginBottom: "0.4rem" }}>B Only (Right unique)</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.3rem", maxHeight: "100px", overflowY: "auto" }}>
              {uniqueB.length > 0 ? (
                uniqueB.map((t: string, i: number) => (
                  <span key={i} style={{ fontSize: "0.7rem", padding: "0.15rem 0.4rem", background: "rgba(245, 158, 11, 0.08)", border: "1px solid rgba(245, 158, 11, 0.15)", borderRadius: "4px", color: "#f59e0b" }}>{t}</span>
                ))
              ) : (
                <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontStyle: "italic" }}>None</span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Metadata Diff Table */}
      {compareData && compareData.metadata_diff && compareData.metadata_diff.length > 0 && (
        <div style={{ background: "var(--bg-secondary)", border: "1px solid var(--border-color)", borderRadius: "8px", padding: "1rem" }}>
          <h4 style={{ margin: "0 0 0.75rem 0", fontSize: "0.8rem", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>Metadata Field Differences</h4>
          <table style={{ width: "100%", fontSize: "0.75rem", borderCollapse: "collapse", textAlign: "left" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border-color)", opacity: 0.6 }}>
                <th style={{ padding: "0.5rem" }}>Field Name</th>
                <th style={{ padding: "0.5rem" }}>Image A (Left)</th>
                <th style={{ padding: "0.5rem" }}>Image B (Right)</th>
              </tr>
            </thead>
            <tbody>
              {compareData.metadata_diff.map((entry: any, i: number) => (
                <tr key={i} style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }}>
                  <td style={{ padding: "0.5rem", fontWeight: 600, color: "var(--accent)" }}>{entry.field}</td>
                  <td style={{ padding: "0.5rem", color: "var(--text-secondary)" }}>{String(entry.left ?? "—")}</td>
                  <td style={{ padding: "0.5rem", color: "var(--text-secondary)" }}>{String(entry.right ?? "—")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
