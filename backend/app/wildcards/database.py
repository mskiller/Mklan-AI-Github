"""Wildcard database connections and initialisation."""
from __future__ import annotations

import sqlite3

from .config import WILDCARD_DATA_DIR, WILDCARD_DB
from .schemas.wildcards import utc_now
from .services.wildcard_parser import CATEGORY_RULES


def connect() -> sqlite3.Connection:
    """Connect to the Wildcards SQLite database."""
    WILDCARD_DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(WILDCARD_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _seed_taxonomy_defaults(conn: sqlite3.Connection) -> None:
    """Seed taxonomy rules from CATEGORY_RULES if not already present."""
    existing = conn.execute("SELECT COUNT(*) AS count FROM taxonomy_rules").fetchone()["count"]
    if existing:
        return
    now = utc_now()
    conn.executemany(
        "INSERT OR IGNORE INTO taxonomy_rules(category, keyword, enabled, updated_at) VALUES (?, ?, 1, ?)",
        [(category, keyword, now) for category, keywords in CATEGORY_RULES.items() for keyword in keywords],
    )
    conn.execute(
        "INSERT OR REPLACE INTO taxonomy_meta(key, value, updated_at) VALUES ('version', ?, ?)",
        (now, now),
    )


def init_db() -> None:
    """Initialise the Wildcards database schema."""
    conn = connect()
    try:
        conn.executescript(
            """
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
            """
        )
        # Migration: add columns if missing (for existing DBs)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(entries)").fetchall()}
        if "tag_categories_json" not in columns:
            conn.execute("ALTER TABLE entries ADD COLUMN tag_categories_json TEXT NOT NULL DEFAULT '[]'")
        if "prompt_mode" not in columns:
            conn.execute("ALTER TABLE entries ADD COLUMN prompt_mode TEXT NOT NULL DEFAULT 'unknown'")
        if "positive_tags_json" not in columns:
            conn.execute("ALTER TABLE entries ADD COLUMN positive_tags_json TEXT NOT NULL DEFAULT '[]'")
        if "negative_tags_json" not in columns:
            conn.execute("ALTER TABLE entries ADD COLUMN negative_tags_json TEXT NOT NULL DEFAULT '[]'")
        if "all_extracted_tags_json" not in columns:
            conn.execute("ALTER TABLE entries ADD COLUMN all_extracted_tags_json TEXT NOT NULL DEFAULT '[]'")
        if "prompt_parts_json" not in columns:
            conn.execute("ALTER TABLE entries ADD COLUMN prompt_parts_json TEXT NOT NULL DEFAULT '{}'")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entries_prompt_mode ON entries(prompt_mode)")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tag_polarity_index (
                tag TEXT NOT NULL,
                category TEXT NOT NULL,
                polarity TEXT NOT NULL,
                usage_count INTEGER NOT NULL,
                PRIMARY KEY (tag, category, polarity)
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS entry_fts USING fts5(effective_text, wildcard_path, tags);
            """
        )
        _seed_taxonomy_defaults(conn)
        conn.commit()
    finally:
        conn.close()
