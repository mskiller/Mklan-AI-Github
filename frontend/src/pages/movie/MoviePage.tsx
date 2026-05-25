/**
 * Movie Scripting page — embeds the original app at /movie.
 * Scopes styles inside .movie-page-container to prevent leaks.
 */
import { useEffect, useState } from 'react';
import './styles.css'; // Load scoped movie scripting styles

export function MoviePage() {
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
        <span style={{ fontSize: '1.1rem', fontWeight: 500 }}>Loading Movie Scripting Studio…</span>
      </div>
    );
  }

  return (
    <div className="movie-page-container">
      <Component />
    </div>
  );
}