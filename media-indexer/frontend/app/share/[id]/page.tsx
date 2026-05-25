"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { fetchPublicShare, mediaUrl } from "@/lib/api";
import { PublicShareResponse } from "@/lib/types";

export default function PublicSharePage() {
  const { id } = useParams();
  const [data, setData] = useState<PublicShareResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (id) {
      void loadShare();
    }
  }, [id]);

  const loadShare = async () => {
    try {
      const res = await fetchPublicShare(String(id));
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load share content");
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <div className="centered-container">Loading shared content...</div>;
  if (error) return <div className="centered-container error-text">{error}</div>;
  if (!data) return null;

  return (
    <div className="public-share-page" style={{ padding: "2rem", minHeight: "100vh", background: "var(--bg-main)" }}>
      <header style={{ marginBottom: "3rem", textAlign: "center" }}>
        <h1 style={{ fontSize: "2rem", marginBottom: "0.5rem" }}>{data.label}</h1>
        <p className="subdued">Shared via Media Indexer</p>
      </header>

      <main className="share-content">
        {data.type === "asset" && data.item && (
          <div style={{ maxWidth: "800px", margin: "0 auto" }}>
             <img 
               src={mediaUrl(data.item.preview_url) ?? undefined} 
               alt={data.item.filename} 
               style={{ width: "100%", borderRadius: "var(--radius-lg)", boxShadow: "var(--shadow-lg)" }} 
             />
             <div style={{ marginTop: "1rem", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
               <div>
                 <h3>{data.item.filename}</h3>
                 <p className="subdued">{(data.item.size_bytes / 1024 / 1024).toFixed(2)} MB</p>
               </div>
               {data.allow_download && data.item.content_url ? (
                 <a href={mediaUrl(data.item.content_url) ?? undefined} download className="button accent-button">Download Original</a>
               ) : null}
             </div>
          </div>
        )}

        {data.type === "collection" && data.items.length > 0 && (
          <div className="gallery-grid" style={{ gap: "1rem" }}>
            {data.items.map((item) => (
              <article key={item.id} className="panel stack" style={{ gap: "0.75rem" }}>
                {item.preview_url ? (
                  <img
                    src={mediaUrl(item.preview_url) ?? undefined}
                    alt={item.filename}
                    style={{ width: "100%", aspectRatio: "1 / 1", objectFit: "cover", borderRadius: "var(--radius-md)" }}
                  />
                ) : (
                  <div className="empty-state">Preview unavailable</div>
                )}
                <div className="stack" style={{ gap: "0.4rem" }}>
                  <strong>{item.filename}</strong>
                  <p className="subdued">{(item.size_bytes / 1024 / 1024).toFixed(2)} MB</p>
                  {data.allow_download && item.content_url ? (
                    <a href={mediaUrl(item.content_url) ?? undefined} download className="button subtle-button small-button">
                      Download
                    </a>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        )}

        {data.type === "collection" && data.items.length === 0 ? (
          <div className="centered-container">This shared collection is empty.</div>
        ) : null}
      </main>
    </div>
  );
}
