"use client";

export function BreadcrumbBar({
  sourceName,
  path,
  onNavigate,
}: {
  sourceName: string;
  path: string;
  onNavigate: (segPath: string) => void;
}) {
  // Split path into segments, filtering empty strings
  const segments = path ? path.split("/").filter(Boolean) : [];

  return (
    <nav className="breadcrumb-bar" aria-label="Folder navigation">
      <button
        type="button"
        className="breadcrumb-seg"
        onClick={() => onNavigate("")}
      >
        {sourceName}
      </button>
      {segments.map((seg, i) => {
        const segPath = segments.slice(0, i + 1).join("/");
        const isLast = i === segments.length - 1;
        return (
          <span key={segPath} className="breadcrumb-item">
            <span className="breadcrumb-sep">/</span>
            {isLast ? (
              <span className="breadcrumb-seg breadcrumb-active" aria-current="page">
                {seg}
              </span>
            ) : (
              <button
                type="button"
                className="breadcrumb-seg"
                onClick={() => onNavigate(segPath)}
              >
                {seg}
              </button>
            )}
          </span>
        );
      })}
    </nav>
  );
}
