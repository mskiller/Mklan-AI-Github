import { useCallback, useEffect, useMemo, useState } from 'react';
import { NavLink } from 'react-router-dom';
import {
  Activity,
  AlertTriangle,
  Brain,
  CheckCircle2,
  Clock3,
  Database,
  Film,
  Gauge,
  Images,
  ListChecks,
  RefreshCw,
  ScrollText,
  Server,
  Settings,
  ShieldAlert,
  Sparkles,
  Tags,
} from 'lucide-react';

interface StudioModule {
  id: string;
  label: string;
  path: string;
  category: string;
  status: string;
}

interface StudioManifest {
  version: string;
  modules: StudioModule[];
  integrations: Record<string, Record<string, unknown>>;
  capabilities: string[];
}

interface PreflightCheck {
  id: string;
  ready: boolean;
  status: string;
  url?: string;
  error?: string;
}

interface PreflightWarning {
  id: string;
  severity: string;
  title: string;
  detail: string;
  action?: string;
}

interface StudioPreflight {
  ok: boolean;
  checks: PreflightCheck[];
  warnings: PreflightWarning[];
  summary: {
    ready: number;
    blocked: number;
    warnings: number;
  };
}

interface JobOverviewItem {
  id: string;
  source: string;
  label: string;
  job_type: string;
  status: string;
  progress: number;
  created_at: string;
  updated_at: string;
  error_text?: string | null;
}

interface JobsOverview {
  counts: Record<string, number>;
  jobs: JobOverviewItem[];
}

const fallbackModules: StudioModule[] = [
  { id: 'training', label: 'Training', path: '/training', category: 'sdxl', status: 'ready' },
  { id: 'generation', label: 'Generation', path: '/generation', category: 'sdxl', status: 'ready' },
  { id: 'gallery', label: 'Gallery', path: '/gallery', category: 'library', status: 'ready' },
  { id: 'wildcards', label: 'Wildcards', path: '/wildcards', category: 'prompting', status: 'ready' },
  { id: 'movie', label: 'Movie Script', path: '/movie', category: 'story', status: 'ready' },
  { id: 'cards', label: 'SillyTavern Cards', path: '/cards', category: 'characters', status: 'ready' },
  { id: 'settings', label: 'Settings', path: '/settings', category: 'system', status: 'ready' },
];

const moduleIcons: Record<string, typeof Gauge> = {
  dashboard: Gauge,
  training: Brain,
  generation: Sparkles,
  gallery: Images,
  wildcards: Tags,
  movie: Film,
  cards: ScrollText,
  settings: Settings,
};

async function readJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || `Request failed: ${response.status}`);
  }
  return payload as T;
}

function statusColor(status: string) {
  if (['ready', 'succeeded'].includes(status)) return 'var(--success)';
  if (['running', 'queued'].includes(status)) return 'var(--accent-hover)';
  if (['warning', 'canceled'].includes(status)) return 'var(--warning)';
  if (['failed', 'error'].includes(status)) return 'var(--danger)';
  return 'var(--text-secondary)';
}

function formatPercent(value: number) {
  return `${Math.round(Math.max(0, Math.min(1, Number(value) || 0)) * 100)}%`;
}

function formatTime(value: string) {
  if (!value) return 'n/a';
  return new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', month: 'short', day: 'numeric' }).format(new Date(value));
}

function serviceLabel(id: string) {
  return id.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function Dashboard() {
  const [manifest, setManifest] = useState<StudioManifest | null>(null);
  const [preflight, setPreflight] = useState<StudioPreflight | null>(null);
  const [jobs, setJobs] = useState<JobsOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [manifestResult, preflightResult, jobsResult] = await Promise.allSettled([
        readJson<StudioManifest>('/api/studio/manifest'),
        readJson<StudioPreflight>('/api/studio/preflight'),
        readJson<JobsOverview>('/api/jobs/overview'),
      ]);
      if (manifestResult.status === 'fulfilled') setManifest(manifestResult.value);
      if (preflightResult.status === 'fulfilled') setPreflight(preflightResult.value);
      if (jobsResult.status === 'fulfilled') setJobs(jobsResult.value);
      const failures = [manifestResult, preflightResult, jobsResult].filter((result) => result.status === 'rejected');
      if (failures.length) setError(`${failures.length} dashboard source${failures.length > 1 ? 's' : ''} failed to load.`);
    } catch (err: any) {
      setError(err.message || 'Dashboard refresh failed.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 12000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const modules = manifest?.modules?.length ? manifest.modules : fallbackModules;
  const checks = preflight?.checks || [];
  const warnings = preflight?.warnings || [];
  const recentJobs = jobs?.jobs?.slice(0, 7) || [];
  const activeJobs = useMemo(() => recentJobs.filter((job) => ['queued', 'running'].includes(job.status)), [recentJobs]);
  const readyChecks = preflight?.summary?.ready ?? checks.filter((check) => check.ready).length;
  const blockedChecks = preflight?.summary?.blocked ?? checks.filter((check) => !check.ready).length;

  return (
    <div style={{ padding: '1.4rem', maxWidth: 1360, margin: '0 auto', display: 'grid', gap: '1.2rem' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem', flexWrap: 'wrap' }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.55rem', color: 'var(--text-secondary)', fontSize: '0.84rem', fontWeight: 700, textTransform: 'uppercase' }}>
            <Gauge size={16} color="var(--accent-hover)" />
            Mklan Studio {manifest?.version ? `v${manifest.version}` : ''}
          </div>
          <h1 style={{ fontSize: 'clamp(1.45rem, 4vw, 2.2rem)', lineHeight: 1.1, marginTop: '0.35rem' }}>Control Center</h1>
        </div>
        <button className="ghost-button" onClick={() => void refresh()} disabled={loading}>
          <RefreshCw className={loading ? 'spin' : undefined} size={16} />
          Refresh
        </button>
      </header>

      {error ? (
        <div style={{ border: '1px solid rgba(255,87,87,0.28)', background: 'rgba(255,87,87,0.1)', borderRadius: 8, padding: '0.85rem 1rem', color: '#ffb3b3', display: 'flex', gap: '0.6rem', alignItems: 'center' }}>
          <AlertTriangle size={18} />
          {error}
        </div>
      ) : null}

      <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(220px, 100%), 1fr))', gap: '0.8rem' }}>
        {[
          { label: 'Services ready', value: readyChecks, icon: CheckCircle2, color: 'var(--success)' },
          { label: 'Blocked checks', value: blockedChecks, icon: ShieldAlert, color: blockedChecks ? 'var(--danger)' : 'var(--text-secondary)' },
          { label: 'Warnings', value: warnings.length, icon: AlertTriangle, color: warnings.length ? 'var(--warning)' : 'var(--text-secondary)' },
          { label: 'Active jobs', value: activeJobs.length, icon: Activity, color: activeJobs.length ? 'var(--accent-hover)' : 'var(--text-secondary)' },
        ].map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="glass-panel" style={{ borderRadius: 8, padding: '1rem', display: 'flex', justifyContent: 'space-between', gap: '0.8rem', alignItems: 'center' }}>
            <div>
              <div style={{ color: 'var(--text-secondary)', fontSize: '0.82rem' }}>{label}</div>
              <strong style={{ display: 'block', color: 'var(--text-primary)', fontSize: '1.6rem', lineHeight: 1.1 }}>{value}</strong>
            </div>
            <Icon size={24} color={color} />
          </div>
        ))}
      </section>

      <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(360px, 100%), 1fr))', gap: '1rem', alignItems: 'start' }}>
        <div style={{ display: 'grid', gap: '0.8rem', minWidth: 0 }}>
          <h2 style={{ fontSize: '1.05rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}><Database size={18} color="var(--accent-hover)" /> Workspace Modules</h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(210px, 100%), 1fr))', gap: '0.75rem' }}>
            {modules.map((module) => {
              const Icon = moduleIcons[module.id] || Gauge;
              return (
                <NavLink key={module.id} to={module.path} className="glass-panel" style={{ borderRadius: 8, padding: '0.95rem', display: 'grid', gap: '0.65rem', color: 'var(--text-primary)', textDecoration: 'none', minHeight: 128 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.6rem', alignItems: 'center' }}>
                    <Icon size={21} color="var(--accent-hover)" />
                    <span style={{ color: statusColor(module.status), fontSize: '0.78rem', fontWeight: 700 }}>{module.status}</span>
                  </div>
                  <div>
                    <strong style={{ display: 'block', fontSize: '1rem' }}>{module.label}</strong>
                    <span style={{ color: 'var(--text-secondary)', fontSize: '0.82rem' }}>{module.category}</span>
                  </div>
                </NavLink>
              );
            })}
          </div>
        </div>

        <div style={{ display: 'grid', gap: '0.8rem', minWidth: 0 }}>
          <h2 style={{ fontSize: '1.05rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}><Server size={18} color="var(--accent-hover)" /> Runtime Checks</h2>
          <div className="glass-panel" style={{ borderRadius: 8, padding: '0.9rem', display: 'grid', gap: '0.65rem' }}>
            {checks.length ? checks.map((check) => (
              <div key={check.id} style={{ display: 'grid', gap: '0.2rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.55rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.7rem' }}>
                  <strong style={{ color: 'var(--text-primary)' }}>{serviceLabel(check.id)}</strong>
                  <span style={{ color: check.ready ? 'var(--success)' : 'var(--danger)', fontWeight: 700 }}>{check.ready ? 'ready' : check.status}</span>
                </div>
                <span style={{ color: check.error ? 'var(--danger)' : 'var(--text-secondary)', fontSize: '0.8rem', wordBreak: 'break-word' }}>{check.error || check.url || 'configured'}</span>
              </div>
            )) : (
              <div style={{ color: 'var(--text-secondary)' }}>Runtime checks will appear after the backend responds.</div>
            )}
          </div>
        </div>
      </section>

      <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(420px, 100%), 1fr))', gap: '1rem', alignItems: 'start' }}>
        <div style={{ display: 'grid', gap: '0.8rem', minWidth: 0 }}>
          <h2 style={{ fontSize: '1.05rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}><ListChecks size={18} color="var(--accent-hover)" /> Preflight Notes</h2>
          <div style={{ display: 'grid', gap: '0.65rem' }}>
            {warnings.length ? warnings.slice(0, 5).map((warning) => (
              <div key={warning.id} className="glass-panel" style={{ borderRadius: 8, padding: '0.9rem', borderColor: warning.severity === 'warning' ? 'rgba(251,191,36,0.28)' : 'var(--border-color)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                  <AlertTriangle size={16} color={warning.severity === 'warning' ? 'var(--warning)' : 'var(--text-secondary)'} />
                  <strong>{warning.title}</strong>
                </div>
                <p style={{ color: 'var(--text-secondary)', margin: 0, fontSize: '0.86rem' }}>{warning.detail}</p>
                {warning.action ? <p style={{ color: 'var(--text-muted)', margin: '0.35rem 0 0', fontSize: '0.8rem' }}>{warning.action}</p> : null}
              </div>
            )) : (
              <div className="glass-panel" style={{ borderRadius: 8, padding: '0.9rem', color: 'var(--text-secondary)' }}>No preflight warnings right now.</div>
            )}
          </div>
        </div>

        <div style={{ display: 'grid', gap: '0.8rem', minWidth: 0 }}>
          <h2 style={{ fontSize: '1.05rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}><Clock3 size={18} color="var(--accent-hover)" /> Job Queue</h2>
          <div className="glass-panel" style={{ borderRadius: 8, padding: '0.9rem', display: 'grid', gap: '0.65rem' }}>
            {recentJobs.length ? recentJobs.map((job) => (
              <div key={job.id} style={{ display: 'grid', gap: '0.35rem', paddingBottom: '0.65rem', borderBottom: '1px solid var(--border-color)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.8rem', alignItems: 'center' }}>
                  <strong style={{ color: 'var(--text-primary)', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{job.label}</strong>
                  <span style={{ color: statusColor(job.status), fontWeight: 700, fontSize: '0.82rem', flex: '0 0 auto' }}>{job.status}</span>
                </div>
                <div style={{ height: 6, borderRadius: 999, background: 'rgba(255,255,255,0.08)', overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: formatPercent(job.progress), background: statusColor(job.status) }} />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.8rem', color: 'var(--text-secondary)', fontSize: '0.78rem', flexWrap: 'wrap' }}>
                  <span>{job.source} · {job.job_type}</span>
                  <span>{formatTime(job.updated_at || job.created_at)}</span>
                </div>
                {job.error_text ? <span style={{ color: 'var(--danger)', fontSize: '0.78rem' }}>{job.error_text}</span> : null}
              </div>
            )) : (
              <div style={{ color: 'var(--text-secondary)' }}>No jobs recorded yet.</div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
