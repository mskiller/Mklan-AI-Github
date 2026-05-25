from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
import sqlite3


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    seed_sentence TEXT NOT NULL DEFAULT '',
    scenario_text TEXT NOT NULL DEFAULT '',
    project_mode TEXT NOT NULL DEFAULT 'character',
    sample_character_target_count INTEGER NOT NULL DEFAULT 5,
    lorebook_scan_depth INTEGER NOT NULL DEFAULT 4,
    lorebook_token_budget INTEGER NOT NULL DEFAULT 512,
    lorebook_recursive_scanning INTEGER NOT NULL DEFAULT 0,
    scenario_image_relative_path TEXT,
    genre TEXT NOT NULL DEFAULT 'roleplay',
    tone TEXT NOT NULL DEFAULT 'immersive',
    gm_card_profile_json TEXT NOT NULL DEFAULT '{}',
    model_settings_override_json TEXT NOT NULL DEFAULT '{}',
    archived_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS characters (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    personality TEXT NOT NULL DEFAULT '',
    scenario TEXT NOT NULL DEFAULT '',
    first_message TEXT NOT NULL DEFAULT '',
    example_dialogue TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]',
    creator_notes TEXT NOT NULL DEFAULT '',
    system_prompt TEXT NOT NULL DEFAULT '',
    post_history_instructions TEXT NOT NULL DEFAULT '',
    alternate_greetings_json TEXT NOT NULL DEFAULT '[]',
    creator TEXT NOT NULL DEFAULT '',
    character_version TEXT NOT NULL DEFAULT '',
    character_note TEXT NOT NULL DEFAULT '',
    character_note_depth INTEGER NOT NULL DEFAULT 4,
    character_note_role TEXT NOT NULL DEFAULT 'system',
    talkativeness REAL,
    appearance_summary TEXT NOT NULL DEFAULT '',
    booru_character_name TEXT NOT NULL DEFAULT '',
    booru_copyright TEXT NOT NULL DEFAULT '',
    avatar_relative_path TEXT,
    portrait_relative_path TEXT,
    cowboy_shot_relative_path TEXT,
    fullbody_shot_relative_path TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_characters_project ON characters(project_id, created_at);

CREATE TABLE IF NOT EXISTS lore_entries (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    keys_json TEXT NOT NULL DEFAULT '[]',
    secondary_keys_json TEXT NOT NULL DEFAULT '[]',
    content TEXT NOT NULL DEFAULT '',
    comment TEXT NOT NULL DEFAULT '',
    image_relative_path TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    insertion_order INTEGER NOT NULL DEFAULT 100,
    position TEXT NOT NULL DEFAULT 'after_char',
    constant INTEGER NOT NULL DEFAULT 0,
    selective_logic INTEGER NOT NULL DEFAULT 0,
    probability INTEGER NOT NULL DEFAULT 100,
    case_sensitive INTEGER NOT NULL DEFAULT 0,
    priority INTEGER NOT NULL DEFAULT 0,
    scan_depth INTEGER,
    match_whole_words INTEGER,
    group_name TEXT NOT NULL DEFAULT '',
    group_weight INTEGER NOT NULL DEFAULT 100,
    prevent_recursion INTEGER NOT NULL DEFAULT 1,
    delay_until_recursion INTEGER NOT NULL DEFAULT 0,
    character_filter_json TEXT NOT NULL DEFAULT '',
    automation_id TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'system',
    extensions_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_lore_project ON lore_entries(project_id, insertion_order, created_at);

CREATE TABLE IF NOT EXISTS user_profiles (
    project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL DEFAULT 'User',
    description TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    personality TEXT NOT NULL DEFAULT '',
    scenario_role TEXT NOT NULL DEFAULT '',
    first_message TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]',
    persona_note TEXT NOT NULL DEFAULT '',
    persona_note_depth INTEGER NOT NULL DEFAULT 4,
    persona_note_role TEXT NOT NULL DEFAULT 'system',
    appearance_summary TEXT NOT NULL DEFAULT '',
    booru_character_name TEXT NOT NULL DEFAULT '',
    booru_copyright TEXT NOT NULL DEFAULT '',
    avatar_relative_path TEXT,
    portrait_relative_path TEXT,
    cowboy_shot_relative_path TEXT,
    fullbody_shot_relative_path TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS generation_runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    task_type TEXT NOT NULL,
    status TEXT NOT NULL,
    progress REAL NOT NULL DEFAULT 0,
    error_text TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_generation_runs_project ON generation_runs(project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value_text TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS image_candidates (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    owner_type TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    image_slot TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    prompt_text TEXT NOT NULL DEFAULT '',
    negative_prompt TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_image_candidates_owner
ON image_candidates(project_id, owner_type, owner_id, image_slot, created_at DESC);

CREATE TABLE IF NOT EXISTS shared_character_vault (
    id TEXT PRIMARY KEY,
    source_module TEXT NOT NULL,
    source_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    personality TEXT NOT NULL DEFAULT '',
    role_summary TEXT NOT NULL DEFAULT '',
    prompt_tags_json TEXT NOT NULL DEFAULT '[]',
    avatar_path TEXT,
    source_metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_shared_character_vault_source
ON shared_character_vault(source_module, source_id);

CREATE TABLE IF NOT EXISTS shared_lore_vault (
    id TEXT PRIMARY KEY,
    source_module TEXT NOT NULL,
    source_id TEXT NOT NULL,
    name TEXT NOT NULL,
    keys_json TEXT NOT NULL DEFAULT '[]',
    content TEXT NOT NULL DEFAULT '',
    source_metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_shared_lore_vault_source
ON shared_lore_vault(source_module, source_id);

CREATE TABLE IF NOT EXISTS compatibility_reports (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    critical_count INTEGER NOT NULL DEFAULT 0,
    warning_count INTEGER NOT NULL DEFAULT 0,
    report_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_compatibility_reports_project
ON compatibility_reports(project_id, created_at DESC);
"""


MIGRATION_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "projects": [
        ("project_mode", "TEXT NOT NULL DEFAULT 'character'"),
        ("sample_character_target_count", "INTEGER NOT NULL DEFAULT 5"),
        ("lorebook_scan_depth", "INTEGER NOT NULL DEFAULT 4"),
        ("lorebook_token_budget", "INTEGER NOT NULL DEFAULT 512"),
        ("lorebook_recursive_scanning", "INTEGER NOT NULL DEFAULT 0"),
        ("scenario_image_relative_path", "TEXT"),
        ("gm_card_profile_json", "TEXT NOT NULL DEFAULT '{}'"),
    ],
    "characters": [
        ("creator", "TEXT NOT NULL DEFAULT ''"),
        ("character_version", "TEXT NOT NULL DEFAULT ''"),
        ("character_note", "TEXT NOT NULL DEFAULT ''"),
        ("character_note_depth", "INTEGER NOT NULL DEFAULT 4"),
        ("character_note_role", "TEXT NOT NULL DEFAULT 'system'"),
        ("talkativeness", "REAL"),
        ("appearance_summary", "TEXT NOT NULL DEFAULT ''"),
        ("booru_character_name", "TEXT NOT NULL DEFAULT ''"),
        ("booru_copyright", "TEXT NOT NULL DEFAULT ''"),
        ("portrait_relative_path", "TEXT"),
        ("cowboy_shot_relative_path", "TEXT"),
        ("fullbody_shot_relative_path", "TEXT"),
    ],
    "lore_entries": [
        ("image_relative_path", "TEXT"),
        ("constant", "INTEGER NOT NULL DEFAULT 0"),
        ("selective_logic", "INTEGER NOT NULL DEFAULT 0"),
        ("probability", "INTEGER NOT NULL DEFAULT 100"),
        ("case_sensitive", "INTEGER NOT NULL DEFAULT 0"),
        ("priority", "INTEGER NOT NULL DEFAULT 0"),
        ("scan_depth", "INTEGER"),
        ("match_whole_words", "INTEGER"),
        ("group_name", "TEXT NOT NULL DEFAULT ''"),
        ("group_weight", "INTEGER NOT NULL DEFAULT 100"),
        ("prevent_recursion", "INTEGER NOT NULL DEFAULT 1"),
        ("delay_until_recursion", "INTEGER NOT NULL DEFAULT 0"),
        ("character_filter_json", "TEXT NOT NULL DEFAULT ''"),
        ("automation_id", "TEXT NOT NULL DEFAULT ''"),
        ("role", "TEXT NOT NULL DEFAULT 'system'"),
        ("extensions_json", "TEXT NOT NULL DEFAULT '{}'"),
    ],
    "user_profiles": [
        ("title", "TEXT NOT NULL DEFAULT ''"),
        ("persona_note", "TEXT NOT NULL DEFAULT ''"),
        ("persona_note_depth", "INTEGER NOT NULL DEFAULT 4"),
        ("persona_note_role", "TEXT NOT NULL DEFAULT 'system'"),
        ("appearance_summary", "TEXT NOT NULL DEFAULT ''"),
        ("booru_character_name", "TEXT NOT NULL DEFAULT ''"),
        ("booru_copyright", "TEXT NOT NULL DEFAULT ''"),
        ("avatar_relative_path", "TEXT"),
        ("portrait_relative_path", "TEXT"),
        ("cowboy_shot_relative_path", "TEXT"),
        ("fullbody_shot_relative_path", "TEXT"),
    ],
}


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            self._apply_schema_migrations(connection)

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

    def _apply_schema_migrations(self, connection: sqlite3.Connection) -> None:
        for table_name, columns in MIGRATION_COLUMNS.items():
            existing_columns = {
                str(row["name"])
                for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
            }
            for column_name, column_type in columns:
                if column_name in existing_columns:
                    continue
                connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
