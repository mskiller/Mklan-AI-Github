/**
 * Wildcard Workshop page — embeds the original app at /wildcards.
 * Scopes styles inside .wildcards-page-container to prevent leaks.
 */
import { useEffect, useState } from 'react';
import './styles.css'; // Load scoped wildcard workshop styles

export function WildcardsPage() {
  const [Component, setComponent] = useState<React.ComponentType | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    import('./App').then((m: any) => setComponent(() => m.default ?? m.App))
      .catch((err) => setError(String(err)));
  }, []);

  if (error) return <div style={{ padding: '2rem', color: 'var(--danger)' }}>Failed to load: {error}</div>;
  if (!Component) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '60vh', color: 'var(--text-secondary)' }}>
        <span style={{ fontSize: '1.1rem', fontWeight: 500 }}>Loading Wildcard Workshop…</span>
      </div>
    );
  }

  return (
    <div className="wildcards-page-container">
      <Component />
    </div>
  );
}