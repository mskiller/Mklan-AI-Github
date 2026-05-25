"use client";

import { appendTagFilter, parseTagList, removeTagFilter } from "@/lib/search-filters";
import { SearchFilterFormState, TagCount } from "@/lib/types";

export function FilterSidebar({
  value,
  onChange,
  tagSuggestions,
}: {
  value: SearchFilterFormState;
  onChange: (next: SearchFilterFormState) => void;
  tagSuggestions: TagCount[];
}) {
  const update = (key: keyof SearchFilterFormState, nextValue: string) => onChange({ ...value, [key]: nextValue });
  const activeTags = parseTagList(value.tags);

  return (
    <aside className="panel filter-panel">
      <label className="field">
        <span>Query</span>
        <input value={value.q} onChange={(event) => update("q", event.target.value)} placeholder="sunset sony 2025" />
      </label>
      <label className="field">
        <span>Media Type</span>
        <select value={value.media_type} onChange={(event) => update("media_type", event.target.value)}>
          <option value="">All</option>
          <option value="image">Image</option>
          <option value="video">Video</option>
        </select>
      </label>
      <label className="field">
        <span>Caption</span>
        <input value={value.caption} onChange={(event) => update("caption", event.target.value)} placeholder="caption text" />
      </label>
      <label className="field">
        <span>OCR Text</span>
        <input value={value.ocr_text} onChange={(event) => update("ocr_text", event.target.value)} placeholder="text seen in image" />
      </label>
      <label className="field">
        <span>Camera Make</span>
        <input value={value.camera_make} onChange={(event) => update("camera_make", event.target.value)} />
      </label>
      <label className="field">
        <span>Camera Model</span>
        <input value={value.camera_model} onChange={(event) => update("camera_model", event.target.value)} />
      </label>
      <label className="field">
        <span>Year</span>
        <input value={value.year} onChange={(event) => update("year", event.target.value)} />
      </label>
      <div className="field-grid">
        <label className="field">
          <span>Width Min</span>
          <input value={value.width_min} onChange={(event) => update("width_min", event.target.value)} />
        </label>
        <label className="field">
          <span>Width Max</span>
          <input value={value.width_max} onChange={(event) => update("width_max", event.target.value)} />
        </label>
      </div>
      <div className="field-grid">
        <label className="field">
          <span>Height Min</span>
          <input value={value.height_min} onChange={(event) => update("height_min", event.target.value)} />
        </label>
        <label className="field">
          <span>Height Max</span>
          <input value={value.height_max} onChange={(event) => update("height_max", event.target.value)} />
        </label>
      </div>
      <div className="field-grid">
        <label className="field">
          <span>Duration Min</span>
          <input value={value.duration_min} onChange={(event) => update("duration_min", event.target.value)} />
        </label>
        <label className="field">
          <span>Duration Max</span>
          <input value={value.duration_max} onChange={(event) => update("duration_max", event.target.value)} />
        </label>
      </div>
      <div className="field-grid">
        <label className="field">
          <span>Min Rating</span>
          <select value={value.min_rating} onChange={(event) => update("min_rating", event.target.value)}>
            <option value="">Any</option>
            <option value="1">1+</option>
            <option value="2">2+</option>
            <option value="3">3+</option>
            <option value="4">4+</option>
            <option value="5">5</option>
          </select>
        </label>
        <label className="field">
          <span>Review Status</span>
          <select value={value.review_status} onChange={(event) => update("review_status", event.target.value)}>
            <option value="">Any</option>
            <option value="unreviewed">Unreviewed</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="favorite">Favorite</option>
          </select>
        </label>
      </div>
      <label className="field checkbox-field">
        <span>Flagged Only</span>
        <input
          type="checkbox"
          checked={value.flagged}
          onChange={(event) => onChange({ ...value, flagged: event.target.checked })}
        />
      </label>
      <label className="field checkbox-field">
        <span>Has GPS</span>
        <input
          type="checkbox"
          checked={value.has_gps}
          onChange={(event) => onChange({ ...value, has_gps: event.target.checked })}
        />
      </label>
      <label className="field">
        <span>Tags</span>
        <input value={value.tags} onChange={(event) => update("tags", event.target.value)} placeholder="camera:canon,travel" />
      </label>
      <label className="field">
        <span>Accepted Auto Tags</span>
        <input value={value.auto_tags} onChange={(event) => update("auto_tags", event.target.value)} placeholder="wd tag,auto tag" />
      </label>
      {activeTags.length ? (
        <div className="chip-row">
          {activeTags.map((tag) => (
            <button
              key={tag}
              type="button"
              className="chip buttonless"
              onClick={() => update("tags", removeTagFilter(value.tags, tag))}
            >
              {tag} x
            </button>
          ))}
        </div>
      ) : null}
      <label className="field">
        <span>Sort</span>
        <select value={value.sort} onChange={(event) => update("sort", event.target.value as SearchFilterFormState["sort"])}>
          <option value="relevance">Relevance</option>
          <option value="created_at">Created Date</option>
          <option value="modified_at">Modified Date</option>
          <option value="filename">Filename</option>
          <option value="rating">Rating</option>
          <option value="review_status">Review Status</option>
        </select>
      </label>
      <div>
        <p className="eyebrow">Popular Tags</p>
        <div className="chip-row">
          {tagSuggestions.slice(0, 12).map((tag) => (
            <button
              type="button"
              className="chip buttonless"
              key={tag.tag}
              onClick={() => update("tags", appendTagFilter(value.tags, tag.tag))}
            >
              {tag.tag}
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
}
