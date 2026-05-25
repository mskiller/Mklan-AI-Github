import { useEffect, useState } from 'react';
import { BadgeCheck, Library, Tags } from 'lucide-react';
import './styles.css';

type AddonState = {
  compatibility?: unknown;
  vaultCharacters?: unknown[];
  wildcardSuggestions?: unknown[];
  error?: string;
};

const CARDS_API = import.meta.env.VITE_CARDS_API_BASE_URL ?? '/cards';

export function CardsPage() {
  const [Component, setComponent] = useState<React.ComponentType | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [addons, setAddons] = useState<AddonState>({});

  useEffect(() => {
    import('./App')
      .then((m) => setComponent(() => m.default))
      .catch((err) => setError(String(err)));
  }, []);

  async function loadVault() {
    try {
      const response = await fetch(`${CARDS_API}/vault/characters`);
      const payload = await response.json();
      setAddons((current) => ({ ...current, vaultCharacters: payload.characters ?? [] }));
    } catch (err) {
      setAddons((current) => ({ ...current, error: err instanceof Error ? err.message : String(err) }));
    }
  }

  async function loadWildcards() {
    try {
      const response = await fetch(`${CARDS_API}/wildcard-bridge/suggestions?limit=12`);
      const payload = await response.json();
      setAddons((current) => ({ ...current, wildcardSuggestions: payload.suggestions ?? [] }));
    } catch (err) {
      setAddons((current) => ({ ...current, error: err instanceof Error ? err.message : String(err) }));
    }
  }

  if (error) return <div style={{ padding: '2rem', color: 'var(--danger)' }}>Failed to load Cards: {error}</div>;

  return (
    <div className="cards-page-container">
      <section className="cards-addon-strip">
        <button type="button" onClick={loadVault}>
          <Library size={16} /> Vault
        </button>
        <button type="button" onClick={loadWildcards}>
          <Tags size={16} /> Wildcard Bridge
        </button>
        <span className="cards-addon-status">
          <BadgeCheck size={16} /> Compatibility Inspector runs before sync and is available per project.
        </span>
        {addons.error ? <span className="cards-addon-error">{addons.error}</span> : null}
      </section>
      {addons.vaultCharacters ? (
        <section className="cards-addon-panel">
          <strong>Shared Character Vault</strong>
          <span>{addons.vaultCharacters.length} reusable character entries</span>
        </section>
      ) : null}
      {addons.wildcardSuggestions ? (
        <section className="cards-addon-panel">
          <strong>Wildcard-to-Card Prompt Bridge</strong>
          <span>{addons.wildcardSuggestions.length} prompt tags ready for image prompts</span>
        </section>
      ) : null}
      {Component ? <Component /> : <div className="cards-loading">Loading SillyTavern Cards...</div>}
    </div>
  );
}
