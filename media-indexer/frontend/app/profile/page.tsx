"use client";

import { FormEvent, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { useSettings } from "@/components/settings-provider";
import { changePassword } from "@/lib/api";

export default function ProfilePage() {
  const { user } = useAuth();
  const { language, setLanguage, theme, setTheme, t } = useSettings();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  return (
    <AppShell title={t("profile")} description="Review your role, preferences, and password.">
      <section className="two-column">
        <section className="panel stack">
          <div>
            <p className="eyebrow">Account</p>
            <h2>{user?.username ?? "User"}</h2>
            <p className="subdued">Signed in as {user?.role ?? "unknown"}.</p>
          </div>
          <div className="metadata-grid">
            <div className="metadata-row">
              <strong>Manage Sources</strong>
              <div className="subdued">{user?.capabilities.can_manage_sources ? "Yes" : "No"}</div>
            </div>
            <div className="metadata-row">
              <strong>Run Scans</strong>
              <div className="subdued">{user?.capabilities.can_run_scans ? "Yes" : "No"}</div>
            </div>
            <div className="metadata-row">
              <strong>Admin Center</strong>
              <div className="subdued">{user?.capabilities.can_view_admin ? "Available" : "Not available for this role"}</div>
            </div>
            <div className="metadata-row">
              <strong>Manage Collections</strong>
              <div className="subdued">{user?.capabilities.can_manage_collections ? "Yes" : "No"}</div>
            </div>
            <div className="metadata-row">
              <strong>Upload Images</strong>
              <div className="subdued">{user?.capabilities.can_upload_assets ? "Yes" : "No"}</div>
            </div>
          </div>
        </section>

        <section className="panel form-grid">
          <div>
            <p className="eyebrow">{t("settings.preferences")}</p>
            <h2>{t("settings.preferences")}</h2>
          </div>
          <label className="field">
            <span>{t("settings.language")}</span>
            <select value={language} onChange={(event) => setLanguage(event.target.value === "fr" ? "fr" : "en")}>
              <option value="en">English</option>
              <option value="fr">Francais</option>
            </select>
          </label>
          <label className="field">
            <span>{t("settings.theme")}</span>
            <select value={theme} onChange={(event) => setTheme(event.target.value === "light" ? "light" : "dark")}>
              <option value="dark">{t("theme.dark")}</option>
              <option value="light">{t("theme.light")}</option>
            </select>
          </label>
        </section>

        <form
          className="panel form-grid"
          onSubmit={async (event: FormEvent) => {
            event.preventDefault();
            setSubmitting(true);
            setError(null);
            setMessage(null);
            try {
              await changePassword({
                current_password: currentPassword,
                new_password: newPassword,
                confirm_password: confirmPassword,
              });
              setCurrentPassword("");
              setNewPassword("");
              setConfirmPassword("");
              setMessage("Password updated.");
            } catch (nextError) {
              setError(nextError instanceof Error ? nextError.message : "Unable to update password.");
            } finally {
              setSubmitting(false);
            }
          }}
        >
          <div>
            <p className="eyebrow">Password</p>
            <h2>Change password</h2>
          </div>
          <label className="field">
            <span>Current password</span>
            <input type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} />
          </label>
          <label className="field">
            <span>New password</span>
            <input type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} />
          </label>
          <label className="field">
            <span>Confirm new password</span>
            <input type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} />
          </label>
          {error ? <p className="subdued">{error}</p> : null}
          {message ? <p className="subdued">{message}</p> : null}
          <button className="button" type="submit" disabled={submitting}>
            {submitting ? "Saving..." : "Update Password"}
          </button>
        </form>
      </section>
    </AppShell>
  );
}
