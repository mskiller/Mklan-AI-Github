"use client";

import { useState } from "react";
import { apiFetch } from "@/lib/api";
import { useToast } from "@/components/use-toast";

interface ShareModalProps {
  targetId: string;
  targetType: "asset" | "collection";
  onClose: () => void;
}

export function ShareModal({ targetId, targetType, onClose }: ShareModalProps) {
  const [loading, setLoading] = useState(false);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [expiresAt, setExpiresAt] = useState("");
  const [allowDownload, setAllowDownload] = useState(false);
  const { push } = useToast();

  const handleCreate = async () => {
    setLoading(true);
    try {
      const res = await apiFetch<{ id: string }>("/share", {
        method: "POST",
        body: JSON.stringify({
          target_id: targetId,
          target_type: targetType,
          expires_at: expiresAt || null,
          allow_download: allowDownload
        }),
      });
      
      const fullUrl = `${window.location.origin}/share/${res.id}`;
      setShareUrl(fullUrl);
      push("Share link created!", "success");
    } catch (e) {
      push("Failed to create share link", "error");
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = () => {
    if (shareUrl) {
      void navigator.clipboard.writeText(shareUrl);
      push("Copied to clipboard!", "success");
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, color: "white" }}>
      <div className="modal-content panel stack" onClick={(e) => e.stopPropagation()} style={{ background: "var(--bg-paper)", padding: "2rem", borderRadius: "var(--radius-lg)", maxWidth: "400px", width: "90%", color: "var(--text-main)" }}>
        <h3>Share {targetType}</h3>
        
        {!shareUrl ? (
          <div className="stack" style={{ gap: "1rem" }}>
            <div className="input-group">
              <label className="eyebrow">Expiry (optional)</label>
              <input type="datetime-local" className="input" value={expiresAt} onChange={(e) => setExpiresAt(e.target.value)} />
            </div>
            
            <div className="row" style={{ gap: "0.5rem", alignItems: "center" }}>
              <input type="checkbox" id="allow-download" checked={allowDownload} onChange={(e) => setAllowDownload(e.target.checked)} />
              <label htmlFor="allow-download">Allow Download</label>
            </div>
            
            <button className="button accent-button" onClick={handleCreate} disabled={loading}>
              {loading ? "Creating..." : "Generate Share Link"}
            </button>
          </div>
        ) : (
          <div className="stack" style={{ gap: "1rem" }}>
            <p className="subdued">Copy the link below to share:</p>
            <div className="row" style={{ gap: "0.5rem" }}>
              <input type="text" readOnly className="input" value={shareUrl} style={{ flex: 1 }} />
              <button className="button accent-button" onClick={copyToClipboard}>Copy</button>
            </div>
            <button className="button ghost-button" onClick={onClose}>Close</button>
          </div>
        )}
      </div>
    </div>
  );
}
