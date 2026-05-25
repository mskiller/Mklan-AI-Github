"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { fetchAdminGroups, createAdminGroup, updateAdminGroup, deleteAdminGroup } from "@/lib/api";
import { GroupSummary } from "@/lib/types";

export default function AdminGroupsPage() {
  const { user } = useAuth();
  const [groups, setGroups] = useState<GroupSummary[]>([]);
  const [selected, setSelected] = useState<GroupSummary | null>(null);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [permJson, setPermJson] = useState("{}");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const reload = async () => {
    const g = await fetchAdminGroups();
    setGroups(g);
    if (selected) setSelected(g.find((x) => x.id === selected.id) ?? null);
  };

  useEffect(() => { if (user?.capabilities.can_view_admin) void reload(); }, [user?.capabilities.can_view_admin]);

  useEffect(() => {
    if (selected) setPermJson(JSON.stringify(selected.permissions ?? {}, null, 2));
  }, [selected?.id]);

  const act = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label); setError(null); setMessage(null);
    try { await fn(); setMessage(`${label} — done.`); await reload(); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(null); }
  };

  if (user && !user.capabilities.can_view_admin) {
    return <AppShell title="Groups" description="Group management"><section className="panel empty-state"><h2>Admin only</h2></section></AppShell>;
  }

  return (
    <AppShell title="Groups" description="Manage permission groups and their capabilities.">
      <nav className="admin-subnav">
        <a href="/admin">Overview</a>
        <a href="/admin/users">Users</a>
        <a href="/admin/groups" className="active">Groups</a>
      </nav>
      {error && <p className="error-message">{error}</p>}
      {message && <p className="success-message">{message}</p>}
      <div className="admin-user-grid">
        <div className="panel stack">
          <h2>Groups</h2>
          <ul className="user-list">
            {groups.map((g) => (
              <li key={g.id}>
                <button type="button"
                  className={`user-list-item ${selected?.id === g.id ? "user-list-item-selected" : ""}`}
                  onClick={() => setSelected(g)}>
                  <span>{g.name}</span>
                  <span className="subdued">{g.description || "No description"}</span>
                </button>
              </li>
            ))}
          </ul>
          <h3>Create group</h3>
          <label className="field"><span>Name</span><input value={newName} onChange={(e) => setNewName(e.target.value)} /></label>
          <label className="field"><span>Description</span><input value={newDesc} onChange={(e) => setNewDesc(e.target.value)} /></label>
          <button className="button small-button" disabled={!newName || !!busy}
            onClick={() => act("Create group", async () => {
              await createAdminGroup({ name: newName, description: newDesc, permissions: {} });
              setNewName(""); setNewDesc("");
            })}>
            + Create Group
          </button>
        </div>

        {selected ? (
          <div className="panel stack">
            <h2>{selected.name}</h2>
            <p className="subdued">Created: {selected.created_at ? new Date(selected.created_at).toLocaleDateString() : "—"}</p>
            <label className="field"><span>Name</span><input value={selected.name} onChange={(e) => setSelected({ ...selected, name: e.target.value })} /></label>
            <label className="field"><span>Description</span><input value={selected.description ?? ""} onChange={(e) => setSelected({ ...selected, description: e.target.value })} /></label>
            <label className="field">
              <span>Permissions (JSON)</span>
              <textarea rows={10} value={permJson} onChange={(e) => setPermJson(e.target.value)} style={{ fontFamily: "monospace", fontSize: "0.8em" }} />
            </label>
            <p className="subdued" style={{ fontSize: "0.8em" }}>
              Keys: <code>can_manage_sources</code>, <code>can_run_scans</code>, <code>can_upload_assets</code>,{" "}
              <code>can_manage_collections</code>, <code>can_review_compare</code>,{" "}
              <code>allowed_source_ids</code> (<code>"all"</code> or <code>["uuid",…]</code>)
            </p>
            <div className="card-actions">
              <button className="button small-button" disabled={!!busy}
                onClick={() => {
                  let perms: Record<string, unknown> = {};
                  try { perms = JSON.parse(permJson); } catch { setError("Invalid JSON"); return; }
                  act("Save", () => updateAdminGroup(selected.id, { name: selected.name, description: selected.description ?? "", permissions: perms }));
                }}>
                Save
              </button>
              <button className="button danger-button small-button" disabled={!!busy}
                onClick={() => {
                  if (!confirm(`Delete group "${selected.name}"?`)) return;
                  act("Delete", async () => { await deleteAdminGroup(selected.id); setSelected(null); });
                }}>
                Delete
              </button>
            </div>
          </div>
        ) : (
          <div className="panel empty-state"><p className="subdued">Select a group to edit.</p></div>
        )}
      </div>
    </AppShell>
  );
}
