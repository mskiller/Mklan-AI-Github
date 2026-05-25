import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { VirtuosoGrid } from "react-virtuoso";
import { useNavigate } from "react-router-dom";
import {
  Archive,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Database,
  Download,
  EyeOff,
  Filter,
  GitCompare,
  Images,
  Layers,
  ListChecks,
  Loader2,
  Maximize2,
  PanelLeft,
  RefreshCw,
  Search,
  Server,
  SlidersHorizontal,
  Sparkles,
  Tags,
  Trash2,
  Upload,
  UploadCloud,
  X,
  Keyboard,
  FolderOpen,
  Plus,
  Save
} from "lucide-react";
import { DeepZoomViewer } from "../components/DeepZoomViewer";
import { MetadataInspector } from "../components/MetadataInspector";
import { CompareWorkspace } from "../components/CompareWorkspace";
import { useDeviceMode } from "../hooks/useDeviceMode";
import { useUiPreferences } from "../hooks/useUiPreferences";

interface GalleryMeta {
  prompt?: string;
  processed_prompt?: string;
  raw_prompt?: string;
  negative_prompt?: string;
  processed_negative_prompt?: string;
  raw_negative_prompt?: string;
  steps?: number;
  cfg_scale?: number;
  sampler_name?: string;
  scheduler?: string;
  width?: number;
  height?: number;
  generator?: string;
  checkpoint?: string;
  seed?: number;
  prompt_tags?: string[];
  prompt_tag_string?: string;
  nsfw_detected?: boolean;
  nsfw_model_detected?: boolean;
  nsfw_prompt_flagged?: boolean;
  nsfw_score?: number | null;
  nsfw_label?: string | null;
  safety_quality_scanned_at?: string | null;
  quality_scanned_at?: string | null;
  quality_warnings?: string[];
  vision_llm_analysis?: string;
  vision_llm_source?: string;
  vision_llm_updated_at?: string;
  [key: string]: unknown;
}

interface GalleryImage {
  id?: string;
  name: string;
  size: number;
  created_at: number;
  url: string;
  fullUrl?: string;
  metadata: GalleryMeta;
  origin: "generated" | "mounted";
  media_type?: "image" | "video" | "unknown" | null;
  source_id?: string;
  source_name?: string;
  relative_path?: string;
  index_state?: SourceBrowseEntry["index_state"];
  tags?: string[];
  prompt_tags?: string[];
  workflow_export_available?: boolean;
  caption?: string | null;
  ocr_text?: string | null;
}

interface MediaCollection {
  id: string;
  name: string;
  asset_count: number;
}

interface MediaSource {
  id: string;
  name: string;
  display_root_path: string;
  status: string;
  last_scan_at: string | null;
}

interface SourceBreadcrumb {
  label: string;
  path: string;
}

interface SourceBrowseEntry {
  name: string;
  relative_path: string;
  entry_type: "directory" | "file";
  media_type: "image" | "video" | "unknown" | null;
  mime_type: string | null;
  size_bytes: number | null;
  modified_at: string | null;
  indexed_asset_id: string | null;
  index_state: "indexed" | "metadata_refresh_pending" | "processing" | "live_browse" | null;
  preview_url: string | null;
  content_url: string | null;
}

interface SourceBrowseResponse {
  source_id: string;
  current_path: string;
  parent_path: string | null;
  breadcrumbs: SourceBreadcrumb[];
  entries: SourceBrowseEntry[];
}

interface SourceTreeResponse {
  path: string;
  dirs: string[];
  files: Array<{
    name: string;
    relative_path: string;
    indexed: boolean;
  }>;
}

interface ScanJob {
  id: string;
  source_id: string | null;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  scan_mode?: ScanMode;
  target_type?: "source" | "collection" | "assets" | string;
  collection_id?: string | null;
  asset_ids_json?: string[] | null;
  path_filter?: string | null;
  progress: number;
  total_count?: number | null;
  stage?: string | null;
  scanned_count: number;
  new_count: number;
  updated_count: number;
  deleted_count: number;
  error_count: number;
  message: string | null;
  started_at: string | null;
  finished_at: string | null;
  worker_heartbeat_at?: string | null;
  created_at: string;
}

interface ScanJobErrorEntry {
  id?: string | null;
  relative_path?: string | null;
  path?: string | null;
  stage?: string | null;
  error: string;
  created_at?: string | null;
  at?: string | null;
}

interface LiveScanProgress {
  status: ScanJob["status"];
  processed: number;
  progressPercent: number;
  totalCount?: number | null;
  stage?: string | null;
  message: string | null;
  newCount: number;
  updatedCount: number;
  deletedCount?: number;
  errorCount: number;
}

type ScanMode =
  | "basic"
  | "metadata"
  | "ai"
  | "workflow"
  | "preview"
  | "similarity"
  | "caption"
  | "ocr"
  | "tags"
  | "safety_quality"
  | "faces"
  | "video_intel"
  | "vision_llm"
  | "sillytavern_card";
type ScanTargetKind = "source" | "collection" | "selected" | "focused";
type GalleryTab = "browse" | "sources" | "metadata" | "collections" | "jobs" | "tools";
type GalleryTabGroup = "Explore" | "Organize" | "Operations";
type SortMode = "relevance" | "modified_at" | "created_at" | "filename";
type QuickFilter = "all" | "has_prompt" | "has_workflow";

const SCAN_MODE_OPTIONS: Array<{ value: ScanMode; label: string; detail: string }> = [
  { value: "basic", label: "Basic", detail: "Inventory files and stat changes" },
  { value: "metadata", label: "Metadata", detail: "EXIF/IPTC/XMP, prompts, ComfyUI/A1111, ffprobe" },
  { value: "workflow", label: "Workflow", detail: "Generation prompt/workflow metadata only" },
  { value: "preview", label: "Preview", detail: "Thumbnails, blurhash, waveform, keyframes" },
  { value: "similarity", label: "Similarity", detail: "pHash, CLIP embedding, duplicate links" },
  { value: "caption", label: "Caption", detail: "Local BLIP caption enrichment" },
  { value: "ocr", label: "OCR", detail: "Readable text extraction" },
  { value: "tags", label: "Tags", detail: "WD/CLIP tag suggestions" },
  { value: "safety_quality", label: "Safety / Quality", detail: "NSFW and blur/resolution checks" },
  { value: "faces", label: "Faces", detail: "Face detection and people refresh" },
  { value: "video_intel", label: "Video", detail: "Video metadata, waveform, keyframes" },
  { value: "vision_llm", label: "Vision LLM", detail: "KoboldCpp/OpenAI-compatible analysis" },
  { value: "sillytavern_card", label: "SillyTavern Card", detail: "Parse embedded character-card JSON from PNG/WebP cards" },
  { value: "ai", label: "Full AI", detail: "Full local enrichment preset" },
];

const SCAN_MODE_LABELS = Object.fromEntries(SCAN_MODE_OPTIONS.map((item) => [item.value, item.label])) as Record<ScanMode, string>;
const SINGLE_IMAGE_SCAN_MODES: ScanMode[] = ["basic", "metadata", "workflow", "preview", "similarity", "caption", "ocr", "tags", "safety_quality", "faces", "vision_llm", "sillytavern_card", "ai"];

interface GalleryViewPrefs {
  hideNsfw: boolean;
  indexedOnly: boolean;
}

type GalleryClientFilters = GalleryViewPrefs;

interface ConnectorHealthItem {
  label: string;
  status: "ok" | "warn" | "error" | "checking";
  detail: string;
  endpoint?: string;
}

const i18n = {
  en: {
    title: "Media Explorer & Comparer",
    subtitle: "items mapped · read-only indexing for mounted folders",
    shortcuts: "Shortcuts",
    searchAssets: "Search indexed assets...",
    refresh: "Refresh",
    uploadImages: "Upload Images",
    uploadFolder: "Upload Folder",
    allAssets: "All Assets",
    indexedSources: "Indexed Sources",
    collections: "Collections",
    scanBasic: "Basic Index",
    scanMetadata: "Scan Metadata",
    scanAi: "CLIP / AI Scan",
    library: "Library",
    filters: "Filters",
    scanCenter: "Scan Center",
    loadMore: "Load More",
    openDetails: "Open image details",
    addSelection: "Add to selection",
    removeSelection: "Remove from selection",
    addCollection: "Add to collection",
    addNsfw: "Add NSFW tag",
    basicIndexFile: "Basic index this file",
    visionLlmScan: "Scan with Vision LLM (KoboldCpp)",
    copyPromptTags: "Copy prompt tags",
    exportWorkflow: "Export workflow JSON",
    sendWildcards: "Send to Wildcards",
    openOriginal: "Open original image",
    viewControls: "View Controls",
    hideNsfw: "Hide NSFW",
    liveIndexed: "Live + Indexed",
    indexedOnly: "Indexed only",
    pageSize: "Page size",
    chooseCollection: "Add to Collection...",
    selectedCount: "selected",
    bulkAddTag: "Bulk Add Tag",
    addNsfwSelected: "Mark NSFW",
    clearSelection: "Clear Selection",
    compareSelected: "Compare Selected",
  },
  fr: {
    title: "Galerie et comparateur",
    subtitle: "elements indexes · indexation en lecture seule",
    shortcuts: "Raccourcis",
    searchAssets: "Rechercher dans la galerie...",
    refresh: "Rafraichir",
    uploadImages: "Importer images",
    uploadFolder: "Importer dossier",
    allAssets: "Tous les assets",
    indexedSources: "Sources indexees",
    collections: "Collections",
    scanBasic: "Index simple",
    scanMetadata: "Scan metadata",
    scanAi: "Scan CLIP / IA",
    library: "Bibliotheque",
    filters: "Filtres",
    scanCenter: "Centre de scan",
    loadMore: "Charger plus",
    openDetails: "Ouvrir les details",
    addSelection: "Ajouter a la selection",
    removeSelection: "Retirer de la selection",
    addCollection: "Ajouter a une collection",
    addNsfw: "Ajouter tag NSFW",
    basicIndexFile: "Indexer ce fichier",
    visionLlmScan: "Scanner avec Vision LLM (KoboldCpp)",
    copyPromptTags: "Copier les tags du prompt",
    exportWorkflow: "Exporter le workflow JSON",
    sendWildcards: "Envoyer vers Wildcards",
    openOriginal: "Ouvrir l'image originale",
    viewControls: "Controles de vue",
    hideNsfw: "Masquer NSFW",
    liveIndexed: "Live + Indexe",
    indexedOnly: "Indexe seulement",
    pageSize: "Taille page",
    chooseCollection: "Ajouter a une collection...",
    selectedCount: "selectionnes",
    bulkAddTag: "Taguer en masse",
    addNsfwSelected: "Marquer NSFW",
    clearSelection: "Vider selection",
    compareSelected: "Comparer selection",
  },
} as const;

interface TagCount {
  tag: string;
  count: number;
}

interface MetadataFilters {
  media_type: "" | "image" | "video";
  manual: string;
  characters: string;
  clothes: string;
  location: string;
  position: string;
  camera_make: string;
  camera_model: string;
  year: string;
  width_min: string;
  width_max: string;
  height_min: string;
  height_max: string;
  has_gps: boolean;
  tags: string;
}

const getSelectionKey = (image: GalleryImage) => image.id || image.url;
const GENERATED_SOURCE_NAME = "Generated Media";
const DEFAULT_METADATA_FILTERS: MetadataFilters = {
  media_type: "",
  manual: "",
  characters: "",
  clothes: "",
  location: "",
  position: "",
  camera_make: "",
  camera_model: "",
  year: "",
  width_min: "",
  width_max: "",
  height_min: "",
  height_max: "",
  has_gps: false,
  tags: "",
};

const GALLERY_VIEW_PREFS_KEY = "mklan-studio.gallery.view-prefs.v1";
const DEFAULT_GALLERY_VIEW_PREFS: GalleryViewPrefs = {
  hideNsfw: false,
  indexedOnly: false,
};
const NSFW_TAGS = new Set(["nsfw", "adult", "explicit", "rating:e", "rating:q", "rating:explicit", "rating:questionable"]);
const NSFW_PATH_PATTERN = /(^|[\\/\s._-])nsfw($|[\\/\s._-])/i;
const SORT_MODE_LABELS: Record<SortMode, string> = {
  relevance: "Relevance",
  modified_at: "Modified",
  created_at: "Created",
  filename: "Name",
};
const QUICK_FILTER_LABELS: Record<QuickFilter, string> = {
  all: "All",
  has_prompt: "Has Prompt",
  has_workflow: "Has Workflow",
};

const galleryTabs: Array<{ id: GalleryTab; label: string; icon: React.ComponentType<{ size?: number }>; group: GalleryTabGroup }> = [
  { id: "browse", label: "Browse", icon: Images, group: "Explore" },
  { id: "metadata", label: "Metadata Search", icon: Search, group: "Explore" },
  { id: "collections", label: "Collections", icon: Archive, group: "Organize" },
  { id: "sources", label: "Sources & Scan", icon: Database, group: "Operations" },
  { id: "jobs", label: "Scan Jobs", icon: Clock, group: "Operations" },
  { id: "tools", label: "Generation Tools", icon: Sparkles, group: "Operations" },
];

const galleryTabGroups: GalleryTabGroup[] = ["Explore", "Organize", "Operations"];

function readGalleryViewPrefs(): GalleryViewPrefs {
  if (typeof window === "undefined") return DEFAULT_GALLERY_VIEW_PREFS;
  try {
    const raw = window.localStorage.getItem(GALLERY_VIEW_PREFS_KEY);
    if (!raw) return DEFAULT_GALLERY_VIEW_PREFS;
    const parsed = JSON.parse(raw) as Partial<GalleryViewPrefs>;
    return {
      hideNsfw: parsed.hideNsfw === true,
      indexedOnly: parsed.indexedOnly === true,
    };
  } catch {
    return DEFAULT_GALLERY_VIEW_PREFS;
  }
}

function writeGalleryViewPrefs(prefs: GalleryViewPrefs) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(GALLERY_VIEW_PREFS_KEY, JSON.stringify(prefs));
}

function normalizeTagValue(value: string) {
  return value.trim().toLowerCase().replace(/\s+/g, "_");
}

function splitTagFilterValue(value: string) {
  return value
    .split(/[,;|]+/)
    .map((item) => normalizeTagValue(item))
    .filter(Boolean);
}

function mergeUniqueTags(...values: Array<string | null | undefined>) {
  return Array.from(new Set(values.flatMap((value) => splitTagFilterValue(value || ""))));
}

function splitTagString(value: unknown) {
  if (typeof value !== "string") return [];
  return value.split(/[,;|]+/).map((item) => item.trim()).filter(Boolean);
}

function isNsfwImage(image: GalleryImage) {
  const metadata = image.metadata || {};
  if (metadata.nsfw_detected === true) {
    return true;
  }
  const tagValues = [
    ...(image.tags || []),
    ...(image.prompt_tags || []),
    ...((Array.isArray(metadata.prompt_tags) ? metadata.prompt_tags : []) as string[]),
    ...splitTagString(metadata.prompt_tag_string),
  ];
  if (tagValues.some((tag) => NSFW_TAGS.has(normalizeTagValue(tag)))) {
    return true;
  }
  return [image.name, image.relative_path].some((value) => typeof value === "string" && NSFW_PATH_PATTERN.test(value));
}

function isIndexedImage(image: GalleryImage) {
  return Boolean(image.id && image.index_state !== "live_browse");
}

function getSourceMergeKey(image: GalleryImage) {
  if (image.id) return `id:${image.id}`;
  if (image.source_id && image.relative_path) return `source:${image.source_id}:${image.relative_path}`;
  return `url:${image.url}`;
}

function galleryImageSignature(image: GalleryImage) {
  const metadata = image.metadata || {};
  return [
    getSourceMergeKey(image),
    image.url,
    image.fullUrl || "",
    image.name,
    image.index_state || "",
    metadata.prompt || "",
    metadata.processed_prompt || "",
    metadata.prompt_tag_string || "",
    (image.tags || []).join("|"),
    (image.prompt_tags || []).join("|"),
    image.workflow_export_available ? "workflow" : "",
  ].join("\u001f");
}

function reconcileGalleryImages(current: GalleryImage[], next: GalleryImage[]) {
  const currentByKey = new Map(current.map((image) => [getSourceMergeKey(image), image]));
  let changed = current.length !== next.length;
  const reconciled = next.map((image, index) => {
    const previous = currentByKey.get(getSourceMergeKey(image));
    if (previous && galleryImageSignature(previous) === galleryImageSignature(image)) {
      if (current[index] !== previous) changed = true;
      return previous;
    }
    changed = true;
    return image;
  });
  return changed ? reconciled : current;
}

function mergeGalleryImages(indexedImages: GalleryImage[], liveImages: GalleryImage[]) {
  const merged: GalleryImage[] = [];
  const seen = new Set<string>();
  for (const image of [...indexedImages, ...liveImages]) {
    const key = getSourceMergeKey(image);
    if (seen.has(key)) continue;
    seen.add(key);
    merged.push(image);
  }
  return merged;
}

function metadataFromItem(item: any): GalleryMeta {
  const normalized = item.normalized_metadata && typeof item.normalized_metadata === "object" ? item.normalized_metadata : {};
  const displayPrompt = normalized.processed_prompt || normalized.prompt || item.prompt_excerpt || item.prompt || "";
  const displayNegativePrompt = normalized.processed_negative_prompt || normalized.negative_prompt || item.negative_prompt || "";
  return {
    ...normalized,
    prompt: displayPrompt,
    processed_prompt: normalized.processed_prompt || displayPrompt,
    raw_prompt: normalized.raw_prompt,
    negative_prompt: displayNegativePrompt,
    processed_negative_prompt: normalized.processed_negative_prompt || displayNegativePrompt,
    raw_negative_prompt: normalized.raw_negative_prompt,
    width: normalized.width ?? item.width,
    height: normalized.height ?? item.height,
    generator: normalized.generator ?? item.generator,
    prompt_tags: normalized.prompt_tags ?? item.prompt_tags,
    prompt_tag_string: normalized.prompt_tag_string ?? item.prompt_tag_string,
  };
}

function mapIndexedItem(item: any): GalleryImage {
  const metadata = metadataFromItem(item);
  const mediaType = item.media_type || metadata.media_type || "image";
  const contentUrl = item.content_url ? `/api/media${item.content_url}` : undefined;
  const previewUrl = item.preview_url ? `/api/media${item.preview_url}` : undefined;
  const imageUrl = item.id ? `/api/media/assets/${item.id}/image?w=1024` : previewUrl || contentUrl || "";
  const fullImageUrl = item.id ? `/api/media/assets/${item.id}/image?w=2048` : contentUrl;
  return {
    name: item.filename,
    size: item.size_bytes ?? 0,
    created_at: new Date(item.modified_at || item.created_at || Date.now()).getTime(),
    url: mediaType === "video" ? previewUrl || contentUrl || "" : imageUrl,
    fullUrl: mediaType === "video" ? contentUrl || previewUrl : fullImageUrl,
    metadata,
    id: item.id,
    origin: item.source_name === GENERATED_SOURCE_NAME ? "generated" : "mounted",
    media_type: mediaType,
    source_id: item.source_id,
    source_name: item.source_name,
    relative_path: item.relative_path,
    tags: item.tags || [],
    prompt_tags: metadata.prompt_tags || item.prompt_tags || [],
    workflow_export_available: Boolean(item.workflow_export_available),
    caption: item.caption ?? null,
    ocr_text: item.ocr_text ?? null,
  };
}

function filterImagesClientSide(
  images: GalleryImage[],
  query: string,
  quickFilter: QuickFilter,
  tagFilter: string | null,
  clientFilters: GalleryClientFilters = DEFAULT_GALLERY_VIEW_PREFS,
) {
  const normalizedQuery = query.toLowerCase().trim();
  return images.filter((image) => {
    const metadata = image.metadata || {};
    if (clientFilters.hideNsfw && isNsfwImage(image)) {
      return false;
    }
    if (clientFilters.indexedOnly && !isIndexedImage(image)) {
      return false;
    }
    if (quickFilter === "has_prompt" && !metadata.prompt) {
      return false;
    }
    if (quickFilter === "has_workflow" && !image.workflow_export_available) {
      return false;
    }
    if (tagFilter) {
      const tags = [...(image.tags || []), ...(image.prompt_tags || [])].map(normalizeTagValue);
      if (!tags.includes(normalizeTagValue(tagFilter))) {
        return false;
      }
    }
    if (!normalizedQuery) {
      return true;
    }
    return (
      image.name.toLowerCase().includes(normalizedQuery) ||
      (metadata.prompt || "").toLowerCase().includes(normalizedQuery) ||
      (image.relative_path || "").toLowerCase().includes(normalizedQuery) ||
      (image.source_name || "").toLowerCase().includes(normalizedQuery) ||
      (image.caption || "").toLowerCase().includes(normalizedQuery) ||
      (image.ocr_text || "").toLowerCase().includes(normalizedQuery)
    );
  });
}

interface SourceTreeNode {
  name: string;
  path: string;
  depth: number;
  expanded: boolean;
  loaded: boolean;
  children: SourceTreeNode[];
}

function findActiveSourceScanJob(sourceId: string, sourceStatus: string, jobs: ScanJob[]) {
  return (
    jobs.find(
      (job) =>
        job.source_id === sourceId &&
        (job.status === "queued" ||
          job.status === "running" ||
          (job.status === "cancelled" && sourceStatus === "scanning")),
    ) ?? null
  );
}

function makeSourceTreeNode(name: string, path: string, depth: number): SourceTreeNode {
  return { name, path, depth, expanded: false, loaded: false, children: [] };
}

function buildSourceTreeRoot(tree: SourceTreeResponse): SourceTreeNode {
  const root = makeSourceTreeNode("Root", "", 0);
  root.loaded = true;
  root.expanded = true;
  root.children = tree.dirs.map((dir) => makeSourceTreeNode(dir, dir, 1));
  return root;
}

function insertSourceTreeChildren(node: SourceTreeNode, targetPath: string, dirs: string[]): SourceTreeNode {
  if (node.path === targetPath) {
    return {
      ...node,
      loaded: true,
      expanded: true,
      children: dirs.map((dir) => {
        const childPath = targetPath ? `${targetPath}/${dir}` : dir;
        return makeSourceTreeNode(dir, childPath, node.depth + 1);
      }),
    };
  }
  return {
    ...node,
    children: node.children.map((child) => insertSourceTreeChildren(child, targetPath, dirs)),
  };
}

function toggleSourceTreeNode(node: SourceTreeNode, targetPath: string): SourceTreeNode {
  if (node.path === targetPath) {
    return { ...node, expanded: !node.expanded };
  }
  return {
    ...node,
    children: node.children.map((child) => toggleSourceTreeNode(child, targetPath)),
  };
}

function flattenSourceTree(node: SourceTreeNode, output: SourceTreeNode[] = []): SourceTreeNode[] {
  output.push(node);
  if (node.expanded) {
    node.children.forEach((child) => flattenSourceTree(child, output));
  }
  return output;
}

export function GalleryPage() {
  const navigate = useNavigate();
  const deviceMode = useDeviceMode();
  const { language } = useUiPreferences();
  const copy = i18n[language];
  const isMobile = deviceMode === "mobile";
  const [images, setImages] = useState<GalleryImage[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [assetPage, setAssetPage] = useState(1);
  const [assetTotal, setAssetTotal] = useState<number | null>(null);
  const [assetPageSize, setAssetPageSize] = useState(60);
  const [mobileLibraryOpen, setMobileLibraryOpen] = useState(false);
  const [mobileScanOpen, setMobileScanOpen] = useState(false);
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false);
  const [galleryViewPrefs, setGalleryViewPrefs] = useState<GalleryViewPrefs>(() => readGalleryViewPrefs());
  const clientFilters = useMemo<GalleryClientFilters>(
    () => ({
      hideNsfw: galleryViewPrefs.hideNsfw,
      indexedOnly: galleryViewPrefs.indexedOnly,
    }),
    [galleryViewPrefs.hideNsfw, galleryViewPrefs.indexedOnly],
  );

  // Zoom Overlay
  const [zoomImg, setZoomImg] = useState<GalleryImage | null>(null);

  // Keyboard Help Toggle
  const [showKeyboardHelp, setShowKeyboardHelp] = useState(false);

  // Selection & Comparer
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [comparerOpen, setComparerOpen] = useState(false);

  // Collections State
  const [collections, setCollections] = useState<MediaCollection[]>([]);
  const [activeCollectionId, setActiveCollectionId] = useState<string | null>(null);
  const [datasetImportingCollectionId, setDatasetImportingCollectionId] = useState<string | null>(null);
  const [sources, setSources] = useState<MediaSource[]>([]);
  const [activeSourceId, setActiveSourceId] = useState<string | null>(null);
  const [sourceName, setSourceName] = useState("");
  const [sourcePath, setSourcePath] = useState("");
  const [sourceSubmitting, setSourceSubmitting] = useState(false);
  const [sourceMessage, setSourceMessage] = useState<{ tone: "success" | "error" | "info"; text: string } | null>(null);
  const [activeSource, setActiveSource] = useState<MediaSource | null>(null);
  const [sourceBrowse, setSourceBrowse] = useState<SourceBrowseResponse | null>(null);
  const [sourceTree, setSourceTree] = useState<SourceTreeNode | null>(null);
  const [currentSourcePath, setCurrentSourcePath] = useState("");
  const [activeScanJob, setActiveScanJob] = useState<ScanJob | null>(null);
  const [scanProgress, setScanProgress] = useState<LiveScanProgress | null>(null);
  const [scanJobs, setScanJobs] = useState<ScanJob[]>([]);
  const [scanJobErrors, setScanJobErrors] = useState<Record<string, ScanJobErrorEntry[]>>({});
  const [expandedScanJobId, setExpandedScanJobId] = useState<string | null>(null);
  const [topTags, setTopTags] = useState<TagCount[]>([]);
  const [activeTab, setActiveTab] = useState<GalleryTab>("browse");
  const [sortMode, setSortMode] = useState<SortMode>("relevance");
  const [quickFilter, setQuickFilter] = useState<QuickFilter>("all");
  const [activeTagFilter, setActiveTagFilter] = useState<string | null>(null);
  const [metadataFilters, setMetadataFilters] = useState<MetadataFilters>(DEFAULT_METADATA_FILTERS);
  const [naturalQuery, setNaturalQuery] = useState("");
  const [toolsMessage, setToolsMessage] = useState<string | null>(null);
  const [scanTargetSourceId, setScanTargetSourceId] = useState("");
  const [scanPathFilter, setScanPathFilter] = useState("");
  const [scanTargetKind, setScanTargetKind] = useState<ScanTargetKind>("source");
  const [scanTargetCollectionId, setScanTargetCollectionId] = useState("");
  const [scanModeSelection, setScanModeSelection] = useState<ScanMode>("metadata");
  const [scanCommandBusy, setScanCommandBusy] = useState<ScanMode | null>(null);
  const [connectorHealth, setConnectorHealth] = useState<ConnectorHealthItem[]>([]);
  const [connectorChecking, setConnectorChecking] = useState(false);
  const [contextMenu, setContextMenu] = useState<{ image: GalleryImage; x: number; y: number } | null>(null);
  const longPressTimer = useRef<number | null>(null);
  const longPressTriggered = useRef(false);

  useEffect(() => {
    writeGalleryViewPrefs(galleryViewPrefs);
  }, [galleryViewPrefs]);

  const updateGalleryViewPrefs = useCallback((patch: Partial<GalleryViewPrefs>) => {
    setGalleryViewPrefs((current) => ({ ...current, ...patch }));
  }, []);

  const updateImages = useCallback((nextImages: GalleryImage[]) => {
    setImages((current) => reconcileGalleryImages(current, nextImages));
  }, []);

  const fetchCollections = useCallback(async () => {
    try {
      const r = await fetch("/api/media/collections");
      if (r.ok) {
        setCollections(await r.json());
      }
    } catch (e) {
      console.error("Failed to fetch collections", e);
    }
  }, []);

  const fetchSources = useCallback(async () => {
    try {
      const r = await fetch("/api/media/sources");
      if (r.ok) {
        setSources(await r.json());
      }
    } catch (e) {
      console.error("Failed to fetch sources", e);
    }
  }, []);

  const fetchScanJobs = useCallback(async () => {
    try {
      const r = await fetch("/api/media/scan-jobs");
      if (r.ok) {
        setScanJobs(await r.json());
      }
    } catch (e) {
      console.error("Failed to fetch scan jobs", e);
    }
  }, []);

  const fetchTopTags = useCallback(async () => {
    try {
      const r = await fetch("/api/media/tags");
      if (r.ok) {
        setTopTags((await r.json()).slice(0, 24));
      }
    } catch (e) {
      console.error("Failed to fetch tags", e);
    }
  }, []);

  useEffect(() => {
    void fetchCollections();
    void fetchSources();
    void fetchScanJobs();
    void fetchTopTags();
  }, [fetchCollections, fetchSources, fetchScanJobs, fetchTopTags]);

  useEffect(() => {
    if (!contextMenu) return;
    const close = (event: PointerEvent) => {
      if ((event.target as Element).closest?.(".mklan-gallery-context-menu")) return;
      setContextMenu(null);
    };
    const onEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setContextMenu(null);
    };
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", onEscape);
    return () => {
      document.removeEventListener("pointerdown", close);
      document.removeEventListener("keydown", onEscape);
    };
  }, [contextMenu]);

  // Upload mechanics
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const folderRef = useRef<HTMLInputElement>(null);

  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    if (activeSourceId && !sources.some((source) => source.id === activeSourceId)) {
      setActiveSourceId(null);
    }
  }, [activeSourceId, sources]);

  useEffect(() => {
    if (activeSourceId) {
      setScanTargetSourceId(activeSourceId);
      return;
    }
    if (!scanTargetSourceId && sources[0]) {
      setScanTargetSourceId(sources[0].id);
    }
  }, [activeSourceId, scanTargetSourceId, sources]);

  useEffect(() => {
    setCurrentSourcePath("");
    setSelectedKeys([]);
  }, [activeSourceId]);

  useEffect(() => {
    if (!activeSourceId) {
      setSourceTree(null);
      return;
    }

    const loadTree = async () => {
      try {
        const response = await fetch(`/api/media/sources/${encodeURIComponent(activeSourceId)}/tree`);
        if (!response.ok) {
          return;
        }
        const tree = (await response.json()) as SourceTreeResponse;
        setSourceTree(buildSourceTreeRoot(tree));
      } catch (error) {
        console.error("Failed to fetch source tree", error);
      }
    };

    void loadTree();
  }, [activeSourceId]);

  const buildAssetParams = useCallback((page = 1) => {
    const params = new URLSearchParams({ page: String(page), page_size: String(assetPageSize), sort: sortMode });
    if (activeSourceId && !activeCollectionId) {
      params.set("source_id", activeSourceId);
    }
    const textQuery = [
      searchQuery,
      metadataFilters.manual,
      metadataFilters.characters,
      metadataFilters.clothes,
      metadataFilters.location,
      metadataFilters.position,
    ].map((value) => value.trim()).filter(Boolean).join(" ");
    if (textQuery) {
      params.set("q", textQuery);
    }
    if (metadataFilters.media_type) {
      params.set("media_type", metadataFilters.media_type);
    } else {
      params.set("media_type", "image");
    }
    if (metadataFilters.camera_make.trim()) {
      params.set("camera_make", metadataFilters.camera_make.trim());
    }
    if (metadataFilters.camera_model.trim()) {
      params.set("camera_model", metadataFilters.camera_model.trim());
    }
    if (metadataFilters.year.trim()) {
      params.set("year", metadataFilters.year.trim());
    }
    if (metadataFilters.width_min.trim()) {
      params.set("width_min", metadataFilters.width_min.trim());
    }
    if (metadataFilters.width_max.trim()) {
      params.set("width_max", metadataFilters.width_max.trim());
    }
    if (metadataFilters.height_min.trim()) {
      params.set("height_min", metadataFilters.height_min.trim());
    }
    if (metadataFilters.height_max.trim()) {
      params.set("height_max", metadataFilters.height_max.trim());
    }
    if (metadataFilters.has_gps) {
      params.set("has_gps", "true");
    }
    if (clientFilters.hideNsfw) {
      params.set("exclude_tags", "nsfw");
    }
    const mergedTags = mergeUniqueTags(metadataFilters.tags, activeTagFilter);
    if (mergedTags.length) {
      params.set("tags", mergedTags.join(","));
    }
    return params;
  }, [activeCollectionId, activeSourceId, activeTagFilter, assetPageSize, clientFilters.hideNsfw, metadataFilters, searchQuery, sortMode]);

  const fetchImages = useCallback(async (options?: { background?: boolean }) => {
    const showLoading = options?.background !== true;
    if (showLoading) {
      setLoading(true);
    }
    try {
      if (activeTab === "metadata" && !activeCollectionId) {
        setSourceBrowse(null);
        setActiveScanJob(null);
        setScanProgress(null);
        setAssetPage(1);
        const [assetsRes, jobsRes] = await Promise.all([
          fetch(`/api/media/assets?${buildAssetParams(1).toString()}`),
          fetch("/api/media/scan-jobs"),
        ]);
        if (jobsRes.ok) {
          setScanJobs(await jobsRes.json());
        }
        if (assetsRes.ok) {
          const data = await assetsRes.json();
          updateImages(filterImagesClientSide((data.items || []).map(mapIndexedItem), "", quickFilter, null, clientFilters));
          setAssetTotal(typeof data.total === "number" ? data.total : null);
        }
      } else if (activeCollectionId) {
        setActiveSource(null);
        setSourceBrowse(null);
        setAssetTotal(null);
        const [collectionRes, jobsRes] = await Promise.all([
          fetch(`/api/media/collections/${activeCollectionId}?page_size=100`),
          fetch("/api/media/scan-jobs"),
        ]);
        if (jobsRes.ok) {
          const jobs = (await jobsRes.json()) as ScanJob[];
          setScanJobs(jobs);
          const activeJob = jobs.find((job) => job.target_type === "collection" && job.collection_id === activeCollectionId && (job.status === "queued" || job.status === "running")) || null;
          setActiveScanJob(activeJob);
          if (!activeJob) setScanProgress(null);
        }
        if (collectionRes.ok) {
          const d = await collectionRes.json();
          updateImages(filterImagesClientSide((d.items || []).map(mapIndexedItem), searchQuery, quickFilter, activeTagFilter, clientFilters));
        }
      } else if (activeSourceId) {
        const browseQuery = currentSourcePath ? `?path=${encodeURIComponent(currentSourcePath)}` : "";
        const [sourceRes, browseRes, jobsRes] = await Promise.all([
          fetch(`/api/media/sources/${encodeURIComponent(activeSourceId)}`),
          fetch(`/api/media/sources/${encodeURIComponent(activeSourceId)}/browse${browseQuery}`),
          fetch("/api/media/scan-jobs"),
        ]);
        if (sourceRes.ok && browseRes.ok && jobsRes.ok) {
          const nextSource = (await sourceRes.json()) as MediaSource;
          const nextBrowse = (await browseRes.json()) as SourceBrowseResponse;
          const jobs = (await jobsRes.json()) as ScanJob[];
          setScanJobs(jobs);
          setActiveSource(nextSource);
          setSources((current) => current.map((source) => (source.id === nextSource.id ? nextSource : source)));
          setSourceBrowse(nextBrowse);
          const activeJob = findActiveSourceScanJob(nextSource.id, nextSource.status, jobs);
          setActiveScanJob(activeJob);
          if (!activeJob) {
            setScanProgress(null);
          }
          const liveMapped = nextBrowse.entries
            .filter((entry) => entry.entry_type === "file" && entry.media_type === "image")
            .map((entry): GalleryImage => ({
              name: entry.name,
              size: entry.size_bytes ?? 0,
              created_at: entry.modified_at ? new Date(entry.modified_at).getTime() : Date.now(),
              url: entry.preview_url
                ? `/api/media${entry.preview_url}`
                : entry.content_url
                  ? `/api/media${entry.content_url}`
                  : entry.indexed_asset_id
                    ? `/api/media/assets/${entry.indexed_asset_id}/image?w=1024`
                    : "",
              fullUrl: entry.content_url
                ? `/api/media${entry.content_url}`
                : entry.indexed_asset_id
                  ? `/api/media/assets/${entry.indexed_asset_id}/image?w=2048`
                  : undefined,
              metadata: {},
              id: entry.indexed_asset_id ?? undefined,
              origin: nextSource.name === GENERATED_SOURCE_NAME ? "generated" : "mounted",
              source_id: nextSource.id,
              source_name: nextSource.name,
              relative_path: entry.relative_path,
              media_type: entry.media_type,
              index_state: entry.index_state,
            }))
            .filter((entry) => Boolean(entry.url));
          if (!currentSourcePath) {
            const params = new URLSearchParams({
              source_id: activeSourceId,
              page: "1",
              page_size: String(assetPageSize),
              sort: sortMode === "relevance" ? "modified_at" : sortMode,
            });
            if (clientFilters.hideNsfw) {
              params.set("exclude_tags", "nsfw");
            }
            const indexedRes = await fetch(`/api/media/assets/browse?${params.toString()}`);
            if (indexedRes.ok) {
              const indexed = await indexedRes.json();
              const indexedMapped = (indexed.items || []).map(mapIndexedItem);
              const sourceImages = clientFilters.indexedOnly ? indexedMapped : mergeGalleryImages(indexedMapped, liveMapped);
              setAssetPage(1);
              setAssetTotal(typeof indexed.total === "number" ? indexed.total : null);
              updateImages(filterImagesClientSide(sourceImages, searchQuery, quickFilter, activeTagFilter, clientFilters));
            } else {
              setAssetTotal(null);
              updateImages(filterImagesClientSide(liveMapped, searchQuery, quickFilter, activeTagFilter, clientFilters));
            }
          } else {
            setAssetTotal(null);
            updateImages(filterImagesClientSide(liveMapped, searchQuery, quickFilter, activeTagFilter, clientFilters));
          }
        }
      } else {
        setActiveSource(null);
        setSourceBrowse(null);
        setActiveScanJob(null);
        setScanProgress(null);
        setAssetPage(1);
        const params = buildAssetParams(1);
        const r = await fetch(`/api/media/assets?${params.toString()}`);
        if (r.ok) {
          const d = await r.json();
          updateImages(filterImagesClientSide((d.items || []).map(mapIndexedItem), "", quickFilter, null, clientFilters));
          setAssetTotal(typeof d.total === "number" ? d.total : null);
        } else {
          // fallback to original if indexer not ready
          const origR = await fetch("/api/studio/generated");
          if (origR.ok) {
              const origD = await origR.json();
              updateImages(filterImagesClientSide((origD.images || []).map((item: any) => ({ ...item, metadata: item.metadata || {}, origin: "generated" })), "", quickFilter, null, clientFilters));
              setAssetTotal(null);
          }
        }
      }
    } catch (e) {
      console.error("Gallery fetch failed", e);
    } finally {
      if (showLoading) {
        setLoading(false);
      }
    }
  }, [activeCollectionId, activeSourceId, activeTab, activeTagFilter, assetPageSize, buildAssetParams, clientFilters, currentSourcePath, quickFilter, searchQuery, sortMode, updateImages]);

  const loadMoreImages = useCallback(async () => {
    const canLoadSourceRoot = Boolean(activeSourceId && !currentSourcePath && !activeCollectionId);
    if (activeCollectionId || (!canLoadSourceRoot && activeSourceId) || loadingMore) {
      return;
    }
    const nextPage = assetPage + 1;
    setLoadingMore(true);
    try {
      const params = canLoadSourceRoot
        ? new URLSearchParams({
            source_id: activeSourceId || "",
            page: String(nextPage),
            page_size: String(assetPageSize),
            sort: sortMode === "relevance" ? "modified_at" : sortMode,
          })
        : buildAssetParams(nextPage);
      if (canLoadSourceRoot && clientFilters.hideNsfw) {
        params.set("exclude_tags", "nsfw");
      }
      const response = await fetch(`/api/media/${canLoadSourceRoot ? "assets/browse" : "assets"}?${params.toString()}`);
      if (!response.ok) {
        throw new Error("Unable to load more assets.");
      }
      const data = await response.json();
      const mapped = filterImagesClientSide(
        (data.items || []).map(mapIndexedItem),
        canLoadSourceRoot ? searchQuery : "",
        quickFilter,
        canLoadSourceRoot ? activeTagFilter : null,
        clientFilters,
      );
      setImages((current) => {
        const seen = new Set(current.map((image) => getSourceMergeKey(image)));
        return [...current, ...mapped.filter((image) => !seen.has(getSourceMergeKey(image)))];
      });
      setAssetPage(nextPage);
      setAssetTotal(typeof data.total === "number" ? data.total : assetTotal);
    } catch (error) {
      setToolsMessage(error instanceof Error ? error.message : "Unable to load more assets.");
    } finally {
      setLoadingMore(false);
    }
  }, [activeCollectionId, activeSourceId, activeTagFilter, assetPage, assetPageSize, assetTotal, buildAssetParams, clientFilters, currentSourcePath, loadingMore, quickFilter, searchQuery, sortMode]);

  useEffect(() => { void fetchImages(); }, [fetchImages]);

  useEffect(() => {
    const shouldRefreshSourceBrowse =
      Boolean(activeSourceId) &&
      activeTab !== "metadata" &&
      (activeSource?.status === "scanning" || activeScanJob?.status === "queued" || activeScanJob?.status === "running");
    if (!shouldRefreshSourceBrowse) {
      return;
    }
    const interval = window.setInterval(() => {
      void fetchImages({ background: true });
    }, 10000);
    return () => window.clearInterval(interval);
  }, [activeScanJob?.status, activeSource?.status, activeSourceId, activeTab, fetchImages]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      void fetchScanJobs();
    }, 5000);
    return () => window.clearInterval(interval);
  }, [fetchScanJobs]);

  useEffect(() => {
    if (!activeScanJob?.id) {
      setScanProgress(null);
      return;
    }

    const eventSource = new EventSource(`/api/media/scan-jobs/${activeScanJob.id}/stream`);
    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as {
          status: ScanJob["status"];
          processed: number;
          progress_percent?: number;
          total_count?: number | null;
          stage?: string | null;
          message?: string | null;
          new_count?: number;
          updated_count?: number;
          deleted_count?: number;
          error_count?: number;
        };
        setScanProgress({
          status: data.status,
          processed: data.processed,
          progressPercent: data.progress_percent ?? 0,
          totalCount: data.total_count ?? null,
          stage: data.stage ?? null,
          message: data.message ?? null,
          newCount: data.new_count ?? 0,
          updatedCount: data.updated_count ?? 0,
          deletedCount: data.deleted_count ?? 0,
          errorCount: data.error_count ?? 0,
        });
        setActiveScanJob((current) =>
          current
            ? {
                ...current,
                status: data.status,
                scanned_count: data.processed,
                progress: data.progress_percent ?? current.progress,
                total_count: data.total_count ?? current.total_count,
                stage: data.stage ?? current.stage,
                message: data.message ?? current.message,
                new_count: data.new_count ?? current.new_count,
                updated_count: data.updated_count ?? current.updated_count,
                deleted_count: data.deleted_count ?? current.deleted_count,
                error_count: data.error_count ?? current.error_count,
              }
            : current,
        );
        if (data.status === "completed" || data.status === "failed" || data.status === "cancelled") {
          eventSource.close();
          setActiveScanJob(null);
          setScanProgress(null);
          window.setTimeout(() => {
            void fetchImages({ background: true });
          }, 600);
        }
      } catch (error) {
        console.error("Failed to parse scan progress", error);
      }
    };
    eventSource.onerror = () => {
      eventSource.close();
    };

    return () => eventSource.close();
  }, [activeScanJob?.id, fetchImages]);

  const openImageDetails = useCallback(async (image: GalleryImage) => {
    setZoomImg(image);
    if (!image.id) {
      return;
    }
    try {
      const response = await fetch(`/api/media/assets/${image.id}`);
      if (!response.ok) {
        return;
      }
      const detail = await response.json();
      setZoomImg(mapIndexedItem(detail));
    } catch (error) {
      setToolsMessage(error instanceof Error ? error.message : "Unable to load image metadata.");
    }
  }, []);

  // Keyboard event handler
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setZoomImg(null);
        setComparerOpen(false);
        setShowKeyboardHelp(false);
      }
      if (zoomImg) {
        const currentIndex = images.findIndex(img => img.name === zoomImg.name);
        if (e.key === "ArrowRight") {
          const nextIndex = Math.min(images.length - 1, currentIndex + 1);
          void openImageDetails(images[nextIndex]);
        }
        if (e.key === "ArrowLeft") {
          const prevIndex = Math.max(0, currentIndex - 1);
          void openImageDetails(images[prevIndex]);
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [zoomImg, images, openImageDetails]);

  const handleUpload = async (files: FileList) => {
    if (!files.length) return;
    setUploading(true);
    const fd = new FormData();
    for (let i = 0; i < files.length; i++) fd.append("files", files[i]);
    try {
      const r = await fetch("/api/studio/generated/upload", { method: "POST", body: fd });
      if (r.ok) {
         setTimeout(fetchImages, 3000); // Give worker a few seconds to index
      }
    } catch (e) {
      console.error("Upload failed", e);
    } finally {
      setUploading(false);
    }
  };

  const deleteImage = async (image: GalleryImage) => {
    if (image.origin !== "generated") {
      alert("Mounted folders are read-only in Gallery. Remove the source or delete the file on disk if you want it gone.");
      return;
    }
    const name = image.name;
    if (!window.confirm("Delete this image?")) return;
    await fetch(`/api/studio/generated/${name}`, { method: "DELETE" });
    setImages(prev => prev.filter(i => i.name !== name));
    setSelectedKeys(prev => prev.filter(key => key !== getSelectionKey(image)));
    if (zoomImg?.name === name) setZoomImg(null);
  };

  const toggleSelect = (image: GalleryImage) => {
    const key = getSelectionKey(image);
    setSelectedKeys(prev =>
      prev.includes(key)
        ? prev.filter(x => x !== key)
        : [...prev, key]
    );
  };

  const selectedImages = useMemo(() => {
    const selectedKeySet = new Set(selectedKeys);
    return images.filter((image) => selectedKeySet.has(getSelectionKey(image)));
  }, [images, selectedKeys]);
  const selectedIds = useMemo(() => selectedImages.map((image) => image.id).filter(Boolean) as string[], [selectedImages]);

  const createCollection = async (name: string, description: string = "") => {
    try {
      const res = await fetch("/api/media/collections", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, description })
      });
      if (res.ok) {
        fetchCollections();
        return await res.json();
      }
    } catch (e) { console.error(e); }
    return null;
  };

  const addToCollection = async (colId: string) => {
    if (selectedIds.length === 0) return;
    try {
      await fetch(`/api/media/collections/${colId}/assets`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ asset_ids: selectedIds })
      });
      setSelectedKeys([]);
      alert(`Added ${selectedIds.length} items to collection.`);
    } catch (e) { console.error(e); }
  };

  const addImageToCollection = async (image: GalleryImage) => {
    if (!image.id) {
      setToolsMessage("Index this image before adding it to a collection.");
      return;
    }
    const collectionName = prompt("Collection name:", collections[0]?.name || "");
    if (!collectionName?.trim()) return;
    let collection = collections.find((item) => item.name.toLowerCase() === collectionName.trim().toLowerCase());
    if (!collection) {
      collection = await createCollection(collectionName.trim());
    }
    if (!collection?.id) return;
    const response = await fetch(`/api/media/collections/${collection.id}/assets`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ asset_ids: [image.id] }),
    });
    if (!response.ok) {
      setToolsMessage("Unable to add image to collection.");
      return;
    }
    await fetchCollections();
    setToolsMessage(`Added ${image.name} to ${collection.name}.`);
  };

  const sendCollectionToDataset = async (collection: MediaCollection) => {
    setDatasetImportingCollectionId(collection.id);
    setToolsMessage(`Creating a training dataset from ${collection.name}...`);
    try {
      const response = await fetch("/api/training/datasets/from-collection", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          collection_id: collection.id,
          name: `${collection.name} training dataset`,
          class_tokens: "person",
          resolution: 1024,
          batch_size: 1,
          num_repeats: 10,
          caption_extension: ".txt",
          enable_bucket: true,
        }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(payload?.detail || "Unable to create dataset from collection.");
      }
      setToolsMessage(`Dataset "${payload?.dataset?.name || collection.name}" created from ${payload?.imported ?? 0} collection image(s).`);
    } catch (error) {
      setToolsMessage(error instanceof Error ? error.message : "Unable to create dataset from collection.");
    } finally {
      setDatasetImportingCollectionId(null);
    }
  };

  const saveSearchAsSmartAlbum = async () => {
    if (!searchQuery) return;
    const name = prompt("Name your Smart Album (Search Collection):", searchQuery);
    if (!name) return;
    const col = await createCollection(name, `Smart Album for query: ${searchQuery}`);
    if (col) {
      await fetch(`/api/media/collections/${col.id}/search-results`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ q: searchQuery })
      });
      fetchCollections();
      alert(`Created smart album: ${name}`);
    }
  };

  const runNaturalLanguageSearch = async () => {
    const query = naturalQuery.trim();
    if (!query) {
      setToolsMessage("Enter a natural-language search first.");
      return;
    }
    setLoading(true);
    setToolsMessage(null);
    try {
      setActiveCollectionId(null);
      setActiveSourceId(null);
      const params = new URLSearchParams({ q: query, limit: "100" });
      const response = await fetch(`/api/media/search/nl?${params.toString()}`);
      if (!response.ok) {
        throw new Error("Natural-language search is unavailable. Check that CLIP indexing is enabled and the worker has embeddings.");
      }
      const data = await response.json();
      setImages(filterImagesClientSide((data.items || []).map(mapIndexedItem), "", quickFilter, activeTagFilter, clientFilters));
      setActiveTab("browse");
    } catch (error) {
      setToolsMessage(error instanceof Error ? error.message : "Natural-language search failed.");
    } finally {
      setLoading(false);
    }
  };

  const cancelScanJob = async (jobId: string) => {
    try {
      const response = await fetch(`/api/media/scan-jobs/${jobId}/cancel`, { method: "POST" });
      if (!response.ok) {
        throw new Error("Unable to cancel scan job.");
      }
      setToolsMessage("Scan job cancelled.");
      await fetchScanJobs();
    } catch (error) {
      setToolsMessage(error instanceof Error ? error.message : "Unable to cancel scan job.");
    }
  };

  const loadScanJobErrors = async (jobId: string) => {
    if (expandedScanJobId === jobId) {
      setExpandedScanJobId(null);
      return;
    }
    setExpandedScanJobId(jobId);
    try {
      const response = await fetch(`/api/media/scan-jobs/${jobId}/errors`);
      if (response.ok) {
        const errors = (await response.json()) as ScanJobErrorEntry[];
        setScanJobErrors((current) => ({ ...current, [jobId]: errors }));
      }
    } catch (error) {
      setToolsMessage(error instanceof Error ? error.message : "Unable to load scan errors.");
    }
  };

  const retryScanJob = async (job: ScanJob) => {
    const mode = (job.scan_mode || "metadata") as ScanMode;
    try {
      if (job.target_type === "collection" && job.collection_id) {
        await queueTargetScan(mode, { type: "collection", collection_id: job.collection_id });
      } else if (job.target_type === "assets" && job.asset_ids_json?.length) {
        await queueTargetScan(mode, { type: "assets", asset_ids: job.asset_ids_json });
      } else if (job.source_id) {
        await queueSourceScan(job.source_id, mode, job.path_filter || null);
      } else {
        throw new Error("This scan job does not have enough target information to retry.");
      }
      setToolsMessage(`Retried ${SCAN_MODE_LABELS[mode] || mode} scan.`);
      await fetchScanJobs();
    } catch (error) {
      setToolsMessage(error instanceof Error ? error.message : "Unable to retry scan job.");
    }
  };

  const downloadWorkflow = async (image: GalleryImage, fromFile = false) => {
    if (!image.id) {
      setToolsMessage("This image is visible through live browse, but it is not indexed yet. Scan it before exporting workflow metadata.");
      return;
    }
    const endpoint = fromFile ? "extract-from-file" : "download";
    try {
      const response = await fetch(`/api/media/assets/${image.id}/workflow/${endpoint}`);
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(detail?.detail || "No exportable workflow was found for this image.");
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = image.name.endsWith(".json") ? image.name : `${image.name.replace(/\.[^.]+$/, "")}-workflow.json`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setToolsMessage(fromFile ? "Workflow re-extracted from the original file." : "Workflow JSON exported.");
    } catch (error) {
      setToolsMessage(error instanceof Error ? error.message : "Workflow export failed.");
    }
  };

  const copyPromptTags = async (image: GalleryImage) => {
    const tags = image.metadata.prompt_tag_string || (image.prompt_tags || []).join(", ");
    if (!tags) {
      setToolsMessage("No parsed prompt tags are available for this image yet.");
      return;
    }
    await navigator.clipboard.writeText(tags);
    setToolsMessage("Prompt tags copied.");
  };

  const importSillyTavernCardToCreator = async (card: Record<string, unknown>) => {
    const data = card.data && typeof card.data === "object" ? (card.data as Record<string, unknown>) : card;
    const name = String(data.name || "Imported Character").trim() || "Imported Character";
    const tags = Array.isArray(data.tags) ? data.tags.map((tag) => String(tag).trim()).filter(Boolean) : [];
    const extensions = data.extensions && typeof data.extensions === "object" ? (data.extensions as Record<string, unknown>) : {};
    const depthPrompt = extensions.depth_prompt && typeof extensions.depth_prompt === "object" ? (extensions.depth_prompt as Record<string, unknown>) : {};
    const projectResponse = await fetch("/cards/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: `${name} Card Import`,
        seed_sentence: String(data.description || data.personality || "").slice(0, 400),
        scenario_text: String(data.scenario || ""),
        project_mode: "character",
        genre: "roleplay",
        tone: "immersive",
      }),
    });
    if (!projectResponse.ok) {
      const detail = await projectResponse.json().catch(() => null);
      throw new Error(detail?.detail || "Unable to create a Cards project.");
    }
    const project = await projectResponse.json();
    const characterResponse = await fetch(`/cards/projects/${project.id}/characters`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        description: String(data.description || ""),
        personality: String(data.personality || ""),
        scenario: String(data.scenario || ""),
        first_message: String(data.first_mes || data.first_message || ""),
        example_dialogue: String(data.mes_example || data.example_dialogue || ""),
        tags,
        creator_notes: String(data.creator_notes || ""),
        system_prompt: String(data.system_prompt || ""),
        post_history_instructions: String(data.post_history_instructions || ""),
        alternate_greetings: Array.isArray(data.alternate_greetings) ? data.alternate_greetings.map((item) => String(item)) : [],
        creator: String(data.creator || ""),
        character_version: String(data.character_version || ""),
        character_note: String(depthPrompt.prompt || ""),
        character_note_depth: Number(depthPrompt.depth || 4),
        character_note_role: "system",
      }),
    });
    if (!characterResponse.ok) {
      const detail = await characterResponse.json().catch(() => null);
      throw new Error(detail?.detail || "Unable to import the character card.");
    }
    setToolsMessage(`Imported ${name} into the Cards creator.`);
    navigate("/cards");
  };

  const applyTagFilterFromInspector = useCallback((tag: string) => {
    const normalizedTag = normalizeTagValue(tag);
    if (!normalizedTag) return;
    setActiveTagFilter(normalizedTag);
    setMetadataFilters((current) => {
      const tags = mergeUniqueTags(current.tags, normalizedTag);
      return { ...current, tags: tags.join(", ") };
    });
    setActiveTab("browse");
    setToolsMessage(`Filtering gallery by tag "${normalizedTag}".`);
  }, []);

  const annotateSelectedWithTag = async (tag: string) => {
    if (!selectedIds.length) {
      setToolsMessage("Select indexed assets before bulk tagging.");
      return;
    }
    const normalizedTag = tag.trim();
    if (!normalizedTag) return;
    try {
      const response = await fetch("/api/media/assets/bulk-annotate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ asset_ids: selectedIds, tags: [normalizedTag] }),
      });
      if (!response.ok) {
        throw new Error("Unable to annotate selected assets.");
      }
      setToolsMessage(`Tagged ${selectedIds.length} selected assets with "${normalizedTag}".`);
      setSelectedKeys([]);
      await fetchImages();
      await fetchTopTags();
    } catch (error) {
      setToolsMessage(error instanceof Error ? error.message : "Bulk tagging failed.");
    }
  };

  const annotateSelected = async () => {
    const tag = prompt("Tag to add to selected assets:");
    if (!tag?.trim()) return;
    await annotateSelectedWithTag(tag);
  };

  const annotateImageWithTag = async (image: GalleryImage, tag = "nsfw") => {
    if (!image.id) {
      setToolsMessage("Index this image before adding tags.");
      return;
    }
    const response = await fetch("/api/media/assets/bulk-annotate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ asset_ids: [image.id], tags: [tag] }),
    });
    if (!response.ok) {
      setToolsMessage("Unable to tag image.");
      return;
    }
    setToolsMessage(`Tagged ${image.name} with "${tag}".`);
    await fetchImages();
    await fetchTopTags();
  };

  const deriveSourceName = (rawPath: string) => {
    const trimmed = rawPath.trim().replace(/[\\/]+$/, "");
    const parts = trimmed.split(/[\\/]+/).filter(Boolean);
    return parts[parts.length - 1] || trimmed;
  };

  const queueSourceScan = async (sourceId: string, scanMode: ScanMode = "basic", pathFilter?: string | null) => {
    const res = await fetch(`/api/media/sources/${sourceId}/scan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scan_mode: scanMode, path_filter: pathFilter || null }),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => null);
      throw new Error(detail?.detail || "Unable to start scan.");
    }
    await fetchScanJobs();
  };

  const queueTargetScan = async (
    scanMode: ScanMode,
    target:
      | { type: "source"; source_id: string; path_filter?: string | null }
      | { type: "collection"; collection_id: string }
      | { type: "assets"; asset_ids: string[] },
  ) => {
    const res = await fetch("/api/media/scan-jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scan_mode: scanMode, target }),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => null);
      throw new Error(detail?.detail || "Unable to start scan.");
    }
    await fetchScanJobs();
  };

  const queueImageScan = async (image: GalleryImage, scanMode: ScanMode) => {
    if (!image.id && (!image.source_id || !image.relative_path)) {
      setToolsMessage("This image needs an indexed source path before it can be scanned directly.");
      return;
    }
    try {
      if (image.id) {
        await queueTargetScan(scanMode, { type: "assets", asset_ids: [image.id] });
      } else {
        await queueSourceScan(image.source_id!, scanMode, image.relative_path);
      }
      setToolsMessage(`${SCAN_MODE_LABELS[scanMode]} scan queued for ${image.name}.`);
      setActiveTab("jobs");
    } catch (error) {
      setToolsMessage(error instanceof Error ? error.message : "Unable to queue image scan.");
    }
  };

  const queueCollectionScan = async (collection: MediaCollection, scanMode: ScanMode = scanModeSelection) => {
    if (!collection.asset_count) {
      setToolsMessage("This collection has no indexed assets to scan.");
      return;
    }
    setScanCommandBusy(scanMode);
    try {
      await queueTargetScan(scanMode, { type: "collection", collection_id: collection.id });
      setToolsMessage(`${SCAN_MODE_LABELS[scanMode]} scan queued for ${collection.name}.`);
      setActiveTab("jobs");
    } catch (error) {
      setToolsMessage(error instanceof Error ? error.message : "Unable to queue collection scan.");
    } finally {
      setScanCommandBusy(null);
    }
  };

  const queueSelectedScan = async (scanMode: ScanMode = scanModeSelection) => {
    if (!selectedIds.length) {
      setToolsMessage("Select indexed assets before queueing a selected-assets scan.");
      return;
    }
    setScanCommandBusy(scanMode);
    try {
      await queueTargetScan(scanMode, { type: "assets", asset_ids: selectedIds });
      setToolsMessage(`${SCAN_MODE_LABELS[scanMode]} scan queued for ${selectedIds.length} selected asset(s).`);
      setActiveTab("jobs");
    } catch (error) {
      setToolsMessage(error instanceof Error ? error.message : "Unable to queue selected-assets scan.");
    } finally {
      setScanCommandBusy(null);
    }
  };

  const runVisionLlm = async (image: GalleryImage) => {
    if (!image.id) {
      setToolsMessage("Index this image before using Vision LLM.");
      return;
    }
    try {
      setToolsMessage(`Asking KoboldCpp Vision LLM about ${image.name}...`);
      const response = await fetch(`/api/media/assets/${image.id}/vision-llm`, { method: "POST" });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(payload?.detail || "Vision LLM scan failed.");
      }
      const analysis = String(payload?.analysis || "");
      setImages((current) =>
        current.map((item) =>
          item.id === image.id
            ? {
                ...item,
                metadata: {
                  ...item.metadata,
                  vision_llm_analysis: analysis,
                  vision_llm_source: payload?.source,
                  vision_llm_updated_at: new Date().toISOString(),
                },
              }
            : item,
        ),
      );
      setZoomImg((current) => {
        if (!current || current.id !== image.id) return current;
        return {
          ...current,
          metadata: {
            ...current.metadata,
            vision_llm_analysis: analysis,
            vision_llm_source: payload?.source,
            vision_llm_updated_at: new Date().toISOString(),
          },
        };
      });
      setToolsMessage("Vision LLM analysis saved to image metadata.");
    } catch (error) {
      setToolsMessage(error instanceof Error ? error.message : "Vision LLM scan failed.");
    }
  };

  const clearGalleryLlmContext = () => {
    setConnectorHealth((current) => current.filter((item) => item.label !== "KoboldCpp"));
    setToolsMessage("Gallery LLM context cleared. Vision scans in Gallery are single-image requests.");
  };

  const clearFinishedScanJobs = async (kind: "finished" | "succeeded" | "failed" | "cancelled" = "finished") => {
    try {
      const response = await fetch(`/api/media/scan-jobs/${kind}`, { method: "DELETE" });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(payload?.detail || "Unable to clear scan jobs.");
      }
      setToolsMessage(`Cleared ${payload?.deleted ?? 0} ${kind} scan job(s).`);
      await fetchScanJobs();
    } catch (error) {
      setToolsMessage(error instanceof Error ? error.message : "Unable to clear scan jobs.");
    }
  };

  const runConnectorHealthCheck = async () => {
    setConnectorChecking(true);
    const next: ConnectorHealthItem[] = [
      { label: "KoboldCpp", status: "checking", detail: "Checking LLM endpoint..." },
      { label: "ComfyUI", status: "checking", detail: "Checking image backend..." },
      { label: "Media Indexer", status: "checking", detail: "Checking media API..." },
      { label: "Scan Worker", status: "checking", detail: "Checking scan queue visibility..." },
    ];
    setConnectorHealth(next);
    try {
      const settingsResponse = await fetch("/api/studio/settings");
      const settings = settingsResponse.ok ? await settingsResponse.json() : null;
      const llm = settings?.llm || {};
      const image = settings?.image || {};

      const [llmResult, comfyResult, mediaResult, jobsResult] = await Promise.allSettled([
        fetch("/api/studio/llm/test", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            provider: llm.provider || "koboldcpp",
            endpoint: llm.endpoint || "http://127.0.0.1:5001/v1",
            model: llm.model || "koboldcpp",
            api_key: llm.api_key || "",
          }),
        }),
        fetch("/api/studio/comfyui/test", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ endpoint: image.endpoint || "http://127.0.0.1:8188" }),
        }),
        fetch("/api/media/health"),
        fetch("/api/media/scan-jobs"),
      ]);

      const readJson = async (result: PromiseSettledResult<Response>) => {
        if (result.status !== "fulfilled") {
          throw result.reason;
        }
        const body = await result.value.json().catch(() => ({}));
        if (!result.value.ok) {
          throw new Error(body?.detail || result.value.statusText);
        }
        return body;
      };

      const healthItems: ConnectorHealthItem[] = [];
      try {
        const body = await readJson(llmResult);
        healthItems.push({ label: "KoboldCpp", status: "ok", endpoint: body.endpoint || llm.endpoint, detail: body.ready ? "LLM endpoint reachable and model list returned." : "Endpoint reachable, selected model was not listed." });
      } catch (error) {
        healthItems.push({ label: "KoboldCpp", status: "error", endpoint: llm.endpoint, detail: error instanceof Error ? error.message : "LLM health check failed." });
      }
      try {
        const body = await readJson(comfyResult);
        healthItems.push({ label: "ComfyUI", status: "ok", endpoint: body.endpoint || image.endpoint, detail: `${body.models?.length || 0} checkpoint entries available.` });
      } catch (error) {
        healthItems.push({ label: "ComfyUI", status: "error", endpoint: image.endpoint, detail: error instanceof Error ? error.message : "ComfyUI health check failed." });
      }
      try {
        await readJson(mediaResult);
        healthItems.push({ label: "Media Indexer", status: "ok", endpoint: "/api/media", detail: "Media API is reachable through Mklan Studio." });
      } catch (error) {
        healthItems.push({ label: "Media Indexer", status: "error", endpoint: "/api/media", detail: error instanceof Error ? error.message : "Media API check failed." });
      }
      try {
        const jobs = await readJson(jobsResult);
        const running = Array.isArray(jobs) ? jobs.filter((job) => job.status === "running" || job.status === "queued").length : 0;
        healthItems.push({ label: "Scan Worker", status: running > 0 ? "warn" : "ok", detail: running > 0 ? `${running} scan job(s) queued or running.` : "Scan queue is reachable and currently idle." });
      } catch (error) {
        healthItems.push({ label: "Scan Worker", status: "error", detail: error instanceof Error ? error.message : "Scan queue check failed." });
      }
      setConnectorHealth(healthItems);
    } finally {
      setConnectorChecking(false);
    }
  };

  const createMountedSource = async () => {
    const rootPath = sourcePath.trim();
    if (!rootPath) {
      setSourceMessage({ tone: "error", text: "Enter a Windows folder path first." });
      return;
    }

    setSourceSubmitting(true);
    setSourceMessage({ tone: "info", text: "Registering the folder and queueing a read-only scan..." });
    try {
      const name = sourceName.trim() || deriveSourceName(rootPath);
      const res = await fetch("/api/media/sources", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, type: "mounted_fs", root_path: rootPath }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => null);
        throw new Error(detail?.detail || "Unable to add this folder.");
      }

      const created = await res.json();
      await fetchSources();
      setActiveCollectionId(null);
      setActiveSourceId(created.id);
      setSourceName("");
      setSourcePath("");
      try {
        await queueSourceScan(created.id);
        setSourceMessage({
          tone: "success",
          text: "Folder added. Quick indexing is running in batches, so images will appear progressively while deeper metadata stays separate.",
        });
      } catch (scanError) {
        setSourceMessage({
          tone: "info",
          text: `Folder added, but the scan was not queued: ${scanError instanceof Error ? scanError.message : "Unable to start scan."}`,
        });
      }
      setTimeout(() => {
        void fetchImages({ background: true });
      }, 2500);
    } catch (e) {
      const message = e instanceof Error ? e.message : "Unable to add this folder.";
      setSourceMessage({ tone: "error", text: message });
    } finally {
      setSourceSubmitting(false);
    }
  };

  const sendToWorkshop = (img: GalleryImage) => {
    const meta = img.metadata;
    const params = new URLSearchParams();
    params.set("tab", "images");
    if (meta.prompt) params.set("prompt", meta.prompt);
    if (meta.negative_prompt) params.set("negative_prompt", meta.negative_prompt);
    if (meta.width) params.set("width", String(meta.width));
    if (meta.height) params.set("height", String(meta.height));
    if (meta.steps) params.set("steps", String(meta.steps));
    if (meta.cfg_scale) params.set("cfg_scale", String(meta.cfg_scale));
    if (meta.sampler_name) params.set("sampler_name", meta.sampler_name);
    if (meta.scheduler) params.set("scheduler", meta.scheduler);
    navigate({ pathname: "/wildcards", search: `?${params.toString()}` });
  };

  const comparerImgs = selectedImages.slice(0, 2);
  const toolImage = zoomImg ?? selectedImages[0] ?? null;
  const canUsePortal = typeof document !== "undefined";
  useEffect(() => {
    if (!zoomImg || !canUsePortal) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [zoomImg, canUsePortal]);

  const galleryGridComponents = useMemo(() => ({
    List: React.forwardRef<HTMLDivElement, any>((props, ref) => (
      <div
        {...props}
        ref={ref}
        style={{
          display: "grid",
          gridTemplateColumns: isMobile ? "repeat(auto-fill, minmax(150px, 1fr))" : "repeat(auto-fill, minmax(240px, 1fr))",
          gap: isMobile ? "0.65rem" : "1rem",
          paddingBottom: "2rem",
          ...props.style,
        }}
      />
    )),
    Item: React.forwardRef<HTMLDivElement, any>((props, ref) => (
      <div {...props} ref={ref} style={{ display: "flex", flexDirection: "column", height: "100%", ...props.style }} />
    )),
  }), [isMobile]);

  useEffect(() => {
    if (selectedImages.length !== 2 && comparerOpen) {
      setComparerOpen(false);
    }
  }, [selectedImages.length, comparerOpen]);

  const sourceDirectories = (sourceBrowse?.entries || []).filter((entry) => entry.entry_type === "directory");
  const sourceFiles = (sourceBrowse?.entries || []).filter((entry) => entry.entry_type === "file");
  const sourceImageEntries = sourceFiles.filter((entry) => entry.media_type === "image");
  const sourceTreeNodes = sourceTree ? flattenSourceTree(sourceTree) : [];
  const browseCurrentPath = sourceBrowse?.current_path || "";
  const browseParentPath = sourceBrowse?.parent_path ?? null;
  const browseBreadcrumbs = sourceBrowse?.breadcrumbs || [];
  const scanPercent = scanProgress?.progressPercent ?? activeScanJob?.progress ?? 0;
  const scanProcessed = scanProgress?.processed ?? activeScanJob?.scanned_count ?? 0;
  const scanTotal = scanProgress?.totalCount ?? activeScanJob?.total_count ?? null;
  const scanStage = scanProgress?.stage ?? activeScanJob?.stage ?? null;
  const scanNewCount = scanProgress?.newCount ?? activeScanJob?.new_count ?? 0;
  const scanUpdatedCount = scanProgress?.updatedCount ?? activeScanJob?.updated_count ?? 0;
  const scanDeletedCount = scanProgress?.deletedCount ?? activeScanJob?.deleted_count ?? 0;
  const scanErrorCount = scanProgress?.errorCount ?? activeScanJob?.error_count ?? 0;
  const scanMessage = scanProgress?.message ?? activeScanJob?.message ?? null;
  const showSourceScanState =
    Boolean(activeSourceId) &&
    (activeSource?.status === "scanning" || scanProgress?.status === "queued" || scanProgress?.status === "running" || activeScanJob?.status === "queued" || activeScanJob?.status === "running");

  const scanTargetSource = sources.find((source) => source.id === scanTargetSourceId) || activeSource || sources[0] || null;
  const scanTargetCollection = collections.find((collection) => collection.id === scanTargetCollectionId) || collections.find((collection) => collection.id === activeCollectionId) || collections[0] || null;
  const activeScanCount = scanJobs.filter((job) => job.status === "queued" || job.status === "running").length;
  const failedScanCount = scanJobs.filter((job) => job.status === "failed").length;
  const isSourceRootBrowse = Boolean(activeSourceId && !browseCurrentPath && !activeCollectionId);
  const hasMoreAssets = !activeCollectionId && (!activeSourceId || isSourceRootBrowse) && assetTotal !== null && images.length < assetTotal;

  const queueCommandScan = async (scanMode: ScanMode) => {
    setScanCommandBusy(scanMode);
    try {
      if (scanTargetKind === "collection") {
        if (!scanTargetCollection?.id) throw new Error("Pick a collection before queueing a scan.");
        await queueTargetScan(scanMode, { type: "collection", collection_id: scanTargetCollection.id });
        setToolsMessage(`${SCAN_MODE_LABELS[scanMode]} scan queued for ${scanTargetCollection.name}.`);
      } else if (scanTargetKind === "selected") {
        if (!selectedIds.length) throw new Error("Select indexed assets before queueing a scan.");
        await queueTargetScan(scanMode, { type: "assets", asset_ids: selectedIds });
        setToolsMessage(`${SCAN_MODE_LABELS[scanMode]} scan queued for ${selectedIds.length} selected asset(s).`);
      } else if (scanTargetKind === "focused") {
        if (!toolImage) throw new Error("Open or select an indexed image before queueing a focused scan.");
        if (!toolImage.id) throw new Error("The focused image must be indexed before it can be scanned.");
        await queueTargetScan(scanMode, { type: "assets", asset_ids: [toolImage.id] });
        setToolsMessage(`${SCAN_MODE_LABELS[scanMode]} scan queued for ${toolImage.name}.`);
      } else {
        if (!scanTargetSource?.id) throw new Error("Pick a source before queueing a scan.");
        await queueSourceScan(scanTargetSource.id, scanMode, scanPathFilter.trim() || null);
        setToolsMessage(`${SCAN_MODE_LABELS[scanMode]} scan queued for ${scanTargetSource.name}.`);
      }
      setActiveTab("jobs");
      setMobileScanOpen(false);
    } catch (error) {
      setToolsMessage(error instanceof Error ? error.message : "Unable to queue scan.");
    } finally {
      setScanCommandBusy(null);
    }
  };

  const handleSourceTreeClick = async (node: SourceTreeNode) => {
    setCurrentSourcePath(node.path);
    if (node.path === "") {
      setSourceTree((current) => (current ? { ...current, expanded: true } : current));
      return;
    }

    if (!node.loaded) {
      try {
        const response = await fetch(`/api/media/sources/${encodeURIComponent(activeSourceId || "")}/tree?path=${encodeURIComponent(node.path)}`);
        if (response.ok) {
          const tree = (await response.json()) as SourceTreeResponse;
          setSourceTree((current) => (current ? insertSourceTreeChildren(current, node.path, tree.dirs) : current));
          return;
        }
      } catch (error) {
        console.error("Failed to expand source tree node", error);
      }
    }

    setSourceTree((current) => (current ? toggleSourceTreeNode(current, node.path) : current));
  };

  const contextMenuStyle = contextMenu
    ? isMobile
      ? {
          position: "fixed" as const,
          left: 0,
          right: 0,
          bottom: 0,
          width: "100%",
          maxHeight: "72vh",
          borderRadius: "18px 18px 0 0",
        }
      : {
          position: "fixed" as const,
          left: Math.max(8, Math.min(contextMenu.x, window.innerWidth - 304)),
          top: Math.max(8, Math.min(contextMenu.y, window.innerHeight - 520)),
          width: 296,
          maxHeight: "calc(100vh - 16px)",
        }
    : undefined;

  const contextActions: Array<{ label: string; run: () => void; disabled?: boolean }> = contextMenu
    ? [
        { label: copy.openDetails, run: () => void openImageDetails(contextMenu.image) },
        { label: selectedKeys.includes(getSelectionKey(contextMenu.image)) ? copy.removeSelection : copy.addSelection, run: () => toggleSelect(contextMenu.image) },
        { label: copy.addCollection, run: () => void addImageToCollection(contextMenu.image), disabled: !contextMenu.image.id },
        { label: copy.addNsfw, run: () => void annotateImageWithTag(contextMenu.image, "nsfw"), disabled: !contextMenu.image.id },
        ...SINGLE_IMAGE_SCAN_MODES.map((mode) => ({
          label: `Scan: ${SCAN_MODE_LABELS[mode]}`,
          run: () => void queueImageScan(contextMenu.image, mode),
          disabled: !contextMenu.image.id && (!contextMenu.image.source_id || !contextMenu.image.relative_path),
        })),
        { label: copy.copyPromptTags, run: () => void copyPromptTags(contextMenu.image) },
        { label: copy.exportWorkflow, run: () => void downloadWorkflow(contextMenu.image), disabled: !contextMenu.image.workflow_export_available },
        { label: copy.sendWildcards, run: () => sendToWorkshop(contextMenu.image) },
        { label: copy.openOriginal, run: () => window.open(contextMenu.image.fullUrl || contextMenu.image.url, "_blank", "noopener,noreferrer") },
      ]
    : [];

  const renderToggleSwitch = (
    label: string,
    checked: boolean,
    onChange: (checked: boolean) => void,
    Icon: React.ComponentType<{ size?: number }>,
    title: string,
  ) => (
    <label
      title={title}
      style={{
        minHeight: 40,
        display: "flex",
        alignItems: "center",
        gap: "0.55rem",
        padding: "0.45rem 0.65rem",
        borderRadius: "10px",
        border: `1px solid ${checked ? "rgba(99,102,241,0.42)" : "var(--border-color)"}`,
        background: checked ? "rgba(99,102,241,0.14)" : "rgba(255,255,255,0.025)",
        color: checked ? "var(--accent)" : "var(--text-secondary)",
        cursor: "pointer",
        fontSize: "0.78rem",
        fontWeight: 750,
        userSelect: "none",
        whiteSpace: "nowrap",
      }}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        aria-label={label}
        style={{ position: "absolute", opacity: 0, pointerEvents: "none" }}
      />
      <span
        aria-hidden="true"
        style={{
          width: 34,
          height: 18,
          borderRadius: 999,
          background: checked ? "var(--accent)" : "rgba(255,255,255,0.12)",
          border: "1px solid rgba(255,255,255,0.12)",
          display: "flex",
          alignItems: "center",
          padding: 2,
          transition: "background 0.18s ease",
        }}
      >
        <span
          style={{
            width: 12,
            height: 12,
            borderRadius: "50%",
            background: "#fff",
            transform: checked ? "translateX(16px)" : "translateX(0)",
            transition: "transform 0.18s ease",
          }}
        />
      </span>
      <Icon size={15} />
      <span>{label}</span>
    </label>
  );

  const renderGalleryCommandBar = (compact = false) => {
    const quickModes: QuickFilter[] = ["all", "has_prompt", "has_workflow"];
    const sortModes: SortMode[] = ["relevance", "modified_at", "created_at", "filename"];

    return (
      <section
        data-gallery-command-bar="true"
        className={compact ? "mklan-sheet-section" : undefined}
        style={{
          position: compact ? undefined : ("sticky" as const),
          top: compact ? undefined : 0,
          zIndex: compact ? undefined : 30,
          display: compact ? "grid" : "flex",
          gridTemplateColumns: compact ? "1fr" : undefined,
          flexWrap: compact ? undefined : "wrap",
          gap: compact ? "0.8rem" : "0.75rem",
          alignItems: "center",
          padding: compact ? "0.2rem 0 0" : "0.85rem",
          border: compact ? "none" : "1px solid var(--border-color)",
          borderRadius: compact ? 0 : "14px",
          background: compact ? "transparent" : "rgba(14, 14, 18, 0.86)",
          backdropFilter: compact ? undefined : "blur(14px)",
          boxShadow: compact ? undefined : "0 14px 34px rgba(0,0,0,0.18)",
        }}
      >
        <div style={{ flex: compact ? undefined : "1 1 260px", display: "flex", alignItems: "center", background: "var(--bg-main)", border: "1px solid var(--border-color)", borderRadius: "10px", padding: "0 0.5rem", minWidth: 0 }}>
          <Search size={16} color="var(--text-muted)" />
          <input
            type="text"
            placeholder={activeCollectionId ? "Filter collection..." : activeSourceId ? "Filter source..." : copy.searchAssets}
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            onKeyDown={(event) => { if (event.key === "Enter") void fetchImages(); }}
            style={{ background: "transparent", border: "none", color: "var(--text-main)", padding: "0.65rem 0.55rem", outline: "none", width: "100%", minWidth: 0 }}
          />
          {searchQuery && (
            <button onClick={() => { setSearchQuery(""); window.setTimeout(() => void fetchImages(), 50); }} style={{ background: "none", border: "none", padding: "0 0.35rem", color: "var(--text-muted)", cursor: "pointer" }} title="Clear search">
              <X size={14} />
            </button>
          )}
          {searchQuery && !activeCollectionId && !activeSourceId && (
            <button onClick={saveSearchAsSmartAlbum} style={{ background: "none", border: "none", borderLeft: "1px solid var(--border-color)", padding: "0.55rem", color: "var(--accent)", cursor: "pointer", display: "flex", alignItems: "center" }} title="Save Search as Smart Album">
              <Save size={14} />
            </button>
          )}
        </div>

        <div style={{ flex: compact ? undefined : "1 1 230px", display: "flex", alignItems: "center", gap: "0.45rem", flexWrap: "wrap", minWidth: 0 }}>
          {sortModes.map((mode) => (
            <button
              key={mode}
              onClick={() => setSortMode(mode)}
              style={{
                border: "1px solid var(--border-color)",
                background: sortMode === mode ? "rgba(99,102,241,0.16)" : "transparent",
                color: sortMode === mode ? "var(--accent)" : "var(--text-secondary)",
                padding: "0.46rem 0.62rem",
                borderRadius: "999px",
                cursor: "pointer",
                fontSize: "0.75rem",
              }}
            >
              {SORT_MODE_LABELS[mode]}
            </button>
          ))}
        </div>

        <div style={{ flex: compact ? undefined : "1 1 220px", display: "flex", alignItems: "center", gap: "0.45rem", flexWrap: "wrap", minWidth: 0 }}>
          {quickModes.map((mode) => (
            <button
              key={mode}
              onClick={() => setQuickFilter(mode)}
              style={{
                border: "1px solid var(--border-color)",
                background: quickFilter === mode ? "rgba(99,102,241,0.16)" : "transparent",
                color: quickFilter === mode ? "var(--accent)" : "var(--text-secondary)",
                padding: "0.46rem 0.62rem",
                borderRadius: "999px",
                cursor: "pointer",
                fontSize: "0.75rem",
              }}
            >
              {QUICK_FILTER_LABELS[mode]}
            </button>
          ))}
        </div>

        <div style={{ flex: compact ? undefined : "1 1 280px", display: "flex", alignItems: "center", justifyContent: compact ? "flex-start" : "flex-end", gap: "0.5rem", flexWrap: "wrap", minWidth: 0 }}>
          {renderToggleSwitch(copy.hideNsfw, clientFilters.hideNsfw, (checked) => updateGalleryViewPrefs({ hideNsfw: checked }), EyeOff, "Hide assets tagged NSFW.")}
          {renderToggleSwitch(clientFilters.indexedOnly ? copy.indexedOnly : copy.liveIndexed, clientFilters.indexedOnly, (checked) => updateGalleryViewPrefs({ indexedOnly: checked }), Layers, "Toggle indexed-only mode.")}
          <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", color: "var(--text-secondary)", fontSize: "0.76rem", fontWeight: 700 }}>
            <span>{copy.pageSize}</span>
            <select value={assetPageSize} onChange={(event) => setAssetPageSize(Number(event.target.value))} style={{ width: "auto", minWidth: 74, padding: "0.46rem 0.5rem" }}>
              <option value={40}>40</option>
              <option value={60}>60</option>
              <option value={100}>100</option>
            </select>
          </label>
          <button onClick={() => void fetchImages()} disabled={loading} style={{ border: "1px solid var(--border-color)" }}>
            <RefreshCw size={16} className={loading ? "spin" : ""} /> {copy.refresh}
          </button>
        </div>

        <div style={{ width: "100%", display: "flex", alignItems: "center", gap: "0.55rem", flexWrap: "wrap", color: "var(--text-secondary)", fontSize: "0.8rem" }}>
          <span>{assetTotal !== null ? `${images.length} / ${assetTotal} loaded` : `${images.length} loaded`}</span>
          {activeTagFilter && (
            <button onClick={() => setActiveTagFilter(null)} style={{ border: "1px solid var(--border-color)", color: "var(--text-secondary)", padding: "0.35rem 0.55rem" }}>
              Tag: {activeTagFilter} <X size={13} />
            </button>
          )}
        </div>
      </section>
    );
  };

  const renderSelectionRail = () => {
    if (!selectedImages.length) return null;
    return (
      <section
        data-gallery-selection-rail="true"
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "0.75rem",
          flexWrap: "wrap",
          padding: "0.75rem 0.85rem",
          border: "1px solid rgba(99,102,241,0.28)",
          borderRadius: "12px",
          background: "rgba(99,102,241,0.08)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "0.55rem", flexWrap: "wrap" }}>
          <strong style={{ color: "var(--text-main)" }}>{selectedImages.length} {copy.selectedCount}</strong>
          <span style={{ color: "var(--text-secondary)", fontSize: "0.82rem" }}>{selectedIds.length} indexed</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
          <select
            disabled={!selectedIds.length}
            onChange={(event) => {
              if (event.target.value) {
                void addToCollection(event.target.value);
                event.target.value = "";
              }
            }}
            style={{ padding: "0.5rem", background: "var(--bg-secondary)", border: "1px solid var(--accent)", color: "var(--accent)", borderRadius: "8px", cursor: selectedIds.length ? "pointer" : "not-allowed" }}
          >
            <option value="">+ {copy.chooseCollection}</option>
            {collections.map((collection) => <option key={collection.id} value={collection.id}>{collection.name}</option>)}
          </select>
          <button className={selectedImages.length === 2 ? "primary" : ""} disabled={selectedImages.length !== 2} onClick={() => setComparerOpen(true)}>
            <GitCompare size={16} /> {copy.compareSelected}
          </button>
          <button onClick={() => void annotateSelected()} disabled={!selectedIds.length} style={{ border: "1px solid var(--border-color)" }}>
            <Tags size={16} /> {copy.bulkAddTag}
          </button>
          <button onClick={() => void annotateSelectedWithTag("nsfw")} disabled={!selectedIds.length} style={{ border: "1px solid var(--border-color)" }}>
            <EyeOff size={16} /> {copy.addNsfwSelected}
          </button>
          <button onClick={() => void queueSelectedScan(scanModeSelection)} disabled={!selectedIds.length || scanCommandBusy !== null} style={{ border: "1px solid var(--border-color)" }}>
            <ListChecks size={16} /> Scan Selected
          </button>
          <button onClick={() => { setSelectedKeys([]); setComparerOpen(false); }} style={{ border: "1px solid var(--border-color)" }}>
            <X size={16} /> {copy.clearSelection}
          </button>
        </div>
      </section>
    );
  };

  const renderLibraryPanel = (asSheet = false) => (
    <>
      <div style={{ padding: asSheet ? "1rem 1rem 0.5rem" : "1.5rem 1.5rem 0.5rem", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3 style={{ margin: 0, fontSize: "0.9rem", color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>{language === "fr" ? "Bibliotheque" : "Library"}</h3>
        <button onClick={() => { const name = prompt("Collection Name:"); if(name) void createCollection(name); }} style={{ background: "none", border: "none", color: "var(--accent)", cursor: "pointer", display: "flex", alignItems: "center" }} title="New Collection">
          <Plus size={16} />
        </button>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.2rem", padding: "0 1rem 1rem", overflowY: "auto", flex: 1 }}>
        <button
          onClick={() => {
            setActiveCollectionId(null);
            setActiveSourceId(null);
            setActiveTab("browse");
            setMobileLibraryOpen(false);
          }}
          style={{ textAlign: "left", background: activeCollectionId === null && activeSourceId === null ? "rgba(99,102,241,0.15)" : "transparent", color: activeCollectionId === null && activeSourceId === null ? "var(--accent)" : "var(--text-main)", border: "none", padding: "0.7rem 1rem", borderRadius: "8px", display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer", transition: "background 0.2s" }}
        >
          <Images size={16} /> {copy.allAssets}
        </button>
        <div style={{ margin: "1rem 0 0.5rem 0.5rem", fontSize: "0.75rem", color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase" }}>{copy.indexedSources}</div>
        {sources.map(source => (
          <button
            key={source.id}
            onClick={() => {
              setActiveCollectionId(null);
              setActiveSourceId(source.id);
              setScanTargetSourceId(source.id);
              setActiveTab("sources");
              setSourceMessage(null);
              setMobileLibraryOpen(false);
            }}
            style={{ textAlign: "left", background: activeSourceId === source.id ? "rgba(99,102,241,0.15)" : "transparent", color: activeSourceId === source.id ? "var(--accent)" : "var(--text-secondary)", border: "none", padding: "0.7rem 1rem", borderRadius: "8px", display: "flex", flexDirection: "column", alignItems: "flex-start", gap: "0.15rem", cursor: "pointer", transition: "background 0.2s" }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", width: "100%" }}>
              <FolderOpen size={16} />
              <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{source.name}</span>
            </div>
            <span style={{ fontSize: "0.72rem", opacity: 0.7, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", width: "100%" }}>{source.display_root_path}</span>
            <span style={{ fontSize: "0.68rem", textTransform: "uppercase", letterSpacing: "0.04em", opacity: 0.5 }}>{source.status === "scanning" ? "scanning" : source.status}</span>
          </button>
        ))}
        <div style={{ margin: "1rem 0 0.5rem 0.5rem", fontSize: "0.75rem", color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase" }}>{copy.collections}</div>
        {collections.map(c => (
          <button
            key={c.id}
            onClick={() => {
              setActiveSourceId(null);
              setActiveCollectionId(c.id);
              setActiveTab("collections");
              setMobileLibraryOpen(false);
            }}
            style={{ textAlign: "left", background: activeCollectionId === c.id ? "rgba(99,102,241,0.15)" : "transparent", color: activeCollectionId === c.id ? "var(--accent)" : "var(--text-secondary)", border: "none", padding: "0.7rem 1rem", borderRadius: "8px", display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer", transition: "background 0.2s" }}
          >
            <FolderOpen size={16} />
            <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.name}</span>
            <span style={{ fontSize: "0.7rem", opacity: 0.5 }}>{c.asset_count}</span>
          </button>
        ))}
      </div>
    </>
  );

  const renderScanCommandCenter = (compact = false) => {
    const selectedMode = SCAN_MODE_OPTIONS.find((item) => item.value === scanModeSelection) || SCAN_MODE_OPTIONS[1];
    const targetButtons: Array<{ id: ScanTargetKind; label: string; disabled?: boolean }> = [
      { id: "source", label: "Source / Folder", disabled: !sources.length },
      { id: "collection", label: "Collection", disabled: !collections.length },
      { id: "selected", label: `Selected (${selectedIds.length})`, disabled: !selectedIds.length },
      { id: "focused", label: toolImage ? "Focused Image" : "Focused", disabled: !toolImage?.id },
    ];
    const canQueue =
      scanCommandBusy === null &&
      ((scanTargetKind === "source" && Boolean(scanTargetSource?.id)) ||
        (scanTargetKind === "collection" && Boolean(scanTargetCollection?.id)) ||
        (scanTargetKind === "selected" && selectedIds.length > 0) ||
        (scanTargetKind === "focused" && Boolean(toolImage?.id)));

    return (
      <section className={compact ? "mklan-sheet-section" : ""} style={{ padding: compact ? 0 : "1rem", background: compact ? "transparent" : "rgba(255,255,255,0.025)", border: compact ? "none" : "1px solid var(--border-color)", borderRadius: compact ? 0 : "12px", display: "flex", flexDirection: "column", gap: "0.85rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.8rem", flexWrap: "wrap" }}>
          <div>
            <strong style={{ display: "flex", alignItems: "center", gap: "0.45rem", fontSize: "1rem" }}><ListChecks size={17} /> {copy.scanCenter}</strong>
            <p style={{ margin: "0.25rem 0 0", color: "var(--text-secondary)", fontSize: "0.84rem" }}>
              Queue targeted scans for sources, folders, collections, selected assets, or one focused image.
            </p>
          </div>
          <div style={{ display: "flex", gap: "0.45rem", flexWrap: "wrap" }}>
            <span style={{ border: "1px solid var(--border-color)", borderRadius: "999px", padding: "0.32rem 0.55rem", color: "var(--text-secondary)", fontSize: "0.74rem" }}>{activeScanCount} active</span>
            <span style={{ border: "1px solid var(--border-color)", borderRadius: "999px", padding: "0.32rem 0.55rem", color: failedScanCount ? "#ffb3b3" : "var(--text-secondary)", fontSize: "0.74rem" }}>{failedScanCount} failed</span>
          </div>
        </div>

        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.45rem" }}>
          {targetButtons.map((target) => (
            <button
              key={target.id}
              onClick={() => setScanTargetKind(target.id)}
              disabled={target.disabled}
              style={{
                border: "1px solid var(--border-color)",
                background: scanTargetKind === target.id ? "rgba(99,102,241,0.16)" : "transparent",
                color: scanTargetKind === target.id ? "var(--accent)" : "var(--text-secondary)",
              }}
            >
              {target.label}
            </button>
          ))}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: isMobile || compact ? "1fr" : "minmax(220px, 1fr) minmax(180px, 0.8fr) minmax(230px, 1fr) auto", gap: "0.7rem", alignItems: "end" }}>
          {scanTargetKind === "source" && (
            <>
              <label style={{ display: "grid", gap: "0.35rem" }}>
                <span style={{ color: "var(--text-muted)", fontSize: "0.72rem", textTransform: "uppercase" }}>Source</span>
                <select value={scanTargetSource?.id || ""} onChange={(event) => setScanTargetSourceId(event.target.value)}>
                  {sources.map((source) => <option key={source.id} value={source.id}>{source.name}</option>)}
                </select>
              </label>
              <label style={{ display: "grid", gap: "0.35rem" }}>
                <span style={{ color: "var(--text-muted)", fontSize: "0.72rem", textTransform: "uppercase" }}>Folder / file filter</span>
                <input value={scanPathFilter} onChange={(event) => setScanPathFilter(event.target.value)} placeholder={browseCurrentPath || "optional relative path"} />
              </label>
            </>
          )}
          {scanTargetKind === "collection" && (
            <label style={{ display: "grid", gap: "0.35rem", gridColumn: isMobile || compact ? undefined : "span 2" }}>
              <span style={{ color: "var(--text-muted)", fontSize: "0.72rem", textTransform: "uppercase" }}>Collection</span>
              <select value={scanTargetCollection?.id || ""} onChange={(event) => setScanTargetCollectionId(event.target.value)}>
                {collections.map((collection) => <option key={collection.id} value={collection.id}>{collection.name} ({collection.asset_count})</option>)}
              </select>
            </label>
          )}
          {scanTargetKind === "selected" && (
            <div style={{ color: "var(--text-secondary)", fontSize: "0.84rem", gridColumn: isMobile || compact ? undefined : "span 2" }}>
              {selectedIds.length} indexed selected asset(s) will be scanned.
            </div>
          )}
          {scanTargetKind === "focused" && (
            <div style={{ color: "var(--text-secondary)", fontSize: "0.84rem", gridColumn: isMobile || compact ? undefined : "span 2", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {toolImage ? `Focused image: ${toolImage.name}` : "Open or select an indexed image."}
            </div>
          )}

          <label style={{ display: "grid", gap: "0.35rem" }}>
            <span style={{ color: "var(--text-muted)", fontSize: "0.72rem", textTransform: "uppercase" }}>Scan mode</span>
            <select value={scanModeSelection} onChange={(event) => setScanModeSelection(event.target.value as ScanMode)}>
              {SCAN_MODE_OPTIONS.map((mode) => <option key={mode.value} value={mode.value}>{mode.label}</option>)}
            </select>
          </label>
          <button onClick={() => void queueCommandScan(scanModeSelection)} disabled={!canQueue} style={{ border: "1px solid var(--border-color)" }}>
            <RefreshCw size={16} className={scanCommandBusy === scanModeSelection ? "spin" : ""} />
            Queue Scan
          </button>
        </div>

        <div style={{ color: "var(--text-secondary)", fontSize: "0.8rem", lineHeight: 1.45 }}>
          <strong style={{ color: "var(--text-main)" }}>{selectedMode.label}:</strong> {selectedMode.detail}
        </div>

        {toolImage ? (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem", flexWrap: "wrap", padding: "0.75rem", border: "1px solid var(--border-color)", borderRadius: "10px", background: "var(--bg-secondary)" }}>
            <span style={{ color: "var(--text-secondary)", fontSize: "0.84rem" }}>Focused image: <strong style={{ color: "var(--text-main)" }}>{toolImage.name}</strong></span>
            <div style={{ display: "flex", gap: "0.45rem", flexWrap: "wrap" }}>
              <button onClick={() => void queueImageScan(toolImage, "vision_llm")} disabled={!toolImage.id} style={{ border: "1px solid var(--border-color)" }}>
                <Sparkles size={16} /> Queue Vision LLM
              </button>
              <button onClick={clearGalleryLlmContext} style={{ border: "1px solid var(--border-color)" }}>
                <X size={16} /> Clear LLM Context
              </button>
            </div>
          </div>
        ) : null}
      </section>
    );
  };

  const renderConnectorHealth = () => (
    <section style={{ padding: "1rem", background: "rgba(255,255,255,0.025)", border: "1px solid var(--border-color)", borderRadius: "12px", display: "flex", flexDirection: "column", gap: "0.85rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: "0.8rem", alignItems: "center", flexWrap: "wrap" }}>
        <strong style={{ display: "flex", alignItems: "center", gap: "0.45rem" }}><Server size={17} /> Connector Health</strong>
        <button onClick={() => void runConnectorHealthCheck()} disabled={connectorChecking} style={{ border: "1px solid var(--border-color)" }}>
          <RefreshCw size={16} className={connectorChecking ? "spin" : ""} /> Check Systems
        </button>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "repeat(2, minmax(0, 1fr))", gap: "0.65rem" }}>
        {(connectorHealth.length ? connectorHealth : [
          { label: "KoboldCpp", status: "warn", detail: "Run a health check to verify the LLM connector." },
          { label: "ComfyUI", status: "warn", detail: "Run a health check to verify image generation." },
          { label: "Media Indexer", status: "warn", detail: "Run a health check to verify gallery indexing." },
          { label: "Scan Worker", status: "warn", detail: "Run a health check to verify queue access." },
        ] as ConnectorHealthItem[]).map((item) => {
          const ok = item.status === "ok";
          const error = item.status === "error";
          return (
            <article key={item.label} style={{ padding: "0.8rem", border: "1px solid var(--border-color)", borderRadius: "10px", background: "var(--bg-secondary)", display: "grid", gap: "0.35rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.45rem", color: ok ? "var(--success)" : error ? "#ff9b9b" : "var(--warning)", fontWeight: 750 }}>
                {ok ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
                {item.label}
              </div>
              {item.endpoint && <span style={{ color: "var(--text-muted)", fontSize: "0.74rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{item.endpoint}</span>}
              <span style={{ color: "var(--text-secondary)", fontSize: "0.82rem", lineHeight: 1.45 }}>{item.detail}</span>
            </article>
          );
        })}
      </div>
    </section>
  );

  return (
    <div style={{ display: "flex", flexDirection: isMobile ? "column" : "row", height: "100%", overflow: "hidden", background: "var(--bg-main)" }}>
      {/* Sidebar Library */}
      <div style={{ width: "260px", minWidth: "260px", borderRight: "1px solid var(--border-color)", background: "var(--bg-secondary)", display: isMobile ? "none" : "flex", flexDirection: "column" }}>
         <div style={{ padding: "1.5rem 1.5rem 0.5rem", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h3 style={{ margin: 0, fontSize: "0.9rem", color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>{language === "fr" ? "Bibliotheque" : "Library"}</h3>
            <button onClick={() => { const name = prompt("Collection Name:"); if(name) createCollection(name); }} style={{ background: "none", border: "none", color: "var(--accent)", cursor: "pointer", display: "flex", alignItems: "center" }} title="New Collection">
               <Plus size={16} />
            </button>
         </div>
         <div style={{ display: "flex", flexDirection: "column", gap: "0.2rem", padding: "0 1rem", overflowY: "auto", flex: 1 }}>
            <button 
              onClick={() => {
                setActiveCollectionId(null);
                setActiveSourceId(null);
                setActiveTab("browse");
              }}
              style={{ textAlign: "left", background: activeCollectionId === null && activeSourceId === null ? "rgba(99,102,241,0.15)" : "transparent", color: activeCollectionId === null && activeSourceId === null ? "var(--accent)" : "var(--text-main)", border: "none", padding: "0.6rem 1rem", borderRadius: "6px", display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer", transition: "background 0.2s" }}
            >
              <Images size={16} /> {copy.allAssets}
            </button>
            <div style={{ margin: "1rem 0 0.5rem 0.5rem", fontSize: "0.75rem", color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase" }}>{copy.indexedSources}</div>
            {sources.map(source => (
              <button
                key={source.id}
                onClick={() => {
                  setActiveCollectionId(null);
                  setActiveSourceId(source.id);
                  setActiveTab("sources");
                  setSourceMessage(null);
                }}
                style={{ textAlign: "left", background: activeSourceId === source.id ? "rgba(99,102,241,0.15)" : "transparent", color: activeSourceId === source.id ? "var(--accent)" : "var(--text-secondary)", border: "none", padding: "0.6rem 1rem", borderRadius: "6px", display: "flex", flexDirection: "column", alignItems: "flex-start", gap: "0.15rem", cursor: "pointer", transition: "background 0.2s" }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", width: "100%" }}>
                  <FolderOpen size={16} />
                  <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{source.name}</span>
                </div>
                <span style={{ fontSize: "0.72rem", opacity: 0.7, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", width: "100%" }}>{source.display_root_path}</span>
                <span style={{ fontSize: "0.68rem", textTransform: "uppercase", letterSpacing: "0.04em", opacity: 0.5 }}>{source.status === "scanning" ? "scanning" : source.status}</span>
              </button>
            ))}
            <div style={{ margin: "1rem 0 0.5rem 0.5rem", fontSize: "0.75rem", color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase" }}>{copy.collections}</div>
            {collections.map(c => (
              <button 
                key={c.id}
                onClick={() => {
                  setActiveSourceId(null);
                  setActiveCollectionId(c.id);
                  setActiveTab("collections");
                }}
                style={{ textAlign: "left", background: activeCollectionId === c.id ? "rgba(99,102,241,0.15)" : "transparent", color: activeCollectionId === c.id ? "var(--accent)" : "var(--text-secondary)", border: "none", padding: "0.6rem 1rem", borderRadius: "6px", display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer", transition: "background 0.2s" }}
              >
                <FolderOpen size={16} />
                <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.name}</span>
                <span style={{ fontSize: "0.7rem", opacity: 0.5 }}>{c.asset_count}</span>
              </button>
            ))}
         </div>
      </div>

      {/* Main Gallery Area */}
      <div style={{ flex: 1, padding: isMobile ? "1rem" : "2rem", display: "flex", flexDirection: "column", gap: isMobile ? "1rem" : "1.5rem", overflowY: "auto", position: "relative" }}>
        {isMobile && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: "0.55rem" }}>
            <button onClick={() => setMobileLibraryOpen(true)} style={{ minHeight: 44, border: "1px solid var(--border-color)" }}>
              <PanelLeft size={16} /> {copy.library}
            </button>
            <button onClick={() => setMobileScanOpen(true)} style={{ minHeight: 44, border: "1px solid var(--border-color)" }}>
              <ListChecks size={16} /> Scan
            </button>
            <button onClick={() => setMobileFiltersOpen(true)} style={{ minHeight: 44, border: "1px solid var(--border-color)" }}>
              <Filter size={16} /> {copy.filters}
            </button>
          </div>
        )}
        {/* Header */}
      <div style={{ display: "flex", alignItems: isMobile ? "stretch" : "center", justifyContent: "space-between", gap: "1rem", flexDirection: isMobile ? "column" : "row" }}>
        <div>
          <h1 style={{ fontSize: "1.75rem", fontWeight: 700, margin: 0, letterSpacing: "-0.02em" }}>
            {copy.title}
          </h1>
          <p style={{ margin: "0.25rem 0 0", color: "var(--text-secondary)", fontSize: "0.9rem" }}>
            {activeSource
              ? isSourceRootBrowse && assetTotal !== null
                ? `${images.length}/${assetTotal} indexed images in this source · scan results appear progressively`
                : `${images.length} images in ${browseCurrentPath || "root"} · Read-only indexing for mounted folders`
              : `${images.length} ${copy.subtitle}`}
          </p>
        </div>
        <div style={{ display: isMobile ? "grid" : "flex", gridTemplateColumns: isMobile ? "repeat(2, minmax(0, 1fr))" : undefined, gap: "0.75rem", alignItems: "center", flexWrap: isMobile ? undefined : "wrap" }}>
          <button 
            onClick={() => setShowKeyboardHelp(h => !h)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.4rem",
              background: showKeyboardHelp ? "rgba(99, 102, 241, 0.15)" : "none",
              border: "1px solid var(--border-color)",
              color: showKeyboardHelp ? "var(--accent)" : "var(--text-secondary)"
            }}
            title="Keyboard Shortcuts Guide"
          >
            <Keyboard size={16} /> {copy.shortcuts}
          </button>
          
          {activeSourceId && (
            <button
              onClick={async () => {
                try {
                  setSourceMessage({ tone: "info", text: "Queueing a source rescan..." });
                  await queueSourceScan(activeSourceId);
                  setSourceMessage({ tone: "success", text: "Source rescan queued." });
                } catch (e) {
                  setSourceMessage({ tone: "error", text: e instanceof Error ? e.message : "Unable to queue a rescan." });
                }
              }}
              style={{ border: "1px solid var(--border-color)" }}
            >
              <RefreshCw size={16} /> Rescan Source
            </button>
          )}
          <button onClick={() => fileRef.current?.click()} disabled={uploading}>
            <UploadCloud size={16} /> {copy.uploadImages}
          </button>
          <button onClick={() => folderRef.current?.click()} disabled={uploading}>
            <Upload size={16} /> {copy.uploadFolder}
          </button>
          <input ref={fileRef} type="file" multiple accept="image/*" style={{ display: "none" }} onChange={e => e.target.files && handleUpload(e.target.files)} />
          <input ref={folderRef} type="file" multiple accept="image/*" {...({ webkitdirectory: "true", directory: "true" } as any)} style={{ display: "none" }} onChange={e => e.target.files && handleUpload(e.target.files)} />
        </div>
      </div>

      {!isMobile && renderGalleryCommandBar()}

      {isMobile && activeTab === "browse" && (
        <section style={{ padding: "0.85rem", background: "rgba(255,255,255,0.025)", border: "1px solid var(--border-color)", borderRadius: "12px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem", flexWrap: "wrap" }}>
          <span style={{ color: "var(--text-secondary)", fontSize: "0.84rem" }}>{assetTotal !== null ? `${images.length} / ${assetTotal}` : `${images.length}`} loaded</span>
          <button onClick={() => setMobileFiltersOpen(true)} style={{ border: "1px solid var(--border-color)" }}>
            <SlidersHorizontal size={16} /> {copy.viewControls}
          </button>
        </section>
      )}

      {renderSelectionRail()}

      {!isMobile && renderScanCommandCenter()}

      <nav style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "minmax(220px, 1fr) minmax(180px, 0.75fr) minmax(320px, 1.3fr)", gap: "0.55rem", padding: "0.5rem", background: "rgba(255,255,255,0.025)", border: "1px solid var(--border-color)", borderRadius: "14px" }}>
        {galleryTabGroups.map((group) => (
          <div key={group} style={{ display: "flex", flexDirection: "column", gap: "0.35rem", minWidth: 0 }}>
            <span style={{ color: "var(--text-muted)", fontSize: "0.68rem", fontWeight: 800, letterSpacing: "0.05em", textTransform: "uppercase", padding: "0 0.35rem" }}>{group}</span>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem" }}>
              {galleryTabs.filter((tab) => tab.group === group).map((tab) => {
                const Icon = tab.icon;
                const isActive = activeTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    style={{
                      flex: isMobile ? "1 1 130px" : "0 1 auto",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: "0.45rem",
                      minHeight: 38,
                      padding: "0.55rem 0.72rem",
                      borderRadius: "10px",
                      border: `1px solid ${isActive ? "rgba(99,102,241,0.35)" : "transparent"}`,
                      background: isActive ? "rgba(99,102,241,0.14)" : "transparent",
                      color: isActive ? "var(--accent)" : "var(--text-secondary)",
                      cursor: "pointer",
                      fontWeight: 700,
                      fontSize: "0.8rem",
                    }}
                  >
                    <Icon size={15} />
                    {tab.label}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {activeTab === "browse" && !isMobile && (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(260px, 0.85fr) minmax(320px, 1.4fr)", gap: "0.85rem" }}>
          <section style={{ padding: "1rem", background: "rgba(255,255,255,0.025)", border: "1px solid var(--border-color)", borderRadius: "12px", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <strong style={{ display: "flex", alignItems: "center", gap: "0.45rem" }}><SlidersHorizontal size={16} /> Current View</strong>
            <span style={{ color: "var(--text-secondary)", fontSize: "0.84rem" }}>
              {clientFilters.hideNsfw ? copy.hideNsfw : "NSFW visible"} · {clientFilters.indexedOnly ? copy.indexedOnly : copy.liveIndexed} · {SORT_MODE_LABELS[sortMode]}
            </span>
            {activeTagFilter && (
              <button
                onClick={() => {
                  setMetadataFilters((current) => ({
                    ...current,
                    tags: mergeUniqueTags(current.tags).filter((tag) => tag !== activeTagFilter).join(", "),
                  }));
                  setActiveTagFilter(null);
                }}
                style={{ alignSelf: "flex-start", border: "1px solid rgba(99,102,241,0.28)", background: "rgba(99,102,241,0.1)", color: "var(--accent)", borderRadius: "999px", padding: "0.3rem 0.55rem", fontSize: "0.74rem" }}
                title="Clear active tag filter"
              >
                <Tags size={12} /> {activeTagFilter}
              </button>
            )}
          </section>

          <section style={{ padding: "1rem", background: "rgba(255,255,255,0.025)", border: "1px solid var(--border-color)", borderRadius: "12px", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem" }}>
              <strong style={{ display: "flex", alignItems: "center", gap: "0.45rem" }}><Tags size={16} /> Top Prompt Tags</strong>
              {activeTagFilter && (
                <button
                  onClick={() => {
                    setMetadataFilters((current) => ({
                      ...current,
                      tags: mergeUniqueTags(current.tags).filter((tag) => tag !== activeTagFilter).join(", "),
                    }));
                    setActiveTagFilter(null);
                  }}
                  style={{ border: "1px solid var(--border-color)", color: "var(--text-secondary)" }}
                >
                  Clear
                </button>
              )}
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem", maxHeight: "88px", overflowY: "auto" }}>
              {topTags.length ? topTags.map((tag) => (
                <button
                  key={tag.tag}
                  onClick={() => setActiveTagFilter(activeTagFilter === tag.tag ? null : normalizeTagValue(tag.tag))}
                  style={{
                    border: "1px solid var(--border-color)",
                    background: activeTagFilter === tag.tag ? "rgba(99,102,241,0.16)" : "rgba(255,255,255,0.025)",
                    color: activeTagFilter === tag.tag ? "var(--accent)" : "var(--text-secondary)",
                    borderRadius: "999px",
                    padding: "0.3rem 0.55rem",
                    fontSize: "0.72rem",
                    cursor: "pointer",
                  }}
                  title={`${tag.count} assets`}
                >
                  {tag.tag} · {tag.count}
                </button>
              )) : <span style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>Tags appear after metadata scans finish.</span>}
            </div>
          </section>
        </div>
      )}

      {activeTab === "metadata" && (
        <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1.4fr 1fr", gap: "0.85rem" }}>
          <section style={{ padding: "1rem", background: "rgba(255,255,255,0.025)", border: "1px solid var(--border-color)", borderRadius: "12px", display: "grid", gridTemplateColumns: isMobile ? "1fr" : "repeat(4, minmax(0, 1fr))", gap: "0.75rem" }}>
            {([
              ["manual", "Manual Search", "free text in prompt, filename, metadata"],
              ["tags", "Tags", "masterpiece, large breasts, outdoor"],
              ["characters", "Characters", "character names, species, roles"],
              ["clothes", "Clothes", "dress, armor, school uniform"],
              ["location", "Location", "beach, bedroom, city street"],
              ["position", "Position / Pose", "sitting, from behind, close-up"],
            ] as Array<[keyof MetadataFilters, string, string]>).map(([key, label, placeholder]) => (
              <label key={key} style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
                <span style={{ color: "var(--text-muted)", fontSize: "0.72rem", textTransform: "uppercase" }}>{label}</span>
                <input
                  value={String(metadataFilters[key] || "")}
                  onChange={(event) => setMetadataFilters((current) => ({ ...current, [key]: event.target.value }))}
                  placeholder={placeholder}
                  style={{ background: "var(--bg-main)", border: "1px solid var(--border-color)", color: "var(--text-main)", borderRadius: "8px", padding: "0.62rem 0.7rem" }}
                />
              </label>
            ))}
            <label style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
              <span style={{ color: "var(--text-muted)", fontSize: "0.72rem", textTransform: "uppercase" }}>Type</span>
              <select value={metadataFilters.media_type} onChange={(event) => setMetadataFilters((current) => ({ ...current, media_type: event.target.value as MetadataFilters["media_type"] }))}>
                <option value="">All</option>
                <option value="image">Image</option>
                <option value="video">Video</option>
              </select>
            </label>
            {([
              ["camera_make", "Camera Make"],
              ["camera_model", "Camera Model"],
              ["year", "Year"],
              ["width_min", "Width Min"],
              ["width_max", "Width Max"],
              ["height_min", "Height Min"],
              ["height_max", "Height Max"],
            ] as Array<[keyof MetadataFilters, string]>).map(([key, label]) => (
              <label key={key} style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
                <span style={{ color: "var(--text-muted)", fontSize: "0.72rem", textTransform: "uppercase" }}>{label}</span>
                <input
                  value={String(metadataFilters[key] || "")}
                  onChange={(event) => setMetadataFilters((current) => ({ ...current, [key]: event.target.value }))}
                  style={{ background: "var(--bg-main)", border: "1px solid var(--border-color)", color: "var(--text-main)", borderRadius: "8px", padding: "0.62rem 0.7rem" }}
                />
              </label>
            ))}
            <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", alignSelf: "end", color: "var(--text-secondary)" }}>
              <input
                type="checkbox"
                checked={metadataFilters.has_gps}
                onChange={(event) => setMetadataFilters((current) => ({ ...current, has_gps: event.target.checked }))}
              />
              Has GPS
            </label>
            <button onClick={() => setMetadataFilters(DEFAULT_METADATA_FILTERS)} style={{ border: "1px solid var(--border-color)", alignSelf: "end" }}>
              Reset Metadata Filters
            </button>
          </section>

          <section style={{ padding: "1rem", background: "rgba(255,255,255,0.025)", border: "1px solid var(--border-color)", borderRadius: "12px", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <strong style={{ display: "flex", alignItems: "center", gap: "0.45rem" }}><Sparkles size={16} /> Natural-Language Search</strong>
            <input
              value={naturalQuery}
              onChange={(event) => setNaturalQuery(event.target.value)}
              onKeyDown={(event) => { if (event.key === "Enter") void runNaturalLanguageSearch(); }}
              placeholder="red-lit portrait with cyberpunk skyline"
              style={{ background: "var(--bg-main)", border: "1px solid var(--border-color)", color: "var(--text-main)", borderRadius: "8px", padding: "0.7rem 0.85rem" }}
            />
            <button onClick={() => void runNaturalLanguageSearch()}>
              <Search size={16} /> Search by Meaning
            </button>
          </section>
        </div>
      )}

      {activeTab === "collections" && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "0.85rem" }}>
          {collections.map((collection) => (
            <article
              key={collection.id}
              style={{ textAlign: "left", border: "1px solid var(--border-color)", background: activeCollectionId === collection.id ? "rgba(99,102,241,0.14)" : "rgba(255,255,255,0.025)", borderRadius: "12px", padding: "1rem", color: "var(--text-main)", display: "grid", gap: "0.75rem" }}
            >
              <div>
                <strong>{collection.name}</strong>
                <p style={{ margin: "0.35rem 0 0", color: "var(--text-secondary)", fontSize: "0.82rem" }}>{collection.asset_count} assets</p>
              </div>
              <div style={{ display: "flex", gap: "0.45rem", flexWrap: "wrap" }}>
                <button
                  onClick={() => {
                    setActiveSourceId(null);
                    setActiveCollectionId(collection.id);
                  }}
                  className={activeCollectionId === collection.id ? "primary" : ""}
                  style={{ border: "1px solid var(--border-color)" }}
                >
                  <FolderOpen size={16} /> Open
                </button>
                <button onClick={() => void sendCollectionToDataset(collection)} disabled={datasetImportingCollectionId === collection.id || collection.asset_count === 0} style={{ border: "1px solid var(--border-color)" }}>
                  {datasetImportingCollectionId === collection.id ? <Loader2 className="spin" size={16} /> : <Database size={16} />}
                  Send to Dataset
                </button>
                <button onClick={() => void queueCollectionScan(collection, scanModeSelection)} disabled={collection.asset_count === 0 || scanCommandBusy !== null} style={{ border: "1px solid var(--border-color)" }}>
                  <ListChecks size={16} /> Scan Collection
                </button>
              </div>
            </article>
          ))}
          <button onClick={() => { const name = prompt("Collection Name:"); if (name) void createCollection(name); }} style={{ border: "1px dashed var(--border-color)", background: "transparent", borderRadius: "12px", padding: "1rem", color: "var(--accent)", cursor: "pointer" }}>
            <Plus size={16} /> New Collection
          </button>
        </div>
      )}

      {activeTab === "jobs" && (
        <section style={{ padding: "1rem", background: "rgba(255,255,255,0.025)", border: "1px solid var(--border-color)", borderRadius: "12px", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "1rem" }}>
            <strong>Scan Jobs</strong>
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <button onClick={() => void fetchScanJobs()} style={{ border: "1px solid var(--border-color)" }}>
                <RefreshCw size={16} /> Refresh Jobs
              </button>
              <button onClick={() => void clearFinishedScanJobs("succeeded")} style={{ border: "1px solid var(--border-color)" }}>
                <Trash2 size={16} /> Clear Succeeded
              </button>
              <button onClick={() => void clearFinishedScanJobs("failed")} style={{ border: "1px solid var(--border-color)" }}>
                <Trash2 size={16} /> Clear Failed
              </button>
              <button onClick={() => void clearFinishedScanJobs("cancelled")} style={{ border: "1px solid var(--border-color)" }}>
                <Trash2 size={16} /> Clear Cancelled
              </button>
            </div>
          </div>
          {renderScanCommandCenter()}
          {scanJobs.length ? scanJobs.map((job) => (
            <article key={job.id} style={{ border: "1px solid var(--border-color)", borderRadius: "10px", padding: "0.85rem", background: "var(--bg-secondary)", display: "flex", flexDirection: "column", gap: "0.55rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", color: "var(--text-main)" }}>
                <span style={{ fontFamily: "monospace", fontSize: "0.78rem" }}>{job.id}</span>
                <span style={{ color: job.status === "failed" ? "#ff9b9b" : "var(--accent)", textTransform: "uppercase", fontSize: "0.72rem", letterSpacing: "0.05em" }}>{job.status}</span>
              </div>
              <div style={{ height: "8px", borderRadius: "999px", background: "rgba(255,255,255,0.08)", overflow: "hidden" }}>
                <div style={{ width: `${Math.min(100, Math.max(0, job.progress || 0))}%`, height: "100%", background: "linear-gradient(90deg, #3b82f6, #60a5fa)" }} />
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem", color: "var(--text-secondary)", fontSize: "0.78rem" }}>
                <span>Target {job.target_type || "source"}</span>
                <span>Mode {job.scan_mode ? SCAN_MODE_LABELS[job.scan_mode] || job.scan_mode : "Basic"}</span>
                {job.stage && <span>Stage {job.stage}</span>}
                <span>Scanned {job.scanned_count}{job.total_count ? `/${job.total_count}` : ""}</span>
                <span>New {job.new_count}</span>
                <span>Updated {job.updated_count}</span>
                <span>Deleted {job.deleted_count}</span>
                <span>Errors {job.error_count}</span>
              </div>
              {job.path_filter && <span style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>Path filter: {job.path_filter}</span>}
              {job.message && <span style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>{job.message}</span>}
              <div style={{ display: "flex", gap: "0.45rem", flexWrap: "wrap" }}>
              {(job.status === "queued" || job.status === "running") ? (
                <button onClick={() => void cancelScanJob(job.id)} style={{ alignSelf: "flex-start", border: "1px solid var(--border-color)" }}>
                  Cancel Scan
                </button>
              ) : null}
              {job.status === "failed" && (
                <button onClick={() => void retryScanJob(job)} style={{ alignSelf: "flex-start", border: "1px solid var(--border-color)" }}>
                  <RefreshCw size={16} /> Retry Failed
                </button>
              )}
              {job.error_count > 0 && (
                <button onClick={() => void loadScanJobErrors(job.id)} style={{ alignSelf: "flex-start", border: "1px solid var(--border-color)" }}>
                  <AlertTriangle size={16} /> {expandedScanJobId === job.id ? "Hide Errors" : "Show Errors"}
                </button>
              )}
              </div>
              {expandedScanJobId === job.id && (
                <div style={{ border: "1px solid rgba(255,255,255,0.08)", borderRadius: "8px", padding: "0.65rem", display: "grid", gap: "0.45rem", maxHeight: "220px", overflowY: "auto" }}>
                  {(scanJobErrors[job.id] || []).length ? (scanJobErrors[job.id] || []).map((entry, index) => (
                    <div key={entry.id || index} style={{ color: "var(--text-secondary)", fontSize: "0.78rem", lineHeight: 1.45 }}>
                      <strong style={{ color: "#ffb3b3" }}>{entry.stage || "scan"}</strong> {entry.relative_path || entry.path || "unknown path"}: {entry.error}
                    </div>
                  )) : <span style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>No detailed errors recorded.</span>}
                </div>
              )}
            </article>
          )) : <span style={{ color: "var(--text-muted)" }}>No scan jobs yet.</span>}
        </section>
      )}

      {activeTab === "tools" && (
        <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "0.85rem" }}>
          {renderConnectorHealth()}
          {renderScanCommandCenter(true)}
          <div style={{ padding: "1rem", background: "rgba(255,255,255,0.025)", border: "1px solid var(--border-color)", borderRadius: "12px", display: "flex", flexDirection: "column", gap: "0.65rem" }}>
            <strong>Selected Assets</strong>
            <span style={{ color: "var(--text-secondary)", fontSize: "0.86rem" }}>{selectedImages.length} selected · {selectedIds.length} indexed</span>
            <button onClick={() => void annotateSelected()} disabled={!selectedIds.length} style={{ border: "1px solid var(--border-color)" }}>
              <Tags size={16} /> Bulk Add Tag
            </button>
            <button onClick={() => setComparerOpen(true)} disabled={selectedImages.length !== 2} className={selectedImages.length === 2 ? "primary" : ""}>
              <GitCompare size={16} /> Compare Two Selected
            </button>
          </div>
          <div style={{ padding: "1rem", background: "rgba(255,255,255,0.025)", border: "1px solid var(--border-color)", borderRadius: "12px", display: "flex", flexDirection: "column", gap: "0.65rem" }}>
            <strong>Focused Image Tools</strong>
            <span style={{ color: "var(--text-secondary)", fontSize: "0.86rem" }}>{toolImage ? toolImage.name : "Select or open an image to use focused tools."}</span>
            <button onClick={() => toolImage && copyPromptTags(toolImage)} disabled={!toolImage} style={{ border: "1px solid var(--border-color)" }}>
              <Tags size={16} /> Copy Prompt Tags
            </button>
            <button onClick={() => toolImage && downloadWorkflow(toolImage)} disabled={!toolImage?.workflow_export_available} style={{ border: "1px solid var(--border-color)" }}>
              <Download size={16} /> Export Stored Workflow
            </button>
            <button onClick={() => toolImage && downloadWorkflow(toolImage, true)} disabled={!toolImage?.id} style={{ border: "1px solid var(--border-color)" }}>
              <Download size={16} /> Re-Extract Workflow From File
            </button>
            <button onClick={() => toolImage && queueImageScan(toolImage, "metadata")} disabled={!toolImage?.id && (!toolImage?.source_id || !toolImage?.relative_path)} style={{ border: "1px solid var(--border-color)" }}>
              <Database size={16} /> Scan Metadata
            </button>
            <button onClick={() => toolImage && queueImageScan(toolImage, scanModeSelection)} disabled={!toolImage?.id && (!toolImage?.source_id || !toolImage?.relative_path)} style={{ border: "1px solid var(--border-color)" }}>
              <Sparkles size={16} /> Scan Focused
            </button>
            <button onClick={() => toolImage && queueImageScan(toolImage, "vision_llm")} disabled={!toolImage?.id} style={{ border: "1px solid var(--border-color)" }}>
              <Sparkles size={16} /> Queue Vision LLM
            </button>
            <button onClick={clearGalleryLlmContext} style={{ border: "1px solid var(--border-color)" }}>
              <X size={16} /> Clear LLM Context
            </button>
          </div>
          <div style={{ padding: "1rem", background: "rgba(255,255,255,0.025)", border: "1px solid var(--border-color)", borderRadius: "12px", display: "flex", flexDirection: "column", gap: "0.65rem" }}>
            <strong>Imported From Previous App</strong>
            <span style={{ color: "var(--text-secondary)", fontSize: "0.86rem", lineHeight: 1.5 }}>
              Source scans, metadata extraction, prompt tags, workflow export, deep zoom, compare, bulk annotation, collections, smart-album-style saved searches, tags, and scan job tracking now run from the local `media-indexer` import.
            </span>
          </div>
        </section>
      )}

      {toolsMessage && (
        <div style={{ padding: "0.75rem 0.9rem", borderRadius: "10px", border: "1px solid rgba(99,102,241,0.28)", background: "rgba(99,102,241,0.08)", color: "var(--text-main)", fontSize: "0.9rem" }}>
          {toolsMessage}
        </div>
      )}

      {activeTab === "sources" && (
      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "minmax(180px, 240px) minmax(260px, 1fr) auto", gap: "0.75rem", padding: "1rem", background: "rgba(255,255,255,0.025)", border: "1px solid var(--border-color)", borderRadius: "12px", alignItems: "end" }}>
        <label style={{ display: "flex", flexDirection: "column", gap: "0.45rem", minWidth: 0 }}>
          <span style={{ fontSize: "0.76rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Source Name</span>
          <input
            type="text"
            value={sourceName}
            onChange={(e) => setSourceName(e.target.value)}
            placeholder="Optional label"
            style={{ background: "var(--bg-main)", border: "1px solid var(--border-color)", color: "var(--text-main)", borderRadius: "8px", padding: "0.7rem 0.85rem", outline: "none" }}
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: "0.45rem", minWidth: 0 }}>
          <span style={{ fontSize: "0.76rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Windows Folder Path</span>
          <input
            type="text"
            value={sourcePath}
            onChange={(e) => setSourcePath(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !sourceSubmitting) void createMountedSource(); }}
            placeholder={"C:\\Images\\ProjectA or Z:\\Archive\\Shots"}
            style={{ background: "var(--bg-main)", border: "1px solid var(--border-color)", color: "var(--text-main)", borderRadius: "8px", padding: "0.7rem 0.85rem", outline: "none" }}
          />
        </label>
        <button onClick={() => void createMountedSource()} disabled={sourceSubmitting} style={{ whiteSpace: "nowrap", height: "fit-content" }}>
          <FolderOpen size={16} /> {sourceSubmitting ? "Indexing..." : "Add Read-Only Folder"}
        </button>
        <div style={{ gridColumn: "1 / -1", color: "var(--text-secondary)", fontSize: "0.86rem", lineHeight: 1.5 }}>
          Paste a Windows path for a local folder or a mapped network drive. The gallery only reads the originals; metadata, previews, and the search index are stored separately.
        </div>
        {sourceMessage && (
          <div
            style={{
              gridColumn: "1 / -1",
              padding: "0.75rem 0.9rem",
              borderRadius: "10px",
              border: sourceMessage.tone === "error" ? "1px solid rgba(255,107,107,0.35)" : "1px solid rgba(99,102,241,0.28)",
              background: sourceMessage.tone === "error" ? "rgba(255,107,107,0.08)" : "rgba(99,102,241,0.08)",
              color: sourceMessage.tone === "error" ? "#ffb3b3" : "var(--text-main)",
              fontSize: "0.9rem",
            }}
          >
            {sourceMessage.text}
          </div>
        )}
      </div>
      )}

      {activeTab === "sources" && activeSourceId && activeSource && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.9rem", padding: "1rem", background: "rgba(255,255,255,0.025)", border: "1px solid var(--border-color)", borderRadius: "12px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "1rem", flexWrap: "wrap" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.55rem", flexWrap: "wrap" }}>
                <strong style={{ fontSize: "1rem" }}>{activeSource.name}</strong>
                <span style={{ fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--accent)" }}>Live Browse</span>
                {showSourceScanState ? (
                  <span style={{ fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "#9ad1ff" }}>
                    {activeScanJob?.status === "queued" ? "Queued" : "Scanning"}
                  </span>
                ) : null}
              </div>
              <span style={{ color: "var(--text-secondary)", fontSize: "0.88rem" }}>{activeSource.display_root_path}</span>
              <span style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>
                {sourceDirectories.length} folders · {sourceFiles.length} files · {sourceImageEntries.length} images in this view
              </span>
            </div>
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              {(["basic", "metadata", "ai"] as ScanMode[]).map((mode) => (
                <button
                  key={mode}
                  onClick={async () => {
                    try {
                      setSourceMessage({ tone: "info", text: `Queueing ${mode} scan${browseCurrentPath ? ` for ${browseCurrentPath}` : ""}...` });
                      await queueSourceScan(activeSource.id, mode, browseCurrentPath || null);
                      setSourceMessage({ tone: "success", text: `${mode} scan queued.` });
                      setActiveTab("jobs");
                    } catch (error) {
                      setSourceMessage({ tone: "error", text: error instanceof Error ? error.message : "Unable to queue scan." });
                    }
                  }}
                  style={{ border: "1px solid var(--border-color)" }}
                  title={mode === "basic" ? "Fast file discovery only" : mode === "metadata" ? "Parse embedded metadata for this source or folder" : "Run CLIP / AI enrichment for this source or folder"}
                >
                  <RefreshCw size={16} />
                  {mode === "basic" ? copy.scanBasic : mode === "metadata" ? copy.scanMetadata : copy.scanAi}
                </button>
              ))}
              {browseParentPath !== null && (
                <button
                  onClick={() => setCurrentSourcePath(browseParentPath || "")}
                  style={{ border: "1px solid var(--border-color)" }}
                >
                  <FolderOpen size={16} /> Up One Folder
                </button>
              )}
              <button
                onClick={() => setCurrentSourcePath("")}
                disabled={!browseCurrentPath}
                style={{ border: "1px solid var(--border-color)" }}
              >
                <Images size={16} /> Browse Root
              </button>
            </div>
          </div>

          {showSourceScanState && (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", padding: "0.9rem 1rem", background: "rgba(84, 160, 255, 0.08)", border: "1px solid rgba(84, 160, 255, 0.22)", borderRadius: "10px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap", color: "var(--text-main)", fontSize: "0.92rem" }}>
                <span>
                  {(scanProgress?.status ?? activeScanJob?.status) === "queued"
                    ? "Scan is queued and waiting for the worker."
                    : `Scanning now: ${scanProcessed}${scanTotal ? `/${scanTotal}` : ""} files checked, ${scanPercent}% complete${scanStage ? ` (${scanStage})` : ""}.`}
                </span>
                <span style={{ color: "var(--text-secondary)" }}>
                  New {scanNewCount} · Updated {scanUpdatedCount} · Deleted {scanDeletedCount} · Errors {scanErrorCount}
                </span>
              </div>
              <div style={{ width: "100%", height: "10px", borderRadius: "999px", background: "rgba(255,255,255,0.08)", overflow: "hidden" }}>
                <div style={{ width: `${Math.max(4, Math.min(100, scanPercent || 0))}%`, height: "100%", borderRadius: "999px", background: "linear-gradient(90deg, #3b82f6, #60a5fa)", transition: "width 0.4s ease" }} />
              </div>
              {scanMessage && (
                <span style={{ color: "var(--text-secondary)", fontSize: "0.82rem" }}>{scanMessage}</span>
              )}
            </div>
          )}

          {sourceBrowse && (
            <>
              {sourceTreeNodes.length > 1 && (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.55rem", padding: "0.85rem 0.95rem", background: "rgba(255,255,255,0.02)", border: "1px solid var(--border-color)", borderRadius: "10px" }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap" }}>
                    <strong style={{ fontSize: "0.82rem", color: "var(--text-main)", letterSpacing: "0.03em", textTransform: "uppercase" }}>Folder Explorer</strong>
                    <span style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>Lazy-loaded tree for large sources</span>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.3rem", maxHeight: "220px", overflowY: "auto", paddingRight: "0.25rem" }}>
                    {sourceTreeNodes.map((node) => {
                      const isActive = node.path === browseCurrentPath;
                      const hasChildren = node.depth === 0 || !node.loaded || node.children.length > 0;
                      return (
                        <button
                          key={node.path || "__root__"}
                          onClick={() => void handleSourceTreeClick(node)}
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "0.45rem",
                            padding: "0.45rem 0.6rem",
                            paddingLeft: `${0.6 + node.depth * 0.85}rem`,
                            textAlign: "left",
                            border: "1px solid rgba(255,255,255,0.04)",
                            borderRadius: "8px",
                            background: isActive ? "rgba(99,102,241,0.14)" : "transparent",
                            color: isActive ? "var(--accent)" : "var(--text-secondary)",
                            cursor: "pointer",
                          }}
                        >
                          <span style={{ width: "0.85rem", opacity: hasChildren ? 0.75 : 0.22 }}>
                            {hasChildren ? (node.expanded ? "▾" : "▸") : "•"}
                          </span>
                          <FolderOpen size={14} />
                          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{node.name}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", alignItems: "center" }}>
                {browseBreadcrumbs.map((breadcrumb, index) => {
                  const isActive = breadcrumb.path === browseCurrentPath;
                  return (
                    <React.Fragment key={`${breadcrumb.path}-${index}`}>
                      {index > 0 && <span style={{ color: "var(--text-muted)" }}>/</span>}
                      <button
                        onClick={() => setCurrentSourcePath(breadcrumb.path)}
                        disabled={isActive}
                        style={{
                          background: isActive ? "rgba(99,102,241,0.15)" : "transparent",
                          color: isActive ? "var(--accent)" : "var(--text-secondary)",
                          border: "1px solid var(--border-color)",
                          borderRadius: "999px",
                          padding: "0.35rem 0.7rem",
                          cursor: isActive ? "default" : "pointer",
                        }}
                      >
                        {breadcrumb.label}
                      </button>
                    </React.Fragment>
                  );
                })}
              </div>

              {sourceDirectories.length > 0 ? (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: "0.75rem" }}>
                  {sourceDirectories.map((directory) => (
                    <button
                      key={directory.relative_path}
                      onClick={() => setCurrentSourcePath(directory.relative_path)}
                      style={{
                        textAlign: "left",
                        border: "1px solid var(--border-color)",
                        borderRadius: "10px",
                        background: "var(--bg-secondary)",
                        padding: "0.9rem 1rem",
                        display: "flex",
                        flexDirection: "column",
                        gap: "0.35rem",
                        cursor: "pointer",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", color: "var(--text-main)", fontWeight: 600 }}>
                        <FolderOpen size={16} />
                        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{directory.name}</span>
                      </div>
                      <span style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>{directory.relative_path || "Root"}</span>
                    </button>
                  ))}
                </div>
              ) : (
                <div style={{ color: "var(--text-muted)", fontSize: "0.86rem" }}>
                  No subfolders in this location. The image grid below is showing this folder’s live contents.
                </div>
              )}
            </>
          )}
        </div>
      )}

      {uploading && (
        <div style={{ padding: "0.75rem 1rem", background: "rgba(99,102,241,0.1)", border: "1px solid rgba(99,102,241,0.3)", borderRadius: "8px", color: "var(--accent)", fontSize: "0.9rem", textAlign: "center" }}>
          Uploading image library assets…
        </div>
      )}

      {/* Keyboard Shortcuts Help Panel */}
      {showKeyboardHelp && (
        <div 
          className="panel form-panel" 
          style={{ 
            background: "var(--bg-secondary)", 
            padding: "1rem", 
            borderRadius: "8px", 
            border: "1px solid var(--border-color)",
            animation: "fadeIn 0.2s ease-out"
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
            <strong style={{ fontSize: "0.85rem", color: "var(--accent)" }}>Keyboard Shortcuts Reference</strong>
            <button onClick={() => setShowKeyboardHelp(false)} style={{ background: "none", border: "none", color: "var(--text-secondary)", cursor: "pointer" }}><X size={14} /></button>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "1rem", fontSize: "0.8rem", color: "var(--text-secondary)" }}>
            <div><kbd style={{ background: "var(--bg-main)", border: "1px solid var(--border-color)", padding: "0.1rem 0.3rem", borderRadius: "4px" }}>Esc</kbd> Close current overlay / compare</div>
            <div><kbd style={{ background: "var(--bg-main)", border: "1px solid var(--border-color)", padding: "0.1rem 0.3rem", borderRadius: "4px" }}>→</kbd> Next image inside explorer</div>
            <div><kbd style={{ background: "var(--bg-main)", border: "1px solid var(--border-color)", padding: "0.1rem 0.3rem", borderRadius: "4px" }}>←</kbd> Previous image inside explorer</div>
          </div>
        </div>
      )}

      {/* Sync Comparer Panel Area */}
      {comparerOpen && comparerImgs.length === 2 && canUsePortal
        ? createPortal(
            <div
              onClick={(event) => {
                if (event.target === event.currentTarget) setComparerOpen(false);
              }}
              style={{
                position: "fixed",
                inset: 0,
                background: "rgba(4, 4, 8, 0.86)",
                backdropFilter: "blur(14px)",
                zIndex: 20000,
                padding: "1.25rem",
                display: "flex",
                alignItems: "stretch",
                justifyContent: "center",
              }}
            >
              <div style={{ width: "min(1440px, 100%)", maxHeight: "100%", overflow: "auto" }}>
                <CompareWorkspace
                  images={[comparerImgs[0], comparerImgs[1]]}
                  onClose={() => setComparerOpen(false)}
                />
              </div>
            </div>,
            document.body,
          )
        : null}

      {/* Gallery Grid Display */}
      {loading && images.length === 0 ? (
        <div style={{ display: "grid", gridTemplateColumns: isMobile ? "repeat(2, minmax(0, 1fr))" : "repeat(auto-fill, minmax(220px, 1fr))", gap: isMobile ? "0.65rem" : "1rem" }}>
          {Array.from({ length: isMobile ? 6 : 12 }).map((_, index) => (
            <div key={index} style={{ aspectRatio: "1 / 1.24", borderRadius: "10px", border: "1px solid var(--border-color)", background: "linear-gradient(110deg, rgba(255,255,255,0.035), rgba(255,255,255,0.08), rgba(255,255,255,0.035))", opacity: 0.8 }} />
          ))}
        </div>
      ) : images.length === 0 && !loading ? (
        <div style={{ textAlign: "center", padding: "6rem 2rem", color: "var(--text-muted)", display: "flex", flexDirection: "column", alignItems: "center", gap: "1rem" }}>
          <Images size={64} style={{ opacity: 0.15 }} />
          {activeSource ? (
            <p style={{ margin: 0, fontSize: "1rem" }}>
              {`No images are visible in ${browseCurrentPath || "this folder"} yet. Try another subfolder, wait for the scan, or use live browse to navigate deeper.`}
            </p>
          ) : (
            <p style={{ margin: 0, fontSize: "1rem" }}>Gallery is empty.<br />Generate images from the Wildcards Sandbox or Settings, or upload images above.</p>
          )}
        </div>
      ) : (
        <>
        <VirtuosoGrid
          useWindowScroll
          style={{ width: "100%", height: "100%" }}
          totalCount={images.length}
          components={galleryGridComponents}
          computeItemKey={(index) => getSelectionKey(images[index])}
          itemContent={(index) => {
            const img = images[index];
            const isSelected = selectedKeys.includes(getSelectionKey(img));
            const displayPrompt = img.metadata?.processed_prompt || img.metadata?.prompt || "";
            const safetyScanned = Boolean(img.metadata?.safety_quality_scanned_at || img.metadata?.quality_scanned_at);
            const isNsfw = isNsfwImage(img);
            const openMediaDetails = (event: React.MouseEvent<HTMLImageElement | HTMLVideoElement>) => {
              if (longPressTriggered.current) {
                longPressTriggered.current = false;
                event.preventDefault();
                return;
              }
              void openImageDetails(img);
            };
            return (
              <div 
                key={img.name} 
                className="mklan-gallery-card"
                data-gallery-card="true"
                onContextMenu={(event) => {
                  event.preventDefault();
                  setContextMenu({ image: img, x: event.clientX, y: event.clientY });
                }}
                onTouchStart={(event) => {
                  if (longPressTimer.current) window.clearTimeout(longPressTimer.current);
                  longPressTriggered.current = false;
                  const touch = event.touches[0];
                  longPressTimer.current = window.setTimeout(() => {
                    longPressTriggered.current = true;
                    setContextMenu({ image: img, x: touch.clientX, y: touch.clientY });
                  }, 460);
                }}
                onTouchEnd={() => {
                  if (longPressTimer.current) {
                    window.clearTimeout(longPressTimer.current);
                    longPressTimer.current = null;
                  }
                }}
                onTouchCancel={() => {
                  if (longPressTimer.current) {
                    window.clearTimeout(longPressTimer.current);
                    longPressTimer.current = null;
                  }
                }}
                style={{
                  border: `1px solid ${isSelected ? "var(--accent)" : "var(--border-color)"}`,
                  borderRadius: isMobile ? "8px" : "10px",
                  overflow: "hidden",
                  background: "var(--bg-secondary)",
                  display: "flex",
                  flexDirection: "column",
                  transition: "box-shadow 0.2s, border-color 0.2s",
                  boxShadow: isSelected ? "0 0 0 2px var(--accent-glow)" : "none",
                  height: "100%"
                }}
              >
                {/* Image Stage */}
                <div style={{ position: "relative", width: "100%", paddingTop: "100%", background: "#0b0b0d" }}>
                  {img.media_type === "video" ? (
                    <video
                      src={img.fullUrl || img.url}
                      onClick={openMediaDetails}
                      muted
                      playsInline
                      preload="metadata"
                      style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", objectFit: "cover", cursor: "zoom-in" }}
                    />
                  ) : (
                    <img
                      src={img.url}
                      alt={img.metadata?.prompt || img.name}
                      onClick={openMediaDetails}
                      loading="lazy"
                      style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", objectFit: "cover", cursor: "zoom-in" }}
                    />
                  )}
                  {/* Circular selector */}
                  <label style={{ position: "absolute", top: "0.5rem", left: "0.5rem", zIndex: 5, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", width: "22px", height: "22px", background: isSelected ? "var(--accent)" : "rgba(0,0,0,0.6)", borderRadius: "50%", border: `1px solid ${isSelected ? "var(--accent)" : "rgba(255,255,255,0.3)"}`, transition: "background 0.15s" }}>
                    <input type="checkbox" checked={isSelected} onChange={() => toggleSelect(img)} style={{ display: "none" }} />
                    {isSelected && <span style={{ color: "#fff", fontSize: "0.75rem", fontWeight: 700 }}>✓</span>}
                  </label>
                  {/* Action overlays */}
                  <div style={{ position: "absolute", top: "0.5rem", right: "0.5rem", display: "flex", gap: "0.25rem", flexWrap: "wrap", justifyContent: "flex-end", maxWidth: "calc(100% - 3.2rem)", zIndex: 6 }}>
                    {img.origin === "mounted" && (
                      <span
                        style={{
                      background: img.index_state === "indexed" ? "rgba(37, 99, 235, 0.82)" : "rgba(15, 23, 42, 0.72)",
                          border: "1px solid rgba(255,255,255,0.12)",
                          color: "#fff",
                          padding: "0.28rem 0.45rem",
                          borderRadius: "999px",
                          fontSize: "0.62rem",
                          textTransform: "uppercase",
                          letterSpacing: "0.05em",
                        }}
                        title={img.index_state === "indexed" ? "Indexed and available in the media database." : "Visible from the live folder browser while indexing catches up."}
                      >
                        {img.index_state === "indexed" ? "Indexed" : "Live"}
                      </span>
                    )}
                    {safetyScanned && (
                      <span
                        style={{
                          background: isNsfw ? "rgba(220, 38, 38, 0.84)" : "rgba(22, 163, 74, 0.78)",
                          border: "1px solid rgba(255,255,255,0.14)",
                          color: "#fff",
                          padding: "0.28rem 0.45rem",
                          borderRadius: "999px",
                          fontSize: "0.62rem",
                          textTransform: "uppercase",
                          letterSpacing: "0.05em",
                        }}
                        title={isNsfw ? "Safety scan detected NSFW signals." : "Safety scan completed without NSFW signals."}
                      >
                        {isNsfw ? "NSFW" : "Safe"}
                      </span>
                    )}
                    <button onClick={() => void openImageDetails(img)} style={{ background: "rgba(0,0,0,0.6)", border: "none", color: "#fff", padding: "0.4rem", borderRadius: "4px", cursor: "pointer", display: "flex", alignItems: "center" }} title="Zoom Image Info">
                      <Maximize2 size={12} />
                    </button>
                    <button onClick={() => deleteImage(img)} style={{ background: "rgba(0,0,0,0.6)", border: "none", color: img.origin === "generated" ? "#ff6b6b" : "#aab0c0", padding: "0.4rem", borderRadius: "4px", cursor: "pointer", display: "flex", alignItems: "center" }} title={img.origin === "generated" ? "Delete generated image" : "Read-only mounted source"}>
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>

                {/* Info summary */}
                <div style={{ padding: isMobile ? "0.55rem" : "0.75rem", flex: 1, display: "flex", flexDirection: "column", gap: "0.5rem", fontSize: "0.75rem" }}>
                  {(img.source_name || img.relative_path) && (
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.2rem" }}>
                      {img.source_name && (
                        <span style={{ fontSize: "0.68rem", color: "var(--accent)", textTransform: "uppercase", letterSpacing: "0.05em" }}>{img.source_name}</span>
                      )}
                      {img.relative_path && (
                        <span title={img.relative_path} style={{ color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{img.relative_path}</span>
                      )}
                    </div>
                  )}
                  {displayPrompt ? (
                    <div title={displayPrompt} style={{ color: "var(--text-secondary)", display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden', lineHeight: 1.4 }}>
                      {displayPrompt}
                    </div>
                  ) : (
                    <div style={{ color: "var(--text-muted)", fontStyle: "italic" }}>No metadata available</div>
                  )}
                  {img.metadata?.steps && (
                    <div style={{ marginTop: "auto", display: "flex", justifyContent: "space-between", opacity: 0.6, fontSize: "0.7rem", paddingTop: "0.25rem", borderTop: "1px solid var(--border-color)" }}>
                      <span>{img.metadata.sampler_name || "—"}</span>
                      <span>CFG {img.metadata.cfg_scale} · {img.metadata.steps}st</span>
                    </div>
                  )}
                </div>
              </div>
            );
          }}
        />
        {hasMoreAssets && (
          <div style={{ display: "flex", justifyContent: "center", padding: "1rem 0 2rem" }}>
            <button onClick={() => void loadMoreImages()} disabled={loadingMore} style={{ border: "1px solid var(--border-color)", minWidth: 180 }}>
              <RefreshCw size={16} className={loadingMore ? "spin" : ""} />
              {loadingMore ? "Loading..." : `${copy.loadMore} (${images.length}/${assetTotal})`}
            </button>
          </div>
        )}
        </>
      )}

      {mobileLibraryOpen && canUsePortal
        ? createPortal(
            <>
              <div onClick={() => setMobileLibraryOpen(false)} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.48)", zIndex: 20500 }} />
              <div className="mklan-mobile-library-sheet" style={{ position: "fixed", left: 0, right: 0, bottom: 0, zIndex: 20501, maxHeight: "78vh", background: "var(--bg-base)", borderTop: "1px solid var(--border-color)", borderRadius: "18px 18px 0 0", boxShadow: "0 -22px 70px rgba(0,0,0,0.5)", display: "flex", flexDirection: "column", paddingBottom: "env(safe-area-inset-bottom)" }}>
                <div style={{ width: 42, height: 4, borderRadius: 999, background: "var(--border-color)", margin: "0.65rem auto 0" }} />
                {renderLibraryPanel(true)}
              </div>
            </>,
            document.body,
          )
        : null}

      {mobileScanOpen && canUsePortal
        ? createPortal(
            <>
              <div onClick={() => setMobileScanOpen(false)} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.48)", zIndex: 20600 }} />
              <div className="mklan-mobile-scan-sheet" style={{ position: "fixed", left: 0, right: 0, bottom: 0, zIndex: 20601, maxHeight: "82vh", overflowY: "auto", background: "var(--bg-base)", borderTop: "1px solid var(--border-color)", borderRadius: "18px 18px 0 0", boxShadow: "0 -22px 70px rgba(0,0,0,0.5)", padding: "0.9rem 1rem calc(1rem + env(safe-area-inset-bottom))" }}>
                <div style={{ width: 42, height: 4, borderRadius: 999, background: "var(--border-color)", margin: "0 auto 0.8rem" }} />
                {renderScanCommandCenter(true)}
              </div>
            </>,
            document.body,
          )
        : null}

      {mobileFiltersOpen && canUsePortal
        ? createPortal(
            <>
              <div onClick={() => setMobileFiltersOpen(false)} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.48)", zIndex: 20700 }} />
              <div className="mklan-mobile-filter-sheet" style={{ position: "fixed", left: 0, right: 0, bottom: 0, zIndex: 20701, maxHeight: "84vh", overflowY: "auto", background: "var(--bg-base)", borderTop: "1px solid var(--border-color)", borderRadius: "18px 18px 0 0", boxShadow: "0 -22px 70px rgba(0,0,0,0.5)", padding: "0.9rem 1rem calc(1rem + env(safe-area-inset-bottom))" }}>
                <div style={{ width: 42, height: 4, borderRadius: 999, background: "var(--border-color)", margin: "0 auto 0.8rem" }} />
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem", marginBottom: "0.75rem" }}>
                  <strong style={{ display: "flex", alignItems: "center", gap: "0.45rem" }}><SlidersHorizontal size={16} /> {copy.viewControls}</strong>
                  <button onClick={() => setMobileFiltersOpen(false)} style={{ border: "1px solid var(--border-color)" }}>
                    <X size={16} /> Close
                  </button>
                </div>
                {renderGalleryCommandBar(true)}
              </div>
            </>,
            document.body,
          )
        : null}

      {contextMenu && canUsePortal
        ? createPortal(
            <>
              {isMobile ? (
                <div
                  onClick={() => setContextMenu(null)}
                  style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 21000 }}
                />
              ) : null}
              <div
                className="mklan-gallery-context-menu"
                style={{
                  ...(contextMenuStyle || {}),
                  zIndex: 21001,
                  overflowY: "auto",
                  background: "var(--bg-elevated)",
                  border: "1px solid var(--border-color)",
                  boxShadow: "0 22px 70px rgba(0,0,0,0.48)",
                  padding: "0.55rem",
                  display: "grid",
                  gap: "0.35rem",
                  backdropFilter: "blur(18px)",
                }}
              >
                {isMobile ? (
                  <div style={{ width: 42, height: 4, borderRadius: 999, background: "var(--border-color)", margin: "0.15rem auto 0.45rem" }} />
                ) : null}
                <div style={{ padding: "0.35rem 0.45rem 0.5rem", color: "var(--text-secondary)", fontSize: "0.78rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {contextMenu.image.name}
                </div>
                {contextActions.map((action) => (
                  <button
                    key={action.label}
                    disabled={action.disabled}
                    onClick={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      setContextMenu(null);
                      action.run();
                    }}
                    style={{
                      justifyContent: "flex-start",
                      textAlign: "left",
                      width: "100%",
                      minHeight: isMobile ? 44 : 34,
                      border: "1px solid var(--border-color)",
                      background: "rgba(255,255,255,0.035)",
                      color: "var(--text-primary)",
                      whiteSpace: "normal",
                    }}
                  >
                    {action.label}
                  </button>
                ))}
              </div>
            </>,
            document.body,
          )
        : null}

      {/* Premium Zoom & Metadata Inspector Panel Modal overlay */}
      {zoomImg && canUsePortal
        ? createPortal(
        <div
          onClick={e => { if (e.target === e.currentTarget) setZoomImg(null); }}
          style={{ position: "fixed", inset: 0, background: "rgba(8,8,10,0.94)", zIndex: 22000, display: "flex", alignItems: isMobile ? "stretch" : "center", justifyContent: "center", padding: isMobile ? 0 : 0, overflowX: "hidden", overflowY: isMobile ? "auto" : "hidden", overscrollBehavior: "contain" }}
        >
          <div style={{ position: "relative", display: "flex", flexDirection: isMobile ? "column" : "row", width: isMobile ? "100vw" : "95vw", height: isMobile ? "auto" : "90vh", minHeight: isMobile ? "100dvh" : undefined, maxHeight: isMobile ? "none" : "90vh", background: "var(--bg-main)", border: isMobile ? "none" : "1px solid var(--border-color)", borderRadius: isMobile ? 0 : "12px", overflow: "hidden", boxShadow: isMobile ? "none" : "0 25px 50px rgba(0,0,0,0.8)" }}>
            
            {/* Left Image deep zoom stage */}
            <div style={{ flex: isMobile ? "0 0 auto" : 1, height: isMobile ? "clamp(260px, 58dvh, 560px)" : "100%", minHeight: 0, position: "relative" }}>
              <DeepZoomViewer src={zoomImg.fullUrl || zoomImg.url} alt={zoomImg.name} compact={isMobile} />
              {isMobile ? (
                <button
                  type="button"
                  aria-label="Close image details"
                  onClick={() => setZoomImg(null)}
                  style={{
                    position: "absolute",
                    top: "calc(0.7rem + env(safe-area-inset-top))",
                    right: "0.7rem",
                    width: 40,
                    height: 40,
                    padding: 0,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    borderRadius: "12px",
                    border: "1px solid rgba(255,255,255,0.12)",
                    background: "rgba(10, 10, 14, 0.72)",
                    color: "#fff",
                    backdropFilter: "blur(14px)",
                    boxShadow: "0 10px 28px rgba(0,0,0,0.35)",
                    zIndex: 20,
                  }}
                >
                  <X size={18} />
                </button>
              ) : null}
              
              {/* Arrow navigators */}
              <button 
                onClick={() => {
                  const idx = images.findIndex(i => i.name === zoomImg.name);
                  if (idx > 0) void openImageDetails(images[idx - 1]);
                }}
                disabled={images.findIndex(i => i.name === zoomImg.name) === 0}
                style={{ display: isMobile ? "none" : "block", position: "absolute", left: "1rem", top: "50%", transform: "translateY(-50%)", background: "rgba(15,15,20,0.6)", color: "#fff", border: "1px solid rgba(255,255,255,0.08)", padding: "0.6rem 0.8rem", borderRadius: "8px", cursor: "pointer", zIndex: 12, opacity: images.findIndex(i => i.name === zoomImg.name) === 0 ? 0.3 : 1 }}
              >
                ◀
              </button>
              <button 
                onClick={() => {
                  const idx = images.findIndex(i => i.name === zoomImg.name);
                  if (idx < images.length - 1) void openImageDetails(images[idx + 1]);
                }}
                disabled={images.findIndex(i => i.name === zoomImg.name) === images.length - 1}
                style={{ display: isMobile ? "none" : "block", position: "absolute", right: "1rem", top: "50%", transform: "translateY(-50%)", background: "rgba(15,15,20,0.6)", color: "#fff", border: "1px solid rgba(255,255,255,0.08)", padding: "0.6rem 0.8rem", borderRadius: "8px", cursor: "pointer", zIndex: 12, opacity: images.findIndex(i => i.name === zoomImg.name) === images.length - 1 ? 0.3 : 1 }}
              >
                ▶
              </button>
            </div>

            {/* Right Side metadata inspector panel info */}
            <div 
              style={{ 
                width: isMobile ? "100%" : "350px", 
                flex: isMobile ? "0 0 auto" : "0 0 350px",
                minHeight: 0,
                maxHeight: isMobile ? "none" : "100%",
                borderLeft: isMobile ? "none" : "1px solid var(--border-color)", 
                borderTop: isMobile ? "1px solid var(--border-color)" : "none",
                background: "var(--bg-secondary)", 
                padding: isMobile ? "0.75rem 0.85rem calc(1rem + env(safe-area-inset-bottom))" : "1.5rem",
                display: "flex",
                flexDirection: "column",
                overflow: isMobile ? "visible" : "hidden",
                overscrollBehavior: "contain",
                height: isMobile ? "auto" : "100%"
              }}
            >
              <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "0.5rem", position: isMobile ? "sticky" : "static", top: 0, zIndex: 2, background: "var(--bg-secondary)", flex: "0 0 auto" }}>
                <button 
                  onClick={() => setZoomImg(null)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.3rem",
                    padding: "0.3rem 0.6rem",
                    background: "rgba(255, 255, 255, 0.05)",
                    border: "1px solid var(--border-color)",
                    color: "var(--text-secondary)",
                    borderRadius: "6px",
                    cursor: "pointer",
                    fontSize: isMobile ? "0.7rem" : "0.75rem",
                    fontWeight: 600
                  }}
                >
                  <X size={14} /> Close Inspector
                </button>
              </div>
              <div style={{ flex: "1 1 auto", minHeight: 0, overflowY: "auto", overscrollBehavior: "contain", paddingRight: isMobile ? 0 : "0.2rem" }}>
                <MetadataInspector 
                  metadata={zoomImg.metadata} 
                  image={{
                    name: zoomImg.name,
                    sourceName: zoomImg.source_name,
                    relativePath: zoomImg.relative_path,
                    size: zoomImg.size,
                    mediaType: zoomImg.media_type,
                  }}
                  onSendToWorkshop={() => {
                    sendToWorkshop(zoomImg);
                    setZoomImg(null);
                  }}
                  onImportSillyTavernCard={(card) => {
                    void importSillyTavernCardToCreator(card).catch((error) => {
                      setToolsMessage(error instanceof Error ? error.message : "Unable to import SillyTavern card.");
                    });
                  }}
                  onTagSelect={applyTagFilterFromInspector}
                  compact={isMobile}
                />
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.45rem", marginTop: isMobile ? "0.65rem" : "1rem", flex: "0 0 auto" }}>
                <button onClick={() => void copyPromptTags(zoomImg)} style={{ border: "1px solid var(--border-color)" }}>
                  <Tags size={16} /> Copy Parsed Tags
                </button>
                <button onClick={() => void downloadWorkflow(zoomImg)} disabled={!zoomImg.workflow_export_available} style={{ border: "1px solid var(--border-color)" }}>
                  <Download size={16} /> Export Stored Workflow
                </button>
                <button onClick={() => void downloadWorkflow(zoomImg, true)} disabled={!zoomImg.id} style={{ border: "1px solid var(--border-color)" }}>
                  <Download size={16} /> Re-Extract Workflow From File
                </button>
              </div>
            </div>
          </div>
        </div>
          ,
          document.body,
        )
        : null}
      </div>
    </div>
  );
}
