"use client";

import { useEffect, useState } from "react";

import { CollectionSummary } from "@/lib/types";

export function CollectionPickerModal({
  open,
  collections,
  busy,
  onClose,
  onConfirm,
}: {
  open: boolean;
  collections: CollectionSummary[];
  busy?: boolean;
  onClose: () => void;
  onConfirm: (collectionId: string) => void;
}) {
  const [selectedId, setSelectedId] = useState<string>("");

  useEffect(() => {
    if (!open) {
      return;
    }
    setSelectedId(collections[0]?.id ?? "");
  }, [collections, open]);

  if (!open) {
    return null;
  }

  return (
    <>
      <button type="button" aria-label="Close collection picker" className="modal-scrim" onClick={onClose} />
      <section className="modal-panel panel stack">
        <div className="row-between">
          <div>
            <p className="eyebrow">Collections</p>
            <h2>Add to collection</h2>
          </div>
          <button className="button ghost-button small-button" type="button" onClick={onClose}>
            Close
          </button>
        </div>
        {collections.length ? (
          <div className="list-stack compact-list-stack">
            {collections.map((collection) => (
              <label key={collection.id} className={`collection-picker-row ${selectedId === collection.id ? "collection-picker-row-selected" : ""}`}>
                <input
                  type="radio"
                  name="collection"
                  value={collection.id}
                  checked={selectedId === collection.id}
                  onChange={() => setSelectedId(collection.id)}
                />
                <div>
                  <strong>{collection.name}</strong>
                  {collection.description ? <p className="subdued">{collection.description}</p> : null}
                  <p className="subdued">{collection.asset_count} assets</p>
                </div>
              </label>
            ))}
          </div>
        ) : (
          <div className="empty-state">Create a collection first from the Collections page.</div>
        )}
        <div className="card-actions">
          <button className="button ghost-button small-button" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="button small-button" type="button" disabled={!selectedId || busy} onClick={() => onConfirm(selectedId)}>
            {busy ? "Saving..." : "Add to Collection"}
          </button>
        </div>
      </section>
    </>
  );
}
