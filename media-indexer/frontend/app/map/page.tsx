"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { fetchGeoAssets, mediaUrl } from "@/lib/api";
import { GeoFeatureCollection } from "@/lib/types";


function iframeUrl(lat: number, lon: number) {
  const bbox = `${lon - 0.04}%2C${lat - 0.04}%2C${lon + 0.04}%2C${lat + 0.04}`;
  return `https://www.openstreetmap.org/export/embed.html?bbox=${bbox}&layer=mapnik&marker=${lat}%2C${lon}`;
}

function MapPageContent() {
  const searchParams = useSearchParams();
  const highlight = searchParams.get("highlight");
  const [geo, setGeo] = useState<GeoFeatureCollection | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(highlight);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const response = await fetchGeoAssets();
        setGeo(response);
        if (!selectedId && response.features.length) {
          setSelectedId(response.features[0].properties.id);
        }
      } catch (nextError) {
        setError(nextError instanceof Error ? nextError.message : "Unable to load geotagged assets.");
      }
    };
    void load();
  }, []);

  const selected = useMemo(
    () => geo?.features.find((feature) => feature.properties.id === selectedId) ?? geo?.features[0] ?? null,
    [geo, selectedId],
  );

  return (
    <AppShell title="Map" description="Browse assets with GPS metadata by location.">
      {error ? <section className="panel empty-state">{error}</section> : null}
      <section className="two-column">
        <section className="panel stack">
          <div>
            <p className="eyebrow">Locations</p>
            <h2>{geo?.features.length ?? 0} geotagged assets</h2>
          </div>
          <div className="list-stack compact-list-stack">
            {geo?.features.map((feature) => (
              <button
                key={feature.properties.id}
                type="button"
                className="metadata-row"
                style={{ width: "100%", textAlign: "left" }}
                onClick={() => setSelectedId(feature.properties.id)}
              >
                <div>
                  <strong>{feature.properties.filename}</strong>
                  <div className="subdued">
                    {feature.geometry.coordinates[1].toFixed(5)}, {feature.geometry.coordinates[0].toFixed(5)}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </section>

        <section className="panel stack">
          <div>
            <p className="eyebrow">Preview</p>
            <h2>{selected?.properties.filename ?? "Select an asset"}</h2>
          </div>
          {selected ? (
            <>
              <iframe
                title="Map Preview"
                src={iframeUrl(selected.geometry.coordinates[1], selected.geometry.coordinates[0])}
                width="100%"
                height="420"
                style={{ border: 0, borderRadius: "1rem" }}
              />
              {selected.properties.thumbnail_url ? (
                <img
                  src={mediaUrl(selected.properties.thumbnail_url)}
                  alt={selected.properties.filename}
                  style={{ width: "100%", maxHeight: "220px", objectFit: "cover", borderRadius: "1rem" }}
                />
              ) : null}
              <div className="card-actions">
                <a href={`/assets/${selected.properties.id}`} className="button small-button">Open Asset</a>
              </div>
            </>
          ) : (
            <p className="subdued">No geotagged assets found.</p>
          )}
        </section>
      </section>
    </AppShell>
  );
}

export default function MapPage() {
  return (
    <Suspense
      fallback={
        <AppShell title="Map" description="Browse assets with GPS metadata by location.">
          <section className="panel empty-state">Loading map…</section>
        </AppShell>
      }
    >
      <MapPageContent />
    </Suspense>
  );
}
