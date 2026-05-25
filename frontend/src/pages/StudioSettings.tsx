import { useEffect, useState, type ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  Bot,
  Check,
  Cpu,
  Image as ImageIcon,
  Loader2,
  Play,
  Save,
  Server,
  Sparkles,
  UploadCloud,
} from 'lucide-react';
import { useUiPreferences } from '../hooks/useUiPreferences';

const API = '/api/studio';

type SettingsTab = 'connections' | 'models' | 'sandbox';
type LlmProvider =
  | 'ollama'
  | 'koboldcpp'
  | 'openai_compatible'
  | 'openai'
  | 'openrouter'
  | 'anthropic'
  | 'google';

interface GenerationDefaults {
  width: number;
  height: number;
  steps: number;
  cfg_scale: number;
  sampler_name: string;
  scheduler: string;
  negative_prompt: string;
}

interface StudioSettingsData {
  llm: {
    provider: LlmProvider;
    endpoint: string;
    model: string;
    api_key: string;
    timeout_s: number;
  };
  image: {
    provider: 'auto' | 'diffusers' | 'sd_webui' | 'comfyui';
    endpoint: string;
    workflow: string;
    workflow_json: string;
    timeout_s: number;
    model: string;
    defaults: GenerationDefaults;
  };
}

interface ModelInventoryItem {
  name: string;
  size: number;
  path?: string;
  provider?: string;
}

const defaultGenerationDefaults: GenerationDefaults = {
  width: 1024,
  height: 1024,
  steps: 30,
  cfg_scale: 7,
  sampler_name: 'Euler a',
  scheduler: 'Automatic',
  negative_prompt: 'worst quality, low quality, blurred, monochrome',
};

const defaultSettings: StudioSettingsData = {
  llm: {
    provider: 'koboldcpp',
    endpoint: 'http://127.0.0.1:5001/v1',
    model: 'koboldcpp',
    api_key: '',
    timeout_s: 120,
  },
  image: {
    provider: 'auto',
    endpoint: 'http://127.0.0.1:8188',
    workflow: 'sdxl',
    workflow_json: '',
    timeout_s: 300,
    model: '',
    defaults: defaultGenerationDefaults,
  },
};

const providerPresets: Record<
  LlmProvider,
  { label: string; endpoint: string; modelPlaceholder: string; helper: string; apiKeyLabel: string }
> = {
  ollama: {
    label: 'Ollama',
    endpoint: 'http://127.0.0.1:11434/v1',
    modelPlaceholder: 'llama3.1:8b',
    helper: 'Best fit for local single-box inference with chat-style APIs.',
    apiKeyLabel: 'API Key (Usually empty)',
  },
  koboldcpp: {
    label: 'KoboldCpp',
    endpoint: 'http://127.0.0.1:5001/v1',
    modelPlaceholder: 'koboldcpp',
    helper: 'Good when you want GGUF-oriented local serving with OpenAI-style routing.',
    apiKeyLabel: 'API Key (Optional)',
  },
  openai_compatible: {
    label: 'OpenAI Compatible',
    endpoint: 'http://127.0.0.1:8081/v1',
    modelPlaceholder: 'my-local-model',
    helper: 'Use this for LM Studio, llama.cpp servers, vLLM, or any OpenAI-compatible proxy.',
    apiKeyLabel: 'Bearer Token (Optional)',
  },
  openai: {
    label: 'OpenAI',
    endpoint: 'https://api.openai.com/v1',
    modelPlaceholder: 'gpt-4.1-mini',
    helper: 'Cloud-hosted OpenAI models with an official API key.',
    apiKeyLabel: 'OpenAI API Key',
  },
  openrouter: {
    label: 'OpenRouter',
    endpoint: 'https://openrouter.ai/api/v1',
    modelPlaceholder: 'openai/gpt-4.1-mini',
    helper: 'Broker multiple hosted providers through one endpoint and one routing key.',
    apiKeyLabel: 'OpenRouter API Key',
  },
  anthropic: {
    label: 'Anthropic',
    endpoint: 'https://api.anthropic.com/v1',
    modelPlaceholder: 'claude-3-7-sonnet-latest',
    helper: 'Hosted Claude models. Keep the endpoint official and add your key here.',
    apiKeyLabel: 'Anthropic API Key',
  },
  google: {
    label: 'Google',
    endpoint: 'https://generativelanguage.googleapis.com/v1beta/openai/',
    modelPlaceholder: 'gemini-2.5-pro',
    helper: 'Gemini via Google endpoints or compatible bridges that accept OpenAI-shaped calls.',
    apiKeyLabel: 'Google API Key',
  },
};

const tabConfig: Array<{ id: SettingsTab; label: string; icon: typeof Server }> = [
  { id: 'connections', label: 'Connections', icon: Server },
  { id: 'models', label: 'Models', icon: Cpu },
];

const samplerOptions = ['Euler a', 'LCM', 'RES-Multistep', 'DPM++ 2S a', 'DPM++ SDE', 'DPM++ 2M'];
const schedulerOptions = ['Automatic', 'Simple', 'Karras', 'KL-Optimal', 'Gits', 'beta'];
const sizePresets = [
  { label: 'Square 1024', width: 1024, height: 1024 },
  { label: 'Story 1216x832', width: 1216, height: 832 },
  { label: 'Portrait 832x1216', width: 832, height: 1216 },
];

function normalizeSettings(raw: unknown): StudioSettingsData {
  const candidate = (raw ?? {}) as Partial<StudioSettingsData>;
  return {
    llm: {
      provider: (candidate.llm?.provider as LlmProvider) || defaultSettings.llm.provider,
      endpoint: candidate.llm?.endpoint || defaultSettings.llm.endpoint,
      model: candidate.llm?.model || defaultSettings.llm.model,
      api_key: candidate.llm?.api_key || '',
      timeout_s: candidate.llm?.timeout_s || defaultSettings.llm.timeout_s,
    },
    image: {
      provider: candidate.image?.provider || defaultSettings.image.provider,
      endpoint: candidate.image?.endpoint || defaultSettings.image.endpoint,
      workflow: candidate.image?.workflow || defaultSettings.image.workflow,
      workflow_json: candidate.image?.workflow_json || '',
      timeout_s: candidate.image?.timeout_s || defaultSettings.image.timeout_s,
      model: candidate.image?.model || '',
      defaults: {
        ...defaultGenerationDefaults,
        ...(candidate.image?.defaults || {}),
      },
    },
  };
}

function SectionCard({
  title,
  subtitle,
  icon: Icon,
  children,
}: {
  title: string;
  subtitle: string;
  icon: typeof Server;
  children: ReactNode;
}) {
  return (
    <div
      style={{
        background: 'rgba(255,255,255,0.02)',
        border: '1px solid var(--border-color)',
        borderRadius: 'var(--radius-lg)',
        padding: '1.4rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '1rem',
        minWidth: 0,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.9rem' }}>
        <div
          style={{
            width: '2.5rem',
            height: '2.5rem',
            borderRadius: '0.9rem',
            background: 'rgba(124, 106, 255, 0.12)',
            border: '1px solid rgba(124, 106, 255, 0.22)',
            display: 'grid',
            placeItems: 'center',
            flexShrink: 0,
          }}
        >
          <Icon size={18} color="var(--accent-hover)" />
        </div>
        <div style={{ minWidth: 0 }}>
          <h2 style={{ fontSize: '1.15rem', fontWeight: 700 }}>{title}</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.88rem', marginTop: '0.35rem' }}>{subtitle}</p>
        </div>
      </div>
      {children}
    </div>
  );
}

export function StudioSettings() {
  const location = useLocation();
  const navigate = useNavigate();
  const { language, theme, setLanguage, setTheme } = useUiPreferences();

  const [activeTab, setActiveTab] = useState<SettingsTab>('connections');
  const [settings, setSettings] = useState<StudioSettingsData | null>(null);
  const [modelsList, setModelsList] = useState<ModelInventoryItem[]>([]);
  const [prompt, setPrompt] = useState('cinematic portrait of a cyberpunk fox, volumetric lighting, unreal engine 5 render, highly detailed');
  const [negativePrompt, setNegativePrompt] = useState(defaultGenerationDefaults.negative_prompt);
  const [width, setWidth] = useState(defaultGenerationDefaults.width);
  const [height, setHeight] = useState(defaultGenerationDefaults.height);
  const [steps, setSteps] = useState(defaultGenerationDefaults.steps);
  const [cfgScale, setCfgScale] = useState(defaultGenerationDefaults.cfg_scale);
  const [sampler, setSampler] = useState(defaultGenerationDefaults.sampler_name);
  const [scheduler, setScheduler] = useState(defaultGenerationDefaults.scheduler);
  const [image, setImage] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState('');
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [sandboxSynced, setSandboxSynced] = useState(false);

  useEffect(() => {
    void fetchSettings();
    void fetchModels();
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const tabParam = params.get('tab');
    if (tabParam === 'llm' || tabParam === 'connections') setActiveTab('connections');
    else if (tabParam === 'models') setActiveTab('models');
    else if (tabParam === 'sandbox') navigate('/generation', { replace: true });
  }, [location.search, navigate]);

  useEffect(() => {
    if (!settings || sandboxSynced) return;
    syncSandboxToDefaults(settings.image.defaults);
    setSandboxSynced(true);
  }, [settings, sandboxSynced]);

  const fetchSettings = async () => {
    try {
      const response = await fetch(`${API}/settings`);
      const payload = await response.json();
      setSettings(normalizeSettings(payload));
    } catch (err: any) {
      setError('Failed to load settings from server: ' + err.message);
    }
  };

  const fetchModels = async () => {
    try {
      const response = await fetch(`${API}/models`);
      const payload = await response.json();
      setModelsList(payload.models || []);
    } catch {
      setModelsList([]);
    }
  };

  const updateLlm = (patch: Partial<StudioSettingsData['llm']>) => {
    setSettings((current) => (current ? { ...current, llm: { ...current.llm, ...patch } } : current));
  };

  const applyLlmProvider = (provider: LlmProvider) => {
    const meta = providerPresets[provider];
    setSettings((current) => {
      if (!current) return current;
      const previousMeta = providerPresets[current.llm.provider] ?? providerPresets.koboldcpp;
      const shouldReplaceModel =
        !current.llm.model ||
        current.llm.model === previousMeta.modelPlaceholder ||
        current.llm.model === defaultSettings.llm.model ||
        current.llm.model === 'llama3.1';
      return {
        ...current,
        llm: {
          ...current.llm,
          provider,
          endpoint: meta.endpoint,
          model: shouldReplaceModel ? meta.modelPlaceholder : current.llm.model,
        },
      };
    });
  };

  const updateImage = (patch: Partial<StudioSettingsData['image']>) => {
    setSettings((current) => (current ? { ...current, image: { ...current.image, ...patch } } : current));
  };

  const updateDefaults = (patch: Partial<GenerationDefaults>) => {
    setSettings((current) =>
      current
        ? {
            ...current,
            image: {
              ...current.image,
              defaults: { ...current.image.defaults, ...patch },
            },
          }
        : current,
    );
  };

  const syncSandboxToDefaults = (defaults: GenerationDefaults) => {
    setNegativePrompt(defaults.negative_prompt);
    setWidth(defaults.width);
    setHeight(defaults.height);
    setSteps(defaults.steps);
    setCfgScale(defaults.cfg_scale);
    setSampler(defaults.sampler_name);
    setScheduler(defaults.scheduler);
  };

  const save = async () => {
    if (!settings) return;
    setSaving(true);
    setError('');
    setSuccessMsg('');
    try {
      const response = await fetch(`${API}/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
      });
      if (!response.ok) {
        throw new Error('Failed to save settings.');
      }
      syncSandboxToDefaults(settings.image.defaults);
      await fetchModels();
      setSuccessMsg('Studio settings saved successfully.');
      setTimeout(() => setSuccessMsg(''), 4000);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const testComfyConnection = async () => {
    if (!settings) return;
    setSaving(true);
    setError('');
    setSuccessMsg('');
    try {
      const response = await fetch(`${API}/comfyui/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ endpoint: settings.image.endpoint }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || 'ComfyUI connection failed.');
      }
      if (payload.models?.length) {
        setModelsList(
          payload.models.map((model: string) => ({
            name: model,
            size: 0,
            path: model,
          })),
        );
      }
      setSuccessMsg(`ComfyUI ready${payload.models?.length ? ` • ${payload.models.length} checkpoints found` : ''}.`);
      setTimeout(() => setSuccessMsg(''), 4000);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const testLlmConnection = async () => {
    if (!settings) return;
    setSaving(true);
    setError('');
    setSuccessMsg('');
    try {
      const response = await fetch(`${API}/llm/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings.llm),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || 'LLM connection failed.');
      }
      setSuccessMsg(`LLM ready at ${payload.endpoint}${payload.models?.length ? ` • ${payload.models.length} model entries` : ''}.`);
      setTimeout(() => setSuccessMsg(''), 4000);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const upload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    if (!event.target.files || event.target.files.length === 0) return;
    const file = event.target.files[0];
    setUploading(true);
    setUploadProgress('Uploading ' + file.name + '...');
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch(`${API}/models/upload`, {
        method: 'POST',
        body: formData,
      });
      if (!response.ok) {
        throw new Error('Model upload failed.');
      }
      setUploadProgress('Successfully uploaded model.');
      await fetchModels();
      if (settings && !settings.image.model) {
        updateImage({ model: file.name });
      }
      setTimeout(() => setUploadProgress(''), 4000);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setUploading(false);
      event.target.value = '';
    }
  };

  const generate = async () => {
    setLoading(true);
    setError('');
    setImage('');
    try {
      const response = await fetch(`${API}/generate-image`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt,
          negative_prompt: negativePrompt,
          width,
          height,
          steps,
          cfg_scale: cfgScale,
          sampler_name: sampler,
          scheduler: scheduler,
        }),
      });
      if (!response.ok) {
        const payload = await response.json();
        throw new Error(payload.detail || 'Failed to generate image from endpoint.');
      }
      const payload = await response.json();
      setImage(`data:image/png;base64,${payload.image_base64}`);
      navigate('/gallery');
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  if (!settings) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '60vh', color: 'var(--text-secondary)' }}>
        <Loader2 className="spin" size={32} />
        <span style={{ marginLeft: '1rem', fontSize: '1.1rem', fontWeight: 500 }}>Loading Studio Configuration...</span>
      </div>
    );
  }

  const llmMeta = providerPresets[settings.llm.provider] ?? providerPresets.ollama;
  const defaultModelName = settings.image.model;

  return (
    <div style={{ width: '100%', padding: 'clamp(1rem, 2vw, 2rem) clamp(1rem, 2.5vw, 2.25rem) 2.5rem', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div className="glass-panel" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'flex-start', justifyContent: 'space-between' }}>
          <div style={{ maxWidth: '780px' }}>
            <h1 className="text-gradient" style={{ fontSize: 'clamp(2rem, 3vw, 2.7rem)', fontWeight: 800, letterSpacing: '-0.04em', marginBottom: '0.45rem' }}>
              Studio Settings
            </h1>
            <p style={{ color: 'var(--text-secondary)', fontSize: '1rem', lineHeight: 1.6 }}>
              Tune provider routing, checkpoint inventory, and default rendering profiles used by Training and Generation.
            </p>
          </div>

          <button onClick={save} disabled={saving} className="primary-button" style={{ minWidth: '190px', minHeight: '44px' }}>
            {saving ? <Loader2 className="spin" size={16} /> : <Save size={16} />}
            {saving ? 'Saving...' : 'Save Configuration'}
          </button>
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
          {tabConfig.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                style={{
                  padding: '0.65rem 1rem',
                  borderRadius: '999px',
                  border: '1px solid',
                  borderColor: isActive ? 'rgba(124, 106, 255, 0.35)' : 'var(--border-color)',
                  background: isActive ? 'rgba(124, 106, 255, 0.12)' : 'rgba(255,255,255,0.02)',
                  color: isActive ? '#fff' : 'var(--text-secondary)',
                  fontWeight: 600,
                }}
              >
                <Icon size={14} />
                {tab.label}
              </button>
            );
          })}
        </div>
      </div>

      {error ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.8rem', padding: '1rem 1.2rem', background: 'rgba(255, 87, 87, 0.1)', border: '1px solid rgba(255, 87, 87, 0.2)', borderRadius: 'var(--radius-md)', color: '#ff7878' }}>
          <AlertTriangle size={18} />
          <span style={{ fontSize: '0.9rem', fontWeight: 500 }}>{error}</span>
        </div>
      ) : null}

      {successMsg ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.8rem', padding: '1rem 1.2rem', background: 'rgba(74, 222, 128, 0.1)', border: '1px solid rgba(74, 222, 128, 0.2)', borderRadius: 'var(--radius-md)', color: '#6be698' }}>
          <Check size={18} />
          <span style={{ fontSize: '0.9rem', fontWeight: 500 }}>{successMsg}</span>
        </div>
      ) : null}

      <div className="glass-panel" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        {activeTab === 'connections' ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1rem' }}>
            <SectionCard
              title={language === 'fr' ? 'Interface' : 'Interface'}
              subtitle={language === 'fr' ? 'Langue et theme appliques a Mklan Studio.' : 'Language and theme applied to Mklan Studio.'}
              icon={Sparkles}
            >
              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                <span style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>
                  {language === 'fr' ? 'Langue' : 'Language'}
                </span>
                <select value={language} onChange={(event) => setLanguage(event.target.value === 'fr' ? 'fr' : 'en')}>
                  <option value="en">English</option>
                  <option value="fr">Français</option>
                </select>
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                <span style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>
                  {language === 'fr' ? 'Theme' : 'Theme'}
                </span>
                <select value={theme} onChange={(event) => setTheme(event.target.value === 'light' ? 'light' : 'dark')}>
                  <option value="dark">{language === 'fr' ? 'Sombre' : 'Dark'}</option>
                  <option value="light">{language === 'fr' ? 'Clair' : 'Light'}</option>
                </select>
              </label>
            </SectionCard>

            <SectionCard
              title="LLM Runtime"
              subtitle="Choose a provider profile, then store the endpoint, model, and credentials Mklan Studio should use."
              icon={Bot}
            >
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '0.55rem' }}>
                {(Object.entries(providerPresets) as Array<[LlmProvider, (typeof providerPresets)[LlmProvider]]>).map(([provider, meta]) => (
                  <button
                    key={provider}
                    onClick={() => applyLlmProvider(provider)}
                    style={{
                      justifyContent: 'flex-start',
                      padding: '0.7rem 0.8rem',
                      border: '1px solid',
                      borderColor: settings.llm.provider === provider ? 'rgba(124, 106, 255, 0.35)' : 'var(--border-color)',
                      background: settings.llm.provider === provider ? 'rgba(124, 106, 255, 0.12)' : 'rgba(255,255,255,0.02)',
                      color: settings.llm.provider === provider ? '#fff' : 'var(--text-secondary)',
                    }}
                  >
                    {meta.label}
                  </button>
                ))}
              </div>

              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                <span style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>Provider</span>
                <select value={settings.llm.provider} onChange={(event) => applyLlmProvider(event.target.value as LlmProvider)}>
                  {(Object.entries(providerPresets) as Array<[LlmProvider, (typeof providerPresets)[LlmProvider]]>).map(([provider, meta]) => (
                    <option key={provider} value={provider}>
                      {meta.label}
                    </option>
                  ))}
                </select>
              </label>

              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                <span style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>Endpoint / Base URL</span>
                <input value={settings.llm.endpoint} onChange={(event) => updateLlm({ endpoint: event.target.value })} placeholder={llmMeta.endpoint} />
              </label>

              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                <span style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>Default Model</span>
                <input value={settings.llm.model} onChange={(event) => updateLlm({ model: event.target.value })} placeholder={llmMeta.modelPlaceholder} />
              </label>

              <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 140px', gap: '0.8rem' }}>
                <label style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                  <span style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>{llmMeta.apiKeyLabel}</span>
                  <input type="password" value={settings.llm.api_key} onChange={(event) => updateLlm({ api_key: event.target.value })} placeholder="Paste secret if required" />
                </label>
                <label style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                  <span style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>Timeout</span>
                  <input type="number" min={15} step={5} value={settings.llm.timeout_s} onChange={(event) => updateLlm({ timeout_s: Number(event.target.value) || 15 })} />
                </label>
              </div>
              <button onClick={testLlmConnection} disabled={saving} style={{ alignSelf: 'flex-start' }}>
                {saving ? <Loader2 className="spin" size={14} /> : <Bot size={14} />}
                Test LLM
              </button>
            </SectionCard>

            <SectionCard
              title="Connection Notes"
              subtitle="Keep one clean home for both LLM and image backends instead of a separate Comfy workflow page."
              icon={Sparkles}
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.9rem' }}>
                <div style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', padding: '1rem' }}>
                  <div style={{ fontSize: '0.82rem', color: 'var(--accent-hover)', fontWeight: 700, marginBottom: '0.35rem' }}>{llmMeta.label}</div>
                  <p style={{ margin: 0, color: 'var(--text-secondary)', fontSize: '0.86rem', lineHeight: 1.6 }}>{llmMeta.helper}</p>
                </div>

                <label style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                  <span style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>Image Provider</span>
                  <select
                    value={settings.image.provider}
                    onChange={(event) => {
                      const provider = event.target.value as StudioSettingsData['image']['provider'];
                      updateImage({
                        provider,
                        endpoint:
                          provider === 'comfyui' && settings.image.endpoint.includes(':7860')
                            ? 'http://127.0.0.1:8188'
                            : settings.image.endpoint,
                        workflow: provider === 'comfyui' && settings.image.workflow === 'sdxl' ? 'comfyui' : settings.image.workflow,
                      });
                    }}
                  >
                    <option value="auto">Auto: local model, then SD WebUI</option>
                    <option value="diffusers">Local Diffusers</option>
                    <option value="sd_webui">Stable Diffusion WebUI API</option>
                    <option value="comfyui">ComfyUI Server</option>
                  </select>
                </label>

                <label style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                  <span style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>Image Generation Endpoint</span>
                  <input value={settings.image.endpoint} onChange={(event) => updateImage({ endpoint: event.target.value })} placeholder={settings.image.provider === 'comfyui' ? 'http://127.0.0.1:8188' : 'http://127.0.0.1:7860'} />
                </label>

                <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 140px', gap: '0.8rem' }}>
                  <label style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                    <span style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>Default Workflow Profile</span>
                    <input value={settings.image.workflow} onChange={(event) => updateImage({ workflow: event.target.value })} placeholder={settings.image.provider === 'comfyui' ? 'comfyui' : 'sdxl'} />
                  </label>
                  <label style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                    <span style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>Timeout</span>
                    <input type="number" min={30} step={30} value={settings.image.timeout_s} onChange={(event) => updateImage({ timeout_s: Number(event.target.value) || 300 })} />
                  </label>
                </div>

                {settings.image.provider === 'comfyui' ? (
                  <>
                    <label style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                      <span style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>ComfyUI API Workflow JSON</span>
                      <textarea
                        value={settings.image.workflow_json}
                        onChange={(event) => updateImage({ workflow_json: event.target.value })}
                        placeholder={'Leave empty to use the built-in txt2img workflow. Supported placeholders: %prompt%, %negative_prompt%, %width%, %height%, %steps%, %scale%, %sampler%, %scheduler%, %seed%, %model%.'}
                        style={{ minHeight: '180px', fontFamily: 'monospace', fontSize: '0.78rem' }}
                      />
                    </label>
                    <button onClick={testComfyConnection} disabled={saving} style={{ alignSelf: 'flex-start' }}>
                      {saving ? <Loader2 className="spin" size={14} /> : <Server size={14} />}
                      Test ComfyUI
                    </button>
                  </>
                ) : null}

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '0.7rem' }}>
                  <div style={{ background: 'rgba(0,0,0,0.18)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', padding: '0.85rem' }}>
                    <div style={{ color: 'var(--text-muted)', fontSize: '0.72rem', textTransform: 'uppercase', marginBottom: '0.25rem' }}>LLM Provider</div>
                    <strong style={{ fontSize: '0.92rem' }}>{llmMeta.label}</strong>
                  </div>
                  <div style={{ background: 'rgba(0,0,0,0.18)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', padding: '0.85rem' }}>
                    <div style={{ color: 'var(--text-muted)', fontSize: '0.72rem', textTransform: 'uppercase', marginBottom: '0.25rem' }}>Default Model</div>
                    <strong style={{ fontSize: '0.92rem', wordBreak: 'break-word' }}>{settings.llm.model || 'Not set'}</strong>
                  </div>
                  <div style={{ background: 'rgba(0,0,0,0.18)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', padding: '0.85rem' }}>
                    <div style={{ color: 'var(--text-muted)', fontSize: '0.72rem', textTransform: 'uppercase', marginBottom: '0.25rem' }}>Image Profile</div>
                    <strong style={{ fontSize: '0.92rem' }}>{settings.image.provider} / {settings.image.workflow || 'sdxl'}</strong>
                  </div>
                </div>
              </div>
            </SectionCard>
          </div>
        ) : null}

        {activeTab === 'models' ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(340px, 0.9fr) minmax(420px, 1.1fr)', gap: '1rem' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', minWidth: 0 }}>
              <SectionCard
                title="Model Inventory"
                subtitle="Review uploaded checkpoints and choose which one should be used by default."
                icon={Cpu}
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', maxHeight: '420px', overflowY: 'auto', paddingRight: '0.25rem' }}>
                  {modelsList.length === 0 ? (
                    <div style={{ padding: '2rem', textAlign: 'center', border: '1px dashed var(--border-color)', borderRadius: 'var(--radius-md)', color: 'var(--text-secondary)' }}>
                      No single-file checkpoints uploaded yet.
                    </div>
                  ) : (
                    modelsList.map((model) => {
                      const isActive = defaultModelName === model.name;
                      return (
                        <button
                          key={`${model.provider || 'local'}:${model.path || model.name}`}
                          onClick={() => updateImage({ model: model.name })}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            textAlign: 'left',
                            padding: '1rem',
                            background: isActive ? 'rgba(124, 106, 255, 0.12)' : 'rgba(255,255,255,0.03)',
                            border: '1px solid',
                            borderColor: isActive ? 'rgba(124, 106, 255, 0.32)' : 'var(--border-color)',
                            borderRadius: 'var(--radius-md)',
                          }}
                        >
                          <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
                            <span style={{ fontWeight: 600, color: '#fff', fontSize: '0.95rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{model.name}</span>
                            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                              {model.provider ? `${model.provider} • ` : ''}{model.path || 'data/models/images'}
                            </span>
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexShrink: 0 }}>
                            {isActive ? (
                              <span style={{ background: 'rgba(124, 106, 255, 0.16)', color: 'var(--accent-hover)', border: '1px solid rgba(124, 106, 255, 0.24)', padding: '0.2rem 0.55rem', borderRadius: '999px', fontSize: '0.72rem', fontWeight: 700 }}>
                                Default
                              </span>
                            ) : null}
                            <span style={{ background: 'rgba(0,0,0,0.3)', padding: '0.2rem 0.6rem', borderRadius: 'var(--radius-sm)', fontSize: '0.8rem', color: 'var(--text-secondary)', border: '1px solid var(--border-color)' }}>
                              {formatSize(model.size)}
                            </span>
                          </div>
                        </button>
                      );
                    })
                  )}
                </div>
              </SectionCard>

              <SectionCard
                title="Upload Checkpoint"
                subtitle="Drop a new local checkpoint into the shared inventory and make it available to the generation defaults panel."
                icon={UploadCloud}
              >
                <label
                  style={{
                    border: '2px dashed var(--border-color)',
                    borderRadius: 'var(--radius-md)',
                    padding: '2.25rem 1.2rem',
                    textAlign: 'center',
                    cursor: 'pointer',
                    background: 'rgba(0,0,0,0.1)',
                    position: 'relative',
                  }}
                >
                  <input type="file" accept=".safetensors,.ckpt,.bin,.pt" onChange={upload} disabled={uploading} style={{ position: 'absolute', inset: 0, opacity: 0, cursor: 'pointer' }} />
                  <UploadCloud size={34} color="var(--text-secondary)" style={{ marginBottom: '0.8rem', opacity: 0.7 }} />
                  <div style={{ fontWeight: 600, fontSize: '0.92rem', color: '#fff', marginBottom: '0.3rem' }}>{uploading ? 'Uploading checkpoint...' : 'Click to browse checkpoint file'}</div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Supports `.safetensors`, `.ckpt`, `.pt`, and `.bin` files</span>
                </label>

                {uploadProgress ? (
                  <div style={{ background: 'rgba(124, 106, 255, 0.05)', border: '1px solid rgba(124, 106, 255, 0.15)', padding: '0.8rem 1rem', borderRadius: 'var(--radius-sm)', color: 'var(--accent-hover)', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Loader2 className={uploading ? 'spin' : ''} size={14} />
                    <span>{uploadProgress}</span>
                  </div>
                ) : null}
              </SectionCard>
            </div>

            <SectionCard
              title="Default Generation Settings"
              subtitle="These values become the baseline rendering recipe for the dedicated Generation workspace and the Wildcards image generator."
              icon={Sparkles}
            >
              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                <span style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>Default Checkpoint</span>
                <select value={settings.image.model} onChange={(event) => updateImage({ model: event.target.value })}>
                  <option value="">Auto-pick first available model</option>
                  {modelsList.map((model) => (
                    <option key={model.name} value={model.name}>
                      {model.name}
                    </option>
                  ))}
                </select>
              </label>

              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                <span style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>Workflow Profile</span>
                <input value={settings.image.workflow} onChange={(event) => updateImage({ workflow: event.target.value })} placeholder="sdxl" />
              </label>

              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                {sizePresets.map((preset) => (
                  <button key={preset.label} onClick={() => updateDefaults({ width: preset.width, height: preset.height })} style={{ border: '1px solid var(--border-color)', background: 'rgba(255,255,255,0.03)' }}>
                    {preset.label}
                  </button>
                ))}
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '0.8rem' }}>
                <label style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                  <span style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>Width</span>
                  <input type="number" value={settings.image.defaults.width} onChange={(event) => updateDefaults({ width: Number(event.target.value) || 512 })} />
                </label>
                <label style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                  <span style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>Height</span>
                  <input type="number" value={settings.image.defaults.height} onChange={(event) => updateDefaults({ height: Number(event.target.value) || 512 })} />
                </label>
                <label style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                  <span style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>Steps</span>
                  <input type="number" value={settings.image.defaults.steps} onChange={(event) => updateDefaults({ steps: Number(event.target.value) || 1 })} />
                </label>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 0.7fr) minmax(0, 1fr) minmax(0, 1fr)', gap: '0.8rem' }}>
                <label style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                  <span style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>CFG Scale</span>
                  <input type="number" step="0.1" value={settings.image.defaults.cfg_scale} onChange={(event) => updateDefaults({ cfg_scale: Number(event.target.value) || 1 })} />
                </label>
                <label style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                  <span style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>Sampler</span>
                  <select value={settings.image.defaults.sampler_name} onChange={(event) => updateDefaults({ sampler_name: event.target.value })}>
                    {samplerOptions.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </label>
                <label style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                  <span style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>Scheduler</span>
                  <select value={settings.image.defaults.scheduler} onChange={(event) => updateDefaults({ scheduler: event.target.value })}>
                    {schedulerOptions.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                <span style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>Default Negative Prompt</span>
                <textarea value={settings.image.defaults.negative_prompt} onChange={(event) => updateDefaults({ negative_prompt: event.target.value })} style={{ minHeight: '120px' }} />
              </label>

              <button onClick={() => syncSandboxToDefaults(settings.image.defaults)} style={{ alignSelf: 'flex-start' }}>
                <ImageIcon size={14} />
                Load Defaults Into Generation Defaults
              </button>
            </SectionCard>
          </div>
        ) : null}

        {activeTab === 'sandbox' ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(360px, 1.05fr) minmax(320px, 0.95fr)', gap: '1rem' }}>
            <SectionCard
              title="Legacy Prompt Preview"
              subtitle="Run a quick render using the currently configured endpoint and the defaults you saved on the Models page."
              icon={ImageIcon}
            >
              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                <span style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>Positive Prompt</span>
                <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="Enter positive tags..." style={{ minHeight: '120px' }} />
              </label>

              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                <span style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>Negative Prompt</span>
                <textarea value={negativePrompt} onChange={(event) => setNegativePrompt(event.target.value)} placeholder="Enter negative tags..." style={{ minHeight: '80px' }} />
              </label>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '0.8rem' }}>
                <label style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                  <span style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>Width</span>
                  <input type="number" value={width} onChange={(event) => setWidth(Number(event.target.value) || 512)} />
                </label>
                <label style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                  <span style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>Height</span>
                  <input type="number" value={height} onChange={(event) => setHeight(Number(event.target.value) || 512)} />
                </label>
                <label style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                  <span style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>Steps</span>
                  <input type="number" value={steps} onChange={(event) => setSteps(Number(event.target.value) || 1)} />
                </label>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 0.7fr) minmax(0, 1fr) minmax(0, 1fr)', gap: '0.8rem' }}>
                <label style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                  <span style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>CFG Scale</span>
                  <input type="number" step="0.1" value={cfgScale} onChange={(event) => setCfgScale(Number(event.target.value) || 1)} />
                </label>
                <label style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                  <span style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>Sampler</span>
                  <select value={sampler} onChange={(event) => setSampler(event.target.value)}>
                    {samplerOptions.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </label>
                <label style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                  <span style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>Scheduler</span>
                  <select value={scheduler} onChange={(event) => setScheduler(event.target.value)}>
                    {schedulerOptions.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.6rem' }}>
                <button onClick={() => syncSandboxToDefaults(settings.image.defaults)}>
                  <Cpu size={14} />
                  Reset To Saved Defaults
                </button>
                <button onClick={save}>
                  <Save size={14} />
                  Save Before Run
                </button>
              </div>

              <button onClick={generate} disabled={loading} className="primary-button" style={{ width: '100%', minHeight: '44px' }}>
                {loading ? <Loader2 className="spin" size={16} /> : <Play size={16} />}
                {loading ? 'Generating Image...' : 'Trigger Generation Run'}
              </button>
            </SectionCard>

            <SectionCard
              title="Active Canvas"
              subtitle={`Target endpoint: ${settings.image.endpoint || 'not configured'}${settings.image.model ? ` • model ${settings.image.model}` : ''}`}
              icon={ImageIcon}
            >
              <div
                style={{
                  background: 'rgba(0,0,0,0.2)',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius-lg)',
                  padding: '1.2rem',
                  justifyContent: 'center',
                  alignItems: 'center',
                  minHeight: '420px',
                  display: 'flex',
                }}
              >
                {loading ? (
                  <div style={{ textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1rem', color: 'var(--text-secondary)' }}>
                    <Loader2 className="spin" size={36} color="var(--accent)" />
                    <span style={{ fontSize: '0.95rem', fontWeight: 500 }}>Running Diffusion Pipeline...</span>
                    <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', maxWidth: '260px' }}>
                      Connecting to the configured image runtime and rendering a new test frame.
                    </p>
                  </div>
                ) : image ? (
                  <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                    <div style={{ overflow: 'hidden', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)', boxShadow: '0 8px 32px rgba(0,0,0,0.5)' }}>
                      <img src={image} style={{ width: '100%', display: 'block', objectFit: 'contain' }} alt="Generated test" />
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
                      <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Dimensions: {width}x{height} • {steps} steps • CFG {cfgScale}</span>
                      <button
                        onClick={() => {
                          const link = document.createElement('a');
                          link.href = image;
                          link.download = `sandbox-${Date.now()}.png`;
                          link.click();
                        }}
                        className="ghost-button"
                        style={{ padding: '0.35rem 0.85rem', fontSize: '0.75rem' }}
                      >
                        Download Image
                      </button>
                    </div>
                  </div>
                ) : (
                  <div style={{ textAlign: 'center', color: 'var(--text-muted)', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.6rem' }}>
                    <ImageIcon size={42} style={{ opacity: 0.3 }} />
                    <span style={{ fontWeight: 600, fontSize: '1rem', color: 'var(--text-secondary)' }}>No Active Canvas</span>
                    <p style={{ fontSize: '0.82rem', maxWidth: '240px', lineHeight: '1.5' }}>
                      Use the Generation workspace for active rendering, progress, and gallery sync.
                    </p>
                  </div>
                )}
              </div>
            </SectionCard>
          </div>
        ) : null}
      </div>
    </div>
  );
}
