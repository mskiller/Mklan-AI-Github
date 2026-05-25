import { useState } from "react";
import { Check, Copy, FileJson, Info, ShieldAlert, Sparkles, Tag, Wand2 } from "lucide-react";

interface InspectorMeta {
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
  workflow_text?: string;
  workflow_format?: string;
  nsfw_detected?: boolean;
  nsfw_model_detected?: boolean;
  nsfw_prompt_flagged?: boolean;
  nsfw_score?: number | null;
  nsfw_label?: string | null;
  nsfw_detector_available?: boolean;
  nsfw_model?: string | null;
  safety_quality_scanned_at?: string | null;
  quality_scanned_at?: string | null;
  quality_warnings?: string[];
  quality_width?: number;
  quality_height?: number;
  quality_sharpness_score?: number;
  visual_workflow_confidence?: number;
  vision_llm_analysis?: string;
  vision_llm_source?: string;
  vision_llm_updated_at?: string;
  sillytavern_card_detected?: boolean;
  sillytavern_card_name?: string;
  sillytavern_card_tags?: string[];
  sillytavern_card_spec?: string;
  sillytavern_card?: Record<string, unknown>;
  [key: string]: unknown;
}

interface InspectorImage {
  name: string;
  sourceName?: string;
  relativePath?: string;
  size?: number;
  mediaType?: string | null;
}

interface MetadataInspectorProps {
  metadata: InspectorMeta;
  image?: InspectorImage;
  onSendToWorkshop: () => void;
  onImportSillyTavernCard?: (card: Record<string, unknown>) => void;
  onTagSelect?: (tag: string) => void;
  compact?: boolean;
}

type InspectorTab = "summary" | "prompt" | "vision" | "workflow" | "sillytavern" | "raw";

const tabs: Array<{ id: InspectorTab; label: string; icon: typeof Info }> = [
  { id: "summary", label: "Summary", icon: Info },
  { id: "prompt", label: "Prompt", icon: Tag },
  { id: "vision", label: "Vision", icon: Sparkles },
  { id: "workflow", label: "Workflow", icon: FileJson },
  { id: "sillytavern", label: "Card", icon: FileJson },
  { id: "raw", label: "Raw", icon: FileJson },
];

const formatBytes = (bytes?: number) => {
  if (!bytes) return "-";
  const units = ["B", "KB", "MB", "GB"];
  let size = bytes;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  return `${size.toFixed(unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
};

function Field({ label, value }: { label: string; value: unknown }) {
  const displayValue = value === null || value === undefined || value === "" ? "-" : String(value);
  return (
    <div>
      <div style={{ color: "var(--text-muted)", fontSize: "0.7rem", marginBottom: "0.15rem", textTransform: "uppercase" }}>{label}</div>
      <div style={{ fontWeight: 650, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{displayValue}</div>
    </div>
  );
}

function TextBox({ value, maxHeight = 180, compact = false }: { value?: string; maxHeight?: number; compact?: boolean }) {
  return (
    <div
      style={{
        background: "var(--bg-secondary)",
        border: "1px solid var(--border-color)",
        borderRadius: "8px",
        padding: compact ? "0.65rem" : "0.8rem",
        fontSize: compact ? "0.78rem" : "0.82rem",
        lineHeight: 1.5,
        color: "var(--text-secondary)",
        maxHeight,
        overflowY: "auto",
        whiteSpace: "pre-wrap",
      }}
    >
      {value || "No data available yet."}
    </div>
  );
}

export function MetadataInspector({ metadata, image, onSendToWorkshop, onImportSillyTavernCard, onTagSelect, compact = false }: MetadataInspectorProps) {
  const [activeTab, setActiveTab] = useState<InspectorTab>("summary");
  const [copiedPrompt, setCopiedPrompt] = useState(false);
  const [copiedRawPrompt, setCopiedRawPrompt] = useState(false);
  const [copiedRaw, setCopiedRaw] = useState(false);
  const [copiedCard, setCopiedCard] = useState(false);
  const processedPrompt = metadata.processed_prompt || metadata.prompt;
  const rawPrompt = metadata.raw_prompt && metadata.raw_prompt !== processedPrompt ? metadata.raw_prompt : undefined;
  const processedNegativePrompt = metadata.processed_negative_prompt || metadata.negative_prompt;
  const rawNegativePrompt =
    metadata.raw_negative_prompt && metadata.raw_negative_prompt !== processedNegativePrompt
      ? metadata.raw_negative_prompt
      : undefined;

  const tags = metadata.prompt_tags?.length
    ? metadata.prompt_tags
    : processedPrompt
      ? processedPrompt.split(",").map((tag) => tag.trim()).filter(Boolean)
      : [];
  const qualityWarnings = Array.isArray(metadata.quality_warnings)
    ? metadata.quality_warnings.filter((value): value is string => typeof value === "string" && value.trim().length > 0)
    : [];
  const hasSafetyData = Boolean(
    metadata.safety_quality_scanned_at ||
      metadata.quality_scanned_at ||
      typeof metadata.nsfw_detected === "boolean" ||
      qualityWarnings.length ||
      typeof metadata.quality_sharpness_score === "number",
  );
  const nsfwStatus = !hasSafetyData ? "Not scanned" : metadata.nsfw_detected ? "NSFW" : "No NSFW signal";
  const nsfwScore = typeof metadata.nsfw_score === "number" ? `${Math.round(metadata.nsfw_score * 100)}%` : "-";
  const sillytavernCard = metadata.sillytavern_card && typeof metadata.sillytavern_card === "object" ? metadata.sillytavern_card : null;
  const sillytavernData =
    sillytavernCard && sillytavernCard.data && typeof sillytavernCard.data === "object"
      ? (sillytavernCard.data as Record<string, unknown>)
      : {};

  const copyText = async (text: string | undefined, setCopied: (value: boolean) => void) => {
    if (!text) return;
    await navigator.clipboard.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };

  const rawMetadata = JSON.stringify(metadata, null, 2);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: compact ? "0.75rem" : "1rem", minHeight: 0, height: "100%", color: "var(--text-main)" }}>
      <div>
        <h3 style={{ fontSize: compact ? "1rem" : "1.1rem", fontWeight: 700, margin: "0 0 0.3rem 0" }}>Image Inspector</h3>
        <p style={{ margin: 0, fontSize: compact ? "0.75rem" : "0.8rem", color: "var(--text-secondary)" }}>
          Metadata, prompt tags, workflow clues, and Vision LLM notes.
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(6, minmax(0, 1fr))", gap: compact ? "0.25rem" : "0.35rem" }}>
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                minWidth: 0,
                padding: compact ? "0.4rem 0.15rem" : "0.45rem 0.25rem",
                border: `1px solid ${active ? "var(--border-highlight)" : "var(--border-color)"}`,
                background: active ? "rgba(124,106,255,0.16)" : "transparent",
                color: active ? "var(--accent)" : "var(--text-secondary)",
                fontSize: compact ? "0.62rem" : "0.68rem",
              }}
              title={tab.label}
            >
              <Icon size={13} />
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {activeTab === "summary" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
          {image && (
            <div style={{ background: "var(--bg-secondary)", border: "1px solid var(--border-color)", borderRadius: "8px", padding: "0.85rem", display: "grid", gap: "0.55rem", fontSize: "0.8rem" }}>
              <Field label="File" value={image.name} />
              <Field label="Source" value={image.sourceName || "Generated / Unknown"} />
              <Field label="Path" value={image.relativePath || "-"} />
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
                <Field label="Type" value={image.mediaType || "image"} />
                <Field label="Size" value={formatBytes(image.size)} />
              </div>
            </div>
          )}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem", background: "var(--bg-secondary)", border: "1px solid var(--border-color)", borderRadius: "8px", padding: "0.85rem", fontSize: "0.8rem" }}>
            <Field label="Dimensions" value={metadata.width && metadata.height ? `${metadata.width} x ${metadata.height}` : "-"} />
            <Field label="Generator" value={metadata.generator} />
            <Field label="Checkpoint" value={metadata.checkpoint} />
            <Field label="Seed" value={metadata.seed} />
            <Field label="Steps" value={metadata.steps} />
            <Field label="CFG" value={metadata.cfg_scale} />
            <Field label="Sampler" value={metadata.sampler_name} />
            <Field label="Scheduler" value={metadata.scheduler} />
          </div>
          <div style={{ background: "var(--bg-secondary)", border: `1px solid ${metadata.nsfw_detected ? "rgba(248,113,113,0.42)" : "var(--border-color)"}`, borderRadius: "8px", padding: "0.85rem", display: "grid", gap: "0.65rem", fontSize: "0.8rem" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.6rem" }}>
              <strong style={{ display: "flex", alignItems: "center", gap: "0.4rem", color: metadata.nsfw_detected ? "#fca5a5" : "var(--text-main)" }}>
                <ShieldAlert size={15} /> Safety / Quality
              </strong>
              <span style={{ color: metadata.nsfw_detected ? "#fca5a5" : "var(--text-secondary)", fontWeight: 800 }}>{nsfwStatus}</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
              <Field label="NSFW Score" value={nsfwScore} />
              <Field label="Prompt Signal" value={metadata.nsfw_prompt_flagged ? "Yes" : hasSafetyData ? "No" : "-"} />
              <Field label="Sharpness" value={metadata.quality_sharpness_score} />
              <Field label="Scanned" value={metadata.safety_quality_scanned_at || metadata.quality_scanned_at || "-"} />
            </div>
            {qualityWarnings.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem" }}>
                {qualityWarnings.map((warning) => (
                  <span key={warning} style={{ border: "1px solid rgba(250,204,21,0.32)", background: "rgba(250,204,21,0.08)", color: "#facc15", borderRadius: "999px", padding: "0.2rem 0.45rem", fontSize: "0.7rem", fontWeight: 700 }}>
                    {warning}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {activeTab === "prompt" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.75rem" }}>
            <span style={{ fontSize: "0.75rem", fontWeight: 800, color: "var(--accent)", textTransform: "uppercase" }}>Processed Prompt</span>
            <button onClick={() => void copyText(processedPrompt, setCopiedPrompt)} disabled={!processedPrompt} style={{ border: "1px solid var(--border-color)" }}>
              {copiedPrompt ? <Check size={13} /> : <Copy size={13} />} {copiedPrompt ? "Copied" : "Copy"}
            </button>
          </div>
          <TextBox value={processedPrompt} maxHeight={compact ? 120 : 170} compact={compact} />
          {rawPrompt && (
            <>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.75rem" }}>
                <span style={{ fontSize: "0.75rem", fontWeight: 800, color: "var(--text-muted)", textTransform: "uppercase" }}>Raw Prompt</span>
                <button onClick={() => void copyText(rawPrompt, setCopiedRawPrompt)} style={{ border: "1px solid var(--border-color)" }}>
                  {copiedRawPrompt ? <Check size={13} /> : <Copy size={13} />} {copiedRawPrompt ? "Copied" : "Copy Raw"}
                </button>
              </div>
              <TextBox value={rawPrompt} maxHeight={compact ? 95 : 130} compact={compact} />
            </>
          )}
          {processedNegativePrompt && (
            <>
              <span style={{ fontSize: "0.75rem", fontWeight: 800, color: "#f87171", textTransform: "uppercase" }}>Negative Prompt</span>
              <TextBox value={processedNegativePrompt} maxHeight={compact ? 85 : 110} compact={compact} />
              {rawNegativePrompt ? <TextBox value={`Raw: ${rawNegativePrompt}`} maxHeight={compact ? 75 : 90} compact={compact} /> : null}
            </>
          )}
          {tags.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <span style={{ fontSize: "0.75rem", fontWeight: 800, color: "var(--text-muted)", textTransform: "uppercase" }}>Prompt Tags</span>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem", maxHeight: compact ? "96px" : "130px", overflowY: "auto" }}>
                {tags.map((tag, index) => (
                  <button
                    key={`${tag}-${index}`}
                    onClick={() => {
                      if (onTagSelect) {
                        onTagSelect(tag);
                      } else {
                        void navigator.clipboard.writeText(tag);
                      }
                    }}
                    title={onTagSelect ? "Filter the gallery by this tag" : "Copy tag"}
                    style={{ border: "1px solid rgba(99,102,241,0.18)", background: "rgba(99,102,241,0.08)", color: "var(--accent)", padding: "0.25rem 0.45rem", fontSize: "0.72rem" }}
                  >
                    <Tag size={10} /> {tag}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {activeTab === "vision" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          <TextBox value={metadata.vision_llm_analysis} maxHeight={compact ? 190 : 300} compact={compact} />
          <span style={{ color: "var(--text-muted)", fontSize: "0.74rem" }}>
            {metadata.vision_llm_source || "KoboldCpp"}{metadata.vision_llm_updated_at ? ` - ${metadata.vision_llm_updated_at}` : ""}
          </span>
        </div>
      )}

      {activeTab === "workflow" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem", background: "var(--bg-secondary)", border: "1px solid var(--border-color)", borderRadius: "8px", padding: "0.85rem", fontSize: "0.8rem" }}>
            <Field label="Format" value={metadata.workflow_format} />
            <Field label="Confidence" value={metadata.visual_workflow_confidence} />
          </div>
          <TextBox value={metadata.workflow_text as string | undefined} maxHeight={compact ? 190 : 300} compact={compact} />
        </div>
      )}

      {activeTab === "sillytavern" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem", background: "var(--bg-secondary)", border: "1px solid var(--border-color)", borderRadius: "8px", padding: "0.85rem", fontSize: "0.8rem" }}>
            <Field label="Detected" value={metadata.sillytavern_card_detected ? "Yes" : "No"} />
            <Field label="Spec" value={metadata.sillytavern_card_spec} />
            <Field label="Name" value={metadata.sillytavern_card_name || sillytavernData.name} />
            <Field label="Tags" value={Array.isArray(sillytavernData.tags) ? sillytavernData.tags.join(", ") : metadata.sillytavern_card_tags?.join(", ")} />
          </div>
          <TextBox value={String(sillytavernData.description || "")} maxHeight={compact ? 90 : 130} compact={compact} />
          <TextBox value={String(sillytavernData.personality || sillytavernData.scenario || "")} maxHeight={compact ? 100 : 150} compact={compact} />
          <div style={{ display: "flex", gap: "0.45rem", flexWrap: "wrap" }}>
            <button onClick={() => void copyText(sillytavernCard ? JSON.stringify(sillytavernCard, null, 2) : undefined, setCopiedCard)} disabled={!sillytavernCard} style={{ border: "1px solid var(--border-color)" }}>
              {copiedCard ? <Check size={13} /> : <Copy size={13} />} {copiedCard ? "Copied" : "Copy Card JSON"}
            </button>
            <button onClick={() => sillytavernCard && onImportSillyTavernCard?.(sillytavernCard)} disabled={!sillytavernCard || !onImportSillyTavernCard} style={{ border: "1px solid var(--border-color)" }}>
              <FileJson size={13} /> Import to Cards
            </button>
          </div>
        </div>
      )}

      {activeTab === "raw" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          <button onClick={() => void copyText(rawMetadata, setCopiedRaw)} style={{ alignSelf: "flex-start", border: "1px solid var(--border-color)" }}>
            {copiedRaw ? <Check size={13} /> : <Copy size={13} />} {copiedRaw ? "Copied" : "Copy JSON"}
          </button>
          <TextBox value={rawMetadata} maxHeight={compact ? 210 : 330} compact={compact} />
        </div>
      )}

      <button className="primary" onClick={onSendToWorkshop} style={{ marginTop: compact ? "0.25rem" : "auto", padding: compact ? "0.65rem" : "0.75rem", fontSize: "0.85rem" }}>
        <Wand2 size={16} /> Send to Workshop
      </button>
    </div>
  );
}
