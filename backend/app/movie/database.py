from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from app.v2.core_db import connect_core_db


SCHEMA = """
PRAGMA foreign_keys = ON;

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
"""


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def initialize(self) -> None:
        pass

    @contextmanager
    def connect(self):
        with connect_core_db(dict_rows=True) as connection:
            yield connection

    def _migrate(self, connection: sqlite3.Connection) -> None:
        self._ensure_columns(
            connection,
            "projects",
            {
                "workflow_version": "INTEGER NOT NULL DEFAULT 1",
                "model_settings_override_json": "TEXT",
                "opening_image_prompt_text": "TEXT NOT NULL DEFAULT ''",
                "opening_image_relative_path": "TEXT",
                "opening_image_original_filename": "TEXT",
                "opening_image_mime_type": "TEXT",
                "opening_image_size_bytes": "INTEGER NOT NULL DEFAULT 0",
                "opening_image_uploaded_at": "TEXT",
                "beat_board_status": "TEXT NOT NULL DEFAULT 'empty'",
                "archived_at": "TEXT",
            },
        )
        self._ensure_table(
            connection,
            """
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
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
        )
        self._ensure_columns(
            connection,
            "story_scenes",
            {
                "duration_locked": "INTEGER NOT NULL DEFAULT 0",
                "first_image_prompt_text": "TEXT NOT NULL DEFAULT ''",
                "first_image_relative_path": "TEXT",
                "first_image_original_filename": "TEXT",
                "first_image_mime_type": "TEXT",
                "first_image_size_bytes": "INTEGER NOT NULL DEFAULT 0",
                "first_image_uploaded_at": "TEXT",
                "first_image_source": "TEXT",
                "image_generation_status": "TEXT NOT NULL DEFAULT 'idle'",
            },
        )
        self._ensure_table(
            connection,
            "CREATE INDEX IF NOT EXISTS idx_story_scenes_project_order ON story_scenes(project_id, order_index)",
        )
        self._ensure_table(
            connection,
            """
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
            )
            """,
        )
        self._ensure_table(
            connection,
            "CREATE INDEX IF NOT EXISTS idx_story_beats_project_act_order ON story_beats(project_id, act_index, order_index)",
        )
        self._ensure_columns(
            connection,
            "scenes",
            {
                "story_scene_id": "TEXT REFERENCES story_scenes(id) ON DELETE CASCADE",
                "absolute_order": "INTEGER",
                "duration_locked": "INTEGER NOT NULL DEFAULT 0",
                "camera_direction": "TEXT NOT NULL DEFAULT ''",
                "action_direction": "TEXT NOT NULL DEFAULT ''",
                "wan_prompt_text": "TEXT NOT NULL DEFAULT ''",
                "uploaded_sequence_relative_path": "TEXT",
                "uploaded_sequence_original_filename": "TEXT",
                "uploaded_sequence_mime_type": "TEXT",
                "uploaded_sequence_size_bytes": "INTEGER NOT NULL DEFAULT 0",
                "uploaded_sequence_uploaded_at": "TEXT",
                "approved_video_relative_path": "TEXT",
                "approved_video_original_filename": "TEXT",
                "approved_video_mime_type": "TEXT",
                "approved_video_size_bytes": "INTEGER NOT NULL DEFAULT 0",
                "approved_video_created_at": "TEXT",
                "approved_video_source": "TEXT",
                "input_frame_relative_path": "TEXT",
                "input_frame_original_filename": "TEXT",
                "input_frame_mime_type": "TEXT",
                "input_frame_size_bytes": "INTEGER NOT NULL DEFAULT 0",
                "input_frame_created_at": "TEXT",
                "last_frame_relative_path": "TEXT",
                "last_frame_original_filename": "TEXT",
                "last_frame_mime_type": "TEXT",
                "last_frame_size_bytes": "INTEGER NOT NULL DEFAULT 0",
                "last_frame_created_at": "TEXT",
                "trim_in_ms": "INTEGER NOT NULL DEFAULT 0",
                "trim_out_ms": "INTEGER NOT NULL DEFAULT 0",
                "include_in_assembly": "INTEGER NOT NULL DEFAULT 1",
            },
        )
        self._ensure_table(
            connection,
            "CREATE INDEX IF NOT EXISTS idx_scenes_story_scene_order ON scenes(story_scene_id, order_index)",
        )
        self._ensure_table(
            connection,
            "CREATE INDEX IF NOT EXISTS idx_scenes_project_absolute_order ON scenes(project_id, absolute_order)",
        )
        self._ensure_table(
            connection,
            """
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
            )
            """,
        )
        self._ensure_table(
            connection,
            "CREATE INDEX IF NOT EXISTS idx_scene_image_variants_scene_created ON scene_image_variants(scene_id, created_at DESC)",
        )
        self._ensure_table(
            connection,
            """
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
            )
            """,
        )
        self._ensure_table(
            connection,
            "CREATE INDEX IF NOT EXISTS idx_sequence_video_variants_sequence_created ON sequence_video_variants(sequence_id, created_at DESC)",
        )
        self._ensure_table(
            connection,
            """
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
            )
            """,
        )
        self._ensure_table(
            connection,
            "CREATE INDEX IF NOT EXISTS idx_continuity_reviews_project_scene ON continuity_reviews(project_id, scene_id)",
        )
        self._ensure_table(
            connection,
            """
            CREATE TABLE IF NOT EXISTS project_characters (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                role_summary TEXT NOT NULL DEFAULT '',
                prompt_tags TEXT NOT NULL DEFAULT '',
                order_index INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
        )
        self._ensure_table(
            connection,
            "CREATE INDEX IF NOT EXISTS idx_project_characters_project_order ON project_characters(project_id, order_index)",
        )
        connection.execute(
            """
            UPDATE scenes
            SET wan_prompt_text = prompt_text
            WHERE COALESCE(wan_prompt_text, '') = '' AND COALESCE(prompt_text, '') <> ''
            """
        )
        connection.execute("UPDATE scenes SET include_in_assembly = 1 WHERE include_in_assembly IS NULL")
        connection.execute("UPDATE scenes SET trim_in_ms = 0 WHERE trim_in_ms IS NULL")
        connection.execute("UPDATE scenes SET trim_out_ms = 0 WHERE trim_out_ms IS NULL")
        connection.execute("UPDATE scenes SET absolute_order = order_index WHERE absolute_order IS NULL")
        if self._has_column(connection, "story_scenes", "duration_locked"):
            connection.execute("UPDATE story_scenes SET duration_locked = 0 WHERE duration_locked IS NULL")
        if self._has_column(connection, "story_scenes", "first_image_source"):
            connection.execute(
                """
                UPDATE story_scenes
                SET first_image_source = CASE
                    WHEN first_image_relative_path IS NOT NULL AND first_image_relative_path != '' THEN 'uploaded'
                    ELSE NULL
                END
                WHERE first_image_source IS NULL OR first_image_source = ''
                """
            )
        if self._has_column(connection, "story_scenes", "image_generation_status"):
            connection.execute(
                """
                UPDATE story_scenes
                SET image_generation_status = CASE
                    WHEN first_image_relative_path IS NOT NULL AND first_image_relative_path != '' THEN 'ready'
                    ELSE 'idle'
                END
                WHERE image_generation_status IS NULL OR image_generation_status = ''
                """
            )
        if self._has_column(connection, "scenes", "duration_locked"):
            connection.execute("UPDATE scenes SET duration_locked = 0 WHERE duration_locked IS NULL")
        if self._has_column(connection, "scenes", "approved_video_relative_path"):
            connection.execute(
                """
                UPDATE scenes
                SET approved_video_relative_path = uploaded_sequence_relative_path
                WHERE (approved_video_relative_path IS NULL OR approved_video_relative_path = '')
                  AND uploaded_sequence_relative_path IS NOT NULL
                  AND uploaded_sequence_relative_path != ''
                """
            )
            connection.execute(
                """
                UPDATE scenes
                SET approved_video_original_filename = COALESCE(uploaded_sequence_original_filename, approved_video_original_filename),
                    approved_video_mime_type = COALESCE(uploaded_sequence_mime_type, approved_video_mime_type),
                    approved_video_size_bytes = CASE
                        WHEN approved_video_size_bytes IS NULL OR approved_video_size_bytes = 0 THEN uploaded_sequence_size_bytes
                        ELSE approved_video_size_bytes
                    END,
                    approved_video_created_at = COALESCE(uploaded_sequence_uploaded_at, approved_video_created_at),
                    approved_video_source = COALESCE(NULLIF(approved_video_source, ''), CASE
                        WHEN uploaded_sequence_relative_path IS NOT NULL AND uploaded_sequence_relative_path != '' THEN 'uploaded'
                        ELSE NULL
                    END)
                """
            )
        if self._has_column(connection, "projects", "beat_board_status"):
            connection.execute("UPDATE projects SET beat_board_status = 'empty' WHERE beat_board_status IS NULL")
        connection.execute("UPDATE projects SET workflow_version = 1 WHERE workflow_version IS NULL")

        self._ensure_columns(
            connection,
            "project_characters",
            {
                "portrait_image_url": "TEXT",
                "cowboyshot_image_url": "TEXT",
                "fullbody_image_url": "TEXT",
            },
        )

    def _ensure_columns(
        self,
        connection: sqlite3.Connection,
        table_name: str,
        columns: dict[str, str],
    ) -> None:
        existing = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        for column_name, column_type in columns.items():
            if column_name not in existing:
                connection.execute(
                    f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                )

    def _ensure_table(self, connection: sqlite3.Connection, statement: str) -> None:
        connection.execute(statement)

    def _has_column(self, connection: sqlite3.Connection, table_name: str, column_name: str) -> bool:
        return any(
            row["name"] == column_name
            for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        )
