"use client";

export function FolderTile({
  name,
  previewUrls = [],
  indexedCount,
  onNavigate,
}: {
  name: string;
  previewUrls?: (string | null)[];
  indexedCount?: number;
  onNavigate: () => void;
}) {
  const previews = previewUrls.filter(Boolean).slice(0, 4) as string[];

  return (
    <button type="button" className="folder-tile" onClick={onNavigate}>
      <div className="folder-tile-mosaic">
        {previews.length > 0 ? (
          previews.map((url, i) => (
            <img key={i} src={url} alt="" loading="lazy" />
          ))
        ) : (
          <div className="folder-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
            </svg>
          </div>
        )}
      </div>
      <div className="folder-tile-name">
        <span>{name}</span>
        {indexedCount !== undefined ? (
          <span className="chip" style={{ fontSize: "0.75rem", padding: "0.15rem 0.5rem" }}>
            {indexedCount}
          </span>
        ) : null}
      </div>
    </button>
  );
}
