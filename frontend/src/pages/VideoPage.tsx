import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { CheckCircle2, Clapperboard, Clock, Film, Loader2, Play, RefreshCw, Settings, Sparkles, Wand2 } from 'lucide-react';
import { useJobEvents } from '../hooks/useJobEvents';
import { WorkflowNodeInspector, type WorkflowSummary } from '../components/WorkflowNodeInspector';

const API = '/api/video';
const terminalStatuses = new Set(['succeeded', 'failed', 'canceled']);

type VideoTab = 'generate' | 'clips' | 'models' | 'jobs';
type Provider = 'mock' | 'lightx2v' | 'wan_gguf' | 'comfyui_template';

interface JobRead {
  id: string;
  job_type: string;
  status: string;
  progress: number;
  payload: Record<string, unknown>;
  result: Record<string, unknown>;
  error_text?: string | null;
  created_at: string;
  updated_at: string;
}

interface VideoSettings {
  provider: Provider;
  model_root: string;
  model_class: string;
  native_width: number;
  native_height: number;
  native_frame_count: number;
  target_output_fps: number;
  seed_mode: 'random' | 'fixed';
  seed: number | null;
  output_root: string;
}

interface VideoClip {
  id: string;
  url: string;
  path: string;
  kind: string;
  source_module: string;
  source_id?: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

interface WorkflowPreset {
  id: string;
  label: string;
  task: string;
  description?: string;
  summary?: WorkflowSummary;
}

async function readJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || `Request failed: ${response.status}`);
  }
  return payload as T;
}

function formatPercent(value: number) {
  return `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`;
}

const tabConfig: Array<{ id: VideoTab; label: string; icon: typeof Film }> = [
  { id: 'generate', label: 'Generate', icon: Wand2 },
  { id: 'clips', label: 'Clips', icon: Clapperboard },
  { id: 'models', label: 'Models', icon: Settings },
  { id: 'jobs', label: 'Jobs', icon: Clock },
];

function Section({ title, icon: Icon, children }: { title: string; icon: typeof Film; children: React.ReactNode }) {
  return (
    <section className="glass-panel" style={{ padding: '1rem', display: 'grid', gap: '0.85rem', minWidth: 0 }}>
      <h2 style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '1rem' }}>
        <Icon size={18} color="var(--accent-hover)" />
        {title}
      </h2>
      {children}
    </section>
  );
}

export function VideoPage() {
  const location = useLocation();
  const params = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const context = useMemo(
    () => ({
      movie_project_id: params.get('movie_project_id') || undefined,
      scene_id: params.get('scene_id') || undefined,
      sequence_id: params.get('sequence_id') || undefined,
    }),
    [params],
  );

  const [activeTab, setActiveTab] = useState<VideoTab>('generate');
  const [settings, setSettings] = useState<VideoSettings | null>(null);
  const [models, setModels] = useState<Record<string, unknown> | null>(null);
  const [clips, setClips] = useState<VideoClip[]>([]);
  const [jobs, setJobs] = useState<JobRead[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowPreset[]>([]);
  const [provider, setProvider] = useState<Provider>('mock');
  const [mode, setMode] = useState<'text_to_video' | 'image_to_video'>('text_to_video');
  const [prompt, setPrompt] = useState(params.get('prompt') || params.get('wan_prompt') || 'cinematic establishing shot, soft motion, detailed lighting');
  const [negativePrompt, setNegativePrompt] = useState('low quality, jitter, flicker, distorted motion');
  const [referenceImageUrl, setReferenceImageUrl] = useState(params.get('reference_image') || '');
  const [durationS, setDurationS] = useState(2);
  const [fps, setFps] = useState(24);
  const [width, setWidth] = useState(832);
  const [height, setHeight] = useState(480);
  const [seed, setSeed] = useState('');
  const [workflowPresetId, setWorkflowPresetId] = useState('');
  const [currentJob, setCurrentJob] = useState<JobRead | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const processedTerminalJobs = useRef(new Set<string>());

  const selectedWorkflow = useMemo(
    () => workflows.find((workflow) => workflow.id === workflowPresetId) || workflows.find((workflow) => workflow.task === 'video') || workflows[0] || null,
    [workflowPresetId, workflows],
  );

  const refresh = useCallback(async () => {
    const [settingsPayload, modelsPayload, clipsPayload, jobsPayload, workflowPayload] = await Promise.all([
      readJson<{ settings: VideoSettings; status: Record<string, unknown> }>(`${API}/settings`),
      readJson<Record<string, unknown>>(`${API}/models`),
      readJson<{ clips: VideoClip[] }>(`${API}/clips`),
      readJson<JobRead[]>(`${API}/jobs`),
      readJson<{ presets: WorkflowPreset[] }>('/api/workflows/presets'),
    ]);
    setSettings(settingsPayload.settings);
    setProvider(settingsPayload.settings.provider);
    setFps(settingsPayload.settings.target_output_fps || 24);
    setWidth(settingsPayload.settings.native_width || 832);
    setHeight(settingsPayload.settings.native_height || 480);
    const presets = workflowPayload.presets || [];
    setModels(modelsPayload);
    setClips(clipsPayload.clips || []);
    setJobs(jobsPayload || []);
    setWorkflows(presets);
    setWorkflowPresetId((current) => (current && presets.some((item) => item.id === current) ? current : presets.find((item) => item.task === 'video')?.id || ''));
  }, []);

  useEffect(() => {
    void refresh().catch((err: Error) => setError(err.message));
  }, [refresh]);

  const handleLiveJob = useCallback((job: JobRead) => {
    setCurrentJob(job);
    setJobs((current) => [job, ...current.filter((item) => item.id !== job.id)]);
    if (!terminalStatuses.has(job.status) || processedTerminalJobs.current.has(job.id)) {
      return;
    }
    processedTerminalJobs.current.add(job.id);
    setBusy(false);
    void refresh()
      .then(() => {
        setActiveTab(job.status === 'succeeded' ? 'clips' : 'jobs');
        setMessage(job.status === 'succeeded' ? 'Video clip generated and registered.' : '');
      })
      .catch((err: Error) => setError(err.message));
  }, [refresh]);

  useJobEvents(currentJob?.id, {
    enabled: Boolean(currentJob && !terminalStatuses.has(currentJob.status)),
    onJob: handleLiveJob,
    onError: (err) => setError(err.message),
    pollIntervalMs: 1500,
  });

  const generate = async () => {
    setBusy(true);
    setError('');
    setMessage('');
    try {
      const payload = await readJson<{ job: JobRead }>(`${API}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode,
          prompt,
          negative_prompt: negativePrompt,
          provider,
          duration_s: durationS,
          fps,
          width,
          height,
          seed: seed ? Number(seed) : undefined,
          reference_image_url: referenceImageUrl || undefined,
          workflow_preset_id: workflowPresetId || undefined,
          ...context,
        }),
      });
      setCurrentJob(payload.job);
      setJobs((current) => [payload.job, ...current.filter((item) => item.id !== payload.job.id)]);
      setActiveTab('jobs');
      setMessage('Video job queued.');
    } catch (err: any) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <div style={{ padding: 'clamp(1rem, 2vw, 2rem)', display: 'grid', gap: '1rem', minWidth: 0 }}>
      <div className="glass-panel" style={{ padding: '1rem', display: 'flex', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap', alignItems: 'center' }}>
        <div style={{ minWidth: 0 }}>
          <h1 className="text-gradient" style={{ fontSize: 'clamp(1.8rem, 3vw, 2.4rem)' }}>Video</h1>
          <p style={{ color: 'var(--text-secondary)', margin: '0.2rem 0 0' }}>Generate native V2 clips, review assets, and inspect video workflow templates.</p>
        </div>
        <button onClick={() => void refresh()} className="ghost-button"><RefreshCw size={16} /> Refresh</button>
      </div>

      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
        {tabConfig.map((tab) => {
          const Icon = tab.icon;
          return (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)} className={activeTab === tab.id ? 'primary-button' : 'ghost-button'}>
              <Icon size={16} />
              {tab.label}
            </button>
          );
        })}
      </div>

      {error ? <div style={{ color: 'var(--danger)', border: '1px solid rgba(255,87,87,0.24)', padding: '0.75rem', borderRadius: 8 }}>{error}</div> : null}
      {message ? <div style={{ color: 'var(--success)', border: '1px solid rgba(74,222,128,0.22)', padding: '0.75rem', borderRadius: 8 }}>{message}</div> : null}

      {activeTab === 'generate' ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(340px, 100%), 1fr))', gap: '1rem' }}>
          <Section title="Render Settings" icon={Sparkles}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '0.65rem' }}>
              <label>Provider<select value={provider} onChange={(event) => setProvider(event.target.value as Provider)}><option value="mock">Mock</option><option value="lightx2v">LightX2V</option><option value="wan_gguf">Wan GGUF</option><option value="comfyui_template">ComfyUI template</option></select></label>
              <label>Mode<select value={mode} onChange={(event) => setMode(event.target.value as 'text_to_video' | 'image_to_video')}><option value="text_to_video">Text to video</option><option value="image_to_video">Image to video</option></select></label>
              <label>Workflow<select value={workflowPresetId} onChange={(event) => setWorkflowPresetId(event.target.value)}><option value="">Studio default</option>{workflows.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
            </div>
            <label>Prompt<textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} style={{ minHeight: 130 }} /></label>
            <label>Negative Prompt<textarea value={negativePrompt} onChange={(event) => setNegativePrompt(event.target.value)} style={{ minHeight: 80 }} /></label>
            <label>Reference Image URL<input value={referenceImageUrl} onChange={(event) => setReferenceImageUrl(event.target.value)} placeholder="/generated/example.png" /></label>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '0.65rem' }}>
              <label>Duration<input type="number" min={0.5} step={0.5} value={durationS} onChange={(event) => setDurationS(Number(event.target.value) || 2)} /></label>
              <label>FPS<input type="number" min={1} value={fps} onChange={(event) => setFps(Number(event.target.value) || 24)} /></label>
              <label>Width<input type="number" value={width} onChange={(event) => setWidth(Number(event.target.value) || 832)} /></label>
              <label>Height<input type="number" value={height} onChange={(event) => setHeight(Number(event.target.value) || 480)} /></label>
              <label>Seed<input value={seed} onChange={(event) => setSeed(event.target.value)} placeholder="random" /></label>
            </div>
            <button onClick={() => void generate()} disabled={busy || !prompt.trim()} className="primary-button">
              {busy ? <Loader2 className="spin" size={16} /> : <Play size={16} />}
              Generate Video
            </button>
            {context.movie_project_id || context.scene_id || context.sequence_id ? (
              <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap', color: 'var(--text-secondary)', fontSize: '0.78rem' }}>
                {context.movie_project_id ? <span className="code-chip">movie {context.movie_project_id}</span> : null}
                {context.scene_id ? <span className="code-chip">scene {context.scene_id}</span> : null}
                {context.sequence_id ? <span className="code-chip">sequence {context.sequence_id}</span> : null}
              </div>
            ) : null}
          </Section>
          <Section title="Workflow Inspector" icon={Film}>
            {selectedWorkflow ? (
              <>
                <div style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.75rem', display: 'grid', gap: '0.35rem' }}>
                  <strong>{selectedWorkflow.label}</strong>
                  <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>{selectedWorkflow.task} · {selectedWorkflow.summary?.node_count ?? 0} nodes</span>
                </div>
                <WorkflowNodeInspector summary={selectedWorkflow.summary} />
              </>
            ) : <p style={{ color: 'var(--text-muted)' }}>No workflow templates available.</p>}
            {currentJob ? (
              <div style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.75rem' }}>
                <strong>{currentJob.status}</strong>
                <div style={{ height: 8, borderRadius: 999, background: 'rgba(255,255,255,0.08)', marginTop: '0.55rem', overflow: 'hidden' }}>
                  <div style={{ width: formatPercent(currentJob.progress), height: '100%', background: 'var(--accent)' }} />
                </div>
              </div>
            ) : null}
          </Section>
        </div>
      ) : null}

      {activeTab === 'clips' ? (
        <Section title="Generated Clips" icon={Clapperboard}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(240px, 100%), 1fr))', gap: '0.85rem' }}>
            {clips.map((clip) => (
              <article key={clip.id} style={{ border: '1px solid var(--border-color)', borderRadius: 8, overflow: 'hidden', background: 'var(--bg-secondary)', minWidth: 0 }}>
                <video controls src={clip.url} style={{ width: '100%', aspectRatio: '16 / 9', display: 'block', background: '#000' }} />
                <div style={{ padding: '0.65rem', display: 'grid', gap: '0.25rem', color: 'var(--text-secondary)', fontSize: '0.78rem' }}>
                  <strong style={{ color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{String(clip.metadata.prompt || clip.path)}</strong>
                  <span>{String(clip.metadata.provider || clip.source_module)} · seed {String(clip.metadata.seed || 'random')}</span>
                </div>
              </article>
            ))}
            {clips.length ? null : <p style={{ color: 'var(--text-muted)' }}>No V2 video clips registered yet.</p>}
          </div>
        </Section>
      ) : null}

      {activeTab === 'models' ? (
        <Section title="Models & Settings" icon={Settings}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(220px, 100%), 1fr))', gap: '0.75rem', color: 'var(--text-secondary)' }}>
            <div style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.75rem' }}><strong style={{ color: 'var(--text-primary)' }}>Provider</strong><br />{settings?.provider || provider}</div>
            <div style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.75rem', minWidth: 0 }}><strong style={{ color: 'var(--text-primary)' }}>Model Root</strong><br /><span style={{ wordBreak: 'break-word' }}>{settings?.model_root || '--'}</span></div>
            <div style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.75rem', minWidth: 0 }}><strong style={{ color: 'var(--text-primary)' }}>Output Root</strong><br /><span style={{ wordBreak: 'break-word' }}>{settings?.output_root || '--'}</span></div>
          </div>
          <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: 'var(--text-secondary)', fontSize: '0.78rem', margin: 0 }}>{JSON.stringify(models, null, 2)}</pre>
        </Section>
      ) : null}

      {activeTab === 'jobs' ? (
        <Section title="Video Jobs" icon={Clock}>
          <div style={{ display: 'grid', gap: '0.65rem' }}>
            {jobs.map((job) => (
              <div key={job.id} style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.75rem', display: 'grid', gap: '0.45rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', flexWrap: 'wrap' }}>
                  <strong>{String(job.payload.prompt || job.job_type)}</strong>
                  <span style={{ color: job.status === 'failed' ? 'var(--danger)' : 'var(--text-secondary)' }}>{job.status} · {formatPercent(job.progress)}</span>
                </div>
                <div style={{ height: 6, borderRadius: 999, background: 'rgba(255,255,255,0.08)', overflow: 'hidden' }}><div style={{ width: formatPercent(job.progress), height: '100%', background: job.status === 'failed' ? 'var(--danger)' : 'var(--accent)' }} /></div>
                {job.error_text ? <span style={{ color: 'var(--danger)' }}>{job.error_text}</span> : null}
                {job.status === 'succeeded' ? <span style={{ color: 'var(--success)', display: 'flex', gap: '0.35rem', alignItems: 'center' }}><CheckCircle2 size={14} /> Registered clip ready</span> : null}
              </div>
            ))}
            {jobs.length ? null : <p style={{ color: 'var(--text-muted)' }}>No video jobs yet.</p>}
          </div>
        </Section>
      ) : null}
    </div>
  );
}
