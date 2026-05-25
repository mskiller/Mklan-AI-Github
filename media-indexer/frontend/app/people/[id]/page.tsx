"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { GalleryTile } from "@/components/gallery-tile";
import { fetchPeople, fetchPerson, mediaUrl, mergePerson, updatePerson } from "@/lib/api";
import { useAuth } from "@/components/auth-provider";
import { PersonDetail, PersonSummary } from "@/lib/types";

export default function PersonDetailPage() {
  const params = useParams<{ id: string }>();
  const { user } = useAuth();
  const [person, setPerson] = useState<PersonDetail | null>(null);
  const [allPeople, setAllPeople] = useState<PersonSummary[]>([]);
  const [name, setName] = useState("");
  const [mergeSourceId, setMergeSourceId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const canCurate = user?.role === "admin" || user?.role === "curator";

  const load = async () => {
    try {
      const [nextPerson, nextPeople] = await Promise.all([
        fetchPerson(params.id),
        canCurate ? fetchPeople() : Promise.resolve([]),
      ]);
      setPerson(nextPerson);
      setName(nextPerson.name ?? "");
      setAllPeople(nextPeople.filter((entry) => entry.id !== params.id));
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Unable to load person.");
    }
  };

  useEffect(() => {
    void load();
  }, [params.id, canCurate]);

  const namedOptions = useMemo(
    () => allPeople.filter((entry) => entry.name !== null),
    [allPeople],
  );

  return (
    <AppShell
      title={person?.name ?? "Unnamed person"}
      description={person ? `${person.face_count} faces across ${person.asset_count} assets.` : "Face detections and related assets."}
      actions={person?.faces.length ? <Link href="/people" className="button ghost-button small-button">All People</Link> : undefined}
    >
      {error ? <section className="panel empty-state">{error}</section> : null}
      {message ? <section className="panel empty-state">{message}</section> : null}

      {canCurate && person ? (
        <section className="two-column">
          <form
            className="panel form-grid"
            onSubmit={async (event: FormEvent) => {
              event.preventDefault();
              setBusy(true);
              setError(null);
              setMessage(null);
              try {
                const next = await updatePerson(person.id, { name: name || null });
                setPerson(next);
                setMessage("Person updated.");
              } catch (nextError) {
                setError(nextError instanceof Error ? nextError.message : "Unable to update person.");
              } finally {
                setBusy(false);
              }
            }}
          >
            <div>
              <p className="eyebrow">Identity</p>
              <h2>Rename or review</h2>
            </div>
            <label className="field">
              <span>Display name</span>
              <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Unnamed person" />
            </label>
            <button className="button small-button" type="submit" disabled={busy}>
              {busy ? "Saving..." : "Save Name"}
            </button>
          </form>

          <form
            className="panel form-grid"
            onSubmit={async (event: FormEvent) => {
              event.preventDefault();
              if (!mergeSourceId) {
                return;
              }
              setBusy(true);
              setError(null);
              setMessage(null);
              try {
                const next = await mergePerson(person.id, mergeSourceId);
                setPerson(next);
                setMergeSourceId("");
                setMessage("People merged.");
                await load();
              } catch (nextError) {
                setError(nextError instanceof Error ? nextError.message : "Unable to merge people.");
              } finally {
                setBusy(false);
              }
            }}
          >
            <div>
              <p className="eyebrow">Merge</p>
              <h2>Combine duplicate identities</h2>
            </div>
            <label className="field">
              <span>Merge another person into this one</span>
              <select value={mergeSourceId} onChange={(event) => setMergeSourceId(event.target.value)}>
                <option value="">Select a person</option>
                {namedOptions.map((entry) => (
                  <option key={entry.id} value={entry.id}>{entry.name}</option>
                ))}
              </select>
            </label>
            <button className="button ghost-button small-button" type="submit" disabled={busy || !mergeSourceId}>
              {busy ? "Merging..." : "Merge"}
            </button>
          </form>
        </section>
      ) : null}

      <section className="panel stack">
        <div>
          <p className="eyebrow">Face Strip</p>
          <h2>{person?.faces.length ?? 0} detections</h2>
        </div>
        <div className="similarity-scroll">
          {person?.faces.map((face) => (
            <button
              key={face.id}
              type="button"
              className="panel"
              style={{ minWidth: "160px", padding: "0.5rem" }}
              onClick={async () => {
                if (!canCurate || !person) {
                  return;
                }
                try {
                  const next = await updatePerson(person.id, { cover_face_id: face.id });
                  setPerson(next);
                  setMessage("Cover face updated.");
                } catch (nextError) {
                  setError(nextError instanceof Error ? nextError.message : "Unable to update cover face.");
                }
              }}
            >
              {face.crop_preview_url ? (
                <img
                  src={mediaUrl(face.crop_preview_url)}
                  alt={face.person?.name ?? "Face crop"}
                  style={{ width: "150px", height: "150px", objectFit: "cover", borderRadius: "1rem" }}
                />
              ) : null}
              <div style={{ marginTop: "0.5rem", textAlign: "left" }}>
                <strong>{face.person?.name ?? person?.name ?? "Unnamed person"}</strong>
                <div className="subdued">Score {(face.det_score * 100).toFixed(0)}%</div>
              </div>
            </button>
          ))}
        </div>
      </section>

      <section className="panel stack">
        <div>
          <p className="eyebrow">Assets</p>
          <h2>{person?.items.length ?? 0} matching assets</h2>
        </div>
        <div className="gallery-grid">
          {person?.items.map((asset) => (
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
