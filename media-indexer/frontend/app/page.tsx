"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { AssetCard } from "@/components/asset-card";
import { useAuth } from "@/components/auth-provider";
import { useSettings } from "@/components/settings-provider";
import { fetchAssets, fetchScanJobs, fetchSources } from "@/lib/api";
import { AssetSummary, ScanJob, Source } from "@/lib/types";

export default function DashboardPage() {
  const { user } = useAuth();
  const { nsfwVisible } = useSettings();
  const [sources, setSources] = useState<Source[]>([]);
  const [jobs, setJobs] = useState<ScanJob[]>([]);
  const [recentAssets, setRecentAssets] = useState<AssetSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      const [nextSources, nextJobs, nextAssets] = await Promise.all([
        fetchSources(),
        fetchScanJobs(),
        fetchAssets({
          sort: "modified_at",
          page_size: 6,
          exclude_tags: !nsfwVisible ? "nsfw" : undefined,
        }),
      ]);
      setSources(nextSources);
      setJobs(nextJobs);
      setRecentAssets(nextAssets.items);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Unable to load dashboard.");
    }
  };

  useEffect(() => {
    void load();
  }, [nsfwVisible]);

  const runningJobs = jobs.filter((job) => job.status === "running" || job.status === "queued").length;

  return (
    <AppShell
      title="Dashboard"
      description="Overview of approved roots, recent indexing activity, and latest indexed media."
      actions={
        <div className="page-actions">
          <Link href="/sources" className="button subtle-button">
            Open Sources
          </Link>
          <Link href="/browse-indexed" className="button ghost-button">
            Browse Indexed
          </Link>
          <Link href="/search" className="button">
            Open Search
          </Link>
        </div>
      }
    >
      <section className="stats-grid">
        <article className="panel">
          <p className="eyebrow">Sources</p>
          <p className="stat-card-value">{sources.length}</p>
          <p className="subdued">Approved mounted roots</p>
        </article>
        <article className="panel">
          <p className="eyebrow">Queued / Running</p>
          <p className="stat-card-value">{runningJobs}</p>
          <p className="subdued">Scan jobs in progress</p>
        </article>
        <article className="panel">
          <p className="eyebrow">Recent Assets</p>
          <p className="stat-card-value">{recentAssets.length}</p>
          <p className="subdued">Latest indexed items</p>
        </article>
      </section>

      {error ? (
        <section className="panel empty-state">
          <p>{error}</p>
        </section>
      ) : null}

      <section className="panel stack">
        <div className="row-between">
          <div>
            <p className="eyebrow">Workspace</p>
            <h2>Browse, search, and review</h2>
            <p className="subdued">Use Browse for live folders and Search for indexed metadata, tags, and prompt-driven discovery.</p>
          </div>
          {user?.capabilities.can_view_admin ? (
            <Link href="/admin" className="button small-button">
              Open Admin Center
            </Link>
          ) : null}
        </div>
        <div className="card-actions">
            <Link href="/sources" className="button subtle-button small-button">
            Browse Sources
          </Link>
          <Link href="/browse-indexed" className="button ghost-button small-button">
            Browse Indexed
          </Link>
          <Link href="/search" className="button ghost-button small-button">
            Search Index
          </Link>
          <Link href="/collections" className="button ghost-button small-button">
            Collections
          </Link>
          <Link href="/scan-jobs" className="button ghost-button small-button">
            View Scan Jobs
          </Link>
        </div>
      </section>

      <section className="panel stack">
        <div className="row-between">
          <div>
            <p className="eyebrow">Latest Assets</p>
            <h2>Fresh from the index</h2>
          </div>
          <Link href="/browse-indexed" className="button subtle-button">
            Browse All
          </Link>
        </div>
        <div className="results-grid">
          {recentAssets.map((asset) => (
            <AssetCard key={asset.id} asset={asset} />
          ))}
        </div>
      </section>
    </AppShell>
  );
}
