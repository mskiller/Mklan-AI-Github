import { useEffect, useState } from 'react';
import { Outlet, NavLink, useLocation } from 'react-router-dom';
import { Box, Brain, Film, Tags, LayoutDashboard, Settings, Images, Menu, X, ScrollText, Sparkles } from 'lucide-react';
import { useDeviceMode } from '../hooks/useDeviceMode';
import { useUiPreferences } from '../hooks/useUiPreferences';

const navItems = [
  { to: '/', key: 'dashboard', label: 'Dashboard', labelFr: 'Tableau', icon: LayoutDashboard, exact: true },
  { to: '/training', key: 'training', label: 'Training', labelFr: 'Training', icon: Brain },
  { to: '/generation', key: 'generation', label: 'Generation', labelFr: 'Generation', icon: Sparkles },
  { to: '/wildcards', key: 'wildcards', label: 'Wildcards', labelFr: 'Wildcards', icon: Tags },
  { to: '/movie', key: 'movie', label: 'Movie Script', labelFr: 'Film', icon: Film },
  { to: '/cards', key: 'cards', label: 'SillyTavern Cards', labelFr: 'Cartes SillyTavern', icon: ScrollText },
  { to: '/gallery', key: 'gallery', label: 'Gallery', labelFr: 'Galerie', icon: Images },
  { to: '/settings', key: 'settings', label: 'Settings', labelFr: 'Réglages', icon: Settings },
];

export function Layout() {
  const location = useLocation();
  const deviceMode = useDeviceMode();
  const { language, theme, setLanguage, setTheme } = useUiPreferences();
  const isMobile = deviceMode === 'mobile';
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const currentNavItem = navItems.find((item) =>
    item.exact ? location.pathname === item.to : item.to !== '/' && location.pathname.startsWith(item.to),
  ) || navItems[0];
  const currentLabel = language === 'fr' ? currentNavItem.labelFr : currentNavItem.label;

  useEffect(() => {
    setMobileMenuOpen(false);
  }, [location.pathname]);

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
    <div className={`studio-shell studio-shell-${deviceMode}`} style={{ display: 'flex', flexDirection: 'column', height: '100vh', position: 'relative', overflow: 'hidden' }}>
      {/* Ambient Background Glows */}
      <div className="ambient-glow primary" />
      <div className="ambient-glow secondary" />

      {/* Top Navbar */}
      <header style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: isMobile ? '0.65rem 0.75rem' : '0 2rem',
        minHeight: isMobile ? '58px' : '64px',
        background: 'rgba(10, 10, 12, 0.7)',
        backdropFilter: 'blur(20px)',
        borderBottom: '1px solid var(--border-color)',
        flexShrink: 0,
        position: 'relative',
        zIndex: 10,
        gap: isMobile ? '0.6rem' : 0,
      }}>
        {/* Brand */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginRight: isMobile ? 0 : '3rem', minWidth: 0 }}>
          <div style={{ background: 'linear-gradient(135deg, var(--accent), #5a4bcf)', borderRadius: '8px', padding: '0.4rem', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 4px 15px var(--accent-glow)' }}>
            <Box size={20} color="#fff" />
          </div>
          <span style={{ fontFamily: 'Outfit', fontWeight: 700, fontSize: isMobile ? '1.05rem' : '1.25rem', letterSpacing: '-0.02em', background: 'linear-gradient(to right, #fff, #bbb)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', whiteSpace: 'nowrap' }}>
            Mklan Studio
          </span>
          {isMobile ? (
            <span style={{ color: 'var(--text-secondary)', fontSize: '0.78rem', fontWeight: 600, padding: '0.2rem 0.45rem', border: '1px solid var(--border-color)', borderRadius: '999px', whiteSpace: 'nowrap' }}>
              {currentLabel}
            </span>
          ) : null}
        </div>

        {/* Nav Items */}
        <nav className="desktop-nav-scroll" style={{ display: isMobile ? 'none' : 'flex', gap: '0.5rem', flex: 1, overflowX: 'auto', minWidth: 0, paddingBottom: '0.1rem' }}>
          {navItems.map(({ to, label, icon: Icon, exact }) => {
            const isActive = exact
              ? location.pathname === to
              : to !== '/' && location.pathname.startsWith(to);
            const displayLabel = language === 'fr' ? navItems.find((item) => item.to === to)?.labelFr || label : label;
            return (
              <NavLink
                key={to}
                to={to}
                end={exact}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  padding: isMobile ? '0.5rem 0.75rem' : '0.5rem 0.82rem',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: isMobile ? '0.82rem' : '0.9rem',
                  fontWeight: isActive ? 600 : 500,
                  color: isActive ? '#fff' : 'var(--text-secondary)',
                  background: isActive ? 'rgba(255,255,255,0.06)' : 'transparent',
                  border: '1px solid',
                  borderColor: isActive ? 'rgba(255,255,255,0.1)' : 'transparent',
                  textDecoration: 'none',
                  transition: 'all 0.2s',
                  whiteSpace: 'nowrap',
                  flex: '0 0 auto',
                }}
                onMouseEnter={e => {
                  if (!isActive) {
                    e.currentTarget.style.background = 'rgba(255,255,255,0.03)';
                    e.currentTarget.style.color = 'var(--text-primary)';
                  }
                }}
                onMouseLeave={e => {
                  if (!isActive) {
                    e.currentTarget.style.background = 'transparent';
                    e.currentTarget.style.color = 'var(--text-secondary)';
                  }
                }}
              >
                <Icon size={16} strokeWidth={isActive ? 2.5 : 2} />
                {displayLabel}
              </NavLink>
            );
          })}
        </nav>

        {/* Status indicator */}
        <div style={{ display: isMobile ? 'none' : 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.8rem', fontWeight: 500, color: 'var(--text-secondary)' }}>
          <select
            value={language}
            onChange={(event) => setLanguage(event.target.value === 'fr' ? 'fr' : 'en')}
            style={{ width: 'auto', minWidth: 74, padding: '0.35rem 0.55rem' }}
            title={language === 'fr' ? 'Langue' : 'Language'}
          >
            <option value="en">EN</option>
            <option value="fr">FR</option>
          </select>
          <select
            value={theme}
            onChange={(event) => setTheme(event.target.value === 'light' ? 'light' : 'dark')}
            style={{ width: 'auto', minWidth: 82, padding: '0.35rem 0.55rem' }}
            title={language === 'fr' ? 'Thème' : 'Theme'}
          >
            <option value="dark">{language === 'fr' ? 'Sombre' : 'Dark'}</option>
            <option value="light">{language === 'fr' ? 'Clair' : 'Light'}</option>
          </select>
        </div>
        <div style={{ display: isMobile ? 'none' : 'flex', alignItems: 'center', gap: '0.6rem', fontSize: '0.8rem', fontWeight: 500, color: 'var(--text-secondary)', background: 'rgba(0,0,0,0.2)', padding: '0.4rem 0.8rem', borderRadius: 'var(--radius-xl)', border: '1px solid var(--border-color)' }}>
          <span style={{ position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <span style={{ position: 'absolute', width: 8, height: 8, borderRadius: '50%', background: 'var(--success)', opacity: 0.4, animation: 'ping 2s cubic-bezier(0, 0, 0.2, 1) infinite' }} />
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--success)' }} />
          </span>
          {language === 'fr' ? 'Studio actif' : 'Studio Active'}
        </div>
        {isMobile ? (
          <button
            type="button"
            aria-label={mobileMenuOpen ? (language === 'fr' ? 'Fermer le menu' : 'Close menu') : (language === 'fr' ? 'Ouvrir le menu' : 'Open menu')}
            aria-expanded={mobileMenuOpen}
            onClick={() => setMobileMenuOpen((open) => !open)}
            className="mobile-menu-trigger"
          >
            {mobileMenuOpen ? <X size={22} /> : <Menu size={22} />}
          </button>
        ) : null}
      </header>

      {/* Main Content */}
      <main style={{ flex: 1, overflow: 'auto', position: 'relative', zIndex: 1, paddingBottom: isMobile ? 'calc(5.4rem + env(safe-area-inset-bottom))' : 0 }}>
        <Outlet />
      </main>

      {isMobile ? (
        <>
          <nav className="mobile-bottom-nav" aria-label={language === 'fr' ? 'Navigation principale' : 'Primary navigation'}>
            {navItems.map(({ to, label, labelFr, icon: Icon, exact }) => {
              const isActive = exact
                ? location.pathname === to
                : to !== '/' && location.pathname.startsWith(to);
              return (
                <NavLink
                  key={to}
                  to={to}
                  end={exact}
                  className={({ isActive: routeActive }) => `mobile-bottom-nav-item ${isActive || routeActive ? 'active' : ''}`}
                  aria-label={language === 'fr' ? labelFr : label}
                >
                  <Icon size={20} strokeWidth={isActive ? 2.6 : 2} />
                  <span>{language === 'fr' ? labelFr : label}</span>
                </NavLink>
              );
            })}
          </nav>

          {mobileMenuOpen ? (
            <div className="mobile-menu-layer" role="presentation">
              <button className="mobile-menu-backdrop" aria-label={language === 'fr' ? 'Fermer le menu' : 'Close menu'} onClick={() => setMobileMenuOpen(false)} />
              <aside className="mobile-menu-panel" aria-label={language === 'fr' ? 'Menu mobile' : 'Mobile menu'}>
                <div className="mobile-menu-panel-header">
                  <div>
                    <strong>Mklan Studio</strong>
                    <span>{language === 'fr' ? 'Studio actif' : 'Studio Active'}</span>
                  </div>
                  <button type="button" className="mobile-menu-close" aria-label={language === 'fr' ? 'Fermer' : 'Close'} onClick={() => setMobileMenuOpen(false)}>
                    <X size={20} />
                  </button>
                </div>

                <div className="mobile-menu-section">
                  {navItems.map(({ to, label, labelFr, icon: Icon, exact }) => {
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
                        <span>{language === 'fr' ? labelFr : label}</span>
                      </NavLink>
                    );
                  })}
                </div>

                <div className="mobile-menu-section mobile-menu-preferences">
                  <label>
                    <span>{language === 'fr' ? 'Langue' : 'Language'}</span>
                    <select value={language} onChange={(event) => setLanguage(event.target.value === 'fr' ? 'fr' : 'en')}>
                      <option value="en">English</option>
                      <option value="fr">Francais</option>
                    </select>
                  </label>
                  <label>
                    <span>{language === 'fr' ? 'Theme' : 'Theme'}</span>
                    <select value={theme} onChange={(event) => setTheme(event.target.value === 'light' ? 'light' : 'dark')}>
                      <option value="dark">{language === 'fr' ? 'Sombre' : 'Dark'}</option>
                      <option value="light">{language === 'fr' ? 'Clair' : 'Light'}</option>
                    </select>
                  </label>
                </div>
              </aside>
            </div>
          ) : null}
        </>
      ) : null}
      
      <style>{`
        @keyframes ping {
          75%, 100% { transform: scale(2.5); opacity: 0; }
        }
      `}</style>
    </div>
  );
}
