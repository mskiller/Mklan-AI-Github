"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { cancelScanJob, fetchScanJob } from "@/lib/api";
import { ScanJob } from "@/lib/types";

export default function ScanJobDetailPage() {
  const { user } = useAuth();
  const params = useParams<{ id: string }>();
  const [job, setJob] = useState<ScanJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = async () => {
    try {
      setJob(await fetchScanJob(params.id));
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Unable to load scan job.");
    }
  };

  useEffect(() => {
    void load();
    const interval = window.setInterval(() => {
      void load();
    }, 5000);
    return () => window.clearInterval(interval);
  }, [params.id]);

  return (
    <AppShell
      title="Scan Job"
      description="Single-job progress, counters, and worker message."
      actions={
        user?.capabilities.can_run_scans && job && (job.status === "queued" || job.status === "running") ? (
          <button
            className="button ghost-button small-button"
            type="button"
            onClick={async () => {
              setError(null);
              setMessage(null);
              try {
                const cancelled = await cancelScanJob(job.id);
                setJob(cancelled);
                setMessage(`Cancelled scan job ${cancelled.id}.`);
              } catch (nextError) {
                setError(nextError instanceof Error ? nextError.message : "Unable to cancel scan job.");
              }
            }}
          >
            Cancel Scan
          </button>
        ) : null
      }
    >
      {error ? <section className="panel empty-state">{error}</section> : null}
      {message ? <section className="panel empty-state">{message}</section> : null}
      {job ? (
        <section className="panel stack">
          <div className="row-between">
            <div>
              <p className="eyebrow">Job Id</p>
              <h2>{job.id}</h2>
              <p className="subdued">{job.message ?? "Waiting for worker update."}</p>
            </div>
            <span className="pill">{job.status}</span>
          </div>
          <div className="progress-track">
            <div className="progress-bar" style={{ width: `${job.progress}%` }} />
          </div>
          <div className="metadata-grid">
            <div className="metadata-row">Mode: {job.scan_mode ?? "basic"}</div>
            <div className="metadata-row">Path: {job.path_filter ?? "source root"}</div>
            <div className="metadata-row">Scanned: {job.scanned_count}</div>
            <div className="metadata-row">New: {job.new_count}</div>
            <div className="metadata-row">Updated: {job.updated_count}</div>
            <div className="metadata-row">Deleted: {job.deleted_count}</div>
            <div className="metadata-row">Errors: {job.error_count}</div>
          </div>
        </section>
      ) : (
        <section className="panel empty-state">Loading scan job…</section>
      )}
    </AppShell>
  );
}
