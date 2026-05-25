"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { createSchedule, deleteSchedule, fetchAdminHealth, fetchSchedules, fetchSources, updateSchedule } from "@/lib/api";
import { formatDate } from "@/lib/asset-metadata";
import { AdminHealthResponse, ScheduledScan, Source } from "@/lib/types";


function describeCron(expr: string): string {
  const parts = expr.trim().split(/\s+/);
  if (parts.length !== 5) {
    return expr;
  }
  const [minute, hour, day, month, weekday] = parts;
  if (day === "*" && month === "*" && weekday === "*" && /^\d+$/.test(hour) && /^\d+$/.test(minute)) {
    return `Daily at ${hour.padStart(2, "0")}:${minute.padStart(2, "0")}`;
  }
  return expr;
}

export default function AdminHealthPage() {
  const [health, setHealth] = useState<AdminHealthResponse | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [sourceId, setSourceId] = useState("");
  const [cronExpression, setCronExpression] = useState("0 2 * * *");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = async () => {
    try {
      const [nextHealth, nextSources] = await Promise.all([fetchAdminHealth(), fetchSources()]);
      setHealth(nextHealth);
      setSources(nextSources);
      if (!sourceId && nextSources.length) {
        setSourceId(nextSources[0].id);
      }
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Unable to load health dashboard.");
    }
  };

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => {
      void load();
    }, 30000);
    return () => window.clearInterval(timer);
  }, []);

  const schedules = useMemo(() => health?.schedules ?? [], [health]);

  return (
    <AppShell
      title="Admin Health"
      description="Operational status, queue visibility, and scheduled scan management."
      actions={
        <div className="page-actions">
          <a href="/admin" className="button ghost-button small-button">Admin Center</a>
          <a href="/admin/integrations" className="button subtle-button small-button">Integrations</a>
        </div>
      }
    >
      {error ? <section className="panel empty-state">{error}</section> : null}

      <section className="stats-grid">
        <article className="panel">
          <p className="eyebrow">Status</p>
          <p className="stat-card-value">{health?.status ?? "..."}</p>
          <p className="subdued">Overall service state</p>
        </article>
        <article className="panel">
          <p className="eyebrow">DB Pool</p>
          <p className="stat-card-value">{health ? `${health.db.checked_out}/${health.db.pool_size}` : "..."}</p>
          <p className="subdued">Checked out / total</p>
        </article>
        <article className="panel">
          <p className="eyebrow">Worker Queue</p>
          <p className="stat-card-value">{health ? `${health.worker_queue.pending_jobs}/${health.worker_queue.running_jobs}` : "..."}</p>
          <p className="subdued">Pending / running</p>
        </article>
      </section>

      <section className="two-column">
        <section className="panel stack">
          <div>
            <p className="eyebrow">Storage</p>
            <h2>Disk Usage</h2>
          </div>
          <div className="metadata-grid">
            {health?.disk.sources.map((source) => (
              <div key={source.source_id} className="metadata-row">
                <strong>{source.name}</strong>
                <div className="subdued">{source.free_gb} GB free / {source.total_gb} GB total</div>
              </div>
            ))}
            <div className="metadata-row">
              <strong>Preview Cache</strong>
              <div className="subdued">{health?.disk.previews_gb ?? 0} GB</div>
            </div>
          </div>
        </section>

        <section className="panel stack">
          <div>
            <p className="eyebrow">Models</p>
            <h2>Worker Model State</h2>
          </div>
          <div className="metadata-grid">
            {health ? Object.entries(health.models).map(([key, value]) => (
              <div key={key} className="metadata-row">
                <strong>{key}</strong>
                <div className="subdued">{value.loaded ? "Loaded" : "Cold"}{value.model_id ? ` · ${value.model_id}` : ""}</div>
              </div>
            )) : null}
          </div>
        </section>
      </section>

      <section className="two-column">
        <form
          className="panel form-grid"
          onSubmit={async (event: FormEvent) => {
            event.preventDefault();
            setBusy("create");
            setError(null);
            try {
              await createSchedule({ source_id: sourceId, cron_expression: cronExpression });
              setCronExpression("0 2 * * *");
              await load();
            } catch (nextError) {
              setError(nextError instanceof Error ? nextError.message : "Unable to create schedule.");
            } finally {
              setBusy(null);
            }
          }}
        >
          <div>
            <p className="eyebrow">Schedules</p>
            <h2>Add Schedule</h2>
          </div>
          <label className="field">
            <span>Source</span>
            <select value={sourceId} onChange={(event) => setSourceId(event.target.value)}>
              {sources.map((source) => (
                <option key={source.id} value={source.id}>{source.name}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Cron</span>
            <input value={cronExpression} onChange={(event) => setCronExpression(event.target.value)} />
          </label>
          <p className="subdued">{describeCron(cronExpression)}</p>
          <button className="button" type="submit" disabled={busy === "create"}>
            {busy === "create" ? "Saving..." : "Create Schedule"}
          </button>
        </form>

        <section className="panel stack">
          <div>
            <p className="eyebrow">Existing</p>
            <h2>Scheduled Scans</h2>
          </div>
          <div className="list-stack compact-list-stack">
            {schedules.map((schedule) => (
              <article key={schedule.schedule_id} className="metadata-row" style={{ alignItems: "flex-start" }}>
                <div>
                  <strong>{schedule.source_name}</strong>
                  <div className="subdued">{describeCron(schedule.cron_expression)}</div>
                  <div className="subdued">Last run: {schedule.last_run ? formatDate(schedule.last_run) : "Never"}</div>
                </div>
                <div className="card-actions">
                  <button
                    type="button"
                    className="button ghost-button small-button"
                    onClick={async () => {
                      await updateSchedule(schedule.schedule_id, { enabled: !schedule.enabled });
                      await load();
                    }}
                  >
                    {schedule.enabled ? "Disable" : "Enable"}
                  </button>
                  <button
                    type="button"
                    className="button ghost-button small-button"
                    onClick={async () => {
                      await deleteSchedule(schedule.schedule_id);
                      await load();
                    }}
                  >
                    Delete
                  </button>
                </div>
              </article>
            ))}
            {!schedules.length ? <p className="subdued">No scheduled scans yet.</p> : null}
          </div>
        </section>
      </section>
    </AppShell>
  );
}
