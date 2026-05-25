"use client";

import { FormEvent, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import {
  createApiToken,
  createWebhook,
  deleteWebhook,
  fetchApiTokens,
  fetchWebhookEvents,
  fetchWebhooks,
  revokeApiToken,
  testWebhook,
  updateWebhook,
} from "@/lib/api";
import { ApiTokenSummary, WebhookEndpoint } from "@/lib/types";


function randomSecret() {
  return Array.from(crypto.getRandomValues(new Uint8Array(24)))
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("");
}

export default function AdminIntegrationsPage() {
  const [webhooks, setWebhooks] = useState<WebhookEndpoint[]>([]);
  const [tokens, setTokens] = useState<ApiTokenSummary[]>([]);
  const [events, setEvents] = useState<string[]>([]);
  const [url, setUrl] = useState("");
  const [secret, setSecret] = useState(() => randomSecret());
  const [selectedEvents, setSelectedEvents] = useState<string[]>([]);
  const [tokenName, setTokenName] = useState("Export Client");
  const [createdToken, setCreatedToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      const [nextWebhooks, nextTokens, nextEvents] = await Promise.all([
        fetchWebhooks(),
        fetchApiTokens(),
        fetchWebhookEvents(),
      ]);
      setWebhooks(nextWebhooks);
      setTokens(nextTokens);
      setEvents(nextEvents);
      if (!selectedEvents.length) {
        setSelectedEvents(nextEvents.slice(0, 2));
      }
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Unable to load integrations.");
    }
  };

  useEffect(() => {
    void load();
  }, []);

  return (
    <AppShell
      title="Admin Integrations"
      description="Manage outgoing webhooks and read-only export API tokens."
      actions={
        <div className="page-actions">
          <a href="/admin" className="button ghost-button small-button">Admin Center</a>
          <a href="/admin/health" className="button subtle-button small-button">Health</a>
        </div>
      }
    >
      {error ? <section className="panel empty-state">{error}</section> : null}

      <section className="two-column">
        <form
          className="panel form-grid"
          onSubmit={async (event: FormEvent) => {
            event.preventDefault();
            setError(null);
            try {
              await createWebhook({ url, secret, events: selectedEvents });
              setUrl("");
              setSecret(randomSecret());
              await load();
            } catch (nextError) {
              setError(nextError instanceof Error ? nextError.message : "Unable to create webhook.");
            }
          }}
        >
          <div>
            <p className="eyebrow">Webhooks</p>
            <h2>Add Endpoint</h2>
          </div>
          <label className="field">
            <span>URL</span>
            <input value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://example.com/webhook" />
          </label>
          <label className="field">
            <span>Secret</span>
            <input value={secret} onChange={(event) => setSecret(event.target.value)} />
          </label>
          <div className="chip-row">
            {events.map((eventName) => {
              const active = selectedEvents.includes(eventName);
              return (
                <button
                  key={eventName}
                  type="button"
                  className={`chip buttonless ${active ? "chip-accent" : ""}`}
                  onClick={() =>
                    setSelectedEvents((current) =>
                      current.includes(eventName)
                        ? current.filter((value) => value !== eventName)
                        : [...current, eventName]
                    )
                  }
                >
                  {eventName}
                </button>
              );
            })}
          </div>
          <button className="button" type="submit">Create Webhook</button>
        </form>

        <section className="panel stack">
          <div>
            <p className="eyebrow">Registered</p>
            <h2>Webhook Endpoints</h2>
          </div>
          <div className="list-stack compact-list-stack">
            {webhooks.map((webhook) => (
              <article key={webhook.id} className="metadata-row" style={{ alignItems: "flex-start" }}>
                <div>
                  <strong>{webhook.url}</strong>
                  <div className="subdued">{webhook.events.join(", ")}</div>
                  <div className="subdued">Last status: {webhook.last_status_code ?? "Never"}</div>
                </div>
                <div className="card-actions">
                  <button
                    type="button"
                    className="button ghost-button small-button"
                    onClick={async () => {
                      await updateWebhook(webhook.id, { enabled: !webhook.enabled });
                      await load();
                    }}
                  >
                    {webhook.enabled ? "Disable" : "Enable"}
                  </button>
                  <button type="button" className="button ghost-button small-button" onClick={async () => { await testWebhook(webhook.id); await load(); }}>
                    Test
                  </button>
                  <button type="button" className="button ghost-button small-button" onClick={async () => { await deleteWebhook(webhook.id); await load(); }}>
                    Delete
                  </button>
                </div>
              </article>
            ))}
            {!webhooks.length ? <p className="subdued">No webhooks configured yet.</p> : null}
          </div>
        </section>
      </section>

      <section className="two-column">
        <form
          className="panel form-grid"
          onSubmit={async (event: FormEvent) => {
            event.preventDefault();
            setError(null);
            try {
              const response = await createApiToken({ name: tokenName });
              setCreatedToken(response.token);
              setTokenName("Export Client");
              await load();
            } catch (nextError) {
              setError(nextError instanceof Error ? nextError.message : "Unable to create token.");
            }
          }}
        >
          <div>
            <p className="eyebrow">API Tokens</p>
            <h2>Create Token</h2>
          </div>
          <label className="field">
            <span>Name</span>
            <input value={tokenName} onChange={(event) => setTokenName(event.target.value)} />
          </label>
          <button className="button" type="submit">Create Token</button>
          {createdToken ? (
            <div className="panel stack">
              <strong>Copy this token now</strong>
              <code style={{ wordBreak: "break-all" }}>{createdToken}</code>
            </div>
          ) : null}
        </form>

        <section className="panel stack">
          <div>
            <p className="eyebrow">Active</p>
            <h2>Export Tokens</h2>
          </div>
          <div className="list-stack compact-list-stack">
            {tokens.map((token) => (
              <article key={token.id} className="metadata-row" style={{ alignItems: "flex-start" }}>
                <div>
                  <strong>{token.name}</strong>
                  <div className="subdued">{token.token_prefix}</div>
                  <div className="subdued">Last used: {token.last_used_at ?? "Never"}</div>
                </div>
                <button type="button" className="button ghost-button small-button" onClick={async () => { await revokeApiToken(token.id); await load(); }}>
                  Revoke
                </button>
              </article>
            ))}
            {!tokens.length ? <p className="subdued">No API tokens created yet.</p> : null}
          </div>
        </section>
      </section>
    </AppShell>
  );
}
