"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { fetchScanJobs, fetchSources } from "@/lib/api";
import { ScanJob, Source } from "@/lib/types";

function findActiveJob(source: Source, jobs: ScanJob[]): ScanJob | undefined {
  return jobs.find(
    (job) =>
      job.source_id === source.id &&
      (job.status === "queued" ||
        job.status === "running" ||
        (job.status === "cancelled" && source.status === "scanning"))
  );
}

export default function SourcesPage() {
  const { user } = useAuth();
  const [sources, setSources] = useState<Source[]>([]);
  const [jobs, setJobs] = useState<ScanJob[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const [nextSources, nextJobs] = await Promise.all([fetchSources(), fetchScanJobs()]);
        setSources(nextSources);
        setJobs(nextJobs);
      } catch (nextError) {
        setError(nextError instanceof Error ? nextError.message : "Unable to load sources.");
      }
    };
    void load();
    const interval = window.setInterval(() => {
      void load();
    }, 5000);
    return () => window.clearInterval(interval);
  }, []);

  return (
    <AppShell
      title="Sources"
      description="Choose a source root, then browse its live folders in a gallery view. Indexed browsing lives on its own page."
      actions={
        <div className="page-actions">
          <Link href="/browse-indexed" className="button subtle-button small-button">
            Browse Indexed
          </Link>
          <Link href="/search" className="button ghost-button small-button">
            Open Search
          </Link>
          {user?.capabilities.can_view_admin ? (
            <Link href="/admin" className="button small-button">
              Open Admin Center
            </Link>
          ) : null}
        </div>
      }
    >
      {error ? <section className="panel empty-state">{error}</section> : null}
      <section className="panel stack">
        <div className="row-between">
          <div>
            <p className="eyebrow">Source Hub</p>
            <h2>Approved roots</h2>
            <p className="subdued">Live gallery browse starts here. Open a source to explore folders and images without the heavy search layout.</p>
          </div>
          <div className="chip-row">
            <span className="chip">{sources.length} sources</span>
            <span className="chip">{jobs.filter((job) => job.status === "queued" || job.status === "running").length} active scans</span>
          </div>
        </div>
        <div className="source-hub-grid">
          {sources.map((source) => {
            const activeJob = findActiveJob(source, jobs);
            return (
              <div key={source.id} style={{ display: "contents" }}>
                <Link href={`/sources/${source.id}`} className="source-hub-card">
                  <div className="source-hub-card-visual">
                    <span className="pill">{source.status}</span>
                  </div>
                  <div className="source-hub-card-body">
                    <div>
                      <p className="asset-name">{source.name}</p>
                      <p className="subdued">{source.display_root_path}</p>
                    </div>
                    {activeJob ? (
                      <p className="subdued">{activeJob.progress}% · {activeJob.message ?? "Scanning..."}</p>
                    ) : (
                      <p className="subdued">Open live gallery</p>
                    )}
                  </div>
                </Link>
                {/* v1.6 — File Explorer shortcut */}
                <Link
                  href={`/sources/${source.id}/explorer`}
                  className="button ghost-button small-button"
                  style={{ justifySelf: "start", marginTop: "-0.5rem", marginBottom: "0.5rem" }}
                >
                  📁 File Explorer
                </Link>
              </div>
            );
          })}
        </div>
      </section>
    </AppShell>
  );
}
