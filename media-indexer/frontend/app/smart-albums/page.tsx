"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useModuleRegistry } from "@/components/module-registry-provider";
import { createSmartAlbum, deleteSmartAlbum, fetchPeople, fetchSmartAlbums, fetchSources } from "@/lib/api";
import { PersonSummary, SmartAlbumRule, SmartAlbumSummary, Source } from "@/lib/types";

const EMPTY_RULE: SmartAlbumRule = {
  source_ids: [],
  tags_any: [],
  auto_tags_any: [],
  people_ids: [],
};

export default function SmartAlbumsPage() {
  const { isModuleEnabled } = useModuleRegistry();
  const [albums, setAlbums] = useState<SmartAlbumSummary[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [people, setPeople] = useState<PersonSummary[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [rule, setRule] = useState<SmartAlbumRule>(EMPTY_RULE);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const peopleModuleEnabled = isModuleEnabled("people");

  const load = async () => {
    try {
      const [nextAlbums, nextSources, nextPeople] = await Promise.all([
        fetchSmartAlbums(),
        fetchSources(),
        peopleModuleEnabled ? fetchPeople() : Promise.resolve([]),
      ]);
      setAlbums(nextAlbums);
      setSources(nextSources);
      setPeople(nextPeople.filter((entry) => entry.name !== null));
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Unable to load smart albums.");
    }
  };

  useEffect(() => {
    void load();
  }, [peopleModuleEnabled]);

  const suggested = useMemo(() => albums.filter((album) => album.source === "suggested"), [albums]);
  const owned = useMemo(() => albums.filter((album) => album.source !== "suggested"), [albums]);

  const toggleValue = (values: string[], value: string) =>
    values.includes(value) ? values.filter((entry) => entry !== value) : [...values, value];

  return (
    <AppShell
      title="My Smart Albums"
      description="Owner-scoped rule-based galleries plus nightly suggestions driven by your curation behavior."
    >
      {error ? <section className="panel empty-state">{error}</section> : null}
      {message ? <section className="panel empty-state">{message}</section> : null}

      <section className="panel form-grid">
        <div>
          <p className="eyebrow">Create Album</p>
          <h2>Build a rule-based gallery</h2>
        </div>
        <form
          className="form-grid"
          onSubmit={async (event: FormEvent) => {
            event.preventDefault();
            setBusy(true);
            setError(null);
            setMessage(null);
            try {
              await createSmartAlbum({
                name,
                description,
                enabled: true,
                rule: {
                  ...rule,
                  tags_any: rule.tags_any.filter(Boolean),
                  auto_tags_any: rule.auto_tags_any.filter(Boolean),
                },
              });
              setName("");
              setDescription("");
              setRule(EMPTY_RULE);
              setMessage("Smart album created.");
              await load();
            } catch (nextError) {
              setError(nextError instanceof Error ? nextError.message : "Unable to create smart album.");
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
          <label className="field">
            <span>Media type</span>
            <select value={rule.media_type ?? ""} onChange={(event) => setRule((current) => ({ ...current, media_type: (event.target.value || null) as SmartAlbumRule["media_type"] }))}>
              <option value="">Any</option>
              <option value="image">Image</option>
              <option value="video">Video</option>
            </select>
          </label>
          <label className="field">
            <span>Manual tags</span>
            <input
              value={rule.tags_any.join(", ")}
              onChange={(event) => setRule((current) => ({ ...current, tags_any: event.target.value.split(",").map((item) => item.trim().toLowerCase()).filter(Boolean) }))}
              placeholder="portrait, travel"
            />
          </label>
          <label className="field">
            <span>Accepted auto tags</span>
            <input
              value={rule.auto_tags_any.join(", ")}
              onChange={(event) => setRule((current) => ({ ...current, auto_tags_any: event.target.value.split(",").map((item) => item.trim().toLowerCase()).filter(Boolean) }))}
              placeholder="beach, sunset"
            />
          </label>
          <label className="field">
            <span>Review status</span>
            <select value={rule.review_status ?? ""} onChange={(event) => setRule((current) => ({ ...current, review_status: (event.target.value || null) as SmartAlbumRule["review_status"] }))}>
              <option value="">Any</option>
              <option value="approved">Approved</option>
              <option value="favorite">Favorite</option>
              <option value="rejected">Rejected</option>
              <option value="unreviewed">Unreviewed</option>
            </select>
          </label>
          <div className="field">
            <span>Sources</span>
            <div className="chip-row">
              {sources.map((source) => (
                <button
                  key={source.id}
                  type="button"
                  className={`chip ${rule.source_ids.includes(source.id) ? "chip-accent" : ""}`}
                  onClick={() => setRule((current) => ({ ...current, source_ids: toggleValue(current.source_ids, source.id) }))}
                >
                  {source.name}
                </button>
              ))}
            </div>
          </div>
          <div className="field">
            <span>People</span>
            {!peopleModuleEnabled ? <p className="subdued">The people module is disabled, so person-based rules are unavailable right now.</p> : null}
            <div className="chip-row">
              {people.slice(0, 20).map((person) => (
                <button
                  key={person.id}
                  type="button"
                  className={`chip ${rule.people_ids.includes(person.id) ? "chip-accent" : ""}`}
                  onClick={() => setRule((current) => ({ ...current, people_ids: toggleValue(current.people_ids, person.id) }))}
                >
                  {person.name}
                </button>
              ))}
            </div>
          </div>
          <div className="two-column">
            <label className="field">
              <span>Min rating</span>
              <input
                type="number"
                min={1}
                max={5}
                value={rule.min_rating ?? ""}
                onChange={(event) => setRule((current) => ({ ...current, min_rating: event.target.value ? Number(event.target.value) : null }))}
              />
            </label>
            <label className="field">
              <span>Date from</span>
              <input type="date" value={rule.date_from ?? ""} onChange={(event) => setRule((current) => ({ ...current, date_from: event.target.value || null }))} />
            </label>
          </div>
          <div className="two-column">
            <label className="field">
              <span>Date to</span>
              <input type="date" value={rule.date_to ?? ""} onChange={(event) => setRule((current) => ({ ...current, date_to: event.target.value || null }))} />
            </label>
            <label className="field">
              <span>GPS filter</span>
              <select value={rule.has_gps === true ? "yes" : rule.has_gps === false ? "no" : ""} onChange={(event) => setRule((current) => ({ ...current, has_gps: event.target.value === "" ? null : event.target.value === "yes" }))}>
                <option value="">Any</option>
                <option value="yes">Has GPS</option>
                <option value="no">No GPS</option>
              </select>
            </label>
          </div>
          <label className="field">
            <span>Flagged filter</span>
            <select value={rule.flagged === true ? "yes" : rule.flagged === false ? "no" : ""} onChange={(event) => setRule((current) => ({ ...current, flagged: event.target.value === "" ? null : event.target.value === "yes" }))}>
              <option value="">Any</option>
              <option value="yes">Flagged only</option>
              <option value="no">Not flagged</option>
            </select>
          </label>
          <button className="button small-button" type="submit" disabled={busy}>
            {busy ? "Creating..." : "Create Smart Album"}
          </button>
        </form>
      </section>

      <section className="panel stack">
        <div>
          <p className="eyebrow">Suggested For You</p>
          <h2>{suggested.length} suggested albums</h2>
        </div>
        <div className="collection-grid">
          {suggested.map((album) => (
            <Link key={album.id} href={`/smart-albums/${album.id}`} className="collection-card">
              <div className="collection-card-visual">
                <span className="pill">{album.asset_count} assets</span>
              </div>
              <div className="collection-card-body">
                <strong>{album.name}</strong>
                <p className="subdued">{album.description ?? "Suggested from recent curation signals."}</p>
                {album.status !== "active" ? <p className="subdued">{album.status}: {album.degraded_reason ?? "Waiting for module dependencies."}</p> : null}
              </div>
            </Link>
          ))}
        </div>
      </section>

      <section className="panel stack">
        <div>
          <p className="eyebrow">My Albums</p>
          <h2>{owned.length} smart albums</h2>
        </div>
        <div className="collection-grid">
          {owned.map((album) => (
            <article key={album.id} className="collection-card">
              <Link href={`/smart-albums/${album.id}`} className="collection-card-visual">
                <span className="pill">{album.asset_count} assets</span>
              </Link>
              <div className="collection-card-body">
                <strong>{album.name}</strong>
                <p className="subdued">{album.description ?? "Rule-based gallery."}</p>
                <div className="chip-row">
                  <span className="chip">{album.status}</span>
                  {!album.enabled ? <span className="chip">disabled</span> : null}
                </div>
                {album.degraded_reason ? <p className="subdued">{album.degraded_reason}</p> : null}
                <div className="card-actions">
                  <Link href={`/smart-albums/${album.id}`} className="button small-button">Open</Link>
                  <button
                    type="button"
                    className="button ghost-button small-button"
                    onClick={async () => {
                      try {
                        await deleteSmartAlbum(album.id);
                        await load();
                      } catch (nextError) {
                        setError(nextError instanceof Error ? nextError.message : "Unable to delete smart album.");
                      }
                    }}
                  >
                    Delete
                  </button>
                </div>
              </div>
            </article>
          ))}
        </div>
      </section>
    </AppShell>
  );
}
