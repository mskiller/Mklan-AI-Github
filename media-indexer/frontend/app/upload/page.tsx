"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { fetchSources, uploadToSource } from "@/lib/api";
import { Source, SourceUploadResponse } from "@/lib/types";

export default function UploadPage() {
  const { user } = useAuth();
  const [sources, setSources] = useState<Source[]>([]);
  const [folder, setFolder] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [result, setResult] = useState<SourceUploadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        setSources(await fetchSources());
      } catch (nextError) {
        setError(nextError instanceof Error ? nextError.message : "Unable to load sources.");
      }
    };
    void load();
  }, []);

  const uploadSource = useMemo(
    () => sources.find((source) => source.name.toLowerCase() === "upload"),
    [sources]
  );

  if (user && !user.capabilities.can_upload_assets) {
    return (
      <AppShell title="Upload" description="Send new images into the managed upload source.">
        <section className="panel empty-state">
          <h2>Upload access required</h2>
          <p className="subdued">This page is available to admin and curator accounts.</p>
        </section>
      </AppShell>
    );
  }

  return (
    <AppShell
      title="Upload"
      description="Upload new media into the inbox-backed upload source. Files land in review first, then can be approved into a target library source."
      actions={
        uploadSource ? (
          <div className="page-actions">
            <Link href={`/sources/${uploadSource.id}`} className="button subtle-button small-button">
              Open Upload Source
            </Link>
            <Link href="/inbox" className="button ghost-button small-button">
              Open Inbox
            </Link>
          </div>
        ) : undefined
      }
    >
      <section className="two-column">
        <form
          className="panel form-grid"
          onSubmit={async (event: FormEvent) => {
            event.preventDefault();
            if (!uploadSource || !files.length) {
              return;
            }
            setSubmitting(true);
            setError(null);
            setResult(null);
            try {
              const response = await uploadToSource(uploadSource.id, files, folder);
              setResult(response);
              setFiles([]);
              setFolder("");
            } catch (nextError) {
              setError(nextError instanceof Error ? nextError.message : "Unable to upload files.");
            } finally {
              setSubmitting(false);
            }
          }}
        >
          <div>
            <p className="eyebrow">Upload Source</p>
            <h2>{uploadSource?.name ?? "Preparing upload source"}</h2>
            <p className="subdued">{uploadSource?.display_root_path ?? "Waiting for the system upload source to appear."}</p>
          </div>
          <label className="field">
            <span>Subfolder inside upload source</span>
            <input
              value={folder}
              onChange={(event) => setFolder(event.target.value)}
              placeholder="optional/subfolder"
            />
          </label>
          <label className="field">
            <span>Images</span>
            <input
              type="file"
              accept="image/*"
              multiple
              onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
            />
          </label>
          <div className="chip-row">
            <span className="chip">{files.length} file{files.length === 1 ? "" : "s"} selected</span>
            {folder ? <span className="chip">Folder: {folder}</span> : <span className="chip">Root folder</span>}
          </div>
          <button className="button" type="submit" disabled={!uploadSource || !files.length || submitting}>
            {submitting ? "Uploading..." : "Upload Images"}
          </button>
          {error ? <p className="subdued">{error}</p> : null}
        </form>

        <section className="panel stack">
          <div>
            <p className="eyebrow">What Happens Next</p>
            <h2>Server-side intake</h2>
          </div>
          <div className="metadata-grid">
            <div className="metadata-row">
              <strong>Storage</strong>
              <div className="subdued">Files go only into the dedicated `upload` source on the server.</div>
            </div>
            <div className="metadata-row">
              <strong>Indexing</strong>
              <div className="subdued">Uploads now enter the inbox review flow. Approving an item moves it into a target source and queues the scan.</div>
            </div>
            <div className="metadata-row">
              <strong>Permissions</strong>
              <div className="subdued">Curators can upload and manage collections without getting source or database admin rights.</div>
            </div>
          </div>
          {result ? (
            <section className="panel stack">
              <div>
                <p className="eyebrow">Upload Complete</p>
                <h2>{result.uploaded_files.length} file{result.uploaded_files.length === 1 ? "" : "s"} added</h2>
              </div>
              <div className="chip-row">
                {result.scan_job_id ? <span className="chip">Scan queued</span> : <span className="chip">Inbox review required</span>}
                <span className="chip">{result.folder || "root folder"}</span>
              </div>
              <div className="list-stack compact-list-stack">
                {result.uploaded_files.map((file) => (
                  <div key={file} className="metadata-row">
                    <strong>{file}</strong>
                  </div>
                ))}
              </div>
              <div className="card-actions">
                {uploadSource ? (
                  <Link href={`/sources/${uploadSource.id}${result.folder ? `?path=${encodeURIComponent(result.folder)}` : ""}`} className="button subtle-button small-button">
                    Open Uploaded Folder
                  </Link>
                ) : null}
                <Link href="/inbox" className="button ghost-button small-button">
                  Review Inbox
                </Link>
              </div>
            </section>
          ) : null}
        </section>
      </section>
    </AppShell>
  );
}
