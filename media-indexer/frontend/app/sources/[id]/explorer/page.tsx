"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import {
  createSource,
  fetchSource,
  fetchSourceBrowse,
  fetchSourceTree,
  triggerScan,
} from "@/lib/api";
import { Source, SourceBrowseResponse, SourceTreeResponse } from "@/lib/types";

// ─── Tree node ───────────────────────────────────────────────────────────────

interface TreeNode {
  name: string;
  path: string;   // relative path within source
  depth: number;
  expanded: boolean;
  loaded: boolean;
  children: TreeNode[];
}

function makeNode(name: string, path: string, depth: number): TreeNode {
  return { name, path, depth, expanded: false, loaded: false, children: [] };
}

// Build root node from source tree response
function buildRootNode(tree: SourceTreeResponse): TreeNode {
  const root = makeNode("(root)", "", 0);
  root.loaded = true;
  root.expanded = true;
  root.children = tree.dirs.map((dir) => makeNode(dir, dir, 1));
  return root;
}

// Insert loaded children into a node by path
function insertChildren(
  node: TreeNode,
  targetPath: string,
  dirs: string[]
): TreeNode {
  if (node.path === targetPath) {
    return {
      ...node,
      loaded: true,
      expanded: true,
      children: dirs.map((dir) => {
        const childPath = targetPath ? `${targetPath}/${dir}` : dir;
        return makeNode(dir, childPath, node.depth + 1);
      }),
    };
  }
  return {
    ...node,
    children: node.children.map((child) =>
      insertChildren(child, targetPath, dirs)
    ),
  };
}

// Collapse/expand a node by path
function toggleNode(node: TreeNode, targetPath: string): TreeNode {
  if (node.path === targetPath) {
    return { ...node, expanded: !node.expanded };
  }
  return {
    ...node,
    children: node.children.map((child) =>
      toggleNode(child, targetPath)
    ),
  };
}

// Flatten tree for rendering
function flattenTree(node: TreeNode, out: TreeNode[] = []): TreeNode[] {
  out.push(node);
  if (node.expanded) {
    for (const child of node.children) {
      flattenTree(child, out);
    }
  }
  return out;
}

// ─── Main page ───────────────────────────────────────────────────────────────

function FileExplorerContent() {
  const { user } = useAuth();
  const params = useParams<{ id: string }>();
  const router = useRouter();

  const [source, setSource] = useState<Source | null>(null);
  const [rootNode, setRootNode] = useState<TreeNode | null>(null);
  const [selectedPath, setSelectedPath] = useState<string>("");
  const [browse, setBrowse] = useState<SourceBrowseResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [browseLoading, setBrowseLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [scanSubmitting, setScanSubmitting] = useState(false);
  const [sourceCreating, setSourceCreating] = useState(false);

  // Load source metadata + initial tree (root level dirs)
  useEffect(() => {
    const init = async () => {
      setLoading(true);
      setError(null);
      try {
        const [src, tree] = await Promise.all([
          fetchSource(params.id),
          fetchSourceTree(params.id, ""),
        ]);
        setSource(src);
        setRootNode(buildRootNode(tree));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load source.");
      } finally {
        setLoading(false);
      }
    };
    void init();
  }, [params.id]);

  // Browse selected folder
  const loadBrowse = useCallback(
    async (path: string) => {
      setBrowseLoading(true);
      setError(null);
      try {
        const result = await fetchSourceBrowse(params.id, path);
        setBrowse(result);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to browse folder.");
      } finally {
        setBrowseLoading(false);
      }
    },
    [params.id]
  );

  // Initial browse of root
  useEffect(() => {
    void loadBrowse("");
  }, [loadBrowse]);

  const selectFolder = (path: string) => {
    setSelectedPath(path);
    void loadBrowse(path);
  };

  // Expand / collapse a tree node, lazy-loading children if needed
  const handleTreeRowClick = async (node: TreeNode) => {
    if (node.path === "" && node.depth === 0) {
      // root — just select it
      selectFolder("");
      return;
    }

    // Select this folder in main panel
    selectFolder(node.path);

    if (!node.loaded) {
      // Lazy-load children
      try {
        const tree = await fetchSourceTree(params.id, node.path);
        setRootNode((prev) =>
          prev ? insertChildren(prev, node.path, tree.dirs) : prev
        );
      } catch {
        // Silently ignore — node stays collapsed
        setRootNode((prev) =>
          prev ? insertChildren(prev, node.path, []) : prev
        );
      }
    } else {
      setRootNode((prev) =>
        prev ? toggleNode(prev, node.path) : prev
      );
    }
  };

  // Breadcrumbs: split selectedPath into segments
  const breadcrumbs: { label: string; path: string }[] = [
    { label: source?.name ?? "Root", path: "" },
    ...selectedPath
      .split("/")
      .filter(Boolean)
      .map((seg, i, arr) => ({
        label: seg,
        path: arr.slice(0, i + 1).join("/"),
      })),
  ];

  const directories = browse?.entries.filter((e) => e.entry_type === "directory") ?? [];
  const images = browse?.entries.filter(
    (e) => e.entry_type === "file" && e.media_type === "image"
  ) ?? [];
  const fileCount = browse?.entries.filter((e) => e.entry_type === "file") ?? [];

  const flatNodes = rootNode ? flattenTree(rootNode) : [];

  const handleCreateSource = async () => {
    if (!source?.root_path || !selectedPath) return;
    const suggestedName = selectedPath.split("/").filter(Boolean).at(-1) ?? "subfolder";
    const name = window.prompt("New source name", suggestedName)?.trim();
    if (!name) return;

    setSourceCreating(true);
    setError(null);
    setMessage(null);
    try {
      const rootPath = `${source.root_path.replace(/\/$/, "")}/${selectedPath}`;
      const created = await createSource({ name, root_path: rootPath, type: "mounted_fs" });
      setMessage(`Source "${created.name}" created.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create source.");
    } finally {
      setSourceCreating(false);
    }
  };

  const handleScan = async (scan_mode: "basic" | "metadata") => {
    setScanSubmitting(true);
    setError(null);
    setMessage(null);
    try {
      const job = await triggerScan(params.id, { scan_mode, path_filter: selectedPath || null });
      setMessage(`${scan_mode.toUpperCase()} scan queued: ${job.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start scan.");
    } finally {
      setScanSubmitting(false);
    }
  };

  return (
    <AppShell
      title={source ? `Explorer — ${source.name}` : "File Explorer"}
      description="Windows-style folder explorer. Expand the tree on the left to navigate, then index a subfolder as its own source."
      actions={
        <div className="page-actions">
          <Link href={`/sources/${params.id}`} className="button ghost-button small-button">
            Gallery View
          </Link>
          <Link href="/sources" className="button ghost-button small-button">
            All Sources
          </Link>
          {user?.capabilities.can_run_scans && (
            <button
              className="button subtle-button small-button"
              type="button"
              disabled={scanSubmitting}
              onClick={() => void handleScan("basic")}
            >
              {scanSubmitting ? "Starting..." : "Quick Index Folder"}
            </button>
          )}
          {user?.capabilities.can_run_scans && (
            <button
              className="button ghost-button small-button"
              type="button"
              disabled={scanSubmitting}
              onClick={() => void handleScan("metadata")}
            >
              Parse Metadata
            </button>
          )}
        </div>
      }
    >
      {error && <section className="panel empty-state" style={{ color: "var(--danger, #e05555)" }}>{error}</section>}
      {message && <section className="panel empty-state">{message}</section>}

      {loading ? (
        <section className="panel empty-state">Loading file explorer…</section>
      ) : (
        <div className="file-explorer-layout">
          {/* ── Left: folder tree ─────────────────────────────────────── */}
          <nav className="file-explorer-sidebar" aria-label="Folder tree">
            <div className="file-explorer-source-header">{source?.name ?? "Source"}</div>
            {flatNodes.map((node) => {
              const isActive = node.path === selectedPath;
              const hasChevron = node.depth === 0 || !node.loaded || node.children.length > 0;
              return (
                <button
                  key={node.path === "" ? "__root__" : node.path}
                  type="button"
                  className={`file-explorer-tree-row ${isActive ? "file-explorer-tree-row-active" : ""}`}
                  onClick={() => void handleTreeRowClick(node)}
                  title={node.path || "(root)"}
                >
                  {/* Indent */}
                  {node.depth > 0 && (
                    <span
                      className="file-explorer-tree-indent"
                      style={{ width: `${(node.depth - 1) * 16 + 12}px` }}
                    />
                  )}
                  {/* Chevron */}
                  {hasChevron ? (
                    <span
                      className={`file-explorer-tree-chevron ${node.expanded ? "file-explorer-tree-chevron-open" : ""}`}
                    >
                      ▶
                    </span>
                  ) : (
                    <span className="file-explorer-tree-chevron" style={{ opacity: 0 }}>▶</span>
                  )}
                  {/* Icon */}
                  <span className="file-explorer-tree-icon">
                    {node.depth === 0 ? "💾" : node.expanded ? "📂" : "📁"}
                  </span>
                  {/* Label */}
                  <span className="file-explorer-tree-label">{node.name}</span>
                </button>
              );
            })}
          </nav>

          {/* ── Right: folder contents ────────────────────────────────── */}
          <main className="file-explorer-main">
            {/* Breadcrumbs */}
            <div className="file-explorer-breadcrumbs">
              {breadcrumbs.map((crumb, i) => (
                <span key={crumb.path} style={{ display: "flex", alignItems: "center", gap: "0.3rem" }}>
                  {i > 0 && <span className="file-explorer-breadcrumb-sep">›</span>}
                  <button
                    type="button"
                    className={`file-explorer-breadcrumb-btn ${i === breadcrumbs.length - 1 ? "file-explorer-breadcrumb-btn-active" : ""}`}
                    onClick={() => selectFolder(crumb.path)}
                    disabled={i === breadcrumbs.length - 1}
                  >
                    {crumb.label}
                  </button>
                </span>
              ))}
            </div>

            {/* Action bar */}
            <div className="file-explorer-action-bar">
              <span className="file-explorer-status">
                {browseLoading
                  ? "Loading…"
                  : `${directories.length} folder${directories.length !== 1 ? "s" : ""}, ${fileCount.length} file${fileCount.length !== 1 ? "s" : ""} (${images.length} image${images.length !== 1 ? "s" : ""})`}
              </span>
              {user?.capabilities.can_manage_sources && selectedPath && (
                <button
                  type="button"
                  className="button small-button"
                  disabled={sourceCreating}
                  onClick={handleCreateSource}
                  title="Create a new indexed source rooted at this folder"
                >
                  {sourceCreating ? "Creating…" : "📌 Index This Folder as Source"}
                </button>
              )}
              {selectedPath && (
                <Link
                  href={`/sources/${params.id}?path=${encodeURIComponent(selectedPath)}`}
                  className="button ghost-button small-button"
                >
                  Open Gallery View
                </Link>
              )}
            </div>

            {browseLoading ? (
              <div className="file-explorer-empty">Loading folder…</div>
            ) : (
              <>
                {/* Sub-folders grid */}
                {directories.length > 0 && (
                  <div>
                    <p className="eyebrow" style={{ marginBottom: "0.5rem" }}>Folders</p>
                    <div className="file-explorer-folder-grid">
                      {directories.map((entry) => (
                        <button
                          key={entry.relative_path}
                          type="button"
                          className="file-explorer-folder-tile"
                          onClick={() => selectFolder(entry.relative_path)}
                        >
                          <span className="file-explorer-folder-icon">📁</span>
                          <span className="file-explorer-folder-name">{entry.name}</span>
                          {entry.modified_at && (
                            <span className="file-explorer-folder-meta">
                              {new Date(entry.modified_at).toLocaleDateString()}
                            </span>
                          )}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* Image count summary */}
                {images.length > 0 && (
                  <div>
                    <p className="eyebrow" style={{ marginBottom: "0.5rem" }}>
                      Images in this folder
                    </p>
                    <div className="panel" style={{ padding: "1rem" }}>
                      <p style={{ margin: 0 }}>
                        <strong>{images.length}</strong> image{images.length !== 1 ? "s" : ""} found.{" "}
                        {selectedPath ? (
                          <>
                            <Link
                              href={`/sources/${params.id}?path=${encodeURIComponent(selectedPath)}`}
                              style={{ color: "var(--accent)" }}
                            >
                              Open gallery view
                            </Link>{" "}
                            to browse them, or use{" "}
                            <strong>📌 Index This Folder as Source</strong> above to make this folder its own indexed source.
                          </>
                        ) : (
                          <>Use the gallery view to browse them.</>
                        )}
                      </p>
                      {/* Image name list (first 12) */}
                      <div style={{ marginTop: "0.75rem", display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
                        {images.slice(0, 12).map((img) => (
                          <span key={img.relative_path} className="chip" style={{ fontSize: "0.75rem" }}>
                            {img.name}
                          </span>
                        ))}
                        {images.length > 12 && (
                          <span className="chip" style={{ fontSize: "0.75rem", opacity: 0.6 }}>
                            +{images.length - 12} more
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                )}

                {directories.length === 0 && images.length === 0 && fileCount.length === 0 && (
                  <div className="file-explorer-empty">
                    This folder is empty.
                  </div>
                )}

                {directories.length === 0 && images.length === 0 && fileCount.length > 0 && (
                  <div className="file-explorer-empty">
                    {fileCount.length} file{fileCount.length !== 1 ? "s" : ""} (no supported images or subfolders).
                  </div>
                )}
              </>
            )}
          </main>
        </div>
      )}
    </AppShell>
  );
}

export default function FileExplorerPage() {
  return (
    <Suspense
      fallback={
        <AppShell title="File Explorer" description="Windows-style folder explorer for sources.">
          <section className="panel empty-state">Loading…</section>
        </AppShell>
      }
    >
      <FileExplorerContent />
    </Suspense>
  );
}
