"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { AssetCard } from "@/components/asset-card";
import { CollectionPickerModal } from "@/components/collection-picker-modal";
import { ZoomableImageViewer } from "@/components/zoomable-image-viewer";
import { useAuth } from "@/components/auth-provider";
import { useModuleRegistry } from "@/components/module-registry-provider";
import { useToast } from "@/components/use-toast";
import { TagSuggestionReview } from "@/components/tag-suggestion-review";
import { ShareModal } from "@/components/share-modal";
import { DetailTabs } from "@/components/DetailTabs";
import { VisualWorkflowGraph } from "@/components/VisualWorkflowGraph";
import { addAssetsToCollection, assetImageUrl, bulkAnnotateAssets, downloadWorkflow, downloadWorkflowFromFile, fetchAsset, fetchAssetFaces, fetchCollections, fetchSimilar, fetchSimilarByImage, mediaUrl, runAssetVisionLlm, triggerScan, updatePerson } from "@/lib/api";
import { metadataVersion, numericMetadata, promptTagStringFromMetadata, promptTagsFromMetadata, stringMetadata } from "@/lib/asset-metadata";
import { sourceFolderBrowseHref } from "@/lib/browse-links";
import { copyTextToClipboard } from "@/lib/clipboard";
import { TagFilterChip } from "@/components/tag-filter-chip";
import { AssetDetail, AssetFacesResponse, CollectionSummary, ReviewStatus, SimilarAsset } from "@/lib/types";

export default function AssetDetailPage() {
  const params = useParams<{ id: string }>();
  const { user } = useAuth();
  const { isModuleEnabled } = useModuleRegistry();
  const { push } = useToast();
  const [asset, setAsset] = useState<AssetDetail | null>(null);
  const [duplicates, setDuplicates] = useState<SimilarAsset[]>([]);
  const [semantic, setSemantic] = useState<SimilarAsset[]>([]);
  const [tagSimilar, setTagSimilar] = useState<SimilarAsset[]>([]);
  const [visualMatches, setVisualMatches] = useState<SimilarAsset[]>([]);
  const [collections, setCollections] = useState<CollectionSummary[]>([]);
  const [collectionOpen, setCollectionOpen] = useState(false);
  const [collectionBusy, setCollectionBusy] = useState(false);
  const [annotationBusy, setAnnotationBusy] = useState(false);
  const [rating, setRating] = useState<number | null>(null);
  const [reviewStatus, setReviewStatus] = useState<ReviewStatus>("unreviewed");
  const [flagged, setFlagged] = useState(false);
  const [note, setNote] = useState("");
  const [pendingTags, setPendingTags] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyExtracting, setBusyExtracting] = useState(false);
  const [analysisBusy, setAnalysisBusy] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const [faces, setFaces] = useState<AssetFacesResponse | null>(null);
  const [showFaceBoxes, setShowFaceBoxes] = useState(false);
  const collectionsEnabled = isModuleEnabled("collections");
  const aiTaggingEnabled = isModuleEnabled("ai_tagging");

  useEffect(() => {
    const load = async () => {
      try {
        const [nextAsset, nextFaces, nextDuplicates, nextSemantic, nextTagSimilar, nextVisualMatches] = await Promise.all([
          fetchAsset(params.id),
          fetchAssetFaces(params.id).catch(() => ({ enabled: false, image_width: null, image_height: null, items: [] })),
          fetchSimilar(params.id, "duplicate", 6),
          fetchSimilar(params.id, "semantic", 6),
          fetchSimilar(params.id, "tag", 6),
          fetchSimilarByImage(params.id, 6).catch(() => []),
        ]);
        setAsset(nextAsset);
        setFaces(nextFaces);
        setRating(nextAsset.annotation?.rating ?? null);
        setReviewStatus(nextAsset.annotation?.review_status ?? "unreviewed");
        setFlagged(nextAsset.annotation?.flagged ?? false);
        setNote(nextAsset.annotation?.note ?? "");
        setDuplicates(nextDuplicates);
        setSemantic(nextSemantic);
        setTagSimilar(nextTagSimilar);
        setVisualMatches(nextVisualMatches);
      } catch (nextError) {
        setError(nextError instanceof Error ? nextError.message : "Unable to load asset detail.");
      }
    };
    void load();
  }, [params.id]);

  useEffect(() => {
    if (!user?.capabilities.can_manage_collections || !collectionsEnabled) {
      return;
    }
    const loadCollections = async () => {
      try {
        setCollections(await fetchCollections());
      } catch {
        setCollections([]);
      }
    };
    void loadCollections();
  }, [user?.capabilities.can_manage_collections, collectionsEnabled]);

  const preview = mediaUrl(asset?.preview_url ?? asset?.content_url);
  const streamUrl = asset ? mediaUrl(`/assets/${asset.id}/stream`) : undefined;
  const content = asset ? assetImageUrl(asset.id, { w: 3000, fmt: "webp" }) : undefined;
  const deepzoom = mediaUrl(asset?.deepzoom_url);
  const waveformPreview = mediaUrl(asset?.waveform_url);
  const keyframePreviews = (asset?.video_keyframes ?? []).map((path) => mediaUrl(path)).filter(Boolean) as string[];
  const promptTags = asset ? promptTagsFromMetadata(asset.normalized_metadata, 12) : [];
  const promptTagString = asset ? promptTagStringFromMetadata(asset.normalized_metadata) : null;
  const assetTags = asset ? asset.tags.filter((tag) => !promptTags.includes(tag)) : [];
  const staleMetadata = asset ? metadataVersion(asset.normalized_metadata) < 6 : false;
  const positivePrompt = asset ? stringMetadata(asset.normalized_metadata["prompt"]) : null;
  const negativePrompt = asset ? stringMetadata(asset.normalized_metadata["negative_prompt"]) : null;
  const workflowText = asset ? stringMetadata(asset.normalized_metadata["workflow_text"]) : null;
  const caption = asset?.caption ?? stringMetadata(asset?.normalized_metadata?.["caption"]);
  const ocrText = asset?.ocr_text ?? stringMetadata(asset?.normalized_metadata?.["ocr_text"]);
  const visionLlmAnalysis = asset ? stringMetadata(asset.normalized_metadata["vision_llm_analysis"]) : null;
  const visionLlmSource = asset ? stringMetadata(asset.normalized_metadata["vision_llm_source"]) : null;
  const visionLlmUpdatedAt = asset ? stringMetadata(asset.normalized_metadata["vision_llm_updated_at"]) : null;
  const gpsLatitude = asset ? numericMetadata(asset.normalized_metadata["gps_latitude"]) : null;
  const gpsLongitude = asset ? numericMetadata(asset.normalized_metadata["gps_longitude"]) : null;
  const browseHref = asset ? sourceFolderBrowseHref(asset.source_id, asset.relative_path) : "/sources";
  const summaryEntries = asset
    ? Object.entries(asset.normalized_metadata).filter(
        ([key]) => !["prompt", "negative_prompt", "workflow_text", "prompt_tags", "caption", "caption_source", "ocr_text", "ocr_confidence", "vision_llm_analysis", "vision_llm_source", "vision_llm_endpoint", "vision_llm_updated_at"].includes(key)
      )
    : [];
  const mapBounds =
    gpsLatitude !== null && gpsLongitude !== null
      ? `${gpsLongitude - 0.02}%2C${gpsLatitude - 0.02}%2C${gpsLongitude + 0.02}%2C${gpsLatitude + 0.02}`
      : null;
  const mapEmbedUrl =
    gpsLatitude !== null && gpsLongitude !== null && mapBounds
      ? `https://www.openstreetmap.org/export/embed.html?bbox=${mapBounds}&layer=mapnik&marker=${gpsLatitude}%2C${gpsLongitude}`
      : null;
  const mapExternalUrl =
    gpsLatitude !== null && gpsLongitude !== null
      ? `https://www.openstreetmap.org/?mlat=${gpsLatitude}&mlon=${gpsLongitude}#map=14/${gpsLatitude}/${gpsLongitude}`
      : null;
  const appMapUrl = asset && gpsLatitude !== null && gpsLongitude !== null ? `/map?highlight=${asset.id}` : null;
  const faceImageWidth = faces?.image_width ?? 0;
  const faceImageHeight = faces?.image_height ?? 0;
  const faceOverlays =
    showFaceBoxes && faces?.enabled && faceImageWidth > 0 && faceImageHeight > 0
      ? faces.items.map((face) => ({
          id: face.id,
          x: face.bbox_x1,
          y: face.bbox_y1,
          width: face.bbox_x2 - face.bbox_x1,
          height: face.bbox_y2 - face.bbox_y1,
          label: face.person?.name ?? "Face",
        }))
      : [];

  const handleVisualExtract = async () => {
    if (!asset) return;
    setBusyExtracting(true);
    try {
      const response = await fetch(`/api/assets/${asset.id}/workflow/visual-extract`, { method: "POST" });
      if (!response.ok) throw new Error("Processing failed.");
      const [nextAsset, nextVisualMatches] = await Promise.all([
        fetchAsset(asset.id),
        fetchSimilarByImage(asset.id, 6).catch(() => []),
      ]);
      setAsset(nextAsset);
      setVisualMatches(nextVisualMatches);
      push("Visual extraction complete!", "success");
    } catch {
      push("Failed to process visual workflow.", "error");
    } finally {
      setBusyExtracting(false);
    }
  };

  const handleQueueMetadataScan = async () => {
    if (!asset) return;
    setAnalysisBusy(true);
    try {
      const job = await triggerScan(asset.source_id, { scan_mode: "metadata", path_filter: asset.relative_path });
      push(`Metadata scan queued: ${job.id}`, "success");
    } catch (nextError) {
      push(nextError instanceof Error ? nextError.message : "Unable to queue metadata scan.", "error");
    } finally {
      setAnalysisBusy(false);
    }
  };

  const handleVisionLlm = async () => {
    if (!asset) return;
    setAnalysisBusy(true);
    try {
      await runAssetVisionLlm(asset.id);
      setAsset(await fetchAsset(asset.id));
      push("Vision LLM analysis saved.", "success");
    } catch (nextError) {
      push(nextError instanceof Error ? nextError.message : "Vision LLM analysis failed.", "error");
    } finally {
      setAnalysisBusy(false);
    }
  };

  const tabs = [
    { id: "preview", label: "Preview", icon: "👁️" },
    { id: "metadata", label: "Metadata", icon: "📑" },
    { id: "workflow", label: "Visual Workflow", icon: "⚡" },
    { id: "similar", label: "Related", icon: "🔗" },
  ];

  if (gpsLatitude !== null && gpsLongitude !== null) {
    tabs.push({ id: "location", label: "Location", icon: "📍" });
  }

  return (
    <AppShell
      title={asset?.filename ?? "Asset Detail"}
      description={asset ? `Source: ${asset.source_name}` : "Metadata, previews, tags, and similarity shortcuts."}
      actions={
        asset ? (
          <div className="page-actions">
            <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
              <span className="eyebrow">Generation Tools</span>
              <div className="page-actions" style={{ flexWrap: "wrap" }}>
                {promptTagString ? (
                  <button
                    type="button"
                    className="button subtle-button small-button"
                    onClick={async () => {
                      await copyTextToClipboard(promptTagString);
                      push("Copied Danbooru tags!", "success");
                    }}
                  >
                    Copy Danbooru Tags
                  </button>
                ) : null}
                {asset?.workflow_export_available ? (
                  <button
                    type="button"
                    className="button ghost-button small-button"
                    onClick={() => asset && downloadWorkflow(asset.id, asset.filename)}
                  >
                    Download Workflow JSON
                  </button>
                ) : null}
                <button
                  type="button"
                  className="button ghost-button small-button"
                  onClick={() => asset && downloadWorkflowFromFile(asset.id, asset.filename)}
                  title="Attempt to extract workflow directly from the current file, bypassing indexed metadata."
                >
                  🚀 Extract from File
                </button>
                <button
                  type="button"
                  className="button accent-button small-button"
                  disabled={busyExtracting}
                  onClick={handleVisualExtract}
                >
                  {busyExtracting ? "Processing..." : "✨ Visual OCR Extraction"}
                </button>
                <button type="button" className="button ghost-button small-button" disabled={analysisBusy} onClick={handleQueueMetadataScan}>
                  Scan Metadata
                </button>
                <button type="button" className="button subtle-button small-button" disabled={analysisBusy} onClick={handleVisionLlm}>
                  Scan with Vision LLM
                </button>
              </div>
            </div>

            {user?.capabilities.can_manage_collections && collectionsEnabled && asset ? (
              <div className="row" style={{ gap: "0.5rem" }}>
                <button type="button" className="button ghost-button small-button" onClick={() => setCollectionOpen(true)}>
                  Add to Collection
                </button>
                <button type="button" className="button ghost-button small-button" onClick={() => setShareOpen(true)}>
                  Share
                </button>
              </div>
            ) : null}
          </div>
        ) : null
      }
    >
      {shareOpen && asset && (
        <ShareModal 
          targetId={asset.id} 
          targetType="asset" 
          onClose={() => setShareOpen(false)} 
        />
      )}
      <main className="asset-detail-container">
        {error && <div className="error-banner">{error}</div>}

        <DetailTabs tabs={tabs}>
          {(activeTab) => (
            <>
              {activeTab === "preview" && (
                <div className="preview-tab">
                  <article className="asset-main stack">
                    <div className="preview-container">
                      {asset?.media_type === "video" ? (
                        <div className="static-preview-container">
                          <video
                            src={streamUrl}
                            poster={preview}
                            controls
                            preload="metadata"
                            className="asset-preview-image"
                            style={{ width: "100%", maxHeight: "72vh", background: "#000" }}
                          />
                          <div className="preview-actions">
                            <a href={streamUrl} target="_blank" rel="noopener noreferrer" className="button ghost-button">
                              Stream in New Tab
                            </a>
                            <a href={mediaUrl(asset?.content_url)} target="_blank" rel="noopener noreferrer" className="button subtle-button">
                              Open Original File
                            </a>
                          </div>
                        </div>
                      ) : deepzoom ? (
                        <ZoomableImageViewer
                          deepzoomUrl={deepzoom}
                          previewSrc={preview}
                          contentSrc={content}
                          alt={asset?.filename ?? "Asset preview"}
                          overlays={faceOverlays}
                        />
                      ) : (
                        <div className="static-preview-container">
                          <div style={{ position: "relative", width: "100%" }}>
                            <img src={preview ?? ""} alt={asset?.filename ?? "Preview"} className="asset-preview-image" />
                            {showFaceBoxes && faceImageWidth > 0 && faceImageHeight > 0
                              ? (faces?.items ?? []).map((face) => (
                                  <div
                                    key={face.id}
                                    style={{
                                      position: "absolute",
                                      left: `${(face.bbox_x1 / faceImageWidth) * 100}%`,
                                      top: `${(face.bbox_y1 / faceImageHeight) * 100}%`,
                                      width: `${((face.bbox_x2 - face.bbox_x1) / faceImageWidth) * 100}%`,
                                      height: `${((face.bbox_y2 - face.bbox_y1) / faceImageHeight) * 100}%`,
                                      border: "2px solid rgba(255, 94, 91, 0.95)",
                                      borderRadius: "0.8rem",
                                      boxSizing: "border-box",
                                      pointerEvents: "none",
                                    }}
                                  />
                                ))
                              : null}
                          </div>
                          <div className="preview-actions">
                            <a href={mediaUrl(asset?.content_url)} target="_blank" rel="noopener noreferrer" className="button ghost-button">
                              View Original High-Res
                            </a>
                          </div>
                        </div>
                      )}
                    </div>

                    <div className="tag-section">
                      <div className="row-between">
                        <span className="eyebrow">Image Tags</span>
                        <Link href={browseHref} className="subdued small">
                          Open source folder
                        </Link>
                      </div>
                      <div className="tag-cloud">
                        {promptTags.map((tag) => (
                          <TagFilterChip key={`prompt-${tag}`} tag={tag} prompt={true} />
                        ))}
                        {assetTags.map((tag) => (
                          <TagFilterChip key={`tag-${tag}`} tag={tag} />
                        ))}
                        {pendingTags.map((tag) => (
                          <button key={`pending-${tag}`} type="button" className="tag-chip pending-tag" onClick={() => setPendingTags((current) => current.filter((t) => t !== tag))}>
                            {tag} (pending)
                          </button>
                        ))}
                      </div>

                      {asset && aiTaggingEnabled ? <TagSuggestionReview assetId={asset.id} onChanged={async () => setAsset(await fetchAsset(asset.id))} /> : null}
                    </div>

                    {faces?.items.length ? (
                      <article className="panel stack">
                        <div className="row-between">
                          <div>
                            <p className="eyebrow">Faces</p>
                            <h2>{faces.items.length} detections</h2>
                          </div>
                          {faces.enabled ? (
                            <button
                              type="button"
                              className={`button ghost-button small-button ${showFaceBoxes ? "image-toolbar-btn-active" : ""}`}
                              onClick={() => setShowFaceBoxes((value) => !value)}
                            >
                              {showFaceBoxes ? "Hide Boxes" : "Show Boxes"}
                            </button>
                          ) : null}
                        </div>
                        <div className="similarity-scroll">
                          {faces.items.map((face) => (
                            <article key={face.id} className="panel" style={{ minWidth: "148px", padding: "0.5rem" }}>
                              {face.crop_preview_url ? (
                                <img
                                  src={mediaUrl(face.crop_preview_url)}
                                  alt={face.person?.name ?? "Face crop"}
                                  style={{ width: "136px", height: "136px", objectFit: "cover", borderRadius: "1rem" }}
                                />
                              ) : null}
                              <div style={{ marginTop: "0.45rem" }}>
                                <strong>{face.person?.name ?? "Unnamed person"}</strong>
                                {face.person ? (
                                  <div className="card-actions" style={{ marginTop: "0.35rem" }}>
                                    <Link href={`/people/${face.person.id}`} className="button ghost-button small-button">Open</Link>
                                    {(user?.role === "admin" || user?.role === "curator") ? (
                                      <button
                                        type="button"
                                        className="button subtle-button small-button"
                                        onClick={async () => {
                                          try {
                                            await updatePerson(face.person!.id, { cover_face_id: face.id });
                                            setFaces(await fetchAssetFaces(params.id));
                                          } catch {
                                            // ignore transient face update errors on detail view
                                          }
                                        }}
                                      >
                                        Set Cover
                                      </button>
                                    ) : null}
                                  </div>
                                ) : null}
                              </div>
                            </article>
                          ))}
                        </div>
                      </article>
                    ) : null}

                    {asset?.media_type === "video" && (waveformPreview || keyframePreviews.length) ? (
                      <article className="panel stack">
                        <div>
                          <p className="eyebrow">Video Artifacts</p>
                          <h2>Waveform & Keyframes</h2>
                        </div>
                        {waveformPreview ? (
                          <img
                            src={waveformPreview}
                            alt={`${asset.filename} waveform`}
                            style={{ width: "100%", borderRadius: "1rem", border: "1px solid var(--border)" }}
                          />
                        ) : null}
                        {keyframePreviews.length ? (
                          <div className="similarity-scroll">
                            {keyframePreviews.map((frameUrl, index) => (
                              <img
                                key={frameUrl}
                                src={frameUrl}
                                alt={`${asset.filename} keyframe ${index + 1}`}
                                style={{
                                  width: "min(260px, 100%)",
                                  aspectRatio: "16 / 9",
                                  objectFit: "cover",
                                  borderRadius: "1rem",
                                  border: "1px solid var(--border)",
                                }}
                              />
                            ))}
                          </div>
                        ) : null}
                      </article>
                    ) : null}
                  </article>
                </div>
              )}

              {activeTab === "metadata" && (
                <div className="metadata-tab stack">
                  {staleMetadata && (
                    <div className="info-banner" style={{ background: "rgba(255, 145, 0, 0.15)", borderColor: "var(--accent)", color: "var(--accent)" }}>
                      <p>
                        <strong>Update Required:</strong> This asset has legacy metadata.
                        <button className="button small-button" onClick={() => void downloadWorkflowFromFile(asset!.id, asset!.filename)}>Run Extraction</button>
                      </p>
                    </div>
                  )}

                  {positivePrompt && (
                    <article className="panel stack">
                      <p className="eyebrow">Positive Prompt</p>
                      <div className="prompt-content selectable">{positivePrompt}</div>
                      <button type="button" className="button subtle-button small-button" onClick={async () => { await copyTextToClipboard(positivePrompt); push("Copied prompt!", "success"); }}>
                        Copy Prompt
                      </button>
                    </article>
                  )}

                  {negativePrompt && (
                    <article className="panel stack">
                      <p className="eyebrow">Negative Prompt</p>
                      <div className="prompt-content subdued selectable">{negativePrompt}</div>
                      <button type="button" className="button subtle-button small-button" onClick={async () => { await copyTextToClipboard(negativePrompt); push("Copied negative prompt!", "success"); }}>
                        Copy Negative Prompt
                      </button>
                    </article>
                  )}

                  {caption && (
                    <article className="panel stack">
                      <p className="eyebrow">Caption</p>
                      <div className="prompt-content selectable">{caption}</div>
                      {asset?.caption_source ? <p className="subdued">Source: {asset.caption_source}</p> : null}
                    </article>
                  )}

                  {ocrText && (
                    <article className="panel stack">
                      <p className="eyebrow">OCR Text</p>
                      <div className="prompt-content subdued selectable">{ocrText}</div>
                      {typeof asset?.ocr_confidence === "number" ? (
                        <p className="subdued">Confidence: {(asset.ocr_confidence * 100).toFixed(0)}%</p>
                      ) : null}
                    </article>
                  )}

                  <article className="panel stack">
                    <div className="row-between">
                      <div>
                        <p className="eyebrow">Vision LLM Analysis</p>
                        <h2>KoboldCpp image read</h2>
                      </div>
                      <button type="button" className="button subtle-button small-button" disabled={analysisBusy} onClick={handleVisionLlm}>
                        {analysisBusy ? "Scanning..." : "Run Vision LLM"}
                      </button>
                    </div>
                    {visionLlmAnalysis ? (
                      <>
                        <div className="prompt-content selectable">{visionLlmAnalysis}</div>
                        <p className="subdued">
                          {[visionLlmSource, visionLlmUpdatedAt].filter(Boolean).join(" · ")}
                        </p>
                      </>
                    ) : (
                      <p className="subdued">No Vision LLM analysis saved yet. Use the gallery context menu or this button to run it on this image.</p>
                    )}
                  </article>

                  <article className="panel stack">
                    <div className="row-between">
                      <div>
                      <p className="eyebrow">Technical Metadata</p>
                      <h2>Summary</h2>
                      </div>
                      <button type="button" className="button ghost-button small-button" disabled={analysisBusy} onClick={handleQueueMetadataScan}>
                        Refresh Metadata
                      </button>
                    </div>
                    <div className="metadata-grid">
                      {summaryEntries.map(([key, value]) => (
                        <div key={key} className="metadata-row">
                          <strong>{key}</strong>
                          <div className="subdued">{String(value ?? "n/a")}</div>
                        </div>
                      ))}
                    </div>
                  </article>
                </div>
              )}

              {activeTab === "workflow" && (
                <div className="workflow-tab stack">
                  <div className="row-between">
                    <div>
                      <p className="eyebrow">Visual Analysis</p>
                      <h2>Extracted Workflow Graph</h2>
                    </div>
                    {asset?.visual_workflow_confidence && (
                      <div className="confidence-badge" style={{ color: (asset?.visual_workflow_confidence ?? 0) > 0.7 ? "var(--accent)" : "var(--subdued)" }}>
                        Confidence: {((asset?.visual_workflow_confidence ?? 0) * 100).toFixed(0)}%
                      </div>
                    )}
                  </div>
                  
                  <VisualWorkflowGraph workflow={asset?.visual_workflow_json ? (asset.visual_workflow_json as any) : null} />
                  
                  {workflowText && (
                    <article className="panel stack">
                      <p className="eyebrow">Embedded Workflow JSON (Metadata)</p>
                      <pre className="prompt-content subdued" style={{ maxHeight: "300px", overflow: "auto", fontSize: "0.8rem" }}>
                        {workflowText}
                      </pre>
                    </article>
                  )}
                </div>
              )}

              {activeTab === "similar" && (
                <div className="similar-tab stack">
                  <section className="stack">
                    <span className="eyebrow">Duplicates ({duplicates.length})</span>
                    <div className="similarity-scroll">
                      {duplicates.map((match) => (
                        <AssetCard key={match.asset.id} asset={match.asset} />
                      ))}
                    </div>
                  </section>

                  <section className="stack">
                    <span className="eyebrow">Visually Similar (Semantic)</span>
                    <div className="similarity-scroll">
                      {semantic.map((match) => (
                        <AssetCard key={match.asset.id} asset={match.asset} />
                      ))}
                    </div>
                  </section>

                  <section className="stack">
                    <span className="eyebrow">Similar Tags</span>
                    <div className="similarity-scroll">
                      {tagSimilar.map((match) => (
                        <AssetCard key={match.asset.id} asset={match.asset} />
                      ))}
                    </div>
                  </section>

                  {visualMatches.length > 0 && (
                    <section className="stack">
                      <span className="eyebrow">Live Visual Search Results</span>
                      <div className="similarity-scroll">
                        {visualMatches.map((match) => (
                          <AssetCard key={match.asset.id} asset={match.asset} />
                        ))}
                      </div>
                    </section>
                  )}
                </div>
              )}

              {activeTab === "location" && gpsLatitude !== null && gpsLongitude !== null && (
                <div className="location-tab stack">
                  <article className="panel stack">
                    <div>
                      <p className="eyebrow">Location Metadata</p>
                      <h2>GPS Coordinates</h2>
                    </div>
                    <div className="gps-map-container" style={{ borderRadius: "16px", overflow: "hidden", border: "1px solid var(--border)" }}>
                      {mapEmbedUrl ? (
                        <iframe
                          width="100%"
                          height="480"
                          style={{ border: 0 }}
                          loading="lazy"
                          src={mapEmbedUrl}
                        />
                      ) : (
                        <div className="empty-state">Map preview unavailable.</div>
                      )}
                      <div style={{ padding: "0.85rem", background: "rgba(7, 16, 20, 0.44)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span className="subdued">
                          {gpsLatitude}, {gpsLongitude}
                        </span>
                        <a href={mapExternalUrl ?? undefined} target="_blank" rel="noopener noreferrer" className="button small-button subtle-button">
                          View on OpenStreetMap
                        </a>
                      </div>
                    </div>
                  </article>
                </div>
              )}
            </>
          )}
        </DetailTabs>

        {/* Sidebar / Sidebar equivalent for detail page */}
        <aside className="asset-sidebar stack">
          {gpsLatitude !== null && gpsLongitude !== null ? (
            <section className="panel stack">
              <div className="row-between">
                <span className="eyebrow">Location</span>
                <Link href={appMapUrl ?? "#"} className="subdued small">
                  Open full map
                </Link>
              </div>
              {mapEmbedUrl ? (
                <iframe
                  title="Asset location preview"
                  src={mapEmbedUrl}
                  width="100%"
                  height="200"
                  style={{ border: 0, borderRadius: "1rem" }}
                  loading="lazy"
                />
              ) : null}
              <a href={mapExternalUrl ?? undefined} target="_blank" rel="noopener noreferrer" className="button ghost-button small-button">
                View on OpenStreetMap
              </a>
            </section>
          ) : null}
          <section className="panel stack">
            <span className="eyebrow">Management</span>
            <div className="stack" style={{ gap: "0.8rem" }}>
              <div className="row-between">
                <strong>Rating</strong>
                <div className="rating-selector">
                  {[1, 2, 3, 4, 5].map((star) => (
                    <button key={star} type="button" className={`star-btn ${rating && rating >= star ? "star-active" : ""}`} onClick={() => setRating(star)}>
                      ★
                    </button>
                  ))}
                </div>
              </div>

              <div className="row-between">
                <strong>Status</strong>
                <select value={reviewStatus} onChange={(e) => setReviewStatus(e.target.value as ReviewStatus)} className="select-input small">
                  <option value="unreviewed">Unreviewed</option>
                  <option value="approved">Approved</option>
                  <option value="rejected">Rejected</option>
                  <option value="favorite">Favorite</option>
                </select>
              </div>

              <div className="row-between">
                <strong>Flagged</strong>
                <input type="checkbox" checked={flagged} onChange={(e) => setFlagged(e.target.checked)} />
              </div>

              <div className="stack">
                <strong>Personal Note</strong>
                <textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Add a private note..." className="text-input" rows={3} />
              </div>

              <button
                type="button"
                className="button accent-button"
                disabled={annotationBusy}
                onClick={async () => {
                  if (!asset) return;
                  setAnnotationBusy(true);
                  try {
                    await bulkAnnotateAssets({
                      asset_ids: [asset.id],
                      rating,
                      review_status: reviewStatus,
                      flagged,
                      note,
                      tags: pendingTags,
                    });
                    setPendingTags([]);
                    const refreshed = await fetchAsset(asset.id);
                    setAsset(refreshed);
                    push("Saved changes!", "success");
                  } catch (nextError) {
                    setError(nextError instanceof Error ? nextError.message : "Unable to save annotation.");
                    push("Failed to save", "error");
                  } finally {
                    setAnnotationBusy(false);
                  }
                }}
              >
                {annotationBusy ? "Saving..." : "Save Changes"}
              </button>
            </div>
          </section>
        </aside>
      </main>

      {asset && (
        <CollectionPickerModal
          open={collectionOpen}
          collections={collections}
          busy={collectionBusy}
          onClose={() => setCollectionOpen(false)}
          onConfirm={async (collectionId) => {
            setCollectionBusy(true);
            try {
              await addAssetsToCollection(collectionId, [asset.id]);
              const collName = collections.find((c) => c.id === collectionId)?.name || "collection";
              push(`Added to ${collName}`, "success");
              setCollectionOpen(false);
            } catch {
              push("Failed to add to collection", "error");
            } finally {
              setCollectionBusy(false);
            }
          }}
        />
      )}
    </AppShell>
  );
}
