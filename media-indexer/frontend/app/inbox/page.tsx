"use client";

import { useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { approveInboxItem, fetchInbox, fetchInboxCompare, fetchSources, mediaUrl, rejectInboxItem } from "@/lib/api";
import { InboxCompareResponse, InboxItem, Source } from "@/lib/types";


export default function InboxPage() {
  const [items, setItems] = useState<InboxItem[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [compare, setCompare] = useState<InboxCompareResponse | null>(null);
  const [targetSourceId, setTargetSourceId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      const [inboxResponse, sourceResponse] = await Promise.all([fetchInbox("pending"), fetchSources()]);
      const nextItems = Array.isArray(inboxResponse) ? inboxResponse : [];
      setItems(nextItems);
      setSources(sourceResponse);
      const firstId = nextItems[0]?.id ?? null;
      setSelectedId((current) => current ?? firstId);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Unable to load inbox.");
    }
  };

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    const loadCompare = async () => {
      if (!selectedId) {
        setCompare(null);
        return;
      }
      try {
        const response = await fetchInboxCompare(selectedId);
        setCompare(response);
        if (response.item.target_source_id) {
          setTargetSourceId(response.item.target_source_id);
        }
      } catch (nextError) {
        setError(nextError instanceof Error ? nextError.message : "Unable to load inbox comparison.");
      }
    };
    void loadCompare();
  }, [selectedId]);

  const selected = useMemo(() => items.find((item) => item.id === selectedId) ?? null, [items, selectedId]);

  return (
    <AppShell title="Inbox" description="Review uploaded files before importing them into a library source.">
      {error ? <section className="panel empty-state">{error}</section> : null}
      <section className="two-column">
        <section className="panel stack">
          <div>
            <p className="eyebrow">Pending</p>
            <h2>{items.length} inbox items</h2>
          </div>
          <div className="list-stack compact-list-stack">
            {items.map((item) => (
              <button
                key={item.id}
                type="button"
                className="metadata-row"
                style={{ width: "100%", textAlign: "left" }}
                onClick={() => setSelectedId(item.id)}
              >
                <div>
                  <strong>{item.filename}</strong>
                  <div className="subdued">{item.target_source_name ?? "No target source"}</div>
                </div>
                <span className="chip">{item.clip_distance_min?.toFixed(3) ?? "n/a"}</span>
              </button>
            ))}
            {!items.length ? <p className="subdued">Inbox is empty.</p> : null}
          </div>
        </section>

        <section className="panel stack">
          <div>
            <p className="eyebrow">Review</p>
            <h2>{selected?.filename ?? "Select an item"}</h2>
          </div>
          {compare?.item ? (
            <>
              <div className="two-column">
                <div className="stack">
                  <strong>Incoming</strong>
                  {compare.item.thumbnail_url ? (
                    <img src={mediaUrl(compare.item.thumbnail_url)} alt={compare.item.filename} style={{ width: "100%", borderRadius: "1rem" }} />
                  ) : null}
                </div>
                <div className="stack">
                  <strong>Nearest Existing</strong>
                  {compare.nearest_asset?.preview_url ? (
                    <img src={mediaUrl(compare.nearest_asset.preview_url)} alt={compare.nearest_asset.filename} style={{ width: "100%", borderRadius: "1rem" }} />
                  ) : (
                    <p className="subdued">No nearby indexed asset.</p>
                  )}
                </div>
              </div>
              <label className="field">
                <span>Target Source</span>
                <select value={targetSourceId} onChange={(event) => setTargetSourceId(event.target.value)}>
                  {sources.map((source) => (
                    <option key={source.id} value={source.id}>{source.name}</option>
                  ))}
                </select>
              </label>
              <div className="card-actions">
                <button
                  type="button"
                  className="button"
                  onClick={async () => {
                    if (!compare) {
                      return;
                    }
                    await approveInboxItem(compare.item.id, targetSourceId || undefined);
                    setCompare(null);
                    setSelectedId(null);
                    await load();
                  }}
                >
                  Approve
                </button>
                <button
                  type="button"
                  className="button ghost-button"
                  onClick={async () => {
                    if (!compare) {
                      return;
                    }
                    await rejectInboxItem(compare.item.id);
                    setCompare(null);
                    setSelectedId(null);
                    await load();
                  }}
                >
                  Reject
                </button>
              </div>
            </>
          ) : (
            <p className="subdued">Select a pending inbox item to review it.</p>
          )}
        </section>
      </section>
    </AppShell>
  );
}
