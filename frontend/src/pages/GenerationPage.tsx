import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Bot,
  CheckCircle2,
  Clock,
  Image as ImageIcon,
  Loader2,
  Maximize2,
  MessageSquare,
  Play,
  RefreshCw,
  Send,
  Sparkles,
  Trash2,
  WandSparkles,
  XCircle,
} from 'lucide-react';

const API = '/api/generation';
const JOB_API = '/api/jobs';
const terminalStatuses = new Set(['succeeded', 'failed', 'canceled']);

type GenerationTab = 'chat' | 'image' | 'images' | 'jobs';
type Provider = 'auto' | 'integrated' | 'comfyui';

interface ChatMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

interface ModelItem {
  name: string;
  path?: string;
  provider?: string;
}

interface LoraItem {
  name: string;
  path: string;
  size: number;
}

interface GeneratedImage {
  name: string;
  url: string;
  size: number;
  created_at: number;
  metadata: Record<string, unknown>;
}

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

interface WildcardPreview {
  original_prompt: string;
  expanded_prompt: string;
  seed: number;
  refs: Array<{ name: string; source: string; value: string }>;
  missing: string[];
}

async function readJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || `Request failed: ${response.status}`);
  }
  return payload as T;
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('Could not read image file.'));
    reader.onload = () => resolve(String(reader.result || '').split(',', 2).pop() || '');
    reader.readAsDataURL(file);
  });
}

function formatPercent(value: number) {
  return `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`;
}

const tabConfig: Array<{ id: GenerationTab; label: string; icon: typeof Sparkles }> = [
  { id: 'chat', label: 'LLM Chat', icon: MessageSquare },
  { id: 'image', label: 'Image Generation', icon: WandSparkles },
  { id: 'images', label: 'Generated Images', icon: ImageIcon },
  { id: 'jobs', label: 'Jobs & Stats', icon: Clock },
];

const samplerOptions = [
  'Euler a',
  'Euler',
  'DPM++ 2M',
  'DPM++ 2M SDE',
  'DPM++ SDE',
  'DPM++ 2S a',
  'DDIM',
  'LCM',
];

const schedulerOptions = [
  'Automatic',
  'Karras',
  'Exponential',
  'Simple',
  'Normal',
  'SGM Uniform',
  'Beta',
  'KL Optimal',
];

function Section({
  title,
  icon: Icon,
  children,
}: {
  title: string;
  icon: typeof Sparkles;
  children: React.ReactNode;
}) {
  return (
    <section className="glass-panel" style={{ padding: '1rem', display: 'grid', gap: '0.9rem', minWidth: 0 }}>
      <h2 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '1rem' }}>
        <Icon size={18} color="var(--accent-hover)" />
        {title}
      </h2>
      {children}
    </section>
  );
}

export function GenerationPage() {
  const [activeTab, setActiveTab] = useState<GenerationTab>('image');
  const [models, setModels] = useState<ModelItem[]>([]);
  const [loras, setLoras] = useState<LoraItem[]>([]);
  const [images, setImages] = useState<GeneratedImage[]>([]);
  const [jobs, setJobs] = useState<JobRead[]>([]);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatContextMessages, setChatContextMessages] = useState<ChatMessage[]>([]);
  const [chatPrompt, setChatPrompt] = useState('Describe a clean SDXL prompt for a dramatic portrait.');
  const [chatImageBase64, setChatImageBase64] = useState('');
  const [chatLoading, setChatLoading] = useState(false);

  const [provider, setProvider] = useState<Provider>('auto');
  const [model, setModel] = useState('');
  const [selectedLora, setSelectedLora] = useState('');
  const [prompt, setPrompt] = useState('cinematic portrait, __ziggart/Zig-style__, detailed eyes, studio lighting');
  const [negativePrompt, setNegativePrompt] = useState('worst quality, low quality, blurred, monochrome');
  const [width, setWidth] = useState(1024);
  const [height, setHeight] = useState(1024);
  const [steps, setSteps] = useState(30);
  const [cfgScale, setCfgScale] = useState(7);
  const [sampler, setSampler] = useState('Euler a');
  const [scheduler, setScheduler] = useState('Automatic');
  const [seed, setSeed] = useState('');
  const [batchCount, setBatchCount] = useState(1);
  const [wildcardPreview, setWildcardPreview] = useState<WildcardPreview | null>(null);
  const [currentJob, setCurrentJob] = useState<JobRead | null>(null);
  const [generating, setGenerating] = useState(false);
  const [openImage, setOpenImage] = useState<GeneratedImage | null>(null);

  const latestImages = useMemo(() => images.slice(0, 12), [images]);

  const refresh = useCallback(async () => {
    const [modelsPayload, imagesPayload, jobsPayload] = await Promise.all([
      readJson<{ models: ModelItem[]; loras: LoraItem[] }>(`${API}/models`),
      readJson<{ images: GeneratedImage[] }>(`${API}/images`),
      readJson<JobRead[]>(`${API}/jobs`),
    ]);
    setModels(modelsPayload.models || []);
    setLoras(modelsPayload.loras || []);
    setImages(imagesPayload.images || []);
    setJobs(jobsPayload || []);
  }, []);

  useEffect(() => {
    void refresh().catch((err: Error) => setError(err.message));
  }, [refresh]);

  useEffect(() => {
    if (!currentJob || terminalStatuses.has(currentJob.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const job = await readJson<JobRead>(`${JOB_API}/${currentJob.id}`);
        setCurrentJob(job);
        setJobs((current) => [job, ...current.filter((item) => item.id !== job.id)]);
        if (terminalStatuses.has(job.status)) {
          setGenerating(false);
          await refresh();
          setActiveTab(job.status === 'succeeded' ? 'images' : 'jobs');
        }
      } catch (err: any) {
        setError(err.message);
      }
    }, 1400);
    return () => window.clearInterval(timer);
  }, [currentJob, refresh]);

  const sendChat = async () => {
    const userMessage: ChatMessage = { role: 'user', content: chatPrompt };
    const nextContext = [...chatContextMessages, userMessage];
    setChatLoading(true);
    setError('');
    setChatMessages((current) => [...current, userMessage]);
    try {
      const payload = await readJson<{ content: string }>(`${API}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: nextContext,
          image_base64: chatImageBase64 || undefined,
          temperature: 0.4,
          max_tokens: 700,
        }),
      });
      const assistantMessage: ChatMessage = { role: 'assistant', content: payload.content };
      setChatMessages((current) => [...current, assistantMessage]);
      setChatContextMessages([...nextContext, assistantMessage]);
      setChatPrompt('');
      setMessage('LLM response received.');
    } catch (err: any) {
      setError(err.message);
    } finally {
      setChatLoading(false);
    }
  };

  const clearChat = () => {
    setChatMessages([]);
    setMessage('Chat transcript cleared. LLM context is still available until you clear it.');
  };

  const clearChatContext = () => {
    setChatContextMessages([]);
    setChatImageBase64('');
    setMessage('LLM context cleared. The next reply will start fresh.');
  };

  const clearJobs = async (status: 'failed' | 'succeeded') => {
    setError('');
    try {
      const payload = await readJson<{ deleted: number; status: string }>(`${API}/jobs?status=${status}`, { method: 'DELETE' });
      await refresh();
      setMessage(`Cleared ${payload.deleted} ${status} generation job(s).`);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const previewWildcards = async () => {
    try {
      const payload = await readJson<WildcardPreview>(`${API}/wildcards/preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, seed: seed ? Number(seed) : undefined }),
      });
      setWildcardPreview(payload);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const generateImage = async () => {
    setGenerating(true);
    setError('');
    setMessage('');
    try {
      const payload = await readJson<{ job: JobRead }>(`${API}/images`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt,
          negative_prompt: negativePrompt,
          provider,
          model: model || undefined,
          loras: selectedLora ? [{ name: selectedLora, weight: 1 }] : [],
          width,
          height,
          steps,
          cfg_scale: cfgScale,
          sampler_name: sampler,
          scheduler,
          seed: seed ? Number(seed) : undefined,
          batch_count: batchCount,
          expand_wildcards: true,
          wildcard_seed: seed ? Number(seed) : undefined,
        }),
      });
      setCurrentJob(payload.job);
      setJobs((current) => [payload.job, ...current.filter((item) => item.id !== payload.job.id)]);
      setActiveTab('jobs');
      setMessage('Generation job queued.');
    } catch (err: any) {
      setError(err.message);
      setGenerating(false);
    }
  };

  return (
    <div style={{ padding: 'clamp(1rem, 2vw, 2rem)', display: 'grid', gap: '1rem' }}>
      <div className="glass-panel" style={{ padding: '1rem', display: 'flex', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap', alignItems: 'center' }}>
        <div>
          <h1 className="text-gradient" style={{ fontSize: 'clamp(1.8rem, 3vw, 2.4rem)' }}>AI Generation</h1>
          <p style={{ color: 'var(--text-secondary)', margin: '0.2rem 0 0' }}>Chat, render images, expand wildcards, and push outputs into the gallery index.</p>
        </div>
        <button onClick={() => void refresh()} style={{ border: '1px solid var(--border-color)' }}>
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>

      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
        {tabConfig.map((tab) => {
          const Icon = tab.icon;
          const active = activeTab === tab.id;
          return (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)} className={active ? 'primary-button' : 'ghost-button'}>
              <Icon size={16} />
              {tab.label}
            </button>
          );
        })}
      </div>

      {error ? <div style={{ color: 'var(--danger)', border: '1px solid rgba(255,87,87,0.24)', padding: '0.75rem', borderRadius: 8 }}>{error}</div> : null}
      {message ? <div style={{ color: 'var(--success)', border: '1px solid rgba(74,222,128,0.22)', padding: '0.75rem', borderRadius: 8 }}>{message}</div> : null}

      {activeTab === 'chat' ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(300px, 0.85fr) minmax(320px, 1.15fr)', gap: '1rem' }}>
          <Section title="Prompt" icon={Bot}>
            <textarea value={chatPrompt} onChange={(event) => setChatPrompt(event.target.value)} style={{ minHeight: 150 }} />
            <label style={{ display: 'grid', gap: '0.35rem', color: 'var(--text-secondary)' }}>
              Vision Image
              <input
                type="file"
                accept="image/*"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void fileToBase64(file).then(setChatImageBase64).catch((err: Error) => setError(err.message));
                }}
              />
            </label>
            <button onClick={() => void sendChat()} disabled={chatLoading || !chatPrompt.trim()} className="primary-button">
              {chatLoading ? <Loader2 className="spin" size={16} /> : <Send size={16} />}
              Send
            </button>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              <button onClick={clearChat} disabled={!chatMessages.length} className="ghost-button"><Trash2 size={16} /> Clear Chat</button>
              <button onClick={clearChatContext} disabled={!chatContextMessages.length && !chatImageBase64} className="ghost-button"><XCircle size={16} /> Clear Context</button>
            </div>
            <span style={{ color: 'var(--text-muted)', fontSize: '0.78rem' }}>{chatContextMessages.length} context message(s){chatImageBase64 ? ' · vision image attached' : ''}</span>
          </Section>
          <Section title="Conversation" icon={MessageSquare}>
            <div style={{ display: 'grid', gap: '0.65rem', maxHeight: 520, overflow: 'auto' }}>
              {chatMessages.length === 0 ? <p style={{ color: 'var(--text-muted)' }}>No messages yet.</p> : null}
              {chatMessages.map((item, index) => (
                <div key={`${item.role}-${index}`} style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.75rem', background: item.role === 'assistant' ? 'rgba(124,106,255,0.08)' : 'rgba(255,255,255,0.03)' }}>
                  <strong style={{ color: item.role === 'assistant' ? 'var(--accent-hover)' : 'var(--text-primary)' }}>{item.role}</strong>
                  <p style={{ whiteSpace: 'pre-wrap', margin: '0.4rem 0 0', color: 'var(--text-secondary)' }}>{item.content}</p>
                </div>
              ))}
            </div>
          </Section>
        </div>
      ) : null}

      {activeTab === 'image' ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(340px, 0.95fr) minmax(320px, 1.05fr)', gap: '1rem' }}>
          <Section title="Render Settings" icon={WandSparkles}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '0.65rem' }}>
              <label>Provider<select value={provider} onChange={(event) => setProvider(event.target.value as Provider)}><option value="auto">Auto</option><option value="comfyui">ComfyUI</option><option value="integrated">Integrated</option></select></label>
              <label>Model<select value={model} onChange={(event) => setModel(event.target.value)}><option value="">Default / auto</option>{models.map((item) => <option key={`${item.provider}:${item.name}`} value={item.name}>{item.name}</option>)}</select></label>
              <label>LoRA<select value={selectedLora} onChange={(event) => setSelectedLora(event.target.value)}><option value="">No LoRA</option>{loras.map((item) => <option key={item.path} value={item.name}>{item.name}</option>)}</select></label>
            </div>
            <label>Positive Prompt<textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} style={{ minHeight: 130 }} /></label>
            <label>Negative Prompt<textarea value={negativePrompt} onChange={(event) => setNegativePrompt(event.target.value)} style={{ minHeight: 84 }} /></label>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: '0.65rem' }}>
              <label>Width<input type="number" value={width} onChange={(event) => setWidth(Number(event.target.value) || 512)} /></label>
              <label>Height<input type="number" value={height} onChange={(event) => setHeight(Number(event.target.value) || 512)} /></label>
              <label>Steps<input type="number" value={steps} onChange={(event) => setSteps(Number(event.target.value) || 1)} /></label>
              <label>CFG<input type="number" step="0.1" value={cfgScale} onChange={(event) => setCfgScale(Number(event.target.value) || 1)} /></label>
              <label>Sampler<select value={sampler} onChange={(event) => setSampler(event.target.value)}>{samplerOptions.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
              <label>Scheduler<select value={scheduler} onChange={(event) => setScheduler(event.target.value)}>{schedulerOptions.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
              <label>Seed<input value={seed} onChange={(event) => setSeed(event.target.value)} placeholder="random" /></label>
              <label>Batch<input type="number" min={1} max={8} value={batchCount} onChange={(event) => setBatchCount(Number(event.target.value) || 1)} /></label>
            </div>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              <button onClick={() => void previewWildcards()} className="ghost-button"><Sparkles size={16} /> Preview Wildcards</button>
              <button onClick={() => void generateImage()} disabled={generating} className="primary-button">{generating ? <Loader2 className="spin" size={16} /> : <Play size={16} />} Generate</button>
            </div>
          </Section>
          <Section title="Preview & Latest" icon={ImageIcon}>
            {wildcardPreview ? (
              <div style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.75rem', display: 'grid', gap: '0.45rem' }}>
                <strong>Expanded Prompt</strong>
                <p style={{ color: 'var(--text-secondary)', margin: 0 }}>{wildcardPreview.expanded_prompt}</p>
                <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>{wildcardPreview.refs.length} refs · seed {wildcardPreview.seed}{wildcardPreview.missing.length ? ` · missing ${wildcardPreview.missing.join(', ')}` : ''}</span>
              </div>
            ) : null}
            {currentJob ? (
              <div style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.75rem' }}>
                <strong>{currentJob.status}</strong>
                <div style={{ height: 8, borderRadius: 999, background: 'rgba(255,255,255,0.08)', marginTop: '0.55rem', overflow: 'hidden' }}>
                  <div style={{ width: formatPercent(currentJob.progress), height: '100%', background: 'var(--accent)' }} />
                </div>
              </div>
            ) : null}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: '0.65rem' }}>
              {latestImages.map((image) => (
                <button key={image.url} onClick={() => setOpenImage(image)} title={`Open ${image.name}`} style={{ padding: 0, border: '1px solid var(--border-color)', background: 'transparent', borderRadius: 8, overflow: 'hidden', cursor: 'zoom-in' }}>
                  <img src={image.url} alt={image.name} style={{ width: '100%', aspectRatio: '1', objectFit: 'cover', display: 'block' }} />
                </button>
              ))}
            </div>
          </Section>
        </div>
      ) : null}

      {activeTab === 'images' ? (
        <Section title="Generated Images" icon={ImageIcon}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '0.9rem' }}>
            {images.map((image) => (
              <div key={image.url} style={{ border: '1px solid var(--border-color)', borderRadius: 8, overflow: 'hidden', background: 'var(--bg-secondary)' }}>
                <button onClick={() => setOpenImage(image)} title={`Open ${image.name}`} style={{ padding: 0, border: 0, background: 'transparent', width: '100%', display: 'block', cursor: 'zoom-in' }}>
                  <img src={image.url} alt={image.name} style={{ width: '100%', aspectRatio: '1', objectFit: 'cover', display: 'block' }} />
                </button>
                <div style={{ padding: '0.65rem', color: 'var(--text-secondary)', fontSize: '0.78rem' }}>
                  <strong style={{ display: 'block', color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{image.name}</strong>
                  <span>{String(image.metadata.provider || 'generation')} · {String(image.metadata.seed || 'random')}</span>
                </div>
              </div>
            ))}
          </div>
        </Section>
      ) : null}

      {activeTab === 'jobs' ? (
        <Section title="Jobs & Stats" icon={Clock}>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
            <button onClick={() => void clearJobs('failed')} className="ghost-button"><Trash2 size={16} /> Clear Failed</button>
            <button onClick={() => void clearJobs('succeeded')} className="ghost-button"><CheckCircle2 size={16} /> Clear Succeeded</button>
          </div>
          <div style={{ display: 'grid', gap: '0.65rem' }}>
            {jobs.map((job) => (
              <div key={job.id} style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.75rem', display: 'grid', gap: '0.45rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', flexWrap: 'wrap' }}>
                  <strong>{job.job_type}</strong>
                  <span style={{ color: job.status === 'failed' ? 'var(--danger)' : 'var(--text-secondary)' }}>{job.status} · {formatPercent(job.progress)}</span>
                </div>
                <div style={{ height: 6, borderRadius: 999, background: 'rgba(255,255,255,0.08)', overflow: 'hidden' }}><div style={{ width: formatPercent(job.progress), height: '100%', background: job.status === 'failed' ? 'var(--danger)' : 'var(--accent)' }} /></div>
                {job.error_text ? <span style={{ color: 'var(--danger)' }}>{job.error_text}</span> : null}
                {job.status === 'succeeded' ? <span style={{ color: 'var(--success)', display: 'flex', gap: '0.35rem', alignItems: 'center' }}><CheckCircle2 size={14} /> Indexed outputs ready</span> : null}
              </div>
            ))}
          </div>
        </Section>
      ) : null}

      {openImage ? (
        <div
          onClick={() => setOpenImage(null)}
          style={{ position: 'fixed', inset: 0, zIndex: 80, background: 'rgba(0,0,0,0.82)', padding: 'clamp(1rem, 3vw, 2rem)', display: 'flex', flexDirection: 'column', gap: '1rem', alignItems: 'center', overflow: 'auto' }}
        >
          <img src={openImage.url} alt={openImage.name} style={{ width: '100%', maxHeight: '70vh', objectFit: 'contain', borderRadius: 8 }} />
          <aside onClick={(event) => event.stopPropagation()} className="glass-panel" style={{ padding: '1rem', display: 'grid', gap: '0.75rem', width: 'min(100%, 520px)', maxHeight: '50vh', overflow: 'auto' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', alignItems: 'center' }}>
              <strong style={{ wordBreak: 'break-word' }}>{openImage.name}</strong>
              <button onClick={() => setOpenImage(null)} className="ghost-button" title="Close"><XCircle size={16} /></button>
            </div>
            <span style={{ color: 'var(--text-secondary)' }}>{String(openImage.metadata.provider || 'generation')} · seed {String(openImage.metadata.seed || 'random')}</span>
            <button onClick={() => window.open(openImage.url, '_blank', 'noopener,noreferrer')} className="primary-button"><Maximize2 size={16} /> Open Original</button>
            <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: 'var(--text-secondary)', fontSize: '0.76rem', margin: 0 }}>{JSON.stringify(openImage.metadata, null, 2)}</pre>
          </aside>
        </div>
      ) : null}
    </div>
  );
}
