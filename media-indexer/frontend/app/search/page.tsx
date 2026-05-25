"use client";

import Link from "next/link";
import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { AssetCard } from "@/components/asset-card";
import { BottomSheet } from "@/components/BottomSheet";
import { BulkActionBar } from "@/components/bulk-action-bar";
import { CompareSelectionTray } from "@/components/compare-selection-tray";
import { CollectionPickerModal } from "@/components/collection-picker-modal";
import { FilterSidebar } from "@/components/filter-sidebar";
import { useModuleRegistry } from "@/components/module-registry-provider";
import {
  addAssetsToCollection,
  addSearchResultsToCollection,
  downloadWorkflow,
  fetchCollections,
  fetchNaturalLanguageSearch,
  fetchSearch,
  fetchTags,
} from "@/lib/api";
import { buildSearchQuery, DEFAULT_SEARCH_FILTERS, parseSearchFilterState, parseTagList, removeTagFilter } from "@/lib/search-filters";
import { useAuth } from "@/components/auth-provider";
import { useSettings } from "@/components/settings-provider";
import { AssetListResponse, AssetSummary, CollectionSummary, ReviewStatus, SearchFilterFormState, TagCount } from "@/lib/types";

type SearchMode = "tag" | "nl";

function SearchPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useAuth();
  const { isModuleEnabled } = useModuleRegistry();
  const { nsfwVisible } = useSettings();
  const searchParamKey = searchParams.toString();
  const [filters, setFilters] = useState<SearchFilterFormState>(DEFAULT_SEARCH_FILTERS);
  const [mode, setMode] = useState<SearchMode>(searchParams.get("mode") === "nl" ? "nl" : "tag");
  const [naturalQuery, setNaturalQuery] = useState(searchParams.get("nl_q") ?? "");
  const [results, setResults] = useState<AssetListResponse | null>(null);
  const [tagSuggestions, setTagSuggestions] = useState<TagCount[]>([]);
  const [collections, setCollections] = useState<CollectionSummary[]>([]);
  const [selected, setSelected] = useState<AssetSummary[]>([]);
  const [selectionMode, setSelectionMode] = useState(false);
  const [bulkMode, setBulkMode] = useState(false);
  const [bulkSelectedIds, setBulkSelectedIds] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [page, setPage] = useState(1);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const isMobile = typeof window !== "undefined" && window.matchMedia("(max-width: 900px)").matches;
  const [collectionOpen, setCollectionOpen] = useState(false);
  const [collectionBusy, setCollectionBusy] = useState(false);
  const [collectionMode, setCollectionMode] = useState<"selected" | "search-results">("selected");
  const [pendingCollectionAssetIds, setPendingCollectionAssetIds] = useState<string[]>([]);
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const collectionsEnabled = isModuleEnabled("collections");

  const emptyResults = (pageSize = 24): AssetListResponse => ({
    items: [],
    total: 0,
    page: 1,
    page_size: pageSize,
  });

  const load = async (
    nextFilters: SearchFilterFormState,
    nextPage: number,
    append = false,
    nextMode: SearchMode = mode,
    nextNaturalQuery: string = naturalQuery,
  ) => {
    if (append) {
      setLoadingMore(true);
    } else {
      setLoading(true);
      setError(null);
    }
    try {
      let nextResults: AssetListResponse;
      if (nextMode === "nl") {
        const query = nextNaturalQuery.trim();
        nextResults = query ? await fetchNaturalLanguageSearch(query, 50) : emptyResults(50);
        setHasMore(false);
      } else {
        const apiFilters = {
          ...nextFilters,
          page: nextPage,
          min_rating: nextFilters.min_rating ? Number(nextFilters.min_rating) : undefined,
          review_status: (nextFilters.review_status as ReviewStatus) || undefined,
          exclude_tags: !nsfwVisible ? "nsfw" : undefined,
        };
        nextResults = await fetchSearch(apiFilters);
        setHasMore(nextPage * nextResults.page_size < nextResults.total);
      }
      setResults((current) =>
        append && current && nextMode === "tag"
          ? {
              ...nextResults,
              items: [...current.items, ...nextResults.items],
            }
          : nextResults
      );
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Unable to load search.");
    } finally {
      if (append) {
        setLoadingMore(false);
      } else {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    const loadTags = async () => {
      try {
        setTagSuggestions(await fetchTags());
      } catch {
        setTagSuggestions([]);
      }
    };
    void loadTags();
  }, []);

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

  useEffect(() => {
    const nextFilters = parseSearchFilterState(searchParams);
    const nextMode = searchParams.get("mode") === "nl" ? "nl" : "tag";
    const nextNaturalQuery = searchParams.get("nl_q") ?? "";
    if (nextFilters.sort === "relevance" && !nextFilters.q.trim()) {
      nextFilters.sort = "modified_at";
    }
    setMode(nextMode);
    setNaturalQuery(nextNaturalQuery);
    setFilters(nextFilters);
    setPage(1);
    setSelected([]);
    void load(nextFilters, 1, false, nextMode, nextNaturalQuery);
  }, [searchParamKey, nsfwVisible]);

  useEffect(() => {
    if (page === 1 || mode === "nl") {
      return;
    }
    void load(filters, page, true, mode, naturalQuery);
  }, [page, mode, naturalQuery]);

  useEffect(() => {
    const target = sentinelRef.current;
    if (!target || mode === "nl" || !hasMore || loading || loadingMore) {
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          setPage((current) => current + 1);
        }
      },
      { rootMargin: "800px 0px" }
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [hasMore, loading, loadingMore, mode, results?.items.length]);

  const toggleSelection = (asset: AssetSummary) => {
    setSelected((current) => {
      const exists = current.some((item) => item.id === asset.id);
      if (exists) {
        return current.filter((item) => item.id !== asset.id);
      }
      return [...current, asset];
    });
  };

  const selectAllLoaded = () => {
    const loadedItems = results?.items ?? [];
    if (!loadedItems.length) {
      return;
    }
    setSelectionMode(true);
    setSelected(loadedItems);
  };

  const pushSearchState = (
    nextFilters: SearchFilterFormState,
    nextMode: SearchMode,
    nextNaturalQuery: string,
  ) => {
    const params = new URLSearchParams(buildSearchQuery(nextFilters));
    if (nextMode === "nl") {
      params.set("mode", "nl");
    } else {
      params.delete("mode");
    }
    if (nextNaturalQuery.trim()) {
      params.set("nl_q", nextNaturalQuery.trim());
    } else {
      params.delete("nl_q");
    }
    const query = params.toString();
    router.push(`/search${query ? `?${query}` : ""}`);
  };

  const applyFilters = () => {
    setFiltersOpen(false);
    pushSearchState(filters, mode, naturalQuery);
  };

  const resetFilters = () => {
    setFiltersOpen(false);
    pushSearchState({ ...DEFAULT_SEARCH_FILTERS }, mode, naturalQuery);
  };

  const activeTags = parseTagList(filters.tags);
  const activeAutoTags = parseTagList(filters.auto_tags);
  const activeFilters = [
    filters.q ? `Query: ${filters.q}` : null,
    filters.media_type ? `Type: ${filters.media_type}` : null,
    filters.caption ? `Caption: ${filters.caption}` : null,
    filters.ocr_text ? `OCR: ${filters.ocr_text}` : null,
    filters.camera_make ? `Make: ${filters.camera_make}` : null,
    filters.camera_model ? `Model: ${filters.camera_model}` : null,
    filters.year ? `Year: ${filters.year}` : null,
    filters.width_min || filters.width_max ? `Width: ${filters.width_min || "0"}-${filters.width_max || "any"}` : null,
    filters.height_min || filters.height_max ? `Height: ${filters.height_min || "0"}-${filters.height_max || "any"}` : null,
    filters.duration_min || filters.duration_max ? `Duration: ${filters.duration_min || "0"}-${filters.duration_max || "any"}` : null,
    filters.has_gps ? "Has GPS" : null,
    filters.sort !== DEFAULT_SEARCH_FILTERS.sort ? `Sort: ${filters.sort}` : null,
  ].filter((value): value is string => Boolean(value));
  const compareHref = selected.length === 2 ? `/compare?a=${selected[0].id}&b=${selected[1].id}` : null;
  const canAddSearchResults = mode === "tag" && Boolean(user?.capabilities.can_manage_collections) && collectionsEnabled && Boolean(results?.total);

  return (
    <AppShell
      title="Search"
      description="Indexed discovery across exact metadata filters and natural-language semantic search."
      actions={
        compareHref || canAddSearchResults ? (
          <div className="page-actions">
            <Link href="/browse-indexed" className="button subtle-button small-button">
              Browse Indexed
            </Link>
            {canAddSearchResults ? (
              <button
                className="button ghost-button small-button"
                type="button"
                onClick={() => {
                  setCollectionMode("search-results");
                  setCollectionOpen(true);
                }}
              >
                Add Search Results
              </button>
            ) : null}
            {compareHref ? (
              <button className="button" type="button" onClick={() => router.push(compareHref)}>
                Compare Selected
              </button>
            ) : null}
          </div>
        ) : undefined
      }
    >
      <CollectionPickerModal
        open={collectionOpen}
        collections={collections}
        busy={collectionBusy}
        onClose={() => setCollectionOpen(false)}
        onConfirm={async (collectionId) => {
          setCollectionBusy(true);
          setError(null);
          try {
            if (collectionMode === "selected") {
              await addAssetsToCollection(
                collectionId,
                pendingCollectionAssetIds.length ? pendingCollectionAssetIds : selected.map((asset) => asset.id)
              );
            } else {
              await addSearchResultsToCollection(collectionId, {
                q: filters.q || undefined,
                media_type: filters.media_type || undefined,
                caption: filters.caption || undefined,
                ocr_text: filters.ocr_text || undefined,
                camera_make: filters.camera_make || undefined,
                camera_model: filters.camera_model || undefined,
                year: filters.year ? Number(filters.year) : undefined,
                width_min: filters.width_min ? Number(filters.width_min) : undefined,
                width_max: filters.width_max ? Number(filters.width_max) : undefined,
                height_min: filters.height_min ? Number(filters.height_min) : undefined,
                height_max: filters.height_max ? Number(filters.height_max) : undefined,
                duration_min: filters.duration_min ? Number(filters.duration_min) : undefined,
                duration_max: filters.duration_max ? Number(filters.duration_max) : undefined,
                tags: parseTagList(filters.tags),
                auto_tags: parseTagList(filters.auto_tags),
              });
            }
            setCollectionOpen(false);
            setPendingCollectionAssetIds([]);
          } catch (nextError) {
            setError(nextError instanceof Error ? nextError.message : "Unable to add assets to collection.");
          } finally {
            setCollectionBusy(false);
          }
        }}
      />
      <div className="search-layout">
        {mode === "tag" && isMobile ? (
          <BottomSheet
            open={filtersOpen}
            onClose={() => setFiltersOpen(false)}
            title="Search Filters"
            subtitle="Refine the index"
          >
            <FilterSidebar value={filters} onChange={setFilters} tagSuggestions={tagSuggestions} />
            <div className="search-sidebar-actions search-mobile-sheet-actions">
              <button className="button ghost-button small-button" type="button" onClick={resetFilters}>
                Reset
              </button>
              <button className="button small-button" type="button" onClick={applyFilters}>
                Apply Filters
              </button>
            </div>
          </BottomSheet>
        ) : null}
        {mode === "tag" && !isMobile ? (
          <>
            <button
              type="button"
              aria-label="Close filters"
              className={`search-overlay ${filtersOpen ? "search-overlay-visible" : ""}`}
              onClick={() => setFiltersOpen(false)}
            />
            <aside className={`search-sidebar ${filtersOpen ? "search-sidebar-open" : ""}`}>
              <div className="search-sidebar-header">
                <div>
                  <p className="eyebrow">Search Filters</p>
                  <h2>Refine the index</h2>
                </div>
                <button className="button ghost-button small-button search-sidebar-close" type="button" onClick={() => setFiltersOpen(false)}>
                  Close
                </button>
              </div>
              <FilterSidebar value={filters} onChange={setFilters} tagSuggestions={tagSuggestions} />
              <div className="search-sidebar-actions">
                <button className="button ghost-button small-button" type="button" onClick={resetFilters}>
                  Reset
                </button>
                <button className="button small-button" type="button" onClick={applyFilters}>
                  Apply Filters
                </button>
              </div>
            </aside>
          </>
        ) : null}
        <section className="stack search-results">
          {bulkMode && bulkSelectedIds.length > 0 ? (
            <BulkActionBar
              selectedIds={bulkSelectedIds}
              onClear={() => setBulkSelectedIds([])}
              onDone={() => {
                setBulkSelectedIds([]);
                setBulkMode(false);
                void load(filters, 1, false, mode, naturalQuery);
              }}
            />
          ) : null}
          <CompareSelectionTray
            selectionMode={selectionMode}
            selectedCount={selected.length}
            compareHref={compareHref}
            onToggleSelectionMode={() => setSelectionMode((value) => !value)}
            onClearSelection={() => setSelected([])}
            hint={
              mode === "nl"
                ? "Natural-language search uses semantic embeddings. Select results for compare or collection work after you find the right visual cluster."
                : "Metadata search combines exact filters, prompt tags, and review state. Keep exactly two selected when you want to compare."
            }
            canAddToCollection={Boolean(user?.capabilities.can_manage_collections) && collectionsEnabled}
            onAddToCollection={
              user?.capabilities.can_manage_collections && collectionsEnabled
                ? () => {
                  setCollectionMode("selected");
                  setPendingCollectionAssetIds(selected.map((asset) => asset.id));
                  setCollectionOpen(true);
                }
                : undefined
            }
          />
          <section className="panel stack">
            <div className="row-between">
              <div>
                <p className="eyebrow">Search Mode</p>
                <h2>{mode === "nl" ? "Natural Language" : "Metadata + Tags"}</h2>
              </div>
              <div className="card-actions">
                <button
                  type="button"
                  className={`button small-button ${mode === "tag" ? "" : "ghost-button"}`}
                  onClick={() => {
                    setMode("tag");
                    pushSearchState(filters, "tag", naturalQuery);
                  }}
                >
                  Metadata
                </button>
                <button
                  type="button"
                  className={`button small-button ${mode === "nl" ? "" : "ghost-button"}`}
                  onClick={() => {
                    setMode("nl");
                    pushSearchState(filters, "nl", naturalQuery);
                  }}
                >
                  Natural Language
                </button>
              </div>
            </div>
            {mode === "nl" ? (
              <div className="stack">
                <label className="field">
                  <span>Describe what you want to find</span>
                  <input
                    value={naturalQuery}
                    onChange={(event) => setNaturalQuery(event.target.value)}
                    placeholder="red bicycle in a rainy street at dusk"
                  />
                </label>
                <div className="card-actions">
                  <button
                    type="button"
                    className="button small-button"
                    onClick={() => pushSearchState(filters, "nl", naturalQuery)}
                  >
                    Search by Meaning
                  </button>
                  {naturalQuery ? (
                    <button
                      type="button"
                      className="button ghost-button small-button"
                      onClick={() => {
                        setNaturalQuery("");
                        pushSearchState(filters, "nl", "");
                      }}
                    >
                      Clear Query
                    </button>
                  ) : null}
                </div>
              </div>
            ) : (
              <p className="subdued">
                Use the filter panel for exact metadata, tags, rating, review state, and GPS-aware searches.
              </p>
            )}
          </section>
          {!selectionMode ? (
            <div className="page-actions results-header" style={{ paddingBottom: "0.5rem" }}>
              <button
                type="button"
                className={`button small-button ${bulkMode ? "" : "ghost-button"}`}
                onClick={() => {
                  setBulkMode((value) => !value);
                  setBulkSelectedIds([]);
                }}
              >
                {bulkMode ? `Bulk Mode (${bulkSelectedIds.length} selected)` : "Bulk Curate"}
              </button>
            </div>
          ) : null}
          <div className="row-between">
            <div>
              <p className="eyebrow">Indexed Results</p>
              <h2>{results?.total ?? 0} assets</h2>
              <p className="subdued">
                {mode === "nl"
                  ? "Semantic results are ordered by embedding similarity."
                  : "Prompt tags and normal tags are clickable anywhere in the app and flow back into this search filter set."}
              </p>
            </div>
            <div className="card-actions">
              <button className="button ghost-button small-button" type="button" onClick={selectAllLoaded} disabled={!results?.items.length}>
                Select All Loaded
              </button>
              {mode === "tag" ? (
                <>
                  <button className="button ghost-button small-button search-filters-button" type="button" onClick={() => setFiltersOpen(true)}>
                    Filters{activeFilters.length || activeTags.length || activeAutoTags.length ? ` (${activeFilters.length + activeTags.length + activeAutoTags.length})` : ""}
                  </button>
                  <button className="button small-button desktop-filter-apply" type="button" onClick={applyFilters}>
                    Apply Filters
                  </button>
                </>
              ) : null}
            </div>
          </div>
          {mode === "tag" && (activeFilters.length || activeTags.length || activeAutoTags.length) ? (
            <section className="panel stack">
              <div className="row-between">
                <div>
                  <p className="eyebrow">Active Filters</p>
                  <h2>{activeFilters.length + activeTags.length + activeAutoTags.length} active</h2>
                </div>
                <button className="button ghost-button small-button" type="button" onClick={resetFilters}>
                  Clear All
                </button>
              </div>
              <div className="chip-row">
                {activeFilters.map((label) => (
                  <span key={label} className="chip">
                    {label}
                  </span>
                ))}
                {activeTags.map((tag) => (
                  <button
                    key={tag}
                    type="button"
                    className="chip buttonless"
                    onClick={() => {
                      const nextFilters = { ...filters, tags: removeTagFilter(filters.tags, tag) };
                      setFilters(nextFilters);
                      pushSearchState(nextFilters, mode, naturalQuery);
                    }}
                  >
                    {tag} x
                  </button>
                ))}
                {activeAutoTags.map((tag) => (
                  <button
                    key={`auto-${tag}`}
                    type="button"
                    className="chip buttonless"
                    onClick={() => {
                      const nextFilters = { ...filters, auto_tags: removeTagFilter(filters.auto_tags, tag) };
                      setFilters(nextFilters);
                      pushSearchState(nextFilters, mode, naturalQuery);
                    }}
                  >
                    auto:{tag} x
                  </button>
                ))}
              </div>
            </section>
          ) : null}
          {error ? <section className="panel empty-state">{error}</section> : null}
          {loading ? <section className="panel empty-state">Loading indexed assets…</section> : null}
          <div className="results-grid">
            {results?.items.map((asset) => (
              <AssetCard
                key={asset.id}
                asset={asset}
                selected={selected.some((item) => item.id === asset.id)}
                onSelect={toggleSelection}
                selectionMode={selectionMode}
                bulkSelected={bulkMode && bulkSelectedIds.includes(asset.id)}
                onBulkToggle={bulkMode ? () => setBulkSelectedIds((ids) => (ids.includes(asset.id) ? ids.filter((x) => x !== asset.id) : [...ids, asset.id])) : undefined}
                onAddToCollection={
                  user?.capabilities.can_manage_collections && collectionsEnabled
                    ? (nextAsset) => {
                        setCollectionMode("selected");
                        setPendingCollectionAssetIds([nextAsset.id]);
                        setCollectionOpen(true);
                      }
                    : undefined
                }
                onDownloadWorkflow={
                  asset.workflow_export_available
                    ? () => void downloadWorkflow(asset.id, asset.filename)
                    : undefined
                }
                onTagged={() => void load(filters, 1, false, mode, naturalQuery)}
              />
            ))}
          </div>
          {results ? (
            <section className="panel stack">
              <div className="row-between">
                <p className="subdued">Showing {results.items.length} of {results.total} indexed assets</p>
                {selected.length ? <p className="subdued">{selected.length} selected for compare</p> : null}
                {loadingMore ? <p className="subdued">Loading more…</p> : null}
              </div>
              {!hasMore && results.items.length && mode === "tag" ? <p className="subdued">You reached the end of the indexed feed.</p> : null}
              {!results.items.length && !loading ? (
                <p className="subdued">
                  {mode === "nl" && !naturalQuery.trim()
                    ? "Enter a natural-language prompt to search by visual meaning."
                    : "No indexed assets match this search yet."}
                </p>
              ) : null}
              <div ref={sentinelRef} className="infinite-sentinel" />
            </section>
          ) : null}
        </section>
      </div>
    </AppShell>
  );
}

export default function SearchPage() {
  return (
    <Suspense
      fallback={
        <AppShell title="Search" description="Indexed discovery across exact metadata filters and natural-language semantic search.">
          <section className="panel empty-state">Loading search…</section>
        </AppShell>
      }
    >
      <SearchPageContent />
    </Suspense>
  );
}
