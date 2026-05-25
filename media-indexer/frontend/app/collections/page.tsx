"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { createCollection, fetchCollections } from "@/lib/api";
import { CollectionSummary } from "@/lib/types";

export default function CollectionsPage() {
  const { user } = useAuth();
  const [collections, setCollections] = useState<CollectionSummary[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      setCollections(await fetchCollections());
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Unable to load collections.");
    }
  };

  useEffect(() => {
    void load();
  }, []);

  return (
    <AppShell
      title="Collections"
      description="Shared image sets for review, curation, and compare staging. Admins manage them, everyone can browse them."
      actions={
        <div className="page-actions">
          <Link href="/browse-indexed" className="button subtle-button small-button">
            Browse Indexed
          </Link>
          <Link href="/search" className="button ghost-button small-button">
            Open Search
          </Link>
        </div>
      }
    >
      {error ? <section className="panel empty-state">{error}</section> : null}
      {message ? <section className="panel empty-state">{message}</section> : null}
      {user?.capabilities.can_manage_collections ? (
        <section className="panel form-grid">
          <div>
            <p className="eyebrow">Create Collection</p>
            <h2>New shared set</h2>
          </div>
          <form
            className="form-grid"
            onSubmit={async (event: FormEvent) => {
              event.preventDefault();
              setBusy(true);
              setError(null);
              setMessage(null);
              try {
                await createCollection({ name, description });
                setName("");
                setDescription("");
                setMessage("Collection created.");
                await load();
              } catch (nextError) {
                setError(nextError instanceof Error ? nextError.message : "Unable to create collection.");
              } finally {
                setBusy(false);
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
            <button className="button small-button" type="submit" disabled={busy}>
              {busy ? "Creating..." : "Create Collection"}
            </button>
          </form>
        </section>
      ) : null}
      <section className="panel stack">
        <div className="row-between">
          <div>
            <p className="eyebrow">Collection Library</p>
            <h2>{collections.length} collections</h2>
          </div>
        </div>
        <div className="collection-grid">
          {collections.map((collection) => (
            <Link key={collection.id} href={`/collections/${collection.id}`} className="collection-card">
              <div className="collection-card-visual">
                <span className="pill">{collection.asset_count} assets</span>
              </div>
              <div className="collection-card-body">
                <strong>{collection.name}</strong>
                {collection.description ? <p className="subdued">{collection.description}</p> : <p className="subdued">Open shared gallery</p>}
              </div>
            </Link>
          ))}
        </div>
      </section>
    </AppShell>
  );
}
