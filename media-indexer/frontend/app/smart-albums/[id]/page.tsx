"use client";

import { FormEvent, useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { GalleryTile } from "@/components/gallery-tile";
import { fetchSmartAlbum, mediaUrl, syncSmartAlbum, updateSmartAlbum } from "@/lib/api";
import { SmartAlbumDetail } from "@/lib/types";

export default function SmartAlbumDetailPage() {
  const params = useParams<{ id: string }>();
  const [album, setAlbum] = useState<SmartAlbumDetail | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = async () => {
    try {
      const nextAlbum = await fetchSmartAlbum(params.id);
      setAlbum(nextAlbum);
      setName(nextAlbum.name);
      setDescription(nextAlbum.description ?? "");
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Unable to load smart album.");
    }
  };

  useEffect(() => {
    void load();
  }, [params.id]);

  return (
    <AppShell
      title={album?.name ?? "Smart Album"}
      description={album ? `${album.asset_count} matching assets · ${album.status}.` : "Rule-based gallery detail."}
      actions={
        <button
          type="button"
          className="button ghost-button small-button"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setError(null);
            try {
              await syncSmartAlbum(params.id);
              setMessage("Album synced.");
              await load();
            } catch (nextError) {
              setError(nextError instanceof Error ? nextError.message : "Unable to sync smart album.");
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? "Syncing..." : "Sync"}
        </button>
      }
    >
      {error ? <section className="panel empty-state">{error}</section> : null}
      {message ? <section className="panel empty-state">{message}</section> : null}
      {album?.degraded_reason ? (
        <section className="panel empty-state">
          <h2>Album Status: {album.status}</h2>
          <p className="subdued">{album.degraded_reason}</p>
        </section>
      ) : null}

      {album ? (
        <section className="two-column">
          <form
            className="panel form-grid"
            onSubmit={async (event: FormEvent) => {
              event.preventDefault();
              setBusy(true);
              setError(null);
              try {
                await updateSmartAlbum(album.id, { name, description });
                setMessage("Album updated.");
                await load();
              } catch (nextError) {
                setError(nextError instanceof Error ? nextError.message : "Unable to update album.");
              } finally {
                setBusy(false);
              }
            }}
          >
            <div>
              <p className="eyebrow">Album</p>
              <h2>Edit metadata</h2>
            </div>
            <div className="chip-row">
              <span className="chip">{album.status}</span>
              {!album.enabled ? <span className="chip">disabled</span> : null}
            </div>
            <label className="field">
              <span>Name</span>
              <input value={name} onChange={(event) => setName(event.target.value)} />
            </label>
            <label className="field">
              <span>Description</span>
              <textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={3} />
            </label>
            <button className="button small-button" type="submit" disabled={busy}>
              {busy ? "Saving..." : "Save"}
            </button>
          </form>

          <section className="panel stack">
            <div>
              <p className="eyebrow">Rule</p>
              <h2>Normalized filter</h2>
            </div>
            <pre className="prompt-content subdued" style={{ maxHeight: "320px", overflow: "auto" }}>
              {JSON.stringify(album.rule, null, 2)}
            </pre>
          </section>
        </section>
      ) : null}

      <section className="panel stack">
        <div>
          <p className="eyebrow">Assets</p>
          <h2>{album?.items.length ?? 0} loaded matches</h2>
        </div>
        <div className="gallery-grid">
          {album?.items.map((asset) => (
            <GalleryTile
              key={asset.id}
              imageSrc={mediaUrl(asset.preview_url)}
              blurHash={asset.blur_hash}
              alt={asset.filename}
              title={asset.filename}
              subtitle={asset.relative_path}
              promptExcerpt={asset.prompt_excerpt}
              promptTags={asset.prompt_tags}
              onOpen={() => {
                window.location.href = `/assets/${asset.id}`;
              }}
              menuActions={[
                {
                  label: "Open Detail",
                  onSelect: () => {
                    window.location.href = `/assets/${asset.id}`;
                  },
                },
              ]}
              workflowAvailable={asset.workflow_export_available}
            />
          ))}
        </div>
      </section>
    </AppShell>
  );
}
