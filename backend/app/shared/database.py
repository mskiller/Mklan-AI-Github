from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
import sqlite3

# Combined schema from both projects
SCHEMA = """
PRAGMA foreign_keys = ON;

-- ============================================
-- MKLAN STUDIO UNIFIED SCHEMA
-- ============================================

-- ========== WILDCARD TABLES ==========

CREATE TABLE IF NOT EXISTS source_files (
    id INTEGER PRIMARY KEY,
    original_path TEXT NOT NULL UNIQUE,
    relative_path TEXT NOT NULL,
    extension TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    last_modified TEXT NOT NULL,
    wildcard_path TEXT NOT NULL,
    import_status TEXT NOT NULL,
    warning_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY,
    source_file_id INTEGER NOT NULL REFERENCES source_files(id) ON DELETE CASCADE,
    wildcard_path TEXT NOT NULL,
    item_index INTEGER NOT NULL,
    raw_text TEXT NOT NULL,
    staged_text TEXT,
    normalized_text TEXT NOT NULL,
    kind TEXT NOT NULL,
    prompt_mode TEXT NOT NULL DEFAULT 'unknown',
    tags_json TEXT NOT NULL,
    positive_tags_json TEXT NOT NULL DEFAULT '[]',
    negative_tags_json TEXT NOT NULL DEFAULT '[]',
    all_extracted_tags_json TEXT NOT NULL DEFAULT '[]',
    prompt_parts_json TEXT NOT NULL DEFAULT '{}',
    tag_categories_json TEXT NOT NULL DEFAULT '[]',
    refs_json TEXT NOT NULL,
    warnings_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entry_history (
    id INTEGER PRIMARY KEY,
    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    previous_text TEXT,
    next_text TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scan_runs (
    id INTEGER PRIMARY KEY,
    source_root TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tag_index (
    tag TEXT NOT NULL,
    category TEXT NOT NULL,
    usage_count INTEGER NOT NULL,
    PRIMARY KEY (tag, category)
);

CREATE TABLE IF NOT EXISTS category_index (
    category TEXT PRIMARY KEY,
    usage_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS category_stats (
    category TEXT PRIMARY KEY,
    entry_count INTEGER NOT NULL,
    file_count INTEGER NOT NULL,
    tag_count INTEGER NOT NULL,
    wildcard_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS prompt_mode_index (
    prompt_mode TEXT PRIMARY KEY,
    entry_count INTEGER NOT NULL,
    file_count INTEGER NOT NULL,
    wildcard_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS prompt_recipes (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    preset TEXT NOT NULL,
    slots_json TEXT NOT NULL,
    negative_tags_json TEXT NOT NULL,
    wildcard_refs_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tag_overrides (
    tag TEXT PRIMARY KEY,
    canonical_tag TEXT,
    category TEXT,
    is_ignored INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS taxonomy_rules (
    category TEXT NOT NULL,
    keyword TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (category, keyword)
);

CREATE TABLE IF NOT EXISTS taxonomy_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_file_stats (
    source_file_id INTEGER PRIMARY KEY REFERENCES source_files(id) ON DELETE CASCADE,
    entry_count INTEGER NOT NULL DEFAULT 0,
    prompt_count INTEGER NOT NULL DEFAULT 0,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    unresolved_refs INTEGER NOT NULL DEFAULT 0,
    categories_json TEXT NOT NULL DEFAULT '[]',
    prompt_modes_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS llm_jobs (
    id INTEGER PRIMARY KEY,
    task TEXT NOT NULL,
    prompt_mode TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    model TEXT NOT NULL,
    input_text TEXT NOT NULL,
    status TEXT NOT NULL,
    suggestion TEXT NOT NULL DEFAULT '',
    error TEXT,
    endpoint_used TEXT,
    raw_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    accepted_at TEXT,
    rejected_at TEXT,
    cancelled_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_entries_source_file ON entries(source_file_id);
CREATE INDEX IF NOT EXISTS idx_entries_wildcard_path ON entries(wildcard_path);
CREATE INDEX IF NOT EXISTS idx_entries_normalized ON entries(normalized_text);
CREATE INDEX IF NOT EXISTS idx_source_files_wildcard_path ON source_files(wildcard_path);
CREATE INDEX IF NOT EXISTS idx_entries_prompt_mode ON entries(prompt_mode);

-- ========== MOVIE SCRIPTING TABLES ==========

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    scenario_text TEXT NOT NULL DEFAULT '',
    genre TEXT NOT NULL DEFAULT 'cinematic drama',
    tone TEXT NOT NULL DEFAULT 'grounded and atmospheric',
    target_duration_s INTEGER NOT NULL DEFAULT 240,
    output_width INTEGER NOT NULL DEFAULT 1280,
    output_height INTEGER NOT NULL DEFAULT 720,
    output_fps INTEGER NOT NULL DEFAULT 24,
    aspect_ratio TEXT NOT NULL DEFAULT '16:9',
    workflow_version INTEGER NOT NULL DEFAULT 1,
    style_anchor_text TEXT NOT NULL DEFAULT '',
    model_settings_override_json TEXT,
    opening_image_prompt_text TEXT NOT NULL DEFAULT '',
    opening_image_relative_path TEXT,
    opening_image_original_filename TEXT,
    opening_image_mime_type TEXT,
    opening_image_size_bytes INTEGER NOT NULL DEFAULT 0,
    opening_image_uploaded_at TEXT,
    beat_board_status TEXT NOT NULL DEFAULT 'empty',
    archived_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS story_scenes (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    order_index INTEGER NOT NULL,
    title TEXT NOT NULL,
    target_duration_s INTEGER NOT NULL,
    narrative_text TEXT NOT NULL,
    duration_locked INTEGER NOT NULL DEFAULT 0,
    first_image_prompt_text TEXT NOT NULL DEFAULT '',
    first_image_relative_path TEXT,
    first_image_original_filename TEXT,
    first_image_mime_type TEXT,
    first_image_size_bytes INTEGER NOT NULL DEFAULT 0,
    first_image_uploaded_at TEXT,
    first_image_source TEXT,
    image_generation_status TEXT NOT NULL DEFAULT 'idle',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_story_scenes_project_order ON story_scenes(project_id, order_index);

CREATE TABLE IF NOT EXISTS story_beats (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    act_index INTEGER NOT NULL,
    order_index INTEGER NOT NULL,
    title TEXT NOT NULL,
    summary_text TEXT NOT NULL DEFAULT '',
    purpose_text TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'generated',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_story_beats_project_act_order ON story_beats(project_id, act_index, order_index);

CREATE TABLE IF NOT EXISTS scenes (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    story_scene_id TEXT REFERENCES story_scenes(id) ON DELETE CASCADE,
    order_index INTEGER NOT NULL,
    absolute_order INTEGER,
    title TEXT NOT NULL,
    target_duration_s INTEGER NOT NULL,
    narrative_text TEXT NOT NULL,
    duration_locked INTEGER NOT NULL DEFAULT 0,
    prompt_text TEXT NOT NULL DEFAULT '',
    camera_direction TEXT NOT NULL DEFAULT '',
    action_direction TEXT NOT NULL DEFAULT '',
    wan_prompt_text TEXT NOT NULL DEFAULT '',
    uploaded_sequence_relative_path TEXT,
    uploaded_sequence_original_filename TEXT,
    uploaded_sequence_mime_type TEXT,
    uploaded_sequence_size_bytes INTEGER NOT NULL DEFAULT 0,
    uploaded_sequence_uploaded_at TEXT,
    approved_video_relative_path TEXT,
    approved_video_original_filename TEXT,
    approved_video_mime_type TEXT,
    approved_video_size_bytes INTEGER NOT NULL DEFAULT 0,
    approved_video_created_at TEXT,
    approved_video_source TEXT,
    input_frame_relative_path TEXT,
    input_frame_original_filename TEXT,
    input_frame_mime_type TEXT,
    input_frame_size_bytes INTEGER NOT NULL DEFAULT 0,
    input_frame_created_at TEXT,
    last_frame_relative_path TEXT,
    last_frame_original_filename TEXT,
    last_frame_mime_type TEXT,
    last_frame_size_bytes INTEGER NOT NULL DEFAULT 0,
    last_frame_created_at TEXT,
    trim_in_ms INTEGER NOT NULL DEFAULT 0,
    trim_out_ms INTEGER NOT NULL DEFAULT 0,
    include_in_assembly INTEGER NOT NULL DEFAULT 1,
    render_status TEXT NOT NULL DEFAULT 'draft',
    approved_clip_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scenes_project_order ON scenes(project_id, order_index);

CREATE TABLE IF NOT EXISTS scene_image_variants (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    scene_id TEXT NOT NULL REFERENCES story_scenes(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    model_name TEXT NOT NULL,
    seed INTEGER,
    prompt_text TEXT NOT NULL DEFAULT '',
    relative_path TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    mime_type TEXT,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scene_image_variants_scene_created ON scene_image_variants(scene_id, created_at DESC);

CREATE TABLE IF NOT EXISTS sequence_video_variants (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    scene_id TEXT NOT NULL REFERENCES story_scenes(id) ON DELETE CASCADE,
    sequence_id TEXT NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    model_name TEXT NOT NULL,
    seed INTEGER,
    prompt_text TEXT NOT NULL DEFAULT '',
    relative_path TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    mime_type TEXT,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    native_duration_s REAL NOT NULL DEFAULT 0,
    output_duration_s REAL NOT NULL DEFAULT 0,
    input_frame_relative_path TEXT,
    input_frame_original_filename TEXT,
    input_frame_mime_type TEXT,
    input_frame_size_bytes INTEGER NOT NULL DEFAULT 0,
    input_frame_created_at TEXT,
    last_frame_relative_path TEXT,
    last_frame_original_filename TEXT,
    last_frame_mime_type TEXT,
    last_frame_size_bytes INTEGER NOT NULL DEFAULT 0,
    last_frame_created_at TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sequence_video_variants_sequence_created ON sequence_video_variants(sequence_id, created_at DESC);

CREATE TABLE IF NOT EXISTS clip_assets (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    scene_id TEXT NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    renderer TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    duration_s REAL NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'succeeded',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_clips_scene_version ON clip_assets(scene_id, version DESC);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    scene_id TEXT,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL,
    progress REAL NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT NOT NULL DEFAULT '{}',
    error_text TEXT,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_project_created ON jobs(project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS continuity_reviews (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    scene_id TEXT NOT NULL UNIQUE REFERENCES story_scenes(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    summary_text TEXT NOT NULL DEFAULT '',
    findings_json TEXT NOT NULL DEFAULT '[]',
    sequence_suggestions_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_continuity_reviews_project_scene ON continuity_reviews(project_id, scene_id);

CREATE TABLE IF NOT EXISTS export_assets (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    relative_path TEXT NOT NULL,
    duration_s REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_characters (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    role_summary TEXT NOT NULL DEFAULT '',
    prompt_tags TEXT NOT NULL DEFAULT '',
    order_index INTEGER NOT NULL,
    portrait_image_url TEXT,
    cowboyshot_image_url TEXT,
    fullbody_image_url TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_project_characters_project_order ON project_characters(project_id, order_index);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value_text TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- FTS for wildcard search
CREATE VIRTUAL TABLE IF NOT EXISTS entry_fts USING fts5(effective_text, wildcard_path, tags);
"""


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            self._migrate(connection)

    @contextmanager
    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _migrate(self, connection: sqlite3.Connection) -> None:
        """Apply any necessary migrations."""
        # For now, schema is already at unified version
        # Migration logic would go here for future schema changes
        pass

    def _ensure_columns(self, connection: sqlite3.Connection, table: str, columns: dict) -> None:
        """Ensure columns exist, add if missing."""
        existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
        for col, definition in columns.items():
            if col.lower() not in existing:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")

    def _ensure_table(self, connection: sqlite3.Connection, sql: str) -> None:
        """Ensure table/index exists."""
        connection.execute(sql)