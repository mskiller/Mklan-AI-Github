import React, { useState } from "react";
import { Film, Clock, Scissors, Check, EyeOff, Play, GripVertical, AlertCircle } from "lucide-react";
import type { Sequence } from "../types";

interface VideoTimelineProps {
  sequences: Sequence[];
  activeSequenceId: string | null;
  onSelectSequence: (id: string) => void;
  onUpdateSequenceAssembly: (id: string, include: boolean, trimInMs?: number, trimOutMs?: number) => void;
  onReorderSequences?: (reorderedIds: string[]) => void;
}

export function VideoTimeline({
  sequences,
  activeSequenceId,
  onSelectSequence,
  onUpdateSequenceAssembly,
  onReorderSequences,
}: VideoTimelineProps) {
  const [draggedId, setDraggedId] = useState<string | null>(null);
  // Local optimistic order — keeps UI responsive while the API call is in-flight
  const [localOrder, setLocalOrder] = useState<string[]>([]);

  const baseOrder = [...sequences].sort((a, b) => a.order - b.order);
  // If a drag is in progress use local order, else fall back to server order
  const sortedSequences =
    localOrder.length > 0
      ? localOrder
          .map((id) => baseOrder.find((s) => s.id === id))
          .filter((s): s is Sequence => s !== undefined)
      : baseOrder;

  const handleDragStart = (e: React.DragEvent, id: string) => {
    setDraggedId(id);
    setLocalOrder(baseOrder.map((s) => s.id));
    e.dataTransfer.effectAllowed = "move";
  };

  const handleDragOver = (e: React.DragEvent, targetId: string) => {
    e.preventDefault();
    if (!draggedId || draggedId === targetId) return;

    // Update local visual order immediately on hover — does NOT call the API
    setLocalOrder((prev) => {
      const current = prev.length > 0 ? prev : baseOrder.map((s) => s.id);
      const draggedIndex = current.indexOf(draggedId);
      const targetIndex = current.indexOf(targetId);
      if (draggedIndex === -1 || targetIndex === -1) return current;
      const next = [...current];
      const [moved] = next.splice(draggedIndex, 1);
      next.splice(targetIndex, 0, moved);
      return next;
    });
  };

  const handleDragEnd = () => {
    // Only fire the API call once when the user releases (not on every pixel of movement)
    if (draggedId && onReorderSequences && localOrder.length > 0) {
      onReorderSequences(localOrder);
    }
    setDraggedId(null);
    setLocalOrder([]);
  };

  const calculateWidth = (duration: number) => {
    const scale = 15; // px per second
    return Math.max(80, Math.min(300, duration * scale));
  };

  const formatMsToSeconds = (ms: number) => {
    return (ms / 1000).toFixed(1) + "s";
  };

  return (
    <div
      style={{
        background: "rgba(20, 20, 25, 0.45)",
        border: "1px solid rgba(255, 255, 255, 0.08)",
        borderRadius: "20px",
        padding: "1.25rem",
        backdropFilter: "blur(24px)",
        boxShadow: "0 8px 32px rgba(0, 0, 0, 0.3)",
        display: "flex",
        flexDirection: "column",
        gap: "1rem",
        marginTop: "1.5rem",
      }}
    >
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <Film size={18} style={{ color: "#7c6aff" }} />
          <span style={{ fontWeight: 600, fontSize: "0.95rem", letterSpacing: "0.01em" }}>
            Sequencer Timeline Track
          </span>
        </div>
        <div style={{ fontSize: "0.75rem", color: "var(--muted)", display: "flex", gap: "1rem" }}>
          <span style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}>
            <Clock size={12} />
            Total Clips: {sequences.length}
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}>
            <Scissors size={12} />
            Draggable to Reorder
          </span>
        </div>
      </div>

      {/* Tracks Container */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "0.75rem",
          background: "rgba(0,0,0,0.2)",
          padding: "1rem",
          borderRadius: "12px",
          border: "1px solid rgba(255, 255, 255, 0.03)",
          overflowX: "auto",
        }}
      >
        {/* Track Grid */}
        <div style={{ display: "flex", gap: "0.5rem", minWidth: "100%", paddingBottom: "0.5rem" }}>
          {sortedSequences.length === 0 ? (
            <div
              style={{
                width: "100%",
                height: "80px",
                display: "flex",
                flexDirection: "column",
                justifyContent: "center",
                alignItems: "center",
                gap: "0.5rem",
                color: "var(--muted)",
                fontSize: "0.8rem",
              }}
            >
              <AlertCircle size={16} />
              No sequences created in this scene yet. Generate some beats or scenes first!
            </div>
          ) : (
            sortedSequences.map((seq, index) => {
              const width = calculateWidth(seq.target_duration_s);
              const isActive = seq.id === activeSequenceId;
              const isIncluded = seq.include_in_assembly !== false;
              const hasVideo = !!(seq.approved_video_asset || seq.uploaded_video_asset);
              const videoUrl = seq.approved_video_asset?.asset_url || seq.uploaded_video_asset?.asset_url;

              return (
                <div
                  key={seq.id}
                  draggable
                  onDragStart={(e) => handleDragStart(e, seq.id)}
                  onDragOver={(e) => handleDragOver(e, seq.id)}
                  onDragEnd={handleDragEnd}
                  onClick={() => onSelectSequence(seq.id)}
                  style={{
                    width: `${width}px`,
                    minWidth: "120px",
                    height: "95px",
                    background: isActive
                      ? "linear-gradient(135deg, rgba(124, 106, 255, 0.25), rgba(124, 106, 255, 0.1))"
                      : "rgba(255, 255, 255, 0.03)",
                    border: isActive
                      ? "1px solid #7c6aff"
                      : "1px solid rgba(255, 255, 255, 0.08)",
                    borderRadius: "10px",
                    padding: "0.6rem",
                    cursor: "pointer",
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "space-between",
                    transition: "all 0.2s ease-in-out",
                    opacity: isIncluded ? 1 : 0.45,
                    position: "relative",
                  }}
                  className="timeline-clip-card"
                >
                  {/* Draggable Icon */}
                  <div
                    style={{
                      position: "absolute",
                      right: "6px",
                      top: "6px",
                      opacity: 0.35,
                      cursor: "grab",
                    }}
                  >
                    <GripVertical size={12} />
                  </div>

                  {/* Order & Title */}
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.15rem" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}>
                      <span
                        style={{
                          fontSize: "0.65rem",
                          fontWeight: 700,
                          background: isActive ? "#7c6aff" : "rgba(255,255,255,0.1)",
                          padding: "0.1rem 0.3rem",
                          borderRadius: "4px",
                          color: "#fff",
                        }}
                      >
                        S{index + 1}
                      </span>
                      <span
                        style={{
                          fontSize: "0.72rem",
                          fontWeight: 600,
                          whiteSpace: "nowrap",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          maxWidth: "80%",
                        }}
                      >
                        {seq.title || "Untitled Sequence"}
                      </span>
                    </div>
                    <span style={{ fontSize: "0.65rem", color: "var(--muted)" }}>
                      Duration: {seq.target_duration_s}s
                    </span>
                  </div>

                  {/* Thumbnail Preview Area */}
                  {hasVideo && videoUrl ? (
                    <div
                      style={{
                        height: "28px",
                        background: "rgba(0,0,0,0.4)",
                        borderRadius: "4px",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        fontSize: "0.6rem",
                        color: "#81c7b8",
                        gap: "0.25rem",
                      }}
                    >
                      <Play size={8} fill="#81c7b8" />
                      Rendered
                    </div>
                  ) : (
                    <div
                      style={{
                        height: "28px",
                        background: "rgba(255,255,255,0.02)",
                        border: "1px dashed rgba(255,255,255,0.06)",
                        borderRadius: "4px",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        fontSize: "0.55rem",
                        color: "var(--muted)",
                      }}
                    >
                      No Video
                    </div>
                  )}

                  {/* Controls (Exclude / Trim indicator) */}
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      fontSize: "0.65rem",
                      marginTop: "0.25rem",
                    }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    {/* Include Toggle */}
                    <button
                      onClick={() => onUpdateSequenceAssembly(seq.id, !isIncluded)}
                      style={{
                        background: isIncluded ? "rgba(74, 222, 128, 0.15)" : "rgba(255, 87, 87, 0.1)",
                        color: isIncluded ? "#4ade80" : "#ff5757",
                        padding: "0.15rem 0.35rem",
                        borderRadius: "4px",
                        display: "flex",
                        alignItems: "center",
                        gap: "0.15rem",
                        fontSize: "0.6rem",
                      }}
                    >
                      {isIncluded ? <Check size={8} /> : <EyeOff size={8} />}
                      {isIncluded ? "Active" : "Muted"}
                    </button>

                    {/* Trim Values Indicator */}
                    {(seq.trim_in_ms > 0 || seq.trim_out_ms > 0) && (
                      <span style={{ color: "var(--warning)", fontSize: "0.58rem" }}>
                        Trimmed
                      </span>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
