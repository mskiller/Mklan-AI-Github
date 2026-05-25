"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { AssetCard } from "@/components/asset-card";
import { CompareSelectionTray } from "@/components/compare-selection-tray";
import { fetchAsset, fetchSimilar } from "@/lib/api";
import { AssetDetail, AssetSummary, SimilarAsset } from "@/lib/types";

export default function SimilarPage() {
  const params = useParams<{ id: string }>();
  const [asset, setAsset] = useState<AssetDetail | null>(null);
  const [duplicates, setDuplicates] = useState<SimilarAsset[]>([]);
  const [semantic, setSemantic] = useState<SimilarAsset[]>([]);
  const [tagSimilar, setTagSimilar] = useState<SimilarAsset[]>([]);
  const [selected, setSelected] = useState<AssetSummary[]>([]);
  const [selectionMode, setSelectionMode] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const [nextAsset, nextDuplicates, nextSemantic, nextTagSimilar] = await Promise.all([
          fetchAsset(params.id),
          fetchSimilar(params.id, "duplicate"),
          fetchSimilar(params.id, "semantic"),
          fetchSimilar(params.id, "tag"),
        ]);
        setAsset(nextAsset);
        setDuplicates(nextDuplicates);
        setSemantic(nextSemantic);
        setTagSimilar(nextTagSimilar);
      } catch (nextError) {
        setError(nextError instanceof Error ? nextError.message : "Unable to load similar assets.");
      }
    };
    void load();
  }, [params.id]);

  const toggleSelection = (asset: AssetSummary) => {
    setSelected((current) => {
      const exists = current.some((item) => item.id === asset.id);
      if (exists) {
        return current.filter((item) => item.id !== asset.id);
      }
      if (current.length === 2) {
        return [current[1], asset];
      }
      return [...current, asset];
    });
  };

  const compareHref = selected.length === 2 ? `/compare?a=${selected[0].id}&b=${selected[1].id}` : null;
  const renderMatchCard = (match: SimilarAsset) => (
    <AssetCard
      key={`${match.match_type}-${match.asset.id}`}
      asset={match.asset}
      selected={selected.some((item) => item.id === match.asset.id)}
      onSelect={toggleSelection}
      selectionMode={selectionMode}
      contextBadges={
        match.shared_prompt_tags.length
          ? [`${match.prompt_tag_overlap} shared prompt tag${match.prompt_tag_overlap === 1 ? "" : "s"}`]
          : [match.match_type === "duplicate" ? "Near duplicate" : match.match_type === "tag" ? "Tag match" : "Semantic match"]
      }
    />
  );

  return (
    <AppShell
      title={asset ? `Similar to ${asset.filename}` : "Similar Results"}
      description="Review near-duplicates separately from semantic neighbors."
    >
      {error ? <section className="panel empty-state">{error}</section> : null}
      <CompareSelectionTray
        selectionMode={selectionMode}
        selectedCount={selected.length}
        compareHref={compareHref}
        onToggleSelectionMode={() => setSelectionMode((value) => !value)}
        onClearSelection={() => setSelected([])}
        hint="Desktop keeps Ctrl/Cmd-click as a shortcut. On phone, turn on selection mode and tap cards to compare."
      />
      <section className="panel stack">
        <div>
          <p className="eyebrow">Near Duplicates</p>
          <h2>{duplicates.length} matches</h2>
        </div>
        <div className="results-grid">
          {duplicates.map(renderMatchCard)}
        </div>
      </section>
      <section className="panel stack">
        <div>
          <p className="eyebrow">Semantic Similarity</p>
          <h2>{semantic.length} matches</h2>
        </div>
        <div className="results-grid">
          {semantic.map(renderMatchCard)}
        </div>
      </section>
      <section className="panel stack">
        <div>
          <p className="eyebrow">Prompt Tag Similarity</p>
          <h2>{tagSimilar.length} matches</h2>
        </div>
        <div className="results-grid">
          {tagSimilar.map(renderMatchCard)}
        </div>
      </section>
    </AppShell>
  );
}
