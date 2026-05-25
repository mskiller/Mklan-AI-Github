"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { CompareSelectionTray } from "@/components/compare-selection-tray";
import { GalleryTile } from "@/components/gallery-tile";
import { ImageExplorerOverlay } from "@/components/image-explorer-overlay";
import { useAuth } from "@/components/auth-provider";
import { deleteCollection, fetchCollection, mediaUrl, removeAssetFromCollection, updateCollection } from "@/lib/api";
import { copyTextToClipboard } from "@/lib/clipboard";
import { CollectionDetail } from "@/lib/types";

export default function CollectionDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { user } = useAuth();
  const [collection, setCollection] = useState<CollectionDetail | null>(null);
  const [selectedAssets, setSelectedAssets] = useState<Array<{ id: string; name: string }>>([]);
  const [selectionMode, setSelectionMode] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [explorerIndex, setExplorerIndex] = useState<number | null>(null);
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  const load = async () => {
    try {
      const nextCollection = await fetchCollection(params.id, 1, 72);
      setCollection(nextCollection);
      setName(nextCollection.name);
      setDescription(nextCollection.description);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Unable to load collection.");
    }
  };

  useEffect(() => {
    void load();
  }, [params.id]);

  useEffect(() => {
    if (sentinelRef.current) {
      // sentinel kept for future pagination extension; page currently loads enough for gallery use.
    }
  }, [collection?.items.length]);

  const toggleSelection = (assetId: string, assetName: string) => {
    setSelectedAssets((current) => {
      const exists = current.some((item) => item.id === assetId);
      if (exists) {
        return current.filter((item) => item.id !== assetId);
      }
      const next = { id: assetId, name: assetName };
      if (current.length === 2) {
        return [current[1], next];
      }
      return [...current, next];
    });
  };

  const compareHref = selectedAssets.length === 2 ? `/compare?a=${selectedAssets[0].id}&b=${selectedAssets[1].id}` : null;
  const explorerItems =
    collection?.items.map((item) => ({
      key: item.id,
      title: item.filename,
      subtitle: [item.source_name, item.generator].filter(Boolean).join(" · ") || undefined,
      promptExcerpt: item.prompt_excerpt,
      promptTags: item.prompt_tags,
      previewSrc: mediaUrl(item.preview_url),
      contentSrc: mediaUrl(item.content_url),
      deepzoomUrl: mediaUrl(item.deepzoom_url),
      detailHref: `/assets/${item.id}`,
      similarHref: `/assets/${item.id}/similar`,
      sourceContext: item.relative_path,
      metadataSummary: [
        ...(item.width && item.height ? [{ label: "Dimensions", value: `${item.width} x ${item.height}` }] : []),
        { label: "Source", value: item.source_name },
      ],
    })) ?? [];

  return (
    <AppShell
      title={collection ? collection.name : "Collection"}
      description={collection?.description || "Shared image gallery collection."}
      actions={
        <div className="page-actions">
          <Link href="/collections" className="button subtle-button small-button">
            Back to Collections
          </Link>
          <Link href="/browse-indexed" className="button ghost-button small-button">
            Browse Indexed
          </Link>
        </div>
      }
    >
      {error ? <section className="panel empty-state">{error}</section> : null}
      {message ? <section className="panel empty-state">{message}</section> : null}
      {collection ? (
        <>
          <ImageExplorerOverlay
            open={explorerIndex !== null}
            items={explorerItems}
            activeIndex={explorerIndex ?? 0}
            onClose={() => setExplorerIndex(null)}
            onActiveIndexChange={(next) => setExplorerIndex(next)}
          />
          <CompareSelectionTray
            selectionMode={selectionMode}
            selectedCount={selectedAssets.length}
            compareHref={compareHref}
            onToggleSelectionMode={() => setSelectionMode((value) => !value)}
            onClearSelection={() => setSelectedAssets([])}
            hint="Collections stay gallery-first too. Hover or long-press to inspect prompt tags and remove assets if you’re an admin."
          />
          {user?.capabilities.can_manage_collections ? (
            <section className="panel form-grid">
              <div>
                <p className="eyebrow">Collection Admin</p>
                <h2>Edit collection</h2>
              </div>
              <form
                className="form-grid"
                onSubmit={async (event: FormEvent) => {
                  event.preventDefault();
                  setBusy("save");
                  setError(null);
                  setMessage(null);
                  try {
                    await updateCollection(collection.id, { name, description });
                    setMessage("Collection updated.");
                    await load();
                  } catch (nextError) {
                    setError(nextError instanceof Error ? nextError.message : "Unable to update collection.");
                  } finally {
                    setBusy(null);
                  }
                }}
              >
                <label className="field">
                  <span>Name</span>
                  <input value={name} onChange={(event) => setName(event.target.value)} />
                </label>
                <label className="field">
                  <span>Description</span>
                  <textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={3} />
                </label>
                <div className="card-actions">
                  <button className="button small-button" type="submit" disabled={busy === "save"}>
                    {busy === "save" ? "Saving..." : "Save Changes"}
                  </button>
                  <button
                    className="button ghost-button small-button"
                    type="button"
                    disabled={busy === "delete"}
                    onClick={async () => {
                      if (!window.confirm(`Delete collection ${collection.name}?`)) {
                        return;
                      }
                      setBusy("delete");
                      try {
                        await deleteCollection(collection.id);
                        router.push("/collections");
                      } catch (nextError) {
                        setError(nextError instanceof Error ? nextError.message : "Unable to delete collection.");
                      } finally {
                        setBusy(null);
                      }
                    }}
                  >
                    Delete Collection
                  </button>
                </div>
              </form>
            </section>
          ) : null}
          <section className="panel stack">
            <div className="row-between">
              <div>
                <p className="eyebrow">Collection Gallery</p>
                <h2>{collection.total} images</h2>
              </div>
            </div>
            <div className="gallery-grid">
              {collection.items.map((item) => {
                const selected = selectedAssets.some((entry) => entry.id === item.id);
                const compareTarget = selectedAssets.find((entry) => entry.id !== item.id);
                return (
                  <GalleryTile
                    key={item.id}
                    imageSrc={mediaUrl(item.preview_url)}
                    alt={item.filename}
                    title={item.filename}
                    subtitle={[item.source_name, item.generator].filter(Boolean).join(" · ") || undefined}
                    promptExcerpt={item.prompt_excerpt}
                    promptTags={item.prompt_tags}
                    selected={selected}
                    selectionMode={selectionMode}
                    onOpen={() => setExplorerIndex(collection.items.findIndex((entry) => entry.id === item.id))}
                    onToggleSelect={() => toggleSelection(item.id, item.filename)}
                    menuActions={[
                      { label: "Open Explorer", onSelect: () => setExplorerIndex(collection.items.findIndex((entry) => entry.id === item.id)) },
                      { label: "Open Detail", onSelect: () => router.push(`/assets/${item.id}`), variant: "subtle" },
                      { label: "Open Similar", onSelect: () => router.push(`/assets/${item.id}/similar`), variant: "subtle" },
                      { label: selected ? "Deselect for Compare" : "Select for Compare", onSelect: () => toggleSelection(item.id, item.filename), variant: "ghost" },
                      ...(compareTarget
                        ? [{ label: "Compare with Selected", onSelect: () => router.push(`/compare?a=${compareTarget.id}&b=${item.id}`), variant: "subtle" as const }]
                        : []),
                      {
                        label: "Copy Danbooru Tags",
                        onSelect: async () => {
                          if (item.prompt_tag_string) {
                            await copyTextToClipboard(item.prompt_tag_string);
                          }
                        },
                        variant: "ghost",
                        disabled: !item.prompt_tag_string,
                      },
                      ...(user?.capabilities.can_manage_collections
                        ? [{
                            label: "Remove from Collection",
                            onSelect: async () => {
                              try {
                                await removeAssetFromCollection(collection.id, item.id);
                                await load();
                              } catch (nextError) {
                                setError(nextError instanceof Error ? nextError.message : "Unable to remove asset from collection.");
                              }
                            },
                            variant: "danger" as const,
                          }]
                        : []),
                    ]}
                  />
                );
              })}
            </div>
            <div ref={sentinelRef} className="infinite-sentinel" />
          </section>
        </>
      ) : (
        <section className="panel empty-state">Loading collection…</section>
      )}
    </AppShell>
  );
}
