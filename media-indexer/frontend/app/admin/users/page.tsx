"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import {
  fetchAdminUsers, fetchAdminGroups, createAdminUser, updateAdminUser,
  resetAdminUserPassword, deleteAdminUser,
} from "@/lib/api";
import { UserSummary, UserRole, UserStatus, GroupSummary } from "@/lib/types";

function statusIcon(status: UserStatus) {
  if (status === "active") return "🟢";
  if (status === "locked") return "🟡";
  if (status === "banned") return "🔴";
  return "⚫";
}

function PasswordModal({ username, onClose, onConfirm }: { username: string; onClose: () => void; onConfirm: (pw: string) => void }) {
  const [pw, setPw] = useState("");
  return (
    <div className="modal-backdrop">
      <div className="modal panel stack">
        <h2>Reset password — {username}</h2>
        <label className="field">
          <span>New password</span>
          <input type="password" value={pw} autoFocus onChange={(e) => setPw(e.target.value)} />
        </label>
        <div className="card-actions">
          <button className="button" disabled={pw.length < 8} onClick={() => onConfirm(pw)}>Confirm Reset</button>
          <button className="button ghost-button" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
}

export default function AdminUsersPage() {
  const { user } = useAuth();
  const [users, setUsers] = useState<UserSummary[]>([]);
  const [groups, setGroups] = useState<GroupSummary[]>([]);
  const [selected, setSelected] = useState<UserSummary | null>(null);
  const [passwordTarget, setPasswordTarget] = useState<UserSummary | null>(null);
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState<UserRole>("guest");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const reload = async () => {
    const [u, g] = await Promise.all([fetchAdminUsers(), fetchAdminGroups()]);
    setUsers(u);
    setGroups(g);
    if (selected) setSelected(u.find((x) => x.id === selected.id) ?? null);
  };

  useEffect(() => { if (user?.capabilities.can_view_admin) void reload(); }, [user?.capabilities.can_view_admin]);

  const act = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label); setError(null); setMessage(null);
    try { await fn(); setMessage(`${label} — done.`); await reload(); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(null); }
  };

  if (user && !user.capabilities.can_view_admin) {
    return <AppShell title="Users" description="User management"><section className="panel empty-state"><h2>Admin only</h2></section></AppShell>;
  }

  return (
    <AppShell title="Users" description="Manage users, roles, status, and group memberships.">
      <nav className="admin-subnav">
        <a href="/admin">Overview</a>
        <a href="/admin/users" className="active">Users</a>
        <a href="/admin/groups">Groups</a>
      </nav>
      {error && <p className="error-message">{error}</p>}
      {message && <p className="success-message">{message}</p>}
      <div className="admin-user-grid">
        {/* Left panel — user list */}
        <div className="panel stack">
          <h2>Users</h2>
          <ul className="user-list">
            {users.map((u) => (
              <li key={u.id}>
                <button
                  type="button"
                  className={`user-list-item ${selected?.id === u.id ? "user-list-item-selected" : ""}`}
                  onClick={() => setSelected(u)}
                >
                  <span>{statusIcon(u.status)}</span>
                  <span>{u.username}</span>
                  <span className="subdued">{u.role}</span>
                </button>
              </li>
            ))}
          </ul>
          <h3>Create user</h3>
          <label className="field"><span>Username</span><input value={newUsername} onChange={(e) => setNewUsername(e.target.value)} /></label>
          <label className="field"><span>Password</span><input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} /></label>
          <label className="field">
            <span>Role</span>
            <select value={newRole} onChange={(e) => setNewRole(e.target.value as UserRole)}>
              <option value="guest">Guest</option>
              <option value="curator">Curator</option>
              <option value="admin">Admin</option>
            </select>
          </label>
          <button className="button small-button" disabled={!newUsername || !newPassword || !!busy}
            onClick={() => act("Create user", async () => {
              await createAdminUser({ username: newUsername, password: newPassword, role: newRole });
              setNewUsername(""); setNewPassword(""); setNewRole("guest");
            })}>
            + Create User
          </button>
        </div>

        {/* Right panel — selected user detail */}
        {selected ? (
          <div className="panel stack">
            <div className="row-between">
              <h2>{selected.username}</h2>
              <span className={`pill pill-${selected.status}`}>{statusIcon(selected.status)} {selected.status}</span>
            </div>
            <p className="subdued">Role: {selected.role} · Created: {selected.created_at ? new Date(selected.created_at).toLocaleDateString() : "—"}</p>
            {selected.locked_until && <p className="subdued">Locked until: {new Date(selected.locked_until).toLocaleString()}</p>}
            {selected.ban_reason && <p className="subdued">Ban reason: {selected.ban_reason}</p>}

            <label className="field">
              <span>Role</span>
              <select value={selected.role} onChange={(e) => setSelected({ ...selected, role: e.target.value as UserRole })}>
                <option value="guest">Guest</option>
                <option value="curator">Curator</option>
                <option value="admin">Admin</option>
              </select>
            </label>
            <label className="field">
              <span>Status</span>
              <select value={selected.status} onChange={(e) => setSelected({ ...selected, status: e.target.value as UserStatus })}>
                <option value="active">Active</option>
                <option value="locked">Locked</option>
                <option value="banned">Banned</option>
                <option value="disabled">Disabled</option>
              </select>
            </label>

            <div className="card-actions">
              <button className="button small-button" disabled={!!busy}
                onClick={() => act("Save", () => updateAdminUser(selected.id, { role: selected.role, status: selected.status }))}>
                Save
              </button>
              <button className="button subtle-button small-button" disabled={!!busy}
                onClick={() => setPasswordTarget(selected)}>
                Reset Password
              </button>
              <button className="button small-button" disabled={!!busy}
                onClick={() => act("Lock 24h", () => {
                  const until = new Date(Date.now() + 24 * 3600 * 1000).toISOString();
                  return updateAdminUser(selected.id, { status: "locked", locked_until: until });
                })}>
                Lock 24h
              </button>
              <button className="button danger-button small-button" disabled={!!busy}
                onClick={() => {
                  const reason = prompt("Ban reason:");
                  if (reason !== null) act("Ban", () => updateAdminUser(selected.id, { status: "banned", ban_reason: reason }));
                }}>
                Ban
              </button>
            </div>
          </div>
        ) : (
          <div className="panel empty-state"><p className="subdued">Select a user to manage.</p></div>
        )}
      </div>

      {passwordTarget && (
        <PasswordModal
          username={passwordTarget.username}
          onClose={() => setPasswordTarget(null)}
          onConfirm={(pw) => {
            act("Reset password", () => resetAdminUserPassword(passwordTarget.id, pw));
            setPasswordTarget(null);
          }}
        />
      )}
    </AppShell>
  );
}
