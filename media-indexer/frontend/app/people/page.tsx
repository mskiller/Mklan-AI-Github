"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { fetchPeople, mediaUrl, reclusterPeople } from "@/lib/api";
import { useAuth } from "@/components/auth-provider";
import { PersonSummary } from "@/lib/types";

export default function PeoplePage() {
  const { user } = useAuth();
  const [people, setPeople] = useState<PersonSummary[]>([]);
  const [query, setQuery] = useState("");
  const [unnamedOnly, setUnnamedOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const canCurate = user?.role === "admin" || user?.role === "curator";

  const load = async (nextQuery = query, nextUnnamedOnly = unnamedOnly) => {
    setLoading(true);
    setError(null);
    try {
      setPeople(await fetchPeople({ q: nextQuery || undefined, unnamed_only: nextUnnamedOnly || undefined }));
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Unable to load people.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  return (
    <AppShell
      title="People"
      description="Review-first face clustering across your indexed media. Everyone can browse; curator actions stay restricted."
      actions={
        canCurate ? (
          <button
            type="button"
            className="button ghost-button small-button"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setError(null);
              setMessage(null);
              try {
                const result = await reclusterPeople();
                setMessage(`Reclustered faces: ${result.reassigned_faces} detections across ${result.created_people} people.`);
                await load();
              } catch (nextError) {
                setError(nextError instanceof Error ? nextError.message : "Unable to recluster people.");
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? "Reclustering..." : "Recluster"}
          </button>
        ) : undefined
      }
    >
      {error ? <section className="panel empty-state">{error}</section> : null}
      {message ? <section className="panel empty-state">{message}</section> : null}

      <section className="panel form-grid">
        <div>
          <p className="eyebrow">Directory</p>
          <h2>Browse people and review unnamed clusters</h2>
        </div>
        <form
          className="row"
          style={{ gap: "0.75rem", flexWrap: "wrap" }}
          onSubmit={(event: FormEvent) => {
            event.preventDefault();
            void load();
          }}
        >
          <label className="field" style={{ flex: "1 1 280px" }}>
            <span>Name search</span>
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search people..." />
          </label>
          <label className="field" style={{ minWidth: "180px" }}>
            <span>Queue</span>
            <select value={unnamedOnly ? "unnamed" : "all"} onChange={(event) => setUnnamedOnly(event.target.value === "unnamed")}>
              <option value="all">All people</option>
              <option value="unnamed">Unnamed only</option>
            </select>
          </label>
          <button className="button small-button" type="submit">Apply</button>
        </form>
      </section>

      <section className="panel stack">
        <div className="row-between">
          <div>
            <p className="eyebrow">Results</p>
            <h2>{people.length} people</h2>
          </div>
        </div>
        {loading ? (
          <div className="empty-state">Loading people…</div>
        ) : (
          <div className="collection-grid">
            {people.map((person) => (
              <Link key={person.id} href={`/people/${person.id}`} className="collection-card">
                <div className="collection-card-visual" style={{ minHeight: "220px", overflow: "hidden" }}>
                  {person.cover_face_url ? (
                    <img
                      src={mediaUrl(person.cover_face_url)}
                      alt={person.name ?? "Unnamed person"}
                      style={{ width: "100%", height: "220px", objectFit: "cover" }}
                    />
                  ) : (
                    <div className="empty-state" style={{ height: "220px" }}>No cover face</div>
                  )}
                </div>
                <div className="collection-card-body">
                  <strong>{person.name ?? "Unnamed person"}</strong>
                  <p className="subdued">{person.face_count} faces across {person.asset_count} assets</p>
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>
    </AppShell>
  );
}
