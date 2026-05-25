"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { CompareViewer } from "@/components/compare-viewer";
import { fetchCompare, submitCompareReview } from "@/lib/api";
import { CompareResponse } from "@/lib/types";

function ComparePageContent() {
  const { user } = useAuth();
  const searchParams = useSearchParams();
  const [comparison, setComparison] = useState<CompareResponse | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const assetA = searchParams.get("a");
  const assetB = searchParams.get("b");

  useEffect(() => {
    const load = async () => {
      setComparison(null);
      setError(null);
      if (!assetA || !assetB) {
        setError("Select two assets first.");
        return;
      }
      if (assetA === assetB) {
        setError("Choose two different images to compare.");
        return;
      }
      try {
        setComparison(await fetchCompare(assetA, assetB));
      } catch (nextError) {
        setError(nextError instanceof Error ? nextError.message : "Unable to load comparison.");
      }
    };
    void load();
  }, [assetA, assetB]);

  const review = async (action: string) => {
    if (!assetA || !assetB) {
      return;
    }
    await submitCompareReview(assetA, assetB, action);
    setMessage(`Saved "${action}" review to the audit log.`);
  };

  return (
    <AppShell
      title="Compare"
      description="Overlay slider or side-by-side inspection with shared zoom/pan and a compact metadata diff."
      actions={
        comparison ? (
          <div className="page-actions">
            <Link href={`/assets/${comparison.asset_a.id}`} className="button subtle-button">
              Open Left Asset
            </Link>
            <Link href={`/assets/${comparison.asset_b.id}`} className="button subtle-button">
              Open Right Asset
            </Link>
          </div>
        ) : null
      }
    >
      {error ? <section className="panel empty-state">{error}</section> : null}
      {comparison ? (
        <>
          <CompareViewer comparison={comparison} />
          {user?.capabilities.can_review_compare ? (
            <section className="panel stack">
              <div className="row-between">
                <div>
                  <p className="eyebrow">Review Actions</p>
                  <h2>Resolution workflow</h2>
                </div>
                {message ? <p className="subdued">{message}</p> : null}
              </div>
              <div className="card-actions">
                <button className="button" type="button" onClick={() => void review("mark_duplicate")}>
                  Mark as Duplicate
                </button>
                <button className="button subtle-button" type="button" onClick={() => void review("ignore")}>
                  Ignore
                </button>
              </div>
            </section>
          ) : (
            <section className="panel stack">
              <p className="eyebrow">Read Only</p>
              <h2>Review actions are admin-only</h2>
              <p className="subdued">Guest users can inspect metadata, prompt tags, and image similarity, but only admins can save compare decisions.</p>
            </section>
          )}
          <section className="panel stack">
            <div>
              <p className="eyebrow">Metadata Diff</p>
              <h2>Key differences</h2>
            </div>
            <div className="metadata-grid">
              {comparison.metadata_diff.map((entry) => (
                <div key={entry.field} className="metadata-row">
                  <strong>{entry.field}</strong>
                  <div className="subdued">A: {String(entry.left ?? "n/a")}</div>
                  <div className="subdued">B: {String(entry.right ?? "n/a")}</div>
                </div>
              ))}
            </div>
          </section>
        </>
      ) : (
        <section className="panel empty-state">Loading comparison…</section>
      )}
    </AppShell>
  );
}

export default function ComparePage() {
  return (
    <Suspense
      fallback={
        <AppShell title="Compare" description="Overlay slider or side-by-side inspection with shared zoom/pan and a compact metadata diff.">
          <section className="panel empty-state">Loading comparison…</section>
        </AppShell>
      }
    >
      <ComparePageContent />
    </Suspense>
  );
}
