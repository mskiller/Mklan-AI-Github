import { useCallback, useEffect, useMemo, useState, useTransition } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  Bot,
  Box,
  Check,
  Copy,
  Database,
  Download,
  FileSearch,
  Filter,
  GitCompare,
  Loader2,
  RefreshCw,
  Save,
  Search,
  Sparkles,
  Tags,
  Wand2,
  Image as ImageIcon,
  Trash2
} from "lucide-react";
import { api } from "./lib/api";
import type {
  DuplicateGroup,
  EntryItem,
  ExportPlan,
  Health,
  LlmJobItem,
  LlmSuggestResponse,
  PromptComposeResponse,
  ScanSummary,
  TagItem,
  WildcardDetail,
  WildcardListItem
} from "./types/api";

type TabId = "browse" | "prompts" | "duplicates" | "llm" | "export" | "images";
type PromptMode = "danbooru_tags" | "sdxl_natural";

const tabs: Array<{ id: TabId; label: string; icon: any }> = [
  { id: "browse", label: "Browse", icon: FileSearch },
  { id: "prompts", label: "Prompt Builder", icon: Wand2 },
  { id: "images", label: "Image Generator", icon: ImageIcon },
  { id: "duplicates", label: "Duplicates", icon: GitCompare },
  { id: "llm", label: "LLM Assistant", icon: Bot },
  { id: "export", label: "Export", icon: Download }
];

const promptSlots = ["quality", "copyright", "characters", "anatomy", "clothing", "pose", "background", "lighting", "style"];
const promptModeLabels: Record<string, string> = {
  danbooru_tags: "NoobAI/Illustrious tags",
  sdxl_natural: "SDXL natural language",
  mixed: "Mixed",
  unknown: "Unknown"
};

const formatBytes = (bytes: number) => {
  if (bytes > 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes > 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
};

const splitCsv = (value: string) =>
  value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

const defaultStudioImageDefaults = {
  width: 1024,
  height: 1024,
  steps: 30,
  cfg_scale: 7.0,
  sampler_name: "Euler a",
  scheduler: "Automatic",
  negative_prompt: "worst quality, low quality, blurred, monochrome",
};

export function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<TabId>("browse");

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const tabParam = params.get('tab');
    if (tabParam === 'taxonomy') setActiveTab('browse');
    else if (tabParam === 'llm') setActiveTab('llm');
    else if (tabParam === 'recipes') setActiveTab('prompts');
    else if (tabParam && tabs.some((tab) => tab.id === tabParam)) setActiveTab(tabParam as TabId);
  }, [location.search]);
  const [health, setHealth] = useState<Health | null>(null);
  const [scanSummary, setScanSummary] = useState<ScanSummary | null>(null);
  const [wildcards, setWildcards] = useState<WildcardListItem[]>([]);
  const [selectedWildcard, setSelectedWildcard] = useState<WildcardListItem | null>(null);
  const [detail, setDetail] = useState<WildcardDetail | null>(null);
  const [tags, setTags] = useState<TagItem[]>([]);
  const [categories, setCategories] = useState<Array<{ category: string; usage_count: number }>>([]);
  const [duplicates, setDuplicates] = useState<DuplicateGroup[]>([]);
  const [search, setSearch] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [tagPolarity, setTagPolarity] = useState<"positive" | "negative" | "all">("all");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [kindFilter, setKindFilter] = useState("");
  const [promptModeFilter, setPromptModeFilter] = useState("");
  const [promptModes, setPromptModes] = useState<Array<{ prompt_mode: string; entry_count: number; file_count: number; wildcard_count: number }>>([]);
  const [editingEntry, setEditingEntry] = useState<EntryItem | null>(null);
  const [editText, setEditText] = useState("");
  const [positiveTags, setPositiveTags] = useState("1girl, solo, looking_at_viewer");
  const [negativeTags, setNegativeTags] = useState("worst quality, low quality, bad anatomy");
  const [wildcardRefs, setWildcardRefs] = useState("");
  const [promptPreset, setPromptPreset] = useState("Illustrious balanced");
  const [promptMode, setPromptMode] = useState<PromptMode>("danbooru_tags");
  const [sdxlFields, setSdxlFields] = useState({
    image_type: "photo",
    subject: "a clear central subject",
    details: "",
    environment: "",
    mood: "",
    style: "natural lighting, shallow depth of field, realistic textures"
  });
  const [slotText, setSlotText] = useState<Record<string, string>>({
    quality: "",
    copyright: "",
    characters: "",
    anatomy: "",
    clothing: "",
    pose: "",
    background: "",
    lighting: "",
    style: ""
  });
  const [promptResult, setPromptResult] = useState<PromptComposeResponse | null>(null);
  const [cleanupText, setCleanupText] = useState("");
  const [cleanupResult, setCleanupResult] = useState<Record<string, unknown> | null>(null);
  const [recipeName, setRecipeName] = useState("New prompt recipe");
  const [recipes, setRecipes] = useState<Array<Record<string, unknown>>>([]);
  const [overrideTag, setOverrideTag] = useState("");
  const [overrideCanonical, setOverrideCanonical] = useState("");
  const [overrideCategory, setOverrideCategory] = useState("characters");
  const [tagOverrides, setTagOverrides] = useState<Array<Record<string, unknown>>>([]);
  const [llmText, setLlmText] = useState("");
  const [llmTask, setLlmTask] = useState("improve_prompt_order");
  const [llmPromptMode, setLlmPromptMode] = useState<PromptMode>("danbooru_tags");
  const [llmEndpoint, setLlmEndpoint] = useState("http://host.docker.internal:5001/v1");
  const [llmResult, setLlmResult] = useState<LlmSuggestResponse | null>(null);
  const [llmJobs, setLlmJobs] = useState<LlmJobItem[]>([]);
  const [taxonomy, setTaxonomy] = useState<Record<string, string[]>>({});
  const [taxonomyCategory, setTaxonomyCategory] = useState("characters");
  const [taxonomyKeywords, setTaxonomyKeywords] = useState("");
  const [exportFormat, setExportFormat] = useState("txt_tree");
  const [exportPromptMode, setExportPromptMode] = useState("all");
  const [exportTarget, setExportTarget] = useState("");
  const [overwriteExport, setOverwriteExport] = useState(false);
  const [exportPlan, setExportPlan] = useState<ExportPlan | null>(null);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [scanRunning, setScanRunning] = useState(false);
  const [isPending, startTransition] = useTransition();
  const [busy, setBusy] = useState(false);

  // === Prompt Suggestion Helper States ===
  const [activeSuggestions, setActiveSuggestions] = useState<string[]>([]);
  const [suggestSource, setSuggestSource] = useState("");
  const [activeSuggestField, setActiveSuggestField] = useState<"positiveTags" | "editText" | "negativeTags" | "">("");

  const fetchPromptSuggestions = useCallback(async (text: string) => {
    if (!text || text.trim().length < 2) {
      setActiveSuggestions([]);
      setSuggestSource("");
      return;
    }
    try {
      const response = await fetch("/api/suggester/suggest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text,
          endpoint: llmEndpoint,
          prompt_mode: promptMode
        })
      });
      if (response.ok) {
        const data = await response.json();
        setActiveSuggestions(data.suggestions || []);
        setSuggestSource(data.source || "");
      }
    } catch (err) {
      console.error("Suggestions failed:", err);
    }
  }, [llmEndpoint, promptMode]);

  const handleSelectSuggestion = (tag: string) => {
    if (activeSuggestField === "positiveTags") {
      setPositiveTags((prev) => [prev, tag].filter(Boolean).join(", "));
    } else if (activeSuggestField === "editText") {
      setEditText((prev) => [prev, tag].filter(Boolean).join(", "));
    } else if (activeSuggestField === "negativeTags") {
      setNegativeTags((prev) => [prev, tag].filter(Boolean).join(", "));
    }
  };

  // === Image Generator Integration ===
  const [sandboxPrompt, setSandboxPrompt] = useState("");
  const [sandboxNegativePrompt, setSandboxNegativePrompt] = useState("worst quality, low quality, blurred, monochrome");
  const [sandboxWidth, setSandboxWidth] = useState(1024);
  const [sandboxHeight, setSandboxHeight] = useState(1024);
  const [sandboxSteps, setSandboxSteps] = useState(30);
  const [sandboxCfg, setSandboxCfg] = useState(7.0);
  const [sandboxSampler, setSandboxSampler] = useState("Euler a");
  const [sandboxScheduler, setSandboxScheduler] = useState("Automatic");
  const [sandboxImage, setSandboxImage] = useState("");
  const [sandboxLoading, setSandboxLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const params = new URLSearchParams(location.search);

    fetch("/api/studio/settings")
      .then((response) => (response.ok ? response.json() : null))
      .then((payload) => {
        if (cancelled || !payload?.image?.defaults) return;
        const defaults = { ...defaultStudioImageDefaults, ...payload.image.defaults };
        if (!params.get("negative_prompt")) setSandboxNegativePrompt(defaults.negative_prompt);
        if (!params.get("width")) setSandboxWidth(Number(defaults.width) || defaultStudioImageDefaults.width);
        if (!params.get("height")) setSandboxHeight(Number(defaults.height) || defaultStudioImageDefaults.height);
        if (!params.get("steps")) setSandboxSteps(Number(defaults.steps) || defaultStudioImageDefaults.steps);
        if (!params.get("cfg_scale")) setSandboxCfg(Number(defaults.cfg_scale) || defaultStudioImageDefaults.cfg_scale);
        if (!params.get("sampler_name")) setSandboxSampler(String(defaults.sampler_name || defaultStudioImageDefaults.sampler_name));
        if (!params.get("scheduler")) setSandboxScheduler(String(defaults.scheduler || defaultStudioImageDefaults.scheduler));
      })
      .catch(() => undefined);

    return () => {
      cancelled = true;
    };
  }, [location.search]);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const p = params.get("prompt");
    const np = params.get("negative_prompt");
    const w = params.get("width");
    const h = params.get("height");
    const s = params.get("steps");
    const c = params.get("cfg_scale");
    const sm = params.get("sampler_name");
    const scheduler = params.get("scheduler");

    if (p) setSandboxPrompt(p);
    if (np) setSandboxNegativePrompt(np);
    if (w) setSandboxWidth(Number(w));
    if (h) setSandboxHeight(Number(h));
    if (s) setSandboxSteps(Number(s));
    if (c) setSandboxCfg(Number(c));
    if (sm) setSandboxSampler(sm);
    if (scheduler) setSandboxScheduler(scheduler);
  }, [location.search]);

  const [generatedGallery, setGeneratedGallery] = useState<any[]>([]);
  const [galleryLoading, setGalleryLoading] = useState(false);
  const [semanticQuery, setSemanticQuery] = useState("");

  const fetchGeneratedGallery = useCallback(async () => {
    setGalleryLoading(true);
    try {
      const r = await fetch('/api/media/assets');
      if (r.ok) {
        const d = await r.json();
        const mapped = (d.items || []).map((item: any) => ({
          name: item.filename,
          size: item.size_bytes,
          created_at: new Date(item.modified_at).getTime(),
          url: `/api/media/assets/${item.id}/image?w=1024`,
          metadata: item.normalized_metadata || {},
          id: item.id
        }));
        setGeneratedGallery(mapped);
      } else {
        const fallbackR = await fetch('/api/studio/generated');
        if (fallbackR.ok) {
            const fallbackD = await fallbackR.json();
            setGeneratedGallery(fallbackD.images || []);
        }
      }
    } catch (err) {
      console.error("Failed to load gallery:", err);
    } finally {
      setGalleryLoading(false);
    }
  }, []);

  const runSemanticSearch = useCallback(async () => {
    if (!semanticQuery.trim()) {
      void fetchGeneratedGallery();
      return;
    }
    setGalleryLoading(true);
    try {
      const r = await fetch(`/api/media/assets?q=${encodeURIComponent(semanticQuery)}`);
      if (r.ok) {
        const d = await r.json();
        const mapped = (d.items || []).map((item: any) => ({
          name: item.filename,
          size: item.size_bytes,
          created_at: new Date(item.modified_at).getTime(),
          url: `/api/media/assets/${item.id}/image?w=1024`,
          metadata: item.normalized_metadata || {},
          id: item.id
        }));
        setGeneratedGallery(mapped);
      } else {
        const fallbackR = await fetch(`/api/studio/semantic-search?q=${encodeURIComponent(semanticQuery)}`);
        if (fallbackR.ok) {
            const fallbackD = await fallbackR.json();
            setGeneratedGallery(fallbackD.images || []);
        }
      }
    } catch (err) {
      console.error("Failed semantic search:", err);
    } finally {
      setGalleryLoading(false);
    }
  }, [semanticQuery, fetchGeneratedGallery]);

  const [comparerOpen, setComparerOpen] = useState(false);
  const [comparerImages, setComparerImages] = useState<any[]>([]);
  const [comparerMode, setComparerMode] = useState<"side" | "slider">("side");
  const [zoomImage, setZoomImage] = useState<any | null>(null);
  const [uploadingGallery, setUploadingGallery] = useState(false);

  const handleGalleryUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    setUploadingGallery(true);
    const fd = new FormData();
    for (let i = 0; i < e.target.files.length; i++) {
      fd.append("files", e.target.files[i]);
    }
    try {
      const r = await fetch('/api/studio/generated/upload', {
        method: 'POST',
        body: fd
      });
      if (r.ok) {
        void fetchGeneratedGallery();
      }
    } catch (err) {
      console.error("Gallery upload failed", err);
    } finally {
      setUploadingGallery(false);
    }
  };

  const deleteGeneratedImage = async (filename: string) => {
    if (!window.confirm("Are you sure you want to delete this generated image?")) return;
    try {
      const r = await fetch(`/api/studio/generated/${filename}`, { method: 'DELETE' });
      if (r.ok) {
        void fetchGeneratedGallery();
      }
    } catch (err) {
      console.error("Failed to delete image:", err);
    }
  };

  const generateSandboxImage = async () => {
    setSandboxLoading(true);
    setError("");
    setSandboxImage("");
    try {
      const r = await fetch('/api/studio/generate-image', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: sandboxPrompt,
          negative_prompt: sandboxNegativePrompt,
          width: sandboxWidth,
          height: sandboxHeight,
          steps: sandboxSteps,
          cfg_scale: sandboxCfg,
          sampler_name: sandboxSampler,
          scheduler: sandboxScheduler
        })
      });
      if (!r.ok) {
        const d = await r.json();
        throw new Error(d.detail || 'Generation failed.');
      }
      const d = await r.json();
      setSandboxImage(`data:image/png;base64,${d.image_base64}`);
      navigate('/gallery');
    } catch (err: any) {
      setError('Image generation failed: ' + err.message);
    } finally {
      setSandboxLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === "images") {
      void fetchGeneratedGallery();
    }
  }, [activeTab, fetchGeneratedGallery]);

  const loadHealth = useCallback(async () => {
    const result = await api.health();
    setHealth(result);
  }, []);

  const loadWildcards = useCallback(async () => {
    const result = await api.wildcards({ search, tag: tagFilter, tag_polarity: tagPolarity, kind: kindFilter, category: categoryFilter, prompt_mode: promptModeFilter, limit: 350 });
    startTransition(() => setWildcards(result));
  }, [categoryFilter, kindFilter, promptModeFilter, search, tagFilter, tagPolarity]);

  const loadTags = useCallback(async () => {
    const result = await api.tags("", categoryFilter, tagPolarity);
    setTags(result.tags);
  }, [categoryFilter, tagPolarity]);

  const loadCategories = useCallback(async () => {
    const result = await api.categories();
    setCategories(result.categories);
  }, []);

  const loadPromptModes = useCallback(async () => {
    const result = await api.promptModes();
    setPromptModes(result.modes);
  }, []);

  const loadDuplicates = useCallback(async () => {
    const result = await api.duplicates();
    setDuplicates(result.groups);
  }, []);

  const loadTaxonomy = useCallback(async () => {
    const result = await api.taxonomy();
    setTaxonomy(result.rules);
    const category = taxonomyCategory || Object.keys(result.rules)[0] || "characters";
    setTaxonomyCategory(category);
    setTaxonomyKeywords((result.rules[category] ?? []).join("\n"));
  }, [taxonomyCategory]);

  const loadLlmJobs = useCallback(async () => {
    const result = await api.llmJobs();
    setLlmJobs(result);
  }, []);

  useEffect(() => {
    loadHealth().catch((err) => setError(String(err)));
  }, [loadHealth]);

  useEffect(() => {
    loadTaxonomy().catch(() => undefined);
    loadLlmJobs().catch(() => undefined);
  }, [loadLlmJobs, loadTaxonomy]);

  useEffect(() => {
    loadWildcards().catch((err) => setError(String(err)));
  }, [loadWildcards]);

  useEffect(() => {
    loadTags().catch(() => undefined);
  }, [loadTags, scanSummary]);

  useEffect(() => {
    loadCategories().catch(() => undefined);
  }, [loadCategories, scanSummary]);

  useEffect(() => {
    loadPromptModes().catch(() => undefined);
  }, [loadPromptModes, scanSummary]);

  const selectWildcard = useCallback(async (item: WildcardListItem) => {
    setSelectedWildcard(item);
    setEditingEntry(null);
    setStatus(`Loading ${item.relative_path}`);
    const result = await api.wildcard(item.id);
    setDetail(result);
    setStatus("");
  }, []);

  const runScan = async () => {
    setBusy(true);
    setError("");
    setStatus("Starting background scan. You can keep browsing while the index rebuilds.");
    try {
      const result = await api.scan();
      if ("source_root" in result) {
        setScanSummary(result);
        setStatus(`Indexed ${result.files_indexed} files and ${result.entries_indexed.toLocaleString()} entries.`);
        await Promise.all([loadHealth(), loadWildcards(), loadTags(), loadCategories(), loadPromptModes()]);
      } else {
        setScanRunning(true);
        setStatus(result.message);
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (!scanRunning) return;
    const timer = window.setInterval(() => {
      api
        .scanStatus()
        .then(async (result) => {
          if (result.running) {
            setStatus("Scanning in background. The library will refresh when it completes.");
            return;
          }
          setScanRunning(false);
          if (result.error) {
            setError(result.error);
            return;
          }
          if (result.summary) {
            setScanSummary(result.summary);
            setStatus(`Indexed ${result.summary.files_indexed} files and ${result.summary.entries_indexed.toLocaleString()} entries.`);
            await Promise.all([loadHealth(), loadWildcards(), loadTags(), loadCategories(), loadPromptModes()]);
          }
        })
        .catch((err) => setError(String(err)));
    }, 3000);
    return () => window.clearInterval(timer);
  }, [loadCategories, loadHealth, loadPromptModes, loadTags, loadWildcards, scanRunning]);

  const saveEntry = async () => {
    if (!editingEntry) return;
    setBusy(true);
    setError("");
    try {
      const updated = await api.patchEntry(editingEntry.id, editText);
      setEditingEntry(updated);
      if (selectedWildcard) {
        const refreshed = await api.wildcard(selectedWildcard.id);
        setDetail(refreshed);
      }
      setStatus("Entry staged. Original source file remains untouched.");
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const composePrompt = async () => {
    const slots = Object.fromEntries(promptSlots.map((slot) => [slot, splitCsv(slotText[slot] ?? "")]));
    const result = await api.composePrompt({
      positive_tags: splitCsv(positiveTags),
      negative_tags: splitCsv(negativeTags),
      wildcard_refs: splitCsv(wildcardRefs),
      model_profile: "Illustrious",
      quality_preset: "balanced",
      preset: promptPreset,
      prompt_mode: promptMode,
      slots,
      sdxl: sdxlFields
    });
    setPromptResult(result);
  };

  const addTagToSlot = (tag: string) => {
    if (tagPolarity === "negative") {
      setNegativeTags((value) => [value, tag].filter(Boolean).join(", "));
      return;
    }
    const targetSlot = categoryFilter || "general";
    if (!promptSlots.includes(targetSlot)) {
      setPositiveTags((value) => [value, tag].filter(Boolean).join(", "));
      return;
    }
    setSlotText((value) => ({ ...value, [targetSlot]: [value[targetSlot], tag].filter(Boolean).join(", ") }));
  };

  const createFromParsedPrompt = () => {
    if (!editingEntry) return;
    const nextSlots: Record<string, string> = { ...slotText };
    for (const tag of editingEntry.positive_tags) {
      const bucket = promptSlots.find((slot) => editingEntry.tag_categories.includes(slot)) ?? "style";
      nextSlots[bucket] = [nextSlots[bucket], tag].filter(Boolean).join(", ");
    }
    setSlotText(nextSlots);
    setNegativeTags(editingEntry.negative_tags.join(", "));
    setWildcardRefs(editingEntry.refs.join(", "));
    setPromptMode(editingEntry.prompt_mode === "sdxl_natural" ? "sdxl_natural" : "danbooru_tags");
    setActiveTab("prompts");
  };

  const runCleanupPreview = async () => {
    const result = await api.cleanupPreview(cleanupText || editText);
    setCleanupResult(result);
  };

  const saveRecipe = async () => {
    const slots = Object.fromEntries(promptSlots.map((slot) => [slot, splitCsv(slotText[slot] ?? "")]));
    await api.savePromptRecipe({
      name: recipeName,
      preset: promptPreset,
      slots,
      negative_tags: splitCsv(negativeTags),
      wildcard_refs: splitCsv(wildcardRefs)
    });
    const result = await api.promptRecipes();
    setRecipes(result.recipes);
    setStatus("Prompt recipe saved.");
  };

  const saveOverride = async () => {
    await api.saveTagOverride({
      tag: overrideTag,
      canonical_tag: overrideCanonical || undefined,
      category: overrideCategory || undefined,
      is_ignored: false
    });
    const result = await api.tagOverrides();
    setTagOverrides(result.overrides);
    setStatus("Tag override saved.");
  };

  const changeTaxonomyCategory = (category: string) => {
    setTaxonomyCategory(category);
    setTaxonomyKeywords((taxonomy[category] ?? []).join("\n"));
  };

  const saveTaxonomy = async () => {
    const keywords = taxonomyKeywords
      .split(/\r?\n/)
      .map((keyword) => keyword.trim())
      .filter(Boolean);
    await api.updateTaxonomy({ category: taxonomyCategory, keywords });
    await loadTaxonomy();
    setStatus("Taxonomy rules saved. Reindex to apply them to existing entries.");
  };

  const reindexTaxonomy = async () => {
    const result = await api.reindexTaxonomy();
    if ("source_root" in result) {
      setScanSummary(result);
      setStatus(`Reindexed ${result.files_indexed} files.`);
    } else {
      setScanRunning(true);
      setStatus(result.message);
    }
  };

  const runLlm = async () => {
    setBusy(true);
    setError("");
    setLlmResult(null);
    try {
      const result = await api.llmSuggest({
        task: llmTask,
        text: llmText,
        endpoint: llmEndpoint,
        model: "local-model",
        prompt_mode: llmPromptMode
      });
      setLlmResult(result);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const testLlm = async () => {
    setBusy(true);
    setError("");
    try {
      const result = await api.llmTest({
        task: llmTask,
        text: llmText || "ok",
        endpoint: llmEndpoint,
        model: "local-model",
        prompt_mode: llmPromptMode
      });
      setLlmResult(result);
      setStatus(result.ok ? `LLM connected through ${result.endpoint_used}.` : "LLM test failed; see the review panel.");
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const queueLlmJob = async () => {
    setBusy(true);
    setError("");
    try {
      await api.createLlmJob({
        task: llmTask,
        text: llmText,
        endpoint: llmEndpoint,
        model: "local-model",
        prompt_mode: llmPromptMode
      });
      await loadLlmJobs();
      setStatus("LLM job queued.");
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const clearLlmContext = () => {
    setLlmText("");
    setLlmResult(null);
    setStatus("LLM context cleared.");
  };

  const dryRunExport = async () => {
    setBusy(true);
    setError("");
    try {
      const result = await api.exportDryRun({
        format: exportFormat,
        target_root: exportTarget || undefined,
        overwrite: overwriteExport,
        prompt_mode: exportPromptMode
      });
      setExportPlan(result);
      setStatus("Export dry-run complete.");
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const runExport = async () => {
    setBusy(true);
    setError("");
    try {
      const result = await api.exportRun({
        format: exportFormat,
        target_root: exportTarget || undefined,
        overwrite: overwriteExport,
        prompt_mode: exportPromptMode
      });
      setExportPlan(result);
      setStatus("Export written.");
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const selectedStats = useMemo(() => {
    if (!detail) return null;
    const dirty = detail.entries.filter((entry) => entry.is_dirty).length;
    const prompts = detail.entries.filter((entry) => entry.kind === "prompt").length;
    return { dirty, prompts, warnings: detail.warnings.length, refs: detail.refs.length };
  }, [detail]);

  const visibleEntries = detail?.entries ?? [];

  return (
    <div className="wildcards-shell">
      <div className="wildcards-hero">
        <div className="wildcards-hero-copy">
          <h1 className="text-gradient" style={{ fontSize: 'clamp(2rem, 3.2vw, 2.8rem)', fontWeight: 800, letterSpacing: '-0.04em', marginBottom: '0.4rem' }}>
            Wildcard Workshop
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '1rem', marginBottom: '1.25rem', maxWidth: '62rem' }}>
            Impact-ready tag library. {health ? `${health.files.toLocaleString()} files, ${health.entries.toLocaleString()} entries` : ''}
          </p>
          <button className="primary-button" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', padding: '0.6rem 1.2rem', borderRadius: 'var(--radius-md)', fontWeight: 600, fontSize: '0.9rem' }} onClick={runScan} disabled={busy || scanRunning}>
            {busy || scanRunning ? <Loader2 className="spin" size={16} /> : <Database size={16} />}
            {scanRunning ? "Scanning..." : "Scan Library"}
          </button>
        </div>

        <div className="wildcards-hero-stats">
          <div className="wildcards-hero-stat">
            <span>Files</span>
            <strong>{health ? health.files.toLocaleString() : "--"}</strong>
          </div>
          <div className="wildcards-hero-stat">
            <span>Entries</span>
            <strong>{health ? health.entries.toLocaleString() : "--"}</strong>
          </div>
          <div className="wildcards-hero-stat">
            <span>Last Scan</span>
            <strong>{health?.last_scan?.created_at ? new Date(health.last_scan.created_at).toLocaleDateString() : "Not yet"}</strong>
          </div>
        </div>
      </div>

      <div className="wildcards-tabs-bar">
        <div className="wildcards-tabs-grid">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                style={{
                  display: 'flex', alignItems: 'center', gap: '0.5rem',
                  padding: '0.65rem 1rem',
                  borderRadius: 'var(--radius-sm)',
                  background: isActive ? 'var(--bg-elevated)' : 'transparent',
                  color: isActive ? '#fff' : 'var(--text-secondary)',
                  border: '1px solid',
                  borderColor: isActive ? 'rgba(255,255,255,0.06)' : 'transparent',
                  fontWeight: 600,
                  fontSize: '0.85rem',
                  boxShadow: isActive ? '0 4px 12px rgba(0,0,0,0.15)' : 'none',
                  cursor: 'pointer',
                  transition: 'all 0.2s'
                }}
              >
                <Icon size={14} />
                {tab.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="wildcards-workspace-row">
        {activeTab === "browse" && (
          <aside className="wildcards-filter-sidebar">

          <div className="section-title">
            <Filter size={15} />
            Categories
          </div>
          <div className="category-list">
            <button className={!categoryFilter ? "active" : ""} onClick={() => setCategoryFilter("")}>
              all
            </button>
            {categories.map((category) => (
              <button
                key={category.category}
                className={categoryFilter === category.category ? "active" : ""}
                onClick={() => setCategoryFilter(category.category)}
                title={`${category.usage_count.toLocaleString()} indexed entries`}
              >
                {category.category}
              </button>
            ))}
          </div>
          <div className="section-title">
            <Tags size={15} />
            Frequent {tagPolarity} Tags
          </div>
          <div className="tag-list">
            {tags.slice(0, 40).map((tag) => (
              <button key={tag.tag} onClick={() => setTagFilter(tag.tag)} title={`${tag.usage_count} uses`}>
                {tag.tag}
              </button>
            ))}
          </div>
          <div className="section-title">
            <Filter size={15} />
            Prompt Modes
          </div>
          <div className="category-list">
            <button className={!promptModeFilter ? "active" : ""} onClick={() => setPromptModeFilter("")}>
              all modes
            </button>
            {promptModes.map((mode) => (
              <button
                key={mode.prompt_mode}
                className={promptModeFilter === mode.prompt_mode ? "active" : ""}
                onClick={() => setPromptModeFilter(mode.prompt_mode)}
                title={`${mode.entry_count.toLocaleString()} entries`}
              >
                {promptModeLabels[mode.prompt_mode] ?? mode.prompt_mode}
              </button>
            ))}
          </div>
          </aside>
        )}

      <section style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'rgba(10, 10, 12, 0.4)', padding: '1rem 1.5rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)' }}>
          <div style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>
            {status || "Local staged library. Exports are explicit."}
          </div>
          <button className="icon-button" style={{ padding: '0.4rem', borderRadius: 'var(--radius-sm)', background: 'rgba(255,255,255,0.05)', color: 'var(--text-secondary)', cursor: 'pointer', border: 'none' }} onClick={() => void Promise.all([loadHealth(), loadWildcards(), loadTags(), loadCategories(), loadPromptModes()])} title="Refresh">
            <RefreshCw size={16} />
          </button>
        </div>

        {error ? (
          <div className="alert">
            <AlertTriangle size={18} />
            <span>{error}</span>
          </div>
        ) : null}

        {scanSummary ? (
          <div className="summary-strip">
            <span>{scanSummary.files_indexed.toLocaleString()} files</span>
            <span>{scanSummary.entries_indexed.toLocaleString()} entries</span>
            <span>{scanSummary.total_mb} MB</span>
            <span>{scanSummary.yaml_files} YAML</span>
          </div>
        ) : null}

        {activeTab === "browse" ? (
          <section className="browse-grid">
            <div className="panel file-panel">
              <div className="toolbar">
                <label className="search-box">
                  <Search size={16} />
                  <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search files or wildcard paths" />
                </label>
                <label className="mini-select">
                  <Filter size={15} />
                  <select value={kindFilter} onChange={(event) => setKindFilter(event.target.value)}>
                    <option value="">All</option>
                    <option value="prompt">Prompts</option>
                    <option value="tag_list">Tag lists</option>
                    <option value="wildcard_item">Items</option>
                  </select>
                </label>
                <label className="mini-select">
                  <Sparkles size={15} />
                  <select value={promptModeFilter} onChange={(event) => setPromptModeFilter(event.target.value)}>
                    <option value="">All modes</option>
                    <option value="danbooru_tags">NoobAI/Illustrious tags</option>
                    <option value="sdxl_natural">SDXL natural language</option>
                    <option value="mixed">Mixed</option>
                    <option value="unknown">Unknown</option>
                  </select>
                </label>
              </div>
              <div className="filter-row">
                <input value={tagFilter} onChange={(event) => setTagFilter(event.target.value)} placeholder="Tag filter" />
                <select value={tagPolarity} onChange={(event) => setTagPolarity(event.target.value as "positive" | "negative" | "all")}>
                  <option value="all">All extracted tags</option>
                  <option value="positive">Positive tags</option>
                  <option value="negative">Negative tags</option>
                </select>
                {tagFilter ? <button onClick={() => setTagFilter("")}>Clear</button> : null}
              </div>
              <div className="filter-row category-filter-row">
                {["copyright", "characters", "pose", "background", "clothing"].map((category) => (
                  <button
                    key={category}
                    className={categoryFilter === category ? "active-filter" : ""}
                    onClick={() => setCategoryFilter(categoryFilter === category ? "" : category)}
                  >
                    {category}
                  </button>
                ))}
              </div>
              <div className="file-list" aria-busy={isPending}>
                {wildcards.map((item) => (
                  <button
                    key={item.id}
                    className={selectedWildcard?.id === item.id ? "file-row selected" : "file-row"}
                    onClick={() => void selectWildcard(item)}
                  >
                    <div>
                      <strong>{item.wildcard_path}</strong>
                      <span>{item.relative_path}</span>
                    </div>
                    <small>{item.entry_count.toLocaleString()}</small>
                    {Object.entries(item.prompt_modes).slice(0, 2).map(([mode, count]) => (
                      <em key={mode} title={promptModeLabels[mode] ?? mode}>{mode === "sdxl_natural" ? "SDXL" : mode === "danbooru_tags" ? "TAG" : `${mode}:${count}`}</em>
                    ))}
                    {item.prompt_count ? <em>P</em> : null}
                    {item.duplicate_count ? <em>D</em> : null}
                    {item.unresolved_refs ? <em>!</em> : null}
                  </button>
                ))}
              </div>
            </div>

            <div className="panel detail-panel">
              {detail && selectedWildcard ? (
                <>
                  <div className="detail-header">
                    <div>
                      <h3>{selectedWildcard.wildcard_path}</h3>
                      <p>
                        {selectedWildcard.relative_path} · {formatBytes(selectedWildcard.size_bytes)}
                      </p>
                    </div>
                    {selectedStats ? (
                      <div className="stat-grid">
                        <span>{selectedStats.prompts} prompts</span>
                        <span>{selectedStats.refs} refs</span>
                        <span>{selectedStats.warnings} warnings</span>
                        <span>{selectedStats.dirty} staged</span>
                      </div>
                    ) : null}
                  </div>

                  {detail.unresolved_refs.length ? (
                    <div className="warning-line">
                      Missing refs: {detail.unresolved_refs.slice(0, 8).join(", ")}
                      {detail.unresolved_refs.length > 8 ? " ..." : ""}
                    </div>
                  ) : null}

                  <div className="entry-list">
                    {visibleEntries.map((entry) => (
                      <button
                        key={entry.id}
                        className={editingEntry?.id === entry.id ? "entry-row selected" : "entry-row"}
                        onClick={() => {
                          setEditingEntry(entry);
                          setEditText(entry.effective_text);
                          if (entry.prompt_mode === "sdxl_natural" || entry.prompt_mode === "danbooru_tags") setLlmPromptMode(entry.prompt_mode);
                          if (!llmText) setLlmText(entry.effective_text);
                        }}
                      >
                        <span>{entry.item_index + 1}</span>
                        <p>{entry.effective_text}</p>
                        <small>{entry.kind} · {promptModeLabels[entry.prompt_mode] ?? entry.prompt_mode} · +{entry.positive_tags.length} / -{entry.negative_tags.length}</small>
                        {entry.is_dirty ? <Check size={15} /> : null}
                      </button>
                    ))}
                  </div>
                </>
              ) : (
                <div className="empty-state">
                  <FileSearch size={34} />
                  <h3>Select a wildcard file</h3>
                  <p>Scan the library, then browse files, prompt templates, refs, warnings, and staged edits.</p>
                </div>
              )}
            </div>

            <div className="panel editor-panel">
              {editingEntry ? (
                <>
                  <div className="section-title">Staged Editor</div>
                  <textarea
                    value={editText}
                    onChange={(event) => {
                      setEditText(event.target.value);
                      setActiveSuggestField("editText");
                      void fetchPromptSuggestions(event.target.value);
                    }}
                    onFocus={() => {
                      setActiveSuggestField("editText");
                      void fetchPromptSuggestions(editText);
                    }}
                    spellCheck={false}
                  />
                  {activeSuggestField === "editText" && activeSuggestions.length > 0 && (
                    <div className="suggestion-chips-container" style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', marginTop: '0.5rem', marginBottom: '1rem', background: 'rgba(255, 255, 255, 0.02)', padding: '0.6rem', borderRadius: '8px', border: '1px solid rgba(255, 255, 255, 0.04)' }}>
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', marginRight: '0.4rem' }}>
                        💡 Suggestions ({suggestSource === 'local_llm' ? 'LLM' : 'Synonyms'}):
                      </span>
                      {activeSuggestions.map((tag) => (
                        <button
                          key={tag}
                          onClick={() => handleSelectSuggestion(tag)}
                          style={{
                            padding: '0.2rem 0.5rem',
                            fontSize: '0.75rem',
                            background: 'rgba(124, 106, 255, 0.1)',
                            border: '1px solid rgba(124, 106, 255, 0.25)',
                            borderRadius: '4px',
                            color: 'var(--accent-hover)',
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            transition: 'all 0.2s'
                          }}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.background = 'rgba(124, 106, 255, 0.2)';
                            e.currentTarget.style.boxShadow = '0 0 8px rgba(124, 106, 255, 0.4)';
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.background = 'rgba(124, 106, 255, 0.1)';
                            e.currentTarget.style.boxShadow = 'none';
                          }}
                        >
                          +{tag}
                        </button>
                      ))}
                    </div>
                  )}
                  <div className="editor-meta">
                    <span>{editingEntry.positive_tags.length} positive</span>
                    <span>{editingEntry.negative_tags.length} negative</span>
                    <span>{editingEntry.all_extracted_tags.length} extracted</span>
                    <span>{promptModeLabels[editingEntry.prompt_mode] ?? editingEntry.prompt_mode}</span>
                    <span>{editingEntry.tag_categories.join(", ") || "general"}</span>
                    <span>{editingEntry.refs.length} refs</span>
                    <span>{editingEntry.warnings.length} warnings</span>
                  </div>
                  <div className="diagnostics">
                    <div>
                      <strong>Positive</strong>
                      <p>{editingEntry.positive_tags.slice(0, 30).join(", ") || "none"}</p>
                    </div>
                    <div>
                      <strong>Negative</strong>
                      <p>{editingEntry.negative_tags.slice(0, 30).join(", ") || "none"}</p>
                    </div>
                    <div>
                      <strong>Prompt parts</strong>
                      <p>
                        {`BREAK x${Number(editingEntry.prompt_parts.break_count ?? 0)} · LoRA ${
                          Array.isArray(editingEntry.prompt_parts.loras) ? editingEntry.prompt_parts.loras.length : 0
                        } · dynamic ${Array.isArray(editingEntry.prompt_parts.dynamic_options) ? editingEntry.prompt_parts.dynamic_options.length : 0}`}
                      </p>
                    </div>
                  </div>
                  <button className="primary" onClick={saveEntry} disabled={busy}>
                    <Save size={16} />
                    Stage Edit
                  </button>
                  <button
                    onClick={() => {
                      setWildcardRefs((value) => [value, editingEntry.wildcard_path].filter(Boolean).join(", "));
                      setActiveTab("prompts");
                    }}
                  >
                    <Wand2 size={16} />
                    Use Wildcard
                  </button>
                  <button onClick={createFromParsedPrompt}>
                    <Tags size={16} />
                    Create from Parsed Prompt
                  </button>
                  <button
                    onClick={() => {
                      setLlmText(editingEntry.effective_text);
                      if (editingEntry.prompt_mode === "sdxl_natural" || editingEntry.prompt_mode === "danbooru_tags") setLlmPromptMode(editingEntry.prompt_mode);
                      setActiveTab("llm");
                    }}
                  >
                    <Sparkles size={16} />
                    Improve with LLM
                  </button>
                </>
              ) : (
                <div className="empty-state compact">
                  <Save size={28} />
                  <h3>No entry selected</h3>
                  <p>Pick a row to stage edits without touching source files.</p>
                </div>
              )}
            </div>
          </section>
        ) : null}

        {activeTab === "prompts" ? (
          <section className="two-column">
            <div className="panel form-panel">
              <div className="prompt-helper">
                <div className="section-title">Category Picker</div>
                <div className="category-list light">
                  {promptSlots.map((category) => (
                    <button
                      key={category}
                      className={categoryFilter === category ? "active" : ""}
                      onClick={() => setCategoryFilter(category)}
                    >
                      {category}
                    </button>
                  ))}
                </div>
                <div className="suggestion-list">
                  {tags.slice(0, 24).map((tag) => (
                    <button
                      key={tag.tag}
                      onClick={() => addTagToSlot(tag.tag)}
                      title={`${tag.usage_count.toLocaleString()} uses`}
                    >
                      {tag.tag}
                    </button>
                  ))}
                </div>
              </div>
              <label>
                Prompt mode
                <select value={promptMode} onChange={(event) => setPromptMode(event.target.value as PromptMode)}>
                  <option value="danbooru_tags">NoobAI/Illustrious tag prompting</option>
                  <option value="sdxl_natural">SDXL natural-language prompting</option>
                </select>
              </label>
              <label>
                Preset
                <select value={promptPreset} onChange={(event) => setPromptPreset(event.target.value)}>
                  <option value="Illustrious balanced">Illustrious balanced</option>
                  <option value="NoobAI tag-heavy">NoobAI tag-heavy</option>
                  <option value="Wildcard-heavy randomizer">Wildcard-heavy randomizer</option>
                </select>
              </label>
              {promptMode === "sdxl_natural" ? (
                <div className="slot-grid">
                  {[
                    ["image_type", "Image type"],
                    ["subject", "Subject/action/location"],
                    ["details", "Details, clothing, textures"],
                    ["environment", "Environment/composition"],
                    ["mood", "Mood/atmosphere"],
                    ["style", "Style execution"]
                  ].map(([key, label]) => (
                    <label key={key}>
                      {label}
                      <input value={sdxlFields[key as keyof typeof sdxlFields]} onChange={(event) => setSdxlFields((value) => ({ ...value, [key]: event.target.value }))} />
                    </label>
                  ))}
                </div>
              ) : (
                <>
                  <div className="slot-grid">
                    {promptSlots.map((slot) => (
                      <label key={slot}>
                        {slot}
                        <input value={slotText[slot] ?? ""} onChange={(event) => setSlotText((value) => ({ ...value, [slot]: event.target.value }))} />
                      </label>
                    ))}
                  </div>
                  <label>
                    Extra positive tags
                    <textarea
                      value={positiveTags}
                      onChange={(event) => {
                        setPositiveTags(event.target.value);
                        setActiveSuggestField("positiveTags");
                        void fetchPromptSuggestions(event.target.value);
                      }}
                      onFocus={() => {
                        setActiveSuggestField("positiveTags");
                        void fetchPromptSuggestions(positiveTags);
                      }}
                    />
                  </label>
                  {activeSuggestField === "positiveTags" && activeSuggestions.length > 0 && (
                    <div className="suggestion-chips-container" style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', marginTop: '0.2rem', marginBottom: '1rem', background: 'rgba(255, 255, 255, 0.02)', padding: '0.6rem', borderRadius: '8px', border: '1px solid rgba(255, 255, 255, 0.04)' }}>
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', marginRight: '0.4rem' }}>
                        💡 Suggestions ({suggestSource === 'local_llm' ? 'LLM' : 'Synonyms'}):
                      </span>
                      {activeSuggestions.map((tag) => (
                        <button
                          key={tag}
                          onClick={() => handleSelectSuggestion(tag)}
                          style={{
                            padding: '0.2rem 0.5rem',
                            fontSize: '0.75rem',
                            background: 'rgba(124, 106, 255, 0.1)',
                            border: '1px solid rgba(124, 106, 255, 0.25)',
                            borderRadius: '4px',
                            color: 'var(--accent-hover)',
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            transition: 'all 0.2s'
                          }}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.background = 'rgba(124, 106, 255, 0.2)';
                            e.currentTarget.style.boxShadow = '0 0 8px rgba(124, 106, 255, 0.4)';
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.background = 'rgba(124, 106, 255, 0.1)';
                            e.currentTarget.style.boxShadow = 'none';
                          }}
                        >
                          +{tag}
                        </button>
                      ))}
                    </div>
                  )}
                </>
              )}
              <label>
                Wildcard refs
                <input value={wildcardRefs} onChange={(event) => setWildcardRefs(event.target.value)} placeholder="starter/styles, starter/subjects" />
              </label>
              <label>
                Negative tags
                <textarea
                  value={negativeTags}
                  onChange={(event) => {
                    setNegativeTags(event.target.value);
                    setActiveSuggestField("negativeTags");
                    void fetchPromptSuggestions(event.target.value);
                  }}
                  onFocus={() => {
                    setActiveSuggestField("negativeTags");
                    void fetchPromptSuggestions(negativeTags);
                  }}
                />
              </label>
              {activeSuggestField === "negativeTags" && activeSuggestions.length > 0 && (
                <div className="suggestion-chips-container" style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', marginTop: '0.2rem', marginBottom: '1rem', background: 'rgba(255, 255, 255, 0.02)', padding: '0.6rem', borderRadius: '8px', border: '1px solid rgba(255, 255, 255, 0.04)' }}>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', marginRight: '0.4rem' }}>
                    💡 Suggestions ({suggestSource === 'local_llm' ? 'LLM' : 'Synonyms'}):
                  </span>
                  {activeSuggestions.map((tag) => (
                    <button
                      key={tag}
                      onClick={() => handleSelectSuggestion(tag)}
                      style={{
                        padding: '0.2rem 0.5rem',
                        fontSize: '0.75rem',
                        background: 'rgba(124, 106, 255, 0.1)',
                        border: '1px solid rgba(124, 106, 255, 0.25)',
                        borderRadius: '4px',
                        color: 'var(--accent-hover)',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        transition: 'all 0.2s'
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.background = 'rgba(124, 106, 255, 0.2)';
                        e.currentTarget.style.boxShadow = '0 0 8px rgba(124, 106, 255, 0.4)';
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.background = 'rgba(124, 106, 255, 0.1)';
                        e.currentTarget.style.boxShadow = 'none';
                      }}
                    >
                      +{tag}
                    </button>
                  ))}
                </div>
              )}
              <button className="primary" onClick={composePrompt}>
                <Wand2 size={16} />
                Compose Prompt
              </button>
              <label>
                Recipe name
                <input value={recipeName} onChange={(event) => setRecipeName(event.target.value)} />
              </label>
              <button onClick={saveRecipe}>
                <Save size={16} />
                Save Recipe
              </button>
            </div>
            <div className="panel output-panel">
              <div className="section-title">Prompt Preview</div>
              <pre>{promptResult?.wildcard_prompt ?? "Compose a prompt to preview either Danbooru tag ordering or SDXL natural-language prose."}</pre>
              {promptResult ? <div className="warning-line">Mode: {promptModeLabels[promptResult.prompt_mode] ?? promptResult.prompt_mode}</div> : null}
              {promptResult?.unresolved_refs.length ? <div className="warning-line">Unresolved refs: {promptResult.unresolved_refs.join(", ")}</div> : null}
              {promptResult ? (
                <button onClick={() => navigator.clipboard.writeText(promptResult.wildcard_prompt)}>
                  <Copy size={16} />
                  Copy
                </button>
              ) : null}
              <div className="section-title">Saved Recipes</div>
              <button onClick={() => api.promptRecipes().then((result) => setRecipes(result.recipes))}>
                <RefreshCw size={16} />
                Refresh Recipes
              </button>
              <div className="mini-list">
                {recipes.slice(0, 12).map((recipe) => (
                  <code key={String(recipe.id)}>{String(recipe.name)} · {String(recipe.preset)}</code>
                ))}
              </div>
            </div>
          </section>
        ) : null}

        {activeTab === "duplicates" ? (
          <section className="panel full-panel">
            <div className="toolbar split">
              <div className="section-title">
                <GitCompare size={16} />
                Duplicate Groups
              </div>
              <button onClick={() => void loadDuplicates()}>
                <RefreshCw size={16} />
                Refresh
              </button>
            </div>
            <div className="duplicate-list">
              {duplicates.length === 0 ? (
                <button className="primary" onClick={() => void loadDuplicates()}>
                  Scan Duplicate Groups
                </button>
              ) : (
                duplicates.map((group, index) => (
                  <article key={`${group.type}-${group.key}-${index}`} className="duplicate-card">
                    <header>
                      <strong>{group.type}</strong>
                      <span>{group.count} matches</span>
                    </header>
                    <code>{group.key.slice(0, 240)}</code>
                    <p>{group.items.slice(0, 8).join(" · ")}</p>
                  </article>
                ))
              )}
            </div>
          </section>
        ) : null}

        {activeTab === "llm" ? (
          <section className="two-column">
            <div className="panel form-panel">
              <label>
                KoboldCpp endpoint
                <input value={llmEndpoint} onChange={(event) => setLlmEndpoint(event.target.value)} placeholder="http://host.docker.internal:5001/v1" />
              </label>
              <label>
                Task
                <select value={llmTask} onChange={(event) => setLlmTask(event.target.value)}>
                  <option value="improve_prompt_order">Improve prompt order</option>
                  <option value="normalize_tags">Normalize tags</option>
                  <option value="split_prose_to_tags">Split prose to tags</option>
                  <option value="improve_sdxl_prompt">Improve SDXL prompt</option>
                  <option value="convert_tags_to_sdxl">Convert tags to SDXL prose</option>
                  <option value="convert_sdxl_to_tags">Convert SDXL prose to tags</option>
                  <option value="suggest_category">Suggest category</option>
                  <option value="detect_duplicates">Detect duplicates</option>
                </select>
              </label>
              <label>
                Prompt profile
                <select value={llmPromptMode} onChange={(event) => setLlmPromptMode(event.target.value as PromptMode)}>
                  <option value="danbooru_tags">NoobAI/Illustrious Danbooru tags</option>
                  <option value="sdxl_natural">SDXL natural language</option>
                </select>
              </label>
              <label>
                Input
                <textarea value={llmText} onChange={(event) => setLlmText(event.target.value)} />
              </label>
              <button className="primary" onClick={runLlm} disabled={busy || !llmText.trim()}>
                {busy ? <Loader2 className="spin" size={16} /> : <Sparkles size={16} />}
                Ask Local LLM
              </button>
              <div className="profile-row">
                <button onClick={testLlm} disabled={busy}>
                  <RefreshCw size={16} />
                  Test
                </button>
                <button onClick={queueLlmJob} disabled={busy || !llmText.trim()}>
                  <Database size={16} />
                  Queue Job
                </button>
                <button onClick={loadLlmJobs}>
                  <RefreshCw size={16} />
                  History
                </button>
                <button onClick={clearLlmContext} disabled={busy || (!llmText && !llmResult)}>
                  <Trash2 size={16} />
                  Clear Context
                </button>
              </div>
            </div>
            <div className="panel output-panel">
              <div className="section-title">Reviewable Suggestion</div>
              <pre>{llmResult?.suggestion || llmResult?.error || "LLM output appears here and never mutates entries automatically."}</pre>
              {llmResult?.suggestion ? (
                <button onClick={() => setEditText(llmResult.suggestion)}>
                  <Save size={16} />
                  Copy to Editor Buffer
                </button>
              ) : null}
              <div className="section-title">Job History</div>
              <div className="mini-list">
                {llmJobs.slice(0, 8).map((job) => (
                  <button
                    key={job.id}
                    className="list-row"
                    onClick={() => {
                      setLlmResult({ ok: job.status === "completed", endpoint_used: job.endpoint_used || job.endpoint, suggestion: job.suggestion, raw: null, error: job.error });
                      if (job.suggestion) setEditText(job.suggestion);
                    }}
                  >
                    <span>#{job.id} {job.task}</span>
                    <strong>{job.status}</strong>
                  </button>
                ))}
              </div>
            </div>
          </section>
        ) : null}

        {activeTab === "export" ? (
          <section className="two-column">
            <div className="panel form-panel">
              <label>
                Format
                <select value={exportFormat} onChange={(event) => setExportFormat(event.target.value)}>
                  <option value="txt_tree">Impact TXT folder tree</option>
                  <option value="sd_yaml">sd-dynamic-prompts YAML</option>
                  <option value="both">TXT tree + YAML</option>
                </select>
              </label>
              <label>
                Prompt mode filter
                <select value={exportPromptMode} onChange={(event) => setExportPromptMode(event.target.value)}>
                  <option value="all">All prompt modes</option>
                  <option value="danbooru_tags">NoobAI/Illustrious tags only</option>
                  <option value="sdxl_natural">SDXL natural language only</option>
                  <option value="mixed">Mixed only</option>
                  <option value="unknown">Unknown only</option>
                </select>
              </label>
              <div className="profile-row">
                <button
                  onClick={() => {
                    setExportPromptMode("danbooru_tags");
                    setExportFormat("txt_tree");
                  }}
                >
                  <Tags size={16} />
                  Danbooru tag pack
                </button>
                <button
                  onClick={() => {
                    setExportPromptMode("sdxl_natural");
                    setExportFormat("sd_yaml");
                  }}
                >
                  <FileSearch size={16} />
                  SDXL prose pack
                </button>
                <button
                  onClick={() => {
                    setExportPromptMode("mixed");
                    setExportFormat("both");
                  }}
                >
                  <GitCompare size={16} />
                  Mixed prompt pack
                </button>
              </div>
              <label>
                Target root
                <input value={exportTarget} onChange={(event) => setExportTarget(event.target.value)} placeholder="Default timestamped exports folder" />
              </label>
              <label className="checkbox-row">
                <input type="checkbox" checked={overwriteExport} onChange={(event) => setOverwriteExport(event.target.checked)} />
                Overwrite changed files
              </label>
              <button onClick={dryRunExport} disabled={busy}>
                <FileSearch size={16} />
                Dry Run
              </button>
              <button className="primary" onClick={runExport} disabled={busy || Boolean(exportPlan?.conflicts.length)}>
                <Download size={16} />
                Write Export
              </button>
            </div>
            <div className="panel output-panel">
              <div className="section-title">Export Plan</div>
              <pre>
                {exportPlan
                  ? JSON.stringify(
                      {
                        target_root: exportPlan.target_root,
                        format: exportPlan.format,
                        prompt_mode: exportPromptMode,
                        created: exportPlan.created.length,
                        changed: exportPlan.changed.length,
                        skipped: exportPlan.skipped.length,
                        conflicts: exportPlan.conflicts.length,
                        unresolved_refs: exportPlan.unresolved_refs.slice(0, 20)
                      },
                      null,
                      2
                    )
                  : "Run a dry-run to inspect planned writes before exporting."}
              </pre>
            </div>
          </section>
        ) : null}

        {activeTab === "images" ? (
          <section className="two-column">
            <div className="panel form-panel">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                <span className="section-title">Image Generation Parameters</span>
                {promptResult?.wildcard_prompt && (
                  <button 
                    onClick={() => setSandboxPrompt(promptResult.wildcard_prompt)}
                    style={{ fontSize: '0.75rem', padding: '0.2rem 0.5rem' }}
                    title="Load composed prompt from Prompt Builder tab"
                  >
                    <Wand2 size={12} />
                    Load from Prompt Builder
                  </button>
                )}
              </div>
              
              <label>
                Positive Prompt
                <textarea 
                  value={sandboxPrompt} 
                  onChange={(e) => setSandboxPrompt(e.target.value)} 
                  placeholder="Paste tags or load from Prompt Builder..."
                  style={{ minHeight: '120px' }}
                />
              </label>

              <label>
                Negative Prompt
                <textarea 
                  value={sandboxNegativePrompt} 
                  onChange={(e) => setSandboxNegativePrompt(e.target.value)} 
                  placeholder="e.g. low quality, blurry..."
                  style={{ minHeight: '60px' }}
                />
              </label>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.75rem' }}>
                <label>
                  Width
                  <select value={sandboxWidth} onChange={(e) => setSandboxWidth(Number(e.target.value))}>
                    <option value={512}>512px</option>
                    <option value={768}>768px</option>
                    <option value={1024}>1024px</option>
                    <option value={1216}>1216px</option>
                  </select>
                </label>

                <label>
                  Height
                  <select value={sandboxHeight} onChange={(e) => setSandboxHeight(Number(e.target.value))}>
                    <option value={512}>512px</option>
                    <option value={768}>768px</option>
                    <option value={1024}>1024px</option>
                    <option value={1216}>1216px</option>
                  </select>
                </label>

                <label>
                  Steps
                  <input type="number" value={sandboxSteps} onChange={(e) => setSandboxSteps(Number(e.target.value))} />
                </label>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.5fr 1fr', gap: '0.75rem' }}>
                <label>
                  CFG Scale
                  <input type="number" step="0.1" value={sandboxCfg} onChange={(e) => setSandboxCfg(Number(e.target.value))} />
                </label>

                <label>
                  Sampler
                  <select value={sandboxSampler} onChange={(e) => setSandboxSampler(e.target.value)}>
                    <option value="Euler a">Euler a</option>
                    <option value="LCM">LCM</option>
                    <option value="RES-Multistep">RES-Multistep</option>
                    <option value="DPM++ 2S a">DPMPP-2S-Ancestral</option>
                    <option value="DPM++ SDE">DPMPP-SDE</option>
                    <option value="DPM++ 2M">DPM++ 2M</option>
                  </select>
                </label>

                <label>
                  Scheduler
                  <select value={sandboxScheduler} onChange={(e) => setSandboxScheduler(e.target.value)}>
                    <option value="Automatic">Automatic</option>
                    <option value="Simple">Simple</option>
                    <option value="Karras">Karras</option>
                    <option value="KL-Optimal">KL-Optimal</option>
                    <option value="Gits">Gits</option>
                    <option value="beta">beta</option>
                  </select>
                </label>
              </div>

              <button 
                className="primary" 
                onClick={generateSandboxImage} 
                disabled={sandboxLoading || !sandboxPrompt.trim()}
                style={{ width: '100%', marginTop: '0.5rem', height: '42px' }}
              >
                {sandboxLoading ? <Loader2 className="spin" size={16} /> : <ImageIcon size={16} />}
                {sandboxLoading ? "Rendering Canvas..." : "Generate Test Image"}
              </button>
            </div>

            <div className="panel" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              <div className="section-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>Active Canvas</span>
                {sandboxImage && (
                  <button onClick={() => {
                    const link = document.createElement('a');
                    link.href = sandboxImage;
                    link.download = `wildcard-${Date.now()}.png`;
                    link.click();
                  }} className="icon-button" title="Download Image" style={{ width: '28px', height: '28px' }}>
                    <Download size={14} />
                  </button>
                )}
              </div>

              {/* Active Canvas Frame */}
              <div style={{ 
                background: 'rgba(0,0,0,0.3)', 
                border: '1px solid var(--border-color)', 
                borderRadius: 'var(--radius-md)', 
                minHeight: '260px', 
                maxHeight: '340px',
                display: 'flex', 
                alignItems: 'center', 
                justifyContent: 'center',
                overflow: 'hidden',
                position: 'relative'
              }}>
                {sandboxLoading ? (
                  <div style={{ textAlign: 'center', color: 'var(--text-secondary)' }}>
                    <Loader2 className="spin" size={32} color="var(--accent)" style={{ marginBottom: '0.5rem' }} />
                    <div style={{ fontSize: '0.85rem' }}>Running diffusion...</div>
                  </div>
                ) : sandboxImage ? (
                  <img src={sandboxImage} style={{ width: '100%', height: '100%', objectFit: 'contain' }} alt="Active Canvas" />
                ) : (
                  <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', textAlign: 'center' }}>
                    <ImageIcon size={32} style={{ opacity: 0.3, marginBottom: '0.5rem' }} />
                    <div>No Image Generated Yet</div>
                  </div>
                )}
              </div>

              {/* Gallery Title */}
              <div className="section-title" style={{ marginTop: '0.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>Generated Gallery</span>
                <button 
                  onClick={() => {
                    setSemanticQuery("");
                    void fetchGeneratedGallery();
                  }} 
                  style={{ padding: '0.15rem 0.4rem', fontSize: '0.7rem' }}
                  disabled={galleryLoading}
                >
                  <RefreshCw size={10} className={galleryLoading ? "spin" : ""} />
                  Refresh Gallery
                </button>
              </div>

              {/* Semantic Search Box */}
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <input 
                  type="text" 
                  value={semanticQuery} 
                  onChange={(e) => setSemanticQuery(e.target.value)} 
                  onKeyDown={(e) => e.key === 'Enter' && void runSemanticSearch()}
                  placeholder="CLIP Semantic Search (e.g. cinematic, vintage)..."
                  style={{ flex: 1, padding: '0.4rem 0.6rem', fontSize: '0.8rem', height: '32px' }}
                />
                <button 
                  onClick={runSemanticSearch}
                  disabled={galleryLoading}
                  style={{ height: '32px', padding: '0 0.8rem', fontSize: '0.8rem' }}
                >
                  <Search size={12} />
                  Search
                </button>
                {semanticQuery && (
                  <button 
                    onClick={() => {
                      setSemanticQuery("");
                      void fetchGeneratedGallery();
                    }}
                    style={{ height: '32px', padding: '0 0.5rem', fontSize: '0.8rem', background: 'rgba(255,255,255,0.05)' }}
                  >
                    Clear
                  </button>
                )}
              </div>

              {/* Gallery Grid */}
              <div className="media-grid">
                {galleryLoading && generatedGallery.length === 0 ? (
                  <div style={{ gridColumn: '1 / -1', textAlign: 'center', padding: '1.5rem', color: 'var(--text-muted)' }}>
                    Loading Gallery...
                  </div>
                ) : generatedGallery.length === 0 ? (
                  <div style={{ gridColumn: '1 / -1', textAlign: 'center', padding: '1.5rem', color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                    Gallery is empty. Generated images will appear here.
                  </div>
                ) : (
                  generatedGallery.map((img) => (
                    <div key={img.name} className="media-card" style={{ cursor: 'pointer' }} onClick={() => setSandboxImage(img.url)}>
                      <img src={img.url} alt={img.name} />
                      <div className="media-card-info">
                        <span title={img.name}>{img.name}</span>
                        <div className="media-card-actions">
                          <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>
                            {formatBytes(img.size)}
                          </span>
                          <button 
                            className="media-card-delete"
                            onClick={(e) => {
                              e.stopPropagation();
                              void deleteGeneratedImage(img.name);
                            }}
                            title="Delete Image"
                          >
                            <Trash2 size={12} />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </section>
        ) : null}



        <section className="management-band">
          <div className="panel form-panel">
            <div className="section-title">Text Management</div>
            <label>
              Cleanup input
              <textarea value={cleanupText} onChange={(event) => setCleanupText(event.target.value)} placeholder="Paste lines, or leave empty to preview the current editor buffer" />
            </label>
            <button onClick={runCleanupPreview}>
              <FileSearch size={16} />
              Preview Cleanup
            </button>
          </div>
          <div className="panel form-panel">
            <div className="section-title">Tags Management</div>
            <label>
              Tag
              <input value={overrideTag} onChange={(event) => setOverrideTag(event.target.value)} placeholder="tag_to_map" />
            </label>
            <label>
              Canonical tag
              <input value={overrideCanonical} onChange={(event) => setOverrideCanonical(event.target.value)} placeholder="canonical_tag" />
            </label>
            <label>
              Category override
              <select value={overrideCategory} onChange={(event) => setOverrideCategory(event.target.value)}>
                {["copyright", "characters", "anatomy", "clothing", "pose", "background", "lighting", "style", "quality", "general"].map((category) => (
                  <option key={category} value={category}>{category}</option>
                ))}
              </select>
            </label>
            <button onClick={saveOverride} disabled={!overrideTag}>
              <Save size={16} />
              Save Override
            </button>
          </div>
          <div className="panel form-panel">
            <div className="section-title">Taxonomy Rules</div>
            <label>
              Category
              <select value={taxonomyCategory} onChange={(event) => changeTaxonomyCategory(event.target.value)}>
                {Object.keys(taxonomy).sort().map((category) => (
                  <option key={category} value={category}>{category}</option>
                ))}
              </select>
            </label>
            <label>
              Keywords
              <textarea value={taxonomyKeywords} onChange={(event) => setTaxonomyKeywords(event.target.value)} />
            </label>
            <div className="profile-row">
              <button onClick={saveTaxonomy} disabled={!taxonomyCategory}>
                <Save size={16} />
                Save Rules
              </button>
              <button onClick={reindexTaxonomy}>
                <Database size={16} />
                Reindex
              </button>
            </div>
          </div>
          <div className="panel output-panel">
            <div className="section-title">Management Preview</div>
            <pre>{JSON.stringify({ cleanup: cleanupResult, tag_overrides: tagOverrides.slice(0, 8), taxonomy: { [taxonomyCategory]: taxonomy[taxonomyCategory] ?? [] } }, null, 2)}</pre>
            <button onClick={() => api.tagOverrides().then((result) => setTagOverrides(result.overrides))}>
              <RefreshCw size={16} />
              Refresh Overrides
            </button>
          </div>
        </section>
      </section>
    </div>
    </div>
  );
}
