import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Archive,
  Brain,
  CheckCircle2,
  Clock,
  Cpu,
  Database,
  Download,
  FileText,
  FolderOpen,
  Image as ImageIcon,
  Images,
  ListChecks,
  Loader2,
  Play,
  RefreshCw,
  Save,
  Search,
  Sparkles,
  Upload,
  Wand2,
} from 'lucide-react';

const API = '/api/training';
const JOB_API = '/api/jobs';
const terminalStatuses = new Set(['succeeded', 'failed', 'canceled']);

type TrainingTab = 'dataset' | 'review' | 'captionScan' | 'settings' | 'runs' | 'artifacts';
type TrainingPreset = 'sdxl_lora' | 'sdxl_finetune' | 'anima_lora' | 'z_image_lora';
type LoraType = 'lora' | 'locon' | 'loha' | 'lokr';
type MixedPrecision = 'auto' | 'bf16' | 'fp16' | 'no';
type CaptionProvider = 'auto' | 'local_blip' | 'koboldcpp_vlm' | 'clip_tagger' | 'filename_fallback';

interface CaptionModelRead {
  id: string;
  label: string;
  provider: 'local_blip' | 'clip_tagger';
  path: string;
  local: boolean;
  source: string;
}

interface TrainingModelFile {
  name: string;
  path: string;
  size: number;
  kind: 'base' | 'vae';
  modified_at: string;
}

interface TrainingModelFilesResponse {
  base_models: TrainingModelFile[];
  vae_models: TrainingModelFile[];
  dry_run_forced: boolean;
  sd_scripts_root: string;
  sd_scripts_ready: boolean;
  accelerate_bin: string;
}

interface DatasetRead {
  id: string;
  name: string;
  path: string;
  image_count: number;
  caption_count: number;
  config_file?: string | null;
  settings: Record<string, unknown>;
  updated_at: string;
}

interface DatasetItemRead {
  filename: string;
  image_url: string;
  caption: string;
  caption_file?: string | null;
  has_caption: boolean;
  size: number;
  modified_at: string;
}

interface DatasetTriggerApplyResponse {
  dataset: DatasetRead;
  items: DatasetItemRead[];
  updated: number;
  unchanged: number;
}

interface MediaCollection {
  id: string;
  name: string;
  description?: string;
  asset_count: number;
}

interface CollectionDatasetImportResponse {
  dataset: DatasetRead;
  imported: number;
  skipped: number;
  collection_id: string;
  collection_name: string;
}

interface DatasetZipImportResponse {
  dataset: DatasetRead;
  items: DatasetItemRead[];
  imported: number;
  captions: number;
  skipped: number;
}

interface CaptionScanResponse {
  job: JobRead;
  events_url: string;
}

interface ArtifactRead {
  name: string;
  path: string;
  size: number;
  modified_at: string;
  kind: string;
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

interface CaptionScanResult {
  updated?: number;
  skipped?: number;
  failed?: number;
  items?: number;
  max_words?: number;
  trigger_applied?: boolean;
  trigger_applied_count?: number;
  fallback_count?: number;
  model_count?: number;
  vlm_count?: number;
  clip_count?: number;
  provider?: CaptionProvider;
  local_model_id?: string | null;
  clip_model_id?: string | null;
  model_used?: string | null;
  download_allowed?: boolean;
  caption_sources?: Record<string, number>;
  errors?: Array<{ filename?: string; error?: string }>;
}

interface CommandPreview {
  preset: string;
  script: string;
  working_dir: string;
  command: string[];
  display_command: string;
  dataset_config: string;
  output_dir: string;
}

async function readJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || `Request failed: ${response.status}`);
  }
  return payload as T;
}

function formatBytes(bytes: number) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function formatPercent(value: number) {
  return `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`;
}

function captionStartsWithTrigger(caption: string, triggerWord: string) {
  const normalized = caption.trimStart();
  const trigger = triggerWord.trim();
  return Boolean(
    trigger &&
    (normalized === trigger ||
      normalized.startsWith(`${trigger} `) ||
      normalized.startsWith(`${trigger},`) ||
      normalized.startsWith(`${trigger}:`)),
  );
}

function captionWithTrigger(caption: string, triggerWord: string) {
  const trigger = triggerWord.trim();
  const trimmedCaption = caption.trim();
  if (!trigger || captionStartsWithTrigger(trimmedCaption, trigger)) return trimmedCaption;
  return trimmedCaption ? `${trigger}, ${trimmedCaption}` : trigger;
}

function captionScanResult(job: JobRead | null): CaptionScanResult | null {
  if (!job?.result || !Object.keys(job.result).length) return null;
  return job.result as CaptionScanResult;
}

const tabConfig: Array<{ id: TrainingTab; label: string; icon: typeof Brain }> = [
  { id: 'dataset', label: 'Dataset Setup', icon: Database },
  { id: 'review', label: 'Dataset Review', icon: Images },
  { id: 'captionScan', label: 'Caption Scan', icon: Sparkles },
  { id: 'settings', label: 'Model Settings', icon: Cpu },
  { id: 'runs', label: 'Training Runs', icon: Clock },
  { id: 'artifacts', label: 'Save Models', icon: FolderOpen },
];

const presetDescriptions: Record<TrainingPreset, string> = {
  sdxl_lora: 'Complete local SDXL LoRA path through kohya sd-scripts.',
  sdxl_finetune: 'Advanced SDXL checkpoint fine-tune with conservative warnings.',
  anima_lora: 'Guarded Anima LoRA adapter requiring DiT, text encoder, and VAE paths.',
  z_image_lora: 'Guarded Z-Image adapter slot requiring an explicit local train script.',
};

const captionProviderLabels: Record<CaptionProvider, string> = {
  auto: 'Auto',
  local_blip: 'Local BLIP',
  koboldcpp_vlm: 'KoboldCPP/vLLM',
  clip_tagger: 'CLIP tagger',
  filename_fallback: 'Filename fallback',
};

const captionSourceLabels: Record<string, string> = {
  local_blip: 'Local BLIP',
  koboldcpp_vlm: 'KoboldCPP/vLLM',
  clip_tagger: 'CLIP tagger',
  filename_fallback: 'Filename fallback',
  skipped_existing: 'Skipped existing',
};

function Section({
  title,
  icon: Icon,
  children,
}: {
  title: string;
  icon: typeof Brain;
  children: React.ReactNode;
}) {
  return (
    <section className="glass-panel" style={{ padding: '1rem', display: 'grid', gap: '0.9rem', minWidth: 0, alignContent: 'start' }}>
      <h2 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '1rem' }}>
        <Icon size={18} color="var(--accent-hover)" />
        {title}
      </h2>
      {children}
    </section>
  );
}

export function TrainingPage() {
  const [activeTab, setActiveTab] = useState<TrainingTab>('dataset');
  const [datasets, setDatasets] = useState<DatasetRead[]>([]);
  const [datasetItems, setDatasetItems] = useState<DatasetItemRead[]>([]);
  const [collections, setCollections] = useState<MediaCollection[]>([]);
  const [captionModels, setCaptionModels] = useState<CaptionModelRead[]>([]);
  const [trainingModelFiles, setTrainingModelFiles] = useState<TrainingModelFilesResponse | null>(null);
  const [runs, setRuns] = useState<JobRead[]>([]);
  const [artifacts, setArtifacts] = useState<ArtifactRead[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState('');
  const [selectedItemFilename, setSelectedItemFilename] = useState('');
  const [currentJob, setCurrentJob] = useState<JobRead | null>(null);
  const [commandPreview, setCommandPreview] = useState<CommandPreview | null>(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const [datasetName, setDatasetName] = useState('SDXL character LoRA dataset');
  const [triggerToken, setTriggerToken] = useState('mklanstyle');
  const [classTokens, setClassTokens] = useState('person');
  const [captionDraft, setCaptionDraft] = useState('');
  const [captionTriggerWord, setCaptionTriggerWord] = useState('mklanstyle');
  const [itemFilter, setItemFilter] = useState('');
  const [uploading, setUploading] = useState(false);
  const [loadingItems, setLoadingItems] = useState(false);
  const [savingCaption, setSavingCaption] = useState(false);
  const [applyingTrigger, setApplyingTrigger] = useState(false);
  const [selectedCollectionId, setSelectedCollectionId] = useState('');
  const [collectionImporting, setCollectionImporting] = useState(false);
  const [importingZip, setImportingZip] = useState(false);
  const [exportingZip, setExportingZip] = useState(false);
  const [captionScanMaxWords, setCaptionScanMaxWords] = useState(40);
  const [captionScanOverwrite, setCaptionScanOverwrite] = useState(false);
  const [captionScanProvider, setCaptionScanProvider] = useState<CaptionProvider>('auto');
  const [captionLocalModelId, setCaptionLocalModelId] = useState('');
  const [captionClipModelId, setCaptionClipModelId] = useState('OysterQAQ/DanbooruCLIP');
  const [captionScanJob, setCaptionScanJob] = useState<JobRead | null>(null);

  const [preset, setPreset] = useState<TrainingPreset>('sdxl_lora');
  const [outputName, setOutputName] = useState('mklan-sdxl-lora');
  const [baseModel, setBaseModel] = useState('');
  const [vae, setVae] = useState('');
  const [maxTrainSteps, setMaxTrainSteps] = useState(1);
  const [stepsEdited, setStepsEdited] = useState(false);
  const [epochs, setEpochs] = useState(10);
  const [numRepeats, setNumRepeats] = useState(7);
  const [resolution, setResolution] = useState(1024);
  const [loraType, setLoraType] = useState<LoraType>('lora');
  const [enableBucket, setEnableBucket] = useState(true);
  const [bucketNoUpscale, setBucketNoUpscale] = useState(true);
  const [shuffleTags, setShuffleTags] = useState(false);
  const [keepTokens, setKeepTokens] = useState(0);
  const [clipSkip, setClipSkip] = useState(1);
  const [flipAug, setFlipAug] = useState(false);
  const [unetLr, setUnetLr] = useState('0.0005');
  const [textEncoderLr, setTextEncoderLr] = useState('0.00005');
  const [lrScheduler, setLrScheduler] = useState('cosine');
  const [lrSchedulerCycles, setLrSchedulerCycles] = useState(3);
  const [minSnrGamma, setMinSnrGamma] = useState('5');
  const [networkDim, setNetworkDim] = useState(32);
  const [networkAlpha, setNetworkAlpha] = useState(32);
  const [noiseOffset, setNoiseOffset] = useState('0.1');
  const [optimizerType, setOptimizerType] = useState('Adafactor');
  const [mixedPrecision, setMixedPrecision] = useState<MixedPrecision>('auto');
  const [saveEveryNEpochs, setSaveEveryNEpochs] = useState(1);
  const [dryRun, setDryRun] = useState(false);
  const [animaDit, setAnimaDit] = useState('');
  const [animaTextEncoder, setAnimaTextEncoder] = useState('');
  const [animaVae, setAnimaVae] = useState('');
  const [zTrainScript, setZTrainScript] = useState('');

  const refresh = useCallback(async () => {
    const [datasetPayload, runPayload, artifactPayload, captionModelPayload, trainingModelPayload] = await Promise.all([
      readJson<DatasetRead[]>(`${API}/datasets`),
      readJson<JobRead[]>(`${API}/runs`),
      readJson<ArtifactRead[]>(`${API}/artifacts`),
      readJson<CaptionModelRead[]>(`${API}/caption-models`),
      readJson<TrainingModelFilesResponse>(`${API}/model-files`),
    ]);
    setDatasets(datasetPayload);
    setRuns(runPayload);
    setArtifacts(artifactPayload);
    setCaptionModels(captionModelPayload);
    setTrainingModelFiles(trainingModelPayload);
    setCaptionLocalModelId((current) => (current && captionModelPayload.some((model) => model.provider === 'local_blip' && model.id === current) ? current : captionModelPayload.find((model) => model.provider === 'local_blip' && model.local)?.id || captionModelPayload.find((model) => model.provider === 'local_blip')?.id || ''));
    setCaptionClipModelId((current) => (current && captionModelPayload.some((model) => model.provider === 'clip_tagger' && model.id === current) ? current : captionModelPayload.find((model) => model.provider === 'clip_tagger' && model.id === 'OysterQAQ/DanbooruCLIP')?.id || captionModelPayload.find((model) => model.provider === 'clip_tagger')?.id || 'OysterQAQ/DanbooruCLIP'));
    setBaseModel((current) => (current && trainingModelPayload.base_models.some((model) => model.path === current) ? current : trainingModelPayload.base_models[0]?.path || current));
    setVae((current) => (current && trainingModelPayload.vae_models.some((model) => model.path === current) ? current : trainingModelPayload.vae_models[0]?.path || ''));
    setSelectedDatasetId((current) => (current && datasetPayload.some((dataset) => dataset.id === current) ? current : datasetPayload[0]?.id || ''));
    try {
      const collectionPayload = await readJson<MediaCollection[]>('/api/media/collections');
      setCollections(collectionPayload);
      setSelectedCollectionId((current) => (current && collectionPayload.some((collection) => collection.id === current) ? current : collectionPayload[0]?.id || ''));
    } catch {
      setCollections([]);
    }
  }, []);

  const refreshDatasetItems = useCallback(async (datasetId = selectedDatasetId, preferredFilename?: string) => {
    if (!datasetId) {
      setDatasetItems([]);
      setSelectedItemFilename('');
      return [];
    }
    setLoadingItems(true);
    try {
      const items = await readJson<DatasetItemRead[]>(`${API}/datasets/${datasetId}/items`);
      setDatasetItems(items);
      setSelectedItemFilename((current) => {
        const next = preferredFilename || current;
        return next && items.some((item) => item.filename === next) ? next : items[0]?.filename || '';
      });
      return items;
    } finally {
      setLoadingItems(false);
    }
  }, [selectedDatasetId]);

  useEffect(() => {
    void refresh().catch((err: Error) => setError(err.message));
  }, [refresh]);

  useEffect(() => {
    void refreshDatasetItems().catch((err: Error) => setError(err.message));
  }, [refreshDatasetItems]);

  useEffect(() => {
    if (!currentJob || terminalStatuses.has(currentJob.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const job = await readJson<JobRead>(`${JOB_API}/${currentJob.id}`);
        setCurrentJob(job);
        setRuns((current) => [job, ...current.filter((item) => item.id !== job.id)]);
        if (terminalStatuses.has(job.status)) {
          await refresh();
          if (job.job_type === 'training.caption_scan') {
            setCaptionScanJob(job);
            const jobDatasetId = typeof job.payload?.dataset_id === 'string' ? job.payload.dataset_id : selectedDatasetId;
            if (jobDatasetId) {
              setSelectedDatasetId(jobDatasetId);
              await refreshDatasetItems(jobDatasetId, selectedItemFilename);
            }
            setActiveTab(job.status === 'succeeded' ? 'review' : 'runs');
          } else {
            setActiveTab(job.status === 'succeeded' ? 'artifacts' : 'runs');
          }
        }
      } catch (err: any) {
        setError(err.message);
      }
    }, 1600);
    return () => window.clearInterval(timer);
  }, [currentJob, refresh, refreshDatasetItems, selectedDatasetId, selectedItemFilename]);

  const selectedDataset = datasets.find((item) => item.id === selectedDatasetId) || null;
  const selectedDatasetItem = datasetItems.find((item) => item.filename === selectedItemFilename) || null;
  const filteredDatasetItems = useMemo(() => {
    const normalizedFilter = itemFilter.trim().toLowerCase();
    if (!normalizedFilter) return datasetItems;
    return datasetItems.filter((item) => `${item.filename} ${item.caption}`.toLowerCase().includes(normalizedFilter));
  }, [datasetItems, itemFilter]);
  const emptyCaptionCount = datasetItems.filter((item) => !item.caption.trim()).length;
  const captionCoverage = datasetItems.length ? formatPercent((datasetItems.length - emptyCaptionCount) / datasetItems.length) : '0%';
  const captionDirty = Boolean(selectedDatasetItem && captionDraft !== selectedDatasetItem.caption);
  const scanResult = captionScanResult(captionScanJob);
  const scanUsedFallback = Boolean(scanResult?.fallback_count);
  const captionSourceEntries = Object.entries(scanResult?.caption_sources || {}).filter(([, count]) => Number(count) > 0);
  const localCaptionModels = captionModels.filter((model) => model.provider === 'local_blip');
  const clipCaptionModels = captionModels.filter((model) => model.provider === 'clip_tagger');
  const calculatedSteps = Math.max(1, Math.ceil(((selectedDataset?.image_count || datasetItems.length || 1) * numRepeats * epochs) / 1));
  const baseModelFiles = trainingModelFiles?.base_models || [];
  const vaeModelFiles = trainingModelFiles?.vae_models || [];
  const queuedRuns = runs.filter((run) => run.status === 'queued').length;
  const activeRuns = runs.filter((run) => run.status === 'running').length;

  useEffect(() => {
    setCaptionDraft(selectedDatasetItem?.caption || '');
  }, [selectedDatasetItem?.filename, selectedDatasetItem?.caption]);

  useEffect(() => {
    const datasetTrigger = selectedDataset?.settings?.trigger_token;
    if (typeof datasetTrigger === 'string' && datasetTrigger.trim()) {
      setCaptionTriggerWord(datasetTrigger.trim());
    }
  }, [selectedDataset?.id, selectedDataset?.settings]);

  useEffect(() => {
    if (!stepsEdited) {
      setMaxTrainSteps(calculatedSteps);
    }
  }, [calculatedSteps, stepsEdited]);

  const runPayload = () => ({
    dataset_id: selectedDatasetId,
    preset,
    output_name: outputName,
    base_model: baseModel,
    vae,
    epochs,
    num_repeats: numRepeats,
    max_train_steps: maxTrainSteps,
    resolution,
    lora_type: loraType,
    enable_bucket: enableBucket,
    bucket_no_upscale: bucketNoUpscale,
    shuffle_caption: shuffleTags,
    keep_tokens: keepTokens,
    clip_skip: clipSkip,
    flip_aug: flipAug,
    learning_rate: Number(unetLr) || 0.0001,
    unet_lr: Number(unetLr) || 0.0005,
    text_encoder_lr: Number(textEncoderLr) || 0.00005,
    lr_scheduler: lrScheduler,
    lr_scheduler_num_cycles: lrSchedulerCycles,
    min_snr_gamma: Number(minSnrGamma) || 0,
    network_dim: networkDim,
    network_alpha: networkAlpha,
    noise_offset: Number(noiseOffset) || 0,
    optimizer_type: optimizerType,
    mixed_precision: mixedPrecision,
    save_every_n_epochs: saveEveryNEpochs,
    dry_run: dryRun,
    model_components: {
      dit: animaDit,
      text_encoder: animaTextEncoder,
      vae: animaVae,
      train_script: zTrainScript,
    },
  });

  const selectDataset = (datasetId: string) => {
    setSelectedDatasetId(datasetId);
    setSelectedItemFilename('');
    setDatasetItems([]);
    setCaptionDraft('');
  };

  const createDataset = async () => {
    setError('');
    try {
      const dataset = await readJson<DatasetRead>(`${API}/datasets`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: datasetName,
          trigger_token: triggerToken,
          class_tokens: classTokens,
          resolution,
          batch_size: 1,
          num_repeats: numRepeats,
          caption_extension: '.txt',
          enable_bucket: enableBucket,
          bucket_no_upscale: bucketNoUpscale,
          shuffle_caption: shuffleTags,
          keep_tokens: keepTokens,
        }),
      });
      setDatasets((current) => [dataset, ...current]);
      selectDataset(dataset.id);
      setCaptionTriggerWord(triggerToken.trim());
      setMessage('Dataset created with the current SDXL caption and bucket settings.');
    } catch (err: any) {
      setError(err.message);
    }
  };

  const uploadImages = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || !selectedDatasetId) return;
    setUploading(true);
    setError('');
    const formData = new FormData();
    Array.from(files).forEach((file) => formData.append('files', file));
    try {
      await readJson(`${API}/datasets/${selectedDatasetId}/upload`, { method: 'POST', body: formData });
      await refresh();
      await refreshDatasetItems(selectedDatasetId);
      setActiveTab('review');
      setMessage(`${files.length} image file(s) uploaded.`);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setUploading(false);
      event.target.value = '';
    }
  };

  const uploadDatasetZip = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || !selectedDatasetId) return;
    setImportingZip(true);
    setError('');
    const formData = new FormData();
    formData.append('file', file);
    try {
      const response = await readJson<DatasetZipImportResponse>(`${API}/datasets/${selectedDatasetId}/upload-zip`, { method: 'POST', body: formData });
      setDatasets((current) => current.map((item) => (item.id === response.dataset.id ? response.dataset : item)));
      setDatasetItems(response.items);
      setSelectedItemFilename((current) => (current && response.items.some((item) => item.filename === current) ? current : response.items[0]?.filename || ''));
      await refresh();
      setActiveTab('review');
      setMessage(`Imported ${response.imported} image(s) and ${response.captions} caption file(s) from zip${response.skipped ? `; skipped ${response.skipped}` : ''}.`);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setImportingZip(false);
      event.target.value = '';
    }
  };

  const exportDatasetZip = () => {
    if (!selectedDatasetId) return;
    setExportingZip(true);
    const anchor = document.createElement('a');
    anchor.href = `${API}/datasets/${selectedDatasetId}/export.zip`;
    anchor.download = `${selectedDataset?.name || 'dataset'}-training-dataset.zip`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => setExportingZip(false), 900);
  };

  const updateCaption = async () => {
    if (!selectedDatasetId || !selectedDatasetItem) return;
    const datasetId = selectedDatasetId;
    const filename = selectedDatasetItem.filename;
    const nextCaption = captionDraft;
    setSavingCaption(true);
    setError('');
    try {
      const dataset = await readJson<DatasetRead>(`${API}/datasets/${datasetId}/captions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename, caption: nextCaption }),
      });
      setDatasets((current) => current.map((item) => (item.id === dataset.id ? dataset : item)));
      setSelectedDatasetId(datasetId);
      const items = await refreshDatasetItems(datasetId, filename);
      const savedItem = items.find((item) => item.filename === filename);
      setCaptionDraft(savedItem?.caption ?? nextCaption.trim());
      await refresh();
      setMessage('Caption saved and dataset config rebuilt.');
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSavingCaption(false);
    }
  };

  const insertTriggerIntoDraft = () => {
    setCaptionDraft((current) => captionWithTrigger(current, captionTriggerWord));
  };

  const applyTriggerToDataset = async () => {
    if (!selectedDatasetId || !captionTriggerWord.trim()) return;
    setApplyingTrigger(true);
    setError('');
    try {
      const response = await readJson<DatasetTriggerApplyResponse>(`${API}/datasets/${selectedDatasetId}/captions/apply-trigger`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trigger_word: captionTriggerWord.trim(), separator: ', ', create_missing: true }),
      });
      setDatasets((current) => current.map((item) => (item.id === response.dataset.id ? response.dataset : item)));
      setDatasetItems(response.items);
      setSelectedItemFilename((current) => (current && response.items.some((item) => item.filename === current) ? current : response.items[0]?.filename || ''));
      setMessage(`Trigger added to ${response.updated} caption(s); ${response.unchanged} already ready.`);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setApplyingTrigger(false);
    }
  };

  const startCaptionScan = async () => {
    if (!selectedDatasetId) return;
    setError('');
    try {
      const response = await readJson<CaptionScanResponse>(`${API}/datasets/${selectedDatasetId}/captions/scan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          max_words: captionScanMaxWords,
          overwrite: captionScanOverwrite,
          prepend_trigger: true,
          trigger_word: captionTriggerWord.trim() || undefined,
          provider: captionScanProvider,
          local_model_id: captionLocalModelId || undefined,
          clip_model_id: captionClipModelId || undefined,
        }),
      });
      setCaptionScanJob(response.job);
      setCurrentJob(response.job);
      setRuns((current) => [response.job, ...current.filter((item) => item.id !== response.job.id)]);
      setActiveTab('runs');
      setMessage('Caption scan queued.');
    } catch (err: any) {
      setError(err.message);
    }
  };

  const importCollectionDataset = async () => {
    if (!selectedCollectionId) return;
    const collection = collections.find((item) => item.id === selectedCollectionId);
    setCollectionImporting(true);
    setError('');
    try {
      const response = await readJson<CollectionDatasetImportResponse>(`${API}/datasets/from-collection`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          collection_id: selectedCollectionId,
          name: collection ? `${collection.name} training dataset` : undefined,
          trigger_token: triggerToken,
          class_tokens: classTokens,
          resolution,
          batch_size: 1,
          num_repeats: numRepeats,
          caption_extension: '.txt',
          enable_bucket: enableBucket,
          bucket_no_upscale: bucketNoUpscale,
          shuffle_caption: shuffleTags,
          keep_tokens: keepTokens,
        }),
      });
      setDatasets((current) => [response.dataset, ...current.filter((item) => item.id !== response.dataset.id)]);
      selectDataset(response.dataset.id);
      setCaptionTriggerWord(triggerToken.trim());
      await refreshDatasetItems(response.dataset.id);
      setActiveTab('review');
      setMessage(`Imported ${response.imported} collection image(s) into ${response.dataset.name}${response.skipped ? `; skipped ${response.skipped}` : ''}.`);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setCollectionImporting(false);
    }
  };

  const previewCommand = async () => {
    setError('');
    try {
      const preview = await readJson<CommandPreview>(`${API}/runs/preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(runPayload()),
      });
      setCommandPreview(preview);
      setMessage('Training command preview ready.');
    } catch (err: any) {
      setError(err.message);
    }
  };

  const startTraining = async () => {
    setError('');
    try {
      const response = await readJson<{ job: JobRead; command?: CommandPreview }>(`${API}/runs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(runPayload()),
      });
      setCurrentJob(response.job);
      setCommandPreview(response.command || null);
      setRuns((current) => [response.job, ...current.filter((item) => item.id !== response.job.id)]);
      setActiveTab('runs');
      setMessage('Training job queued.');
    } catch (err: any) {
      setError(err.message);
    }
  };

  return (
    <div style={{ padding: 'clamp(1rem, 2vw, 2rem)', display: 'grid', gap: '1rem', minWidth: 0 }}>
      <div className="glass-panel" style={{ padding: '1rem', display: 'flex', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap', alignItems: 'center' }}>
        <div>
          <h1 className="text-gradient" style={{ fontSize: 'clamp(1.8rem, 3vw, 2.4rem)' }}>AI Training</h1>
          <p style={{ color: 'var(--text-secondary)', margin: '0.2rem 0 0' }}>Build datasets, launch SDXL LoRA jobs, and collect trained model artifacts.</p>
        </div>
        <button onClick={() => void refresh()} style={{ border: '1px solid var(--border-color)' }}>
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>

      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', minWidth: 0 }}>
        {tabConfig.map((tab) => {
          const Icon = tab.icon;
          const active = activeTab === tab.id;
          return (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)} className={active ? 'primary-button' : 'ghost-button'} style={{ minWidth: 0 }}>
              <Icon size={16} />
              {tab.label}
            </button>
          );
        })}
      </div>

      {error ? <div style={{ color: 'var(--danger)', border: '1px solid rgba(255,87,87,0.24)', padding: '0.75rem', borderRadius: 8 }}>{error}</div> : null}
      {message ? <div style={{ color: 'var(--success)', border: '1px solid rgba(74,222,128,0.22)', padding: '0.75rem', borderRadius: 8 }}>{message}</div> : null}

      {activeTab === 'dataset' ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1rem' }}>
          <Section title="Create Dataset" icon={Database}>
            <label>Name<input value={datasetName} onChange={(event) => setDatasetName(event.target.value)} /></label>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '0.65rem' }}>
              <label>Trigger token<input value={triggerToken} onChange={(event) => setTriggerToken(event.target.value)} /></label>
              <label>Class tokens<input value={classTokens} onChange={(event) => setClassTokens(event.target.value)} /></label>
            </div>
            <button onClick={() => void createDataset()} className="primary-button"><Save size={16} /> Create SDXL Dataset</button>
          </Section>

          <Section title="Dataset Files" icon={Upload}>
            <label>Active Dataset<select value={selectedDatasetId} onChange={(event) => selectDataset(event.target.value)}><option value="">Select dataset</option>{datasets.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.name}</option>)}</select></label>
            {selectedDataset ? (
              <div style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.75rem', color: 'var(--text-secondary)' }}>
                <strong style={{ color: 'var(--text-primary)' }}>{selectedDataset.name}</strong>
                <div>{selectedDataset.image_count} images · {selectedDataset.caption_count} caption files · {captionCoverage} filled</div>
                <div style={{ wordBreak: 'break-word' }}>{selectedDataset.config_file || 'Config pending'}</div>
              </div>
            ) : null}
            <label style={{ border: '1px dashed var(--border-color)', borderRadius: 8, padding: '1rem', textAlign: 'center', cursor: 'pointer' }}>
              <input type="file" multiple accept="image/*" onChange={(event) => void uploadImages(event)} disabled={!selectedDatasetId || uploading} style={{ display: 'none' }} />
              {uploading ? <Loader2 className="spin" size={18} /> : <Upload size={18} />}
              {uploading ? 'Uploading...' : 'Upload dataset images'}
            </label>
            <label style={{ border: '1px dashed var(--border-color)', borderRadius: 8, padding: '1rem', textAlign: 'center', cursor: 'pointer' }}>
              <input type="file" accept=".zip,application/zip" onChange={(event) => void uploadDatasetZip(event)} disabled={!selectedDatasetId || importingZip} style={{ display: 'none' }} />
              {importingZip ? <Loader2 className="spin" size={18} /> : <Archive size={18} />}
              {importingZip ? 'Importing...' : 'Import ready dataset zip'}
            </label>
            <button onClick={() => setActiveTab('review')} disabled={!selectedDatasetId} className="ghost-button"><Images size={16} /> Review Captions</button>
          </Section>

          <Section title="Import Collection" icon={FolderOpen}>
            <label>Media Collection<select value={selectedCollectionId} onChange={(event) => setSelectedCollectionId(event.target.value)}><option value="">Select collection</option>{collections.map((collection) => <option key={collection.id} value={collection.id}>{collection.name} ({collection.asset_count})</option>)}</select></label>
            <button onClick={() => void importCollectionDataset()} disabled={!selectedCollectionId || collectionImporting} className="primary-button">
              {collectionImporting ? <Loader2 className="spin" size={16} /> : <Database size={16} />}
              Add Collection as Dataset
            </button>
          </Section>

          <Section title="Dataset Readiness" icon={ListChecks}>
            <div style={{ display: 'grid', gap: '0.55rem', color: 'var(--text-secondary)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem' }}><span>Images</span><strong style={{ color: 'var(--text-primary)' }}>{selectedDataset?.image_count || 0}</strong></div>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem' }}><span>Caption coverage</span><strong style={{ color: 'var(--text-primary)' }}>{captionCoverage}</strong></div>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem' }}><span>Trigger</span><strong style={{ color: 'var(--text-primary)' }}>{captionTriggerWord || 'Unset'}</strong></div>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem' }}><span>Resolution</span><strong style={{ color: 'var(--text-primary)' }}>{String(selectedDataset?.settings?.resolution || 1024)}</strong></div>
            </div>
          </Section>
        </div>
      ) : null}

      {activeTab === 'review' ? (
        <div className="training-review-layout">
          <Section title="Dataset Images" icon={Images}>
            <label>Active Dataset<select value={selectedDatasetId} onChange={(event) => selectDataset(event.target.value)}><option value="">Select dataset</option>{datasets.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.name}</option>)}</select></label>
            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', gap: '0.55rem', alignItems: 'center' }}>
              <label style={{ position: 'relative' }}>
                <Search size={15} style={{ position: 'absolute', left: 12, top: 35, color: 'var(--text-muted)' }} />
                Search
                <input value={itemFilter} onChange={(event) => setItemFilter(event.target.value)} placeholder="filename or caption" style={{ paddingLeft: '2.2rem' }} />
              </label>
              <button onClick={() => void refreshDatasetItems()} disabled={!selectedDatasetId || loadingItems} className="ghost-button" style={{ alignSelf: 'end' }}>
                {loadingItems ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
              </button>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '0.5rem' }}>
              <div style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.55rem', color: 'var(--text-secondary)' }}><strong style={{ color: 'var(--text-primary)' }}>{datasetItems.length}</strong><br />images</div>
              <div style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.55rem', color: 'var(--text-secondary)' }}><strong style={{ color: 'var(--text-primary)' }}>{captionCoverage}</strong><br />captioned</div>
              <div style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.55rem', color: 'var(--text-secondary)' }}><strong style={{ color: emptyCaptionCount ? 'var(--warning)' : 'var(--success)' }}>{emptyCaptionCount}</strong><br />empty</div>
            </div>
            <button onClick={exportDatasetZip} disabled={!selectedDatasetId || !datasetItems.length || exportingZip} className="ghost-button">
              {exportingZip ? <Loader2 className="spin" size={16} /> : <Download size={16} />}
              Export Zip
            </button>
            <div style={{ display: 'grid', gap: '0.45rem', maxHeight: 'min(60vh, 620px)', overflowY: 'auto', paddingRight: '0.15rem' }}>
              {loadingItems ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-secondary)' }}><Loader2 className="spin" size={16} /> Loading images</div>
              ) : filteredDatasetItems.length ? filteredDatasetItems.map((item) => {
                const active = selectedItemFilename === item.filename;
                return (
                  <button
                    key={item.filename}
                    onClick={() => setSelectedItemFilename(item.filename)}
                    className={active ? 'primary-button' : 'ghost-button'}
                    style={{ display: 'grid', gridTemplateColumns: '64px minmax(0, 1fr)', gap: '0.7rem', alignItems: 'center', justifyContent: 'stretch', textAlign: 'left', width: '100%', padding: '0.45rem' }}
                    aria-pressed={active}
                  >
                    <img src={item.image_url} alt="" loading="lazy" style={{ width: 64, height: 64, objectFit: 'cover', borderRadius: 6, background: 'rgba(255,255,255,0.06)' }} />
                    <span style={{ minWidth: 0 }}>
                      <strong style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.filename}</strong>
                      <span style={{ display: 'block', color: active ? 'rgba(255,255,255,0.78)' : 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {item.caption || 'No caption yet'}
                      </span>
                    </span>
                  </button>
                );
              }) : (
                <div style={{ border: '1px dashed var(--border-color)', borderRadius: 8, padding: '1rem', color: 'var(--text-secondary)', textAlign: 'center' }}>
                  {selectedDatasetId ? 'No images match this dataset view.' : 'Select a dataset to review images.'}
                </div>
              )}
            </div>
          </Section>

          <Section title="Caption Editor" icon={FileText}>
            {selectedDatasetItem ? (
              <div className="training-caption-editor-grid">
                <div style={{ display: 'grid', gap: '0.65rem' }}>
                  <div style={{ border: '1px solid var(--border-color)', borderRadius: 8, background: 'rgba(0,0,0,0.22)', overflow: 'hidden' }}>
                    <img src={selectedDatasetItem.image_url} alt={selectedDatasetItem.filename} style={{ width: '100%', aspectRatio: '1 / 1', objectFit: 'contain', display: 'block' }} />
                  </div>
                  <div style={{ display: 'grid', gap: '0.35rem', color: 'var(--text-secondary)' }}>
                    <strong style={{ color: 'var(--text-primary)', wordBreak: 'break-word' }}>{selectedDatasetItem.filename}</strong>
                    <span>{formatBytes(selectedDatasetItem.size)} · {selectedDatasetItem.has_caption ? 'caption file present' : 'caption file missing'}</span>
                    <span style={{ wordBreak: 'break-word' }}>{selectedDatasetItem.caption_file || 'Caption will be created on save'}</span>
                  </div>
                </div>
                <div style={{ display: 'grid', gap: '0.75rem' }}>
                  <label>Caption<textarea rows={12} value={captionDraft} onChange={(event) => setCaptionDraft(event.target.value)} style={{ minHeight: 260, resize: 'vertical' }} /></label>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '0.55rem', alignItems: 'end' }}>
                    <label>Trigger word<input value={captionTriggerWord} onChange={(event) => setCaptionTriggerWord(event.target.value)} /></label>
                    <button onClick={insertTriggerIntoDraft} disabled={!captionTriggerWord.trim()} className="ghost-button"><Wand2 size={16} /> Insert</button>
                    <button onClick={() => void updateCaption()} disabled={!captionDirty || savingCaption} className="primary-button">{savingCaption ? <Loader2 className="spin" size={16} /> : <Save size={16} />} Save</button>
                  </div>
                  <button onClick={() => void applyTriggerToDataset()} disabled={!selectedDatasetId || !captionTriggerWord.trim() || applyingTrigger} className="ghost-button">
                    {applyingTrigger ? <Loader2 className="spin" size={16} /> : <Wand2 size={16} />}
                    Apply Trigger to All Captions
                  </button>
                </div>
              </div>
            ) : (
              <div style={{ border: '1px dashed var(--border-color)', borderRadius: 8, padding: '2rem', color: 'var(--text-secondary)', textAlign: 'center' }}>
                <ImageIcon size={24} />
                <div>{selectedDatasetId ? 'Select an image to edit its caption.' : 'Select a dataset to open the review editor.'}</div>
              </div>
            )}
          </Section>
        </div>
      ) : null}

      {activeTab === 'captionScan' ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(360px, 100%), 1fr))', gap: '1rem' }}>
          <Section title="Caption Scan" icon={Sparkles}>
            <label>Dataset<select value={selectedDatasetId} onChange={(event) => selectDataset(event.target.value)}><option value="">Select dataset</option>{datasets.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.name}</option>)}</select></label>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '0.65rem' }}>
              <label>Max words<input type="number" min={1} max={200} value={captionScanMaxWords} onChange={(event) => setCaptionScanMaxWords(Math.max(1, Number(event.target.value) || 1))} /></label>
              <label>Trigger word<input value={captionTriggerWord} onChange={(event) => setCaptionTriggerWord(event.target.value)} /></label>
              <label>Provider<select value={captionScanProvider} onChange={(event) => setCaptionScanProvider(event.target.value as CaptionProvider)}><option value="auto">Auto</option><option value="local_blip">Local BLIP</option><option value="koboldcpp_vlm">KoboldCPP/vLLM</option><option value="clip_tagger">CLIP tagger</option><option value="filename_fallback">Filename fallback</option></select></label>
            </div>
            {captionScanProvider === 'auto' || captionScanProvider === 'local_blip' ? (
              <label>BLIP model<select value={captionLocalModelId} onChange={(event) => setCaptionLocalModelId(event.target.value)}>
                {localCaptionModels.map((model) => <option key={model.id} value={model.id}>{model.label}{model.local ? ' (local)' : ''}</option>)}
              </select></label>
            ) : null}
            {captionScanProvider === 'auto' || captionScanProvider === 'clip_tagger' ? (
              <label>CLIP tag model<select value={captionClipModelId} onChange={(event) => setCaptionClipModelId(event.target.value)}>
                {clipCaptionModels.map((model) => <option key={model.id} value={model.id}>{model.label}{model.local ? ' (local)' : ''}</option>)}
              </select></label>
            ) : null}
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}><input type="checkbox" checked={captionScanOverwrite} onChange={(event) => setCaptionScanOverwrite(event.target.checked)} style={{ width: 'auto' }} /> Overwrite existing captions</label>
            <button onClick={() => void startCaptionScan()} disabled={!selectedDatasetId} className="primary-button"><Sparkles size={16} /> Queue Caption Scan</button>
          </Section>

          <Section title="Scan Readiness" icon={ListChecks}>
            <div style={{ display: 'grid', gap: '0.55rem', color: 'var(--text-secondary)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem' }}><span>Images</span><strong style={{ color: 'var(--text-primary)' }}>{datasetItems.length || selectedDataset?.image_count || 0}</strong></div>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem' }}><span>Empty captions</span><strong style={{ color: emptyCaptionCount ? 'var(--warning)' : 'var(--success)' }}>{emptyCaptionCount}</strong></div>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem' }}><span>Caption coverage</span><strong style={{ color: 'var(--text-primary)' }}>{captionCoverage}</strong></div>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem' }}><span>Last caption scan</span><strong style={{ color: 'var(--text-primary)' }}>{captionScanJob ? `${captionScanJob.status} · ${formatPercent(captionScanJob.progress)}` : 'Not queued'}</strong></div>
            </div>
            {scanResult ? (
              <div style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.85rem', display: 'grid', gap: '0.6rem', color: 'var(--text-secondary)' }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))', gap: '0.5rem' }}>
                  <div><strong style={{ color: 'var(--text-primary)' }}>{scanResult.updated ?? 0}</strong><br />updated</div>
                  <div><strong style={{ color: 'var(--text-primary)' }}>{scanResult.skipped ?? 0}</strong><br />skipped</div>
                  <div><strong style={{ color: scanResult.failed ? 'var(--danger)' : 'var(--text-primary)' }}>{scanResult.failed ?? 0}</strong><br />failed</div>
                  <div><strong style={{ color: scanUsedFallback ? 'var(--warning)' : 'var(--text-primary)' }}>{scanResult.fallback_count ?? 0}</strong><br />fallback</div>
                </div>
                <div style={{ display: 'grid', gap: '0.35rem', fontSize: '0.86rem' }}>
                  <span>Max words: <strong style={{ color: 'var(--text-primary)' }}>{scanResult.max_words ?? captionScanMaxWords}</strong></span>
                  <span>Provider: <strong style={{ color: 'var(--text-primary)' }}>{captionProviderLabels[scanResult.provider || captionScanProvider]}</strong></span>
                  {scanResult.local_model_id || captionScanProvider === 'local_blip' ? <span>BLIP model: <strong style={{ color: 'var(--text-primary)' }}>{scanResult.local_model_id || captionLocalModelId || 'default'}</strong></span> : null}
                  {scanResult.clip_model_id || captionScanProvider === 'clip_tagger' ? <span>CLIP model: <strong style={{ color: 'var(--text-primary)' }}>{scanResult.clip_model_id || captionClipModelId}</strong></span> : null}
                  <span>Trigger added: <strong style={{ color: 'var(--text-primary)' }}>{scanResult.trigger_applied_count ?? 0}</strong>{scanResult.trigger_applied ? ` using ${captionTriggerWord || 'dataset trigger'}` : ''}</span>
                  <span>Caption source: <strong style={{ color: 'var(--text-primary)' }}>{scanResult.model_count ? scanResult.model_used || 'image caption model' : 'filename fallback'}</strong></span>
                  {captionSourceEntries.length ? (
                    <span>Source counts: <strong style={{ color: 'var(--text-primary)' }}>{captionSourceEntries.map(([source, count]) => `${captionSourceLabels[source] || source}: ${count}`).join(' - ')}</strong></span>
                  ) : null}
                </div>
                {scanUsedFallback ? (
                  <div style={{ color: 'var(--warning)', fontSize: '0.86rem' }}>
                    Filename fallback was used for at least one image. Select KoboldCPP/vLLM, Local BLIP, or CLIP tagger and enable overwrite to replace weak captions.
                  </div>
                ) : null}
                {scanResult.errors?.length ? (
                  <div style={{ display: 'grid', gap: '0.25rem', color: 'var(--danger)', fontSize: '0.82rem' }}>
                    {scanResult.errors.slice(0, 3).map((item, index) => <span key={`${item.filename || 'caption-error'}-${index}`}>{item.filename || 'image'}: {item.error}</span>)}
                  </div>
                ) : null}
              </div>
            ) : (
              <div style={{ border: '1px dashed var(--border-color)', borderRadius: 8, padding: '0.85rem', color: 'var(--text-secondary)' }}>
                The next scan will report generated captions, skipped files, fallback usage, and trigger insertion counts here.
              </div>
            )}
          </Section>
        </div>
      ) : null}

      {activeTab === 'settings' ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(360px, 100%), 1fr))', gap: '1rem' }}>
          <Section title="Training Preset" icon={Brain}>
            <div style={{ display: 'grid', gap: '0.55rem' }}>
              {(Object.keys(presetDescriptions) as TrainingPreset[]).map((item) => (
                <button key={item} onClick={() => setPreset(item)} className={preset === item ? 'primary-button' : 'ghost-button'} style={{ justifyContent: 'flex-start', textAlign: 'left', minWidth: 0 }}>
                  <Brain size={16} />
                  <span style={{ minWidth: 0 }}><strong>{item.replace(/_/g, ' ')}</strong><br /><span style={{ color: 'var(--text-secondary)', fontSize: '0.78rem', whiteSpace: 'normal' }}>{presetDescriptions[item]}</span></span>
                </button>
              ))}
            </div>
          </Section>

          <Section title="Run Settings" icon={Cpu}>
            <label>Dataset<select value={selectedDatasetId} onChange={(event) => selectDataset(event.target.value)}><option value="">Select dataset</option>{datasets.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.name}</option>)}</select></label>
            <label>Output name<input value={outputName} onChange={(event) => setOutputName(event.target.value)} /></label>
            <label>Base SDXL model<select value={baseModel} onChange={(event) => setBaseModel(event.target.value)}><option value="">Select base checkpoint</option>{baseModelFiles.map((model) => <option key={model.path} value={model.path}>{model.name} · {formatBytes(model.size)}</option>)}</select></label>
            <label>VAE<select value={vae} onChange={(event) => setVae(event.target.value)}><option value="">No VAE override</option>{vaeModelFiles.map((model) => <option key={model.path} value={model.path}>{model.name} · {formatBytes(model.size)}</option>)}</select></label>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '0.65rem' }}>
              <label>Epochs<input type="number" min={1} value={epochs} onChange={(event) => setEpochs(Number(event.target.value) || 1)} /></label>
              <label>Num Repeats<input type="number" min={1} value={numRepeats} onChange={(event) => setNumRepeats(Number(event.target.value) || 1)} /></label>
              <label>Steps<input type="number" min={1} value={maxTrainSteps} onChange={(event) => { setStepsEdited(true); setMaxTrainSteps(Math.max(1, Number(event.target.value) || 1)); }} /></label>
              <label>Resolution<input type="number" min={256} step={64} value={resolution} onChange={(event) => setResolution(Number(event.target.value) || 1024)} /></label>
              <label>LoRA Type<select value={loraType} onChange={(event) => setLoraType(event.target.value as LoraType)}><option value="lora">lora</option><option value="locon">locon</option><option value="loha">loha</option><option value="lokr">lokr</option></select></label>
              <label>Keep Tokens<input type="number" min={0} value={keepTokens} onChange={(event) => setKeepTokens(Math.max(0, Number(event.target.value) || 0))} /></label>
              <label>Clip Skip<input type="number" min={1} value={clipSkip} onChange={(event) => setClipSkip(Math.max(1, Number(event.target.value) || 1))} /></label>
              <label>Optimizer<input value={optimizerType} onChange={(event) => setOptimizerType(event.target.value)} /></label>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '0.55rem' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}><input type="checkbox" checked={enableBucket} onChange={(event) => setEnableBucket(event.target.checked)} style={{ width: 'auto' }} /> Enable Bucket</label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}><input type="checkbox" checked={bucketNoUpscale} onChange={(event) => setBucketNoUpscale(event.target.checked)} style={{ width: 'auto' }} /> Bucket No Upscale</label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}><input type="checkbox" checked={shuffleTags} onChange={(event) => setShuffleTags(event.target.checked)} style={{ width: 'auto' }} /> Shuffle Tags</label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}><input type="checkbox" checked={flipAug} onChange={(event) => setFlipAug(event.target.checked)} style={{ width: 'auto' }} /> Flip Augmentation</label>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '0.65rem' }}>
              <label>Unet LR<input value={unetLr} onChange={(event) => setUnetLr(event.target.value)} /></label>
              <label>Text Encoder LR<input value={textEncoderLr} onChange={(event) => setTextEncoderLr(event.target.value)} /></label>
              <label>LR Scheduler<select value={lrScheduler} onChange={(event) => setLrScheduler(event.target.value)}><option value="cosine">cosine</option><option value="constant">constant</option><option value="linear">linear</option><option value="polynomial">polynomial</option><option value="cosine_with_restarts">cosine with restarts</option></select></label>
              <label>LR Scheduler Cycles<input type="number" min={1} value={lrSchedulerCycles} onChange={(event) => setLrSchedulerCycles(Math.max(1, Number(event.target.value) || 1))} /></label>
              <label>Min SNR Gamma<input value={minSnrGamma} onChange={(event) => setMinSnrGamma(event.target.value)} /></label>
              <label>Network Dim<input type="number" min={1} value={networkDim} onChange={(event) => setNetworkDim(Number(event.target.value) || 1)} /></label>
              <label>Network Alpha<input type="number" min={1} value={networkAlpha} onChange={(event) => setNetworkAlpha(Number(event.target.value) || 1)} /></label>
              <label>Noise Offset<input value={noiseOffset} onChange={(event) => setNoiseOffset(event.target.value)} /></label>
              <label>Mixed Precision<select value={mixedPrecision} onChange={(event) => setMixedPrecision(event.target.value as MixedPrecision)}><option value="auto">auto</option><option value="bf16">bf16</option><option value="fp16">fp16</option><option value="no">no</option></select></label>
              <label>Save Every Epochs<input type="number" min={1} value={saveEveryNEpochs} onChange={(event) => setSaveEveryNEpochs(Math.max(1, Number(event.target.value) || 1))} /></label>
            </div>
            {preset === 'anima_lora' ? (
              <div style={{ display: 'grid', gap: '0.65rem' }}>
                <input value={animaDit} onChange={(event) => setAnimaDit(event.target.value)} placeholder="Anima DiT path" />
                <input value={animaTextEncoder} onChange={(event) => setAnimaTextEncoder(event.target.value)} placeholder="Qwen/text encoder path" />
                <input value={animaVae} onChange={(event) => setAnimaVae(event.target.value)} placeholder="VAE path" />
              </div>
            ) : null}
            {preset === 'z_image_lora' ? <input value={zTrainScript} onChange={(event) => setZTrainScript(event.target.value)} placeholder="Z-Image train script path" /> : null}
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}><input type="checkbox" checked={dryRun} onChange={(event) => setDryRun(event.target.checked)} style={{ width: 'auto' }} /> Dry-run command/artifact</label>
            <div style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.65rem', color: 'var(--text-secondary)', display: 'flex', justifyContent: 'space-between', gap: '0.75rem', flexWrap: 'wrap' }}>
              <span>Queue</span>
              <strong style={{ color: 'var(--text-primary)' }}>{queuedRuns} queued · {activeRuns} running</strong>
            </div>
            <div style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.65rem', color: 'var(--text-secondary)', display: 'grid', gap: '0.35rem' }}>
              <span>Calculated steps: <strong style={{ color: 'var(--text-primary)' }}>{calculatedSteps}</strong> <button className="ghost-button" onClick={() => { setStepsEdited(false); setMaxTrainSteps(calculatedSteps); }} style={{ padding: '0.25rem 0.5rem', marginLeft: '0.4rem' }}>Use</button></span>
              <span>Trainer: <strong style={{ color: trainingModelFiles?.sd_scripts_ready ? 'var(--success)' : 'var(--danger)' }}>{trainingModelFiles?.sd_scripts_ready ? 'ready' : 'missing'}</strong>{trainingModelFiles?.dry_run_forced ? <strong style={{ color: 'var(--warning)' }}> · forced dry-run</strong> : null}</span>
            </div>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              <button onClick={() => void previewCommand()} className="ghost-button"><FileText size={16} /> Preview Command</button>
              <button onClick={() => void startTraining()} disabled={!selectedDatasetId || !baseModel} className="primary-button"><Play size={16} /> Queue Training</button>
            </div>
          </Section>

          {commandPreview ? (
            <Section title="Command Preview" icon={FileText}>
              <code style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: 'var(--text-secondary)' }}>{commandPreview.display_command}</code>
            </Section>
          ) : null}
        </div>
      ) : null}

      {activeTab === 'runs' ? (
        <Section title="Training Runs" icon={Clock}>
          <div style={{ display: 'grid', gap: '0.65rem' }}>
            {runs.map((run) => (
              <div key={run.id} style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.75rem', display: 'grid', gap: '0.45rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', flexWrap: 'wrap' }}>
                  <strong>{run.job_type}</strong>
                  <span style={{ color: run.status === 'failed' ? 'var(--danger)' : 'var(--text-secondary)' }}>{run.status} · {formatPercent(run.progress)}</span>
                </div>
                <div style={{ height: 6, borderRadius: 999, background: 'rgba(255,255,255,0.08)', overflow: 'hidden' }}><div style={{ width: formatPercent(run.progress), height: '100%', background: run.status === 'failed' ? 'var(--danger)' : 'var(--accent)' }} /></div>
                {run.error_text ? <span style={{ color: 'var(--danger)' }}>{run.error_text}</span> : null}
              </div>
            ))}
          </div>
        </Section>
      ) : null}

      {activeTab === 'artifacts' ? (
        <Section title="Saved Models" icon={FolderOpen}>
          <div style={{ display: 'grid', gap: '0.65rem' }}>
            {artifacts.map((artifact) => (
              <div key={artifact.path} style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.75rem', display: 'flex', justifyContent: 'space-between', gap: '0.75rem', flexWrap: 'wrap' }}>
                <div>
                  <strong>{artifact.name}</strong>
                  <div style={{ color: 'var(--text-secondary)', fontSize: '0.8rem', wordBreak: 'break-word' }}>{artifact.path}</div>
                </div>
                <span style={{ color: artifact.kind === 'lora' ? 'var(--success)' : 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                  {artifact.kind === 'lora' ? <CheckCircle2 size={14} /> : null}
                  {artifact.kind} · {formatBytes(artifact.size)}
                </span>
              </div>
            ))}
          </div>
        </Section>
      ) : null}
    </div>
  );
}
