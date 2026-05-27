import { useCallback, useEffect, useState } from 'react';
import { Outlet, NavLink, useLocation } from 'react-router-dom';
import { Box, Brain, Briefcase, Film, Tags, LayoutDashboard, Loader2, MessageSquare, Plus, Send, Settings, Images, Menu, X, ScrollText, Sparkles, Video, Contact, Database, ChevronLeft, ChevronRight } from 'lucide-react';
import { useDeviceMode } from '../hooks/useDeviceMode';
import { useUiPreferences } from '../hooks/useUiPreferences';
import { useTranslation } from '../i18n';

const navItems = [
  { to: '/', key: 'dashboard', icon: LayoutDashboard, exact: true },
  { to: '/training', key: 'training', icon: Brain },
  { to: '/generation', key: 'generation', icon: Sparkles },
  { to: '/characters', key: 'characters', icon: Contact },
  { to: '/video', key: 'video', icon: Video },
  { to: '/wildcards', key: 'wildcards', icon: Tags },
  { to: '/movie', key: 'movie', icon: Film },
  { to: '/cards', key: 'cards', icon: ScrollText },
  { to: '/gallery', key: 'gallery', icon: Images },
  { to: '/library', key: 'library', icon: Database },
  { to: '/settings', key: 'settings', icon: Settings },
];

interface WorkspaceRead {
  id: string;
  name: string;
  active: boolean;
}

interface CopilotMessage {
  role: 'user' | 'assistant';
  content: string;
}

async function readJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || `Request failed: ${response.status}`);
  }
  return payload as T;
}

export function Layout() {
  const location = useLocation();
  const deviceMode = useDeviceMode();
  const { language, theme, setLanguage, setTheme } = useUiPreferences();
  const { t } = useTranslation();
  const isMobile = deviceMode === 'mobile';
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [sidebarExpanded, setSidebarExpanded] = useState(true);
  const [workspaces, setWorkspaces] = useState<WorkspaceRead[]>([]);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState('default');
  const [workspaceBusy, setWorkspaceBusy] = useState(false);
  const [copilotOpen, setCopilotOpen] = useState(false);
  const [copilotPrompt, setCopilotPrompt] = useState('');
  const [copilotMessages, setCopilotMessages] = useState<CopilotMessage[]>([]);
  const [copilotBusy, setCopilotBusy] = useState(false);
  const [copilotError, setCopilotError] = useState('');
  const currentNavItem = navItems.find((item) =>
    item.exact ? location.pathname === item.to : item.to !== '/' && location.pathname.startsWith(item.to),
  ) || navItems[0];
  const currentLabel = t(`nav.${currentNavItem.key}`);

  const loadWorkspaces = useCallback(async () => {
    const payload = await readJson<{ active_workspace_id: string; workspaces: WorkspaceRead[] }>('/api/workspaces');
    setWorkspaces(payload.workspaces || []);
    setActiveWorkspaceId(payload.active_workspace_id || 'default');
  }, []);

  const activateWorkspace = useCallback(async (workspaceId: string) => {
    if (!workspaceId || workspaceId === activeWorkspaceId) return;
    setWorkspaceBusy(true);
    try {
      const workspace = await readJson<WorkspaceRead>(`/api/workspaces/${workspaceId}/activate`, { method: 'POST' });
      setActiveWorkspaceId(workspace.id);
      await loadWorkspaces();
    } finally {
      setWorkspaceBusy(false);
    }
  }, [activeWorkspaceId, loadWorkspaces]);

  const createWorkspace = useCallback(async () => {
    const name = window.prompt('Workspace name');
    if (!name?.trim()) return;
    setWorkspaceBusy(true);
    try {
      const workspace = await readJson<WorkspaceRead>('/api/workspaces', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim(), activate: true }),
      });
      setActiveWorkspaceId(workspace.id);
      await loadWorkspaces();
    } finally {
      setWorkspaceBusy(false);
    }
  }, [loadWorkspaces]);

  const sendCopilot = useCallback(async () => {
    const prompt = copilotPrompt.trim();
    if (!prompt || copilotBusy) return;
    const userMessage: CopilotMessage = { role: 'user', content: prompt };
    const history = [...copilotMessages, userMessage].slice(-8);
    setCopilotMessages((current) => [...current, userMessage]);
    setCopilotPrompt('');
    setCopilotBusy(true);
    setCopilotError('');
    try {
      const response = await readJson<{ content: string; mode: string }>('/api/copilot/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          route: location.pathname,
          module: currentNavItem.key,
          message: prompt,
          history,
          selection: { nav_label: currentLabel },
        }),
      });
      setCopilotMessages((current) => [...current, { role: 'assistant', content: response.content }]);
    } catch (error: any) {
      setCopilotError(error.message || 'Copilot request failed.');
    } finally {
      setCopilotBusy(false);
    }
  }, [copilotBusy, copilotMessages, copilotPrompt, currentLabel, currentNavItem.key, location.pathname]);

  useEffect(() => {
    setMobileMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    void loadWorkspaces().catch(() => {
      setWorkspaces([{ id: 'default', name: 'Default Workspace', active: true }]);
      setActiveWorkspaceId('default');
    });
  }, [loadWorkspaces]);

  useEffect(() => {
    if (!isMobile) {
      setMobileMenuOpen(false);
    }
  }, [isMobile]);

  useEffect(() => {
    if (!mobileMenuOpen) {
      return;
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setMobileMenuOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [mobileMenuOpen]);

  return (
    <div className={`studio-shell studio-shell-${deviceMode}`} style={{ display: 'flex', flexDirection: isMobile ? 'column' : 'row', height: '100vh', position: 'relative', overflow: 'hidden' }}>
      {/* Ambient Background Glows */}
      <div className="ambient-glow primary" />
      <div className="ambient-glow secondary" />

      {isMobile ? (
        <header style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0.65rem 0.75rem',
          minHeight: '58px',
          background: 'rgba(10, 10, 12, 0.7)',
          backdropFilter: 'blur(20px)',
          borderBottom: '1px solid var(--border-color)',
          flexShrink: 0,
          position: 'relative',
          zIndex: 10,
          gap: '0.6rem',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', minWidth: 0 }}>
            <div style={{ background: 'linear-gradient(135deg, var(--accent), #5a4bcf)', borderRadius: '8px', padding: '0.4rem', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 4px 15px var(--accent-glow)' }}>
              <Box size={20} color="#fff" />
            </div>
            <span style={{ fontFamily: 'Outfit', fontWeight: 700, fontSize: '1.05rem', letterSpacing: '-0.02em', background: 'linear-gradient(to right, #fff, #bbb)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', whiteSpace: 'nowrap' }}>
              Mklan Studio
            </span>
            <span style={{ color: 'var(--text-secondary)', fontSize: '0.78rem', fontWeight: 600, padding: '0.2rem 0.45rem', border: '1px solid var(--border-color)', borderRadius: '999px', whiteSpace: 'nowrap' }}>
              {currentLabel}
            </span>
          </div>
          <button
            type="button"
            aria-label="Menu"
            aria-expanded={mobileMenuOpen}
            onClick={() => setMobileMenuOpen((open) => !open)}
            className="mobile-menu-trigger"
          >
            {mobileMenuOpen ? <X size={22} /> : <Menu size={22} />}
          </button>
        </header>
      ) : (
        <aside className={`studio-sidebar ${sidebarExpanded ? '' : 'collapsed'}`}>
          <div className="sidebar-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', overflow: 'hidden' }}>
              <div style={{ background: 'linear-gradient(135deg, var(--accent), #5a4bcf)', borderRadius: '8px', padding: '0.4rem', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, boxShadow: '0 4px 15px var(--accent-glow)' }}>
                <Box size={20} color="#fff" />
              </div>
              {sidebarExpanded && (
                <span style={{ fontFamily: 'Outfit', fontWeight: 700, fontSize: '1.25rem', letterSpacing: '-0.02em', background: 'linear-gradient(to right, #fff, #bbb)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', whiteSpace: 'nowrap' }}>
                  Mklan Studio
                </span>
              )}
            </div>
            {sidebarExpanded && (
              <button className="ghost-button" style={{ marginLeft: 'auto', padding: '0.3rem', minWidth: 'auto' }} onClick={() => setSidebarExpanded(false)}>
                <ChevronLeft size={16} />
              </button>
            )}
            {!sidebarExpanded && (
              <button className="ghost-button" style={{ margin: '0 auto', padding: '0.3rem', minWidth: 'auto', border: 'none' }} onClick={() => setSidebarExpanded(true)}>
                <ChevronRight size={16} />
              </button>
            )}
          </div>
          
          <nav className="sidebar-nav">
            {navItems.map(({ to, key, icon: Icon, exact }) => {
              const isActive = exact
                ? location.pathname === to
                : to !== '/' && location.pathname.startsWith(to);
              const displayLabel = t(`nav.${key}`) || key;
              return (
                <NavLink
                  key={to}
                  to={to}
                  end={exact}
                  className={`sidebar-item ${isActive ? 'active' : ''}`}
                  title={!sidebarExpanded ? displayLabel : undefined}
                >
                  <Icon size={18} strokeWidth={isActive ? 2.5 : 2} style={{ flexShrink: 0 }} />
                  {sidebarExpanded && <span>{displayLabel}</span>}
                </NavLink>
              );
            })}
          </nav>
          
          <div className="sidebar-footer">
            {sidebarExpanded && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', marginBottom: '0.5rem' }}>
                <Briefcase size={16} color="var(--text-secondary)" style={{ flexShrink: 0 }} />
                <select
                  value={activeWorkspaceId}
                  onChange={(event) => void activateWorkspace(event.target.value)}
                  disabled={workspaceBusy}
                  title="Workspace"
                  style={{ width: '100%', padding: '0.35rem 0.55rem', fontSize: '0.8rem' }}
                >
                  {workspaces.map((workspace) => (
                    <option key={workspace.id} value={workspace.id}>{workspace.name}</option>
                  ))}
                </select>
                <button type="button" onClick={() => void createWorkspace()} disabled={workspaceBusy} className="ghost-button" title="New workspace" style={{ width: 34, height: 34, padding: 0, flexShrink: 0 }}>
                  {workspaceBusy ? <Loader2 className="spin" size={15} /> : <Plus size={15} />}
                </button>
              </div>
            )}
            
            {sidebarExpanded && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                <select
                  value={language}
                  onChange={(event) => setLanguage(event.target.value === 'fr' ? 'fr' : 'en')}
                  style={{ width: 'auto', minWidth: 60, padding: '0.35rem 0.55rem', fontSize: '0.8rem' }}
                  title={t('nav.language')}
                >
                  <option value="en">EN</option>
                  <option value="fr">FR</option>
                </select>
                <select
                  value={theme}
                  onChange={(event) => setTheme(event.target.value === 'light' ? 'light' : 'dark')}
                  style={{ width: 'auto', flex: 1, padding: '0.35rem 0.55rem', fontSize: '0.8rem' }}
                  title={t('nav.theme')}
                >
                  <option value="dark">{t('theme.dark')}</option>
                  <option value="light">{t('theme.light')}</option>
                </select>
              </div>
            )}

            <button
              type="button"
              onClick={() => setCopilotOpen((open) => !open)}
              className={copilotOpen ? 'primary-button' : 'ghost-button'}
              title="Copilot"
              style={{ width: '100%', padding: sidebarExpanded ? '0.6rem' : '0.6rem 0' }}
            >
              <MessageSquare size={16} style={{ flexShrink: 0 }} />
              {sidebarExpanded && "Copilot"}
            </button>
          </div>
        </aside>
      )}

      {/* Main Content */}
      <main style={{ flex: 1, overflow: 'auto', position: 'relative', zIndex: 1, paddingBottom: isMobile ? 'calc(5.4rem + env(safe-area-inset-bottom))' : 0 }}>
        <Outlet />
      </main>

      {isMobile ? (
        <>
          <nav className="mobile-bottom-nav" aria-label="Navigation">
            {navItems.map(({ to, key, icon: Icon, exact }) => {
              const isActive = exact
                ? location.pathname === to
                : to !== '/' && location.pathname.startsWith(to);
              return (
                <NavLink
                  key={to}
                  to={to}
                  end={exact}
                  className={({ isActive: routeActive }) => `mobile-bottom-nav-item ${isActive || routeActive ? 'active' : ''}`}
                  aria-label={t(`nav.${key}`)}
                >
                  <Icon size={20} strokeWidth={isActive ? 2.6 : 2} />
                  <span>{t(`nav.${key}`)}</span>
                </NavLink>
              );
            })}
          </nav>

          {mobileMenuOpen ? (
            <div className="mobile-menu-layer" role="presentation">
              <button className="mobile-menu-backdrop" aria-label="Close" onClick={() => setMobileMenuOpen(false)} />
              <aside className="mobile-menu-panel" aria-label="Menu">
                <div className="mobile-menu-panel-header">
                  <div>
                    <strong>Mklan Studio</strong>
                    <span>{t('nav.active_studio')}</span>
                  </div>
                  <button type="button" className="mobile-menu-close" aria-label="Close" onClick={() => setMobileMenuOpen(false)}>
                    <X size={20} />
                  </button>
                </div>

                <div className="mobile-menu-section">
                  {navItems.map(({ to, key, icon: Icon, exact }) => {
                    const isActive = exact
                      ? location.pathname === to
                      : to !== '/' && location.pathname.startsWith(to);
                    return (
                      <NavLink
                        key={to}
                        to={to}
                        end={exact}
                        className={`mobile-menu-link ${isActive ? 'active' : ''}`}
                        onClick={() => setMobileMenuOpen(false)}
                      >
                        <Icon size={19} />
                        <span>{t(`nav.${key}`)}</span>
                      </NavLink>
                    );
                  })}
                </div>

                <div className="mobile-menu-section mobile-menu-preferences">
                  <label>
                    <span>Workspace</span>
                    <select value={activeWorkspaceId} onChange={(event) => void activateWorkspace(event.target.value)} disabled={workspaceBusy}>
                      {workspaces.map((workspace) => (
                        <option key={workspace.id} value={workspace.id}>{workspace.name}</option>
                      ))}
                    </select>
                  </label>
                  <button type="button" onClick={() => void createWorkspace()} disabled={workspaceBusy} className="ghost-button">
                    {workspaceBusy ? <Loader2 className="spin" size={16} /> : <Plus size={16} />}
                    New Workspace
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setCopilotOpen((open) => !open);
                      setMobileMenuOpen(false);
                    }}
                    className={copilotOpen ? 'primary-button' : 'ghost-button'}
                  >
                    <MessageSquare size={16} />
                    Copilot
                  </button>
                  <label>
                    <span>{t('nav.language')}</span>
                    <select value={language} onChange={(event) => setLanguage(event.target.value as any)}>
                      <option value="en">English</option>
                      <option value="fr">Francais</option>
                    </select>
                  </label>
                  <label>
                    <span>{t('nav.theme')}</span>
                    <select value={theme} onChange={(event) => setTheme(event.target.value as any)}>
                      <option value="dark">{t('theme.dark')}</option>
                      <option value="light">{t('theme.light')}</option>
                    </select>
                  </label>
                </div>
              </aside>
            </div>
          ) : null}
        </>
      ) : null}

      {copilotOpen ? (
        <aside className={`copilot-panel ${isMobile ? 'mobile' : ''}`} aria-label="Studio Copilot">
          <div className="copilot-panel-header">
            <div>
              <strong>Copilot</strong>
              <span>{workspaces.find((workspace) => workspace.id === activeWorkspaceId)?.name || activeWorkspaceId} · {currentLabel}</span>
            </div>
            <button type="button" className="ghost-button" onClick={() => setCopilotOpen(false)} title="Close Copilot" style={{ width: 36, height: 36, padding: 0 }}>
              <X size={18} />
            </button>
          </div>

          <div className="copilot-message-list">
            {copilotMessages.length === 0 ? (
              <div className="copilot-empty-state">
                Ask about the current page, workspace setup, training settings, or workflow presets.
              </div>
            ) : null}
            {copilotMessages.map((item, index) => (
              <div key={`${item.role}-${index}`} className={`copilot-message ${item.role}`}>
                <strong>{item.role === 'assistant' ? 'Copilot' : 'You'}</strong>
                <p>{item.content}</p>
              </div>
            ))}
            {copilotError ? <div className="copilot-error">{copilotError}</div> : null}
          </div>

          <div className="copilot-input-row">
            <textarea
              value={copilotPrompt}
              onChange={(event) => setCopilotPrompt(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  void sendCopilot();
                }
              }}
              placeholder="Ask Copilot"
              rows={3}
            />
            <button type="button" onClick={() => void sendCopilot()} disabled={!copilotPrompt.trim() || copilotBusy} className="primary-button" title="Send">
              {copilotBusy ? <Loader2 className="spin" size={16} /> : <Send size={16} />}
            </button>
          </div>
        </aside>
      ) : null}
      
      <style>{`
        @keyframes ping {
          75%, 100% { transform: scale(2.5); opacity: 0; }
        }
      `}</style>
    </div>
  );
}
