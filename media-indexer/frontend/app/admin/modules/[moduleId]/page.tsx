"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { useModuleRegistry } from "@/components/module-registry-provider";
import { fetchAdminModule, updateAdminModule } from "@/lib/api";
import { ModuleSettingFieldRead, PlatformModule } from "@/lib/types";

function normalizeDraftValue(field: ModuleSettingFieldRead, rawValue: unknown) {
  if (field.type === "boolean") {
    return Boolean(rawValue);
  }
  if (rawValue === null || rawValue === undefined) {
    return "";
  }
  return String(rawValue);
}

export default function AdminModuleDetailPage() {
  const params = useParams<{ moduleId: string }>();
  const { user } = useAuth();
  const { refresh: refreshRegistry } = useModuleRegistry();
  const [moduleItem, setModuleItem] = useState<PlatformModule | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [settingsDraft, setSettingsDraft] = useState<Record<string, string | boolean>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = async () => {
    try {
      const nextModule = await fetchAdminModule(params.moduleId);
      setModuleItem(nextModule);
      setEnabled(nextModule.enabled);
      setSettingsDraft(
        Object.fromEntries(
          nextModule.settings_schema.map((field) => [
            field.key,
            normalizeDraftValue(field, nextModule.settings_json[field.key] ?? field.default),
          ])
        )
      );
      setError(null);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Unable to load module.");
    }
  };

  useEffect(() => {
    if (user?.capabilities.can_view_admin) {
      void load();
    }
  }, [params.moduleId, user?.capabilities.can_view_admin]);

  if (user && !user.capabilities.can_view_admin) {
    return (
      <AppShell title="Module" description="Module configuration and dependency health.">
        <section className="panel empty-state">
          <h2>Admin only</h2>
          <p className="subdued">This page is only available to admin users.</p>
        </section>
      </AppShell>
    );
  }

  return (
    <AppShell
      title={moduleItem?.name ?? "Module"}
      description={moduleItem ? `${moduleItem.module_id} · ${moduleItem.status}` : "Module configuration and dependency health."}
      actions={
        <div className="page-actions">
          <Link href="/admin/modules" className="button subtle-button small-button">All Modules</Link>
          {moduleItem?.user_mount ? <Link href={moduleItem.user_mount} className="button ghost-button small-button">Open User Surface</Link> : null}
        </div>
      }
    >
      {error ? <section className="panel empty-state">{error}</section> : null}
      {message ? <section className="panel empty-state">{message}</section> : null}

      {moduleItem ? (
        <>
          <section className="two-column">
            <section className="panel stack">
              <div>
                <p className="eyebrow">Status</p>
                <h2>Module health</h2>
              </div>
              <div className="chip-row">
                <span className="chip">{moduleItem.status}</span>
                <span className="chip">{moduleItem.enabled ? "enabled" : "disabled"}</span>
                <span className="chip">API v{moduleItem.platform_api_version}</span>
              </div>
              {moduleItem.description ? <p className="subdued">{moduleItem.description}</p> : null}
              {moduleItem.error ? <p className="subdued">{moduleItem.error}</p> : null}
              <div className="list-stack compact-list-stack">
                <div className="metadata-row">
                  <strong>Source</strong>
                  <p className="subdued">{moduleItem.source_ref ?? "built-in"}</p>
                </div>
                <div className="metadata-row">
                  <strong>Manifest</strong>
                  <p className="subdued">{moduleItem.manifest_path ?? "Not reported"}</p>
                </div>
                <div className="metadata-row">
                  <strong>Backend entrypoint</strong>
                  <p className="subdued">{moduleItem.backend_entrypoint ?? "None"}</p>
                </div>
                <div className="metadata-row">
                  <strong>Worker entrypoint</strong>
                  <p className="subdued">{moduleItem.worker_entrypoint ?? "None"}</p>
                </div>
                <div className="metadata-row">
                  <strong>Frontend entrypoint</strong>
                  <p className="subdued">{moduleItem.frontend_entrypoint ?? "None"}</p>
                </div>
                <div className="metadata-row">
                  <strong>Migrations</strong>
                  <p className="subdued">{moduleItem.backend_migrations ?? "None"}</p>
                </div>
              </div>
              <div className="chip-row">
                {moduleItem.dependencies.map((dependency) => (
                  <span key={`${moduleItem.module_id}-dep-${dependency}`} className="chip">depends on {dependency}</span>
                ))}
                {moduleItem.permissions.map((permission) => (
                  <span key={`${moduleItem.module_id}-perm-${permission}`} className="chip">{permission}</span>
                ))}
              </div>
            </section>

            <form
              className="panel form-grid"
              onSubmit={async (event: FormEvent) => {
                event.preventDefault();
                setBusy(true);
                setError(null);
                setMessage(null);
                try {
                  const settingsPayload = Object.fromEntries(
                    moduleItem.settings_schema.map((field) => {
                      const rawValue = settingsDraft[field.key];
                      if (field.type === "boolean") {
                        return [field.key, Boolean(rawValue)];
                      }
                      if (field.type === "integer") {
                        return [field.key, rawValue === "" ? null : Number.parseInt(String(rawValue), 10)];
                      }
                      if (field.type === "number") {
                        return [field.key, rawValue === "" ? null : Number(rawValue)];
                      }
                      return [field.key, String(rawValue ?? "")];
                    })
                  );
                  const updated = await updateAdminModule(moduleItem.module_id, {
                    enabled,
                    settings_json: settingsPayload,
                  });
                  setModuleItem(updated);
                  setEnabled(updated.enabled);
                  setSettingsDraft(
                    Object.fromEntries(
                      updated.settings_schema.map((field) => [
                        field.key,
                        normalizeDraftValue(field, updated.settings_json[field.key] ?? field.default),
                      ])
                    )
                  );
                  await refreshRegistry();
                  setMessage("Module configuration saved.");
                } catch (nextError) {
                  setError(nextError instanceof Error ? nextError.message : "Unable to save module settings.");
                } finally {
                  setBusy(false);
                }
              }}
            >
              <div>
                <p className="eyebrow">Configuration</p>
                <h2>Runtime settings</h2>
              </div>
              <label className="field checkbox-field">
                <span>Enabled</span>
                <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />
              </label>
              {moduleItem.settings_schema.length === 0 ? (
                <p className="subdued">This module does not expose configurable settings yet.</p>
              ) : (
                moduleItem.settings_schema.map((field) => (
                  <label key={field.key} className={`field ${field.type === "boolean" ? "checkbox-field" : ""}`.trim()}>
                    <span>{field.label}</span>
                    {field.type === "boolean" ? (
                      <input
                        type="checkbox"
                        checked={Boolean(settingsDraft[field.key])}
                        onChange={(event) => setSettingsDraft((current) => ({ ...current, [field.key]: event.target.checked }))}
                      />
                    ) : (
                      <input
                        type={field.type === "string" ? "text" : "number"}
                        value={String(settingsDraft[field.key] ?? "")}
                        onChange={(event) => setSettingsDraft((current) => ({ ...current, [field.key]: event.target.value }))}
                      />
                    )}
                    {field.description ? <small className="subdued">{field.description}</small> : null}
                  </label>
                ))
              )}
              <button className="button small-button" type="submit" disabled={busy}>
                {busy ? "Saving..." : "Save Module"}
              </button>
            </form>
          </section>
        </>
      ) : null}
    </AppShell>
  );
}
