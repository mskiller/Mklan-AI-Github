from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:  # SQLModel is a Docker/runtime dependency for the V2 core DB.
    from sqlalchemy import JSON, Column
    from sqlmodel import Field, SQLModel

    SQLMODEL_AVAILABLE = True
except Exception:  # pragma: no cover - local fallback when deps are not installed yet.
    JSON = None  # type: ignore[assignment]
    Column = None  # type: ignore[assignment]
    Field = None  # type: ignore[assignment]
    SQLModel = object  # type: ignore[misc,assignment]
    SQLMODEL_AVAILABLE = False

try:
    import psycopg
    from psycopg.rows import dict_row

    PSYCOPG_AVAILABLE = True
except Exception:  # pragma: no cover - exercised when only SQLite fallback deps exist.
    psycopg = None  # type: ignore[assignment]
    dict_row = None  # type: ignore[assignment]
    PSYCOPG_AVAILABLE = False


def studio_database_url() -> str:
    return os.getenv("STUDIO_DATABASE_URL", "").strip()


def normalize_database_url(url: str) -> str:
    normalized = url.strip()
    if normalized.startswith("postgresql+psycopg://"):
        return "postgresql://" + normalized.split("postgresql+psycopg://", 1)[1]
    return normalized


def core_db_enabled() -> bool:
    return bool(studio_database_url())


def connect_core_db(*, dict_rows: bool = True):
    if not PSYCOPG_AVAILABLE:
        raise RuntimeError("psycopg is required when STUDIO_DATABASE_URL is configured.")
    row_factory = dict_row if dict_rows else None
    return psycopg.connect(normalize_database_url(studio_database_url()), row_factory=row_factory)


def _column_exists(cursor: Any, table: str, column: str) -> bool:
    cursor.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = %s AND column_name = %s
         LIMIT 1
        """,
        (table, column),
    )
    return cursor.fetchone() is not None


def initialize_core_db() -> None:
    if not core_db_enabled():
        return
    with connect_core_db(dict_rows=False) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
            except Exception:
                conn.rollback()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS platform_jobs (
                    id TEXT PRIMARY KEY,
                    job_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress DOUBLE PRECISION NOT NULL DEFAULT 0,
                    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                    result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                    error_text TEXT,
                    cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    workspace_id TEXT NOT NULL DEFAULT 'default'
                )
                """
            )
            if not _column_exists(cursor, "platform_jobs", "workspace_id"):
                cursor.execute("ALTER TABLE platform_jobs ADD COLUMN workspace_id TEXT NOT NULL DEFAULT 'default'")
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_platform_jobs_status_created ON platform_jobs(status, created_at)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_platform_jobs_workspace_created ON platform_jobs(workspace_id, created_at DESC)"
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS platform_job_events (
                    id BIGSERIAL PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES platform_jobs(id) ON DELETE CASCADE,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL DEFAULT '',
                    progress DOUBLE PRECISION,
                    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_platform_job_events_job_id ON platform_job_events(job_id, id)"
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS platform_assets (
                    id TEXT PRIMARY KEY,
                    path TEXT NOT NULL UNIQUE,
                    url TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    source_module TEXT NOT NULL,
                    source_id TEXT,
                    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                    provenance_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                    media_indexer_status TEXT NOT NULL DEFAULT 'registered',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    workspace_id TEXT NOT NULL DEFAULT 'default'
                )
                """
            )
            if not _column_exists(cursor, "platform_assets", "workspace_id"):
                cursor.execute("ALTER TABLE platform_assets ADD COLUMN workspace_id TEXT NOT NULL DEFAULT 'default'")
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_platform_assets_source ON platform_assets(source_module, source_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_platform_assets_kind_created ON platform_assets(kind, created_at DESC)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_platform_assets_workspace_created ON platform_assets(workspace_id, created_at DESC)"
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS platform_audit_events (
                    id BIGSERIAL PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target TEXT NOT NULL DEFAULT '',
                    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                    workspace_id TEXT NOT NULL DEFAULT 'default'
                )
                """
            )
            if not _column_exists(cursor, "platform_audit_events", "workspace_id"):
                cursor.execute("ALTER TABLE platform_audit_events ADD COLUMN workspace_id TEXT NOT NULL DEFAULT 'default'")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_platform_audit_action ON platform_audit_events(action)")
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_platform_audit_workspace_action ON platform_audit_events(workspace_id, action)"
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS platform_workspaces (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    active BOOLEAN NOT NULL DEFAULT FALSE,
                    settings_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_platform_workspaces_active ON platform_workspaces(active)")
            now = datetime_utc_now()
            cursor.execute(
                """
                INSERT INTO platform_workspaces (id, name, description, active, settings_json, created_at, updated_at)
                VALUES ('default', 'Default Workspace', 'Shared local Studio workspace.', TRUE, '{}'::jsonb, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (now, now),
            )
            cursor.execute("SELECT COUNT(*) FROM platform_workspaces WHERE active = TRUE")
            if int(cursor.fetchone()[0]) == 0:
                cursor.execute(
                    "UPDATE platform_workspaces SET active = TRUE, updated_at = %s WHERE id = 'default'",
                    (now,),
                )
        conn.commit()


if SQLMODEL_AVAILABLE:

    class PlatformJob(SQLModel, table=True):
        __tablename__ = "platform_jobs"

        id: str = Field(primary_key=True)
        job_type: str
        status: str
        progress: float = 0
        payload_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
        result_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
        error_text: str | None = None
        cancel_requested: bool = False
        created_at: str
        updated_at: str
        started_at: str | None = None
        finished_at: str | None = None
        workspace_id: str = "default"


    class PlatformJobEvent(SQLModel, table=True):
        __tablename__ = "platform_job_events"

        id: int | None = Field(default=None, primary_key=True)
        job_id: str = Field(foreign_key="platform_jobs.id")
        event_type: str
        message: str = ""
        progress: float | None = None
        payload_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
        created_at: str


    class PlatformAsset(SQLModel, table=True):
        __tablename__ = "platform_assets"

        id: str = Field(primary_key=True)
        path: str = Field(index=True)
        url: str
        kind: str
        source_module: str
        source_id: str | None = None
        metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
        provenance_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
        media_indexer_status: str = "registered"
        created_at: str
        updated_at: str
        workspace_id: str = "default"


    class PlatformAuditEvent(SQLModel, table=True):
        __tablename__ = "platform_audit_events"

        id: int | None = Field(default=None, primary_key=True)
        timestamp: str
        actor: str = "local"
        action: str
        target: str = ""
        payload_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
        workspace_id: str = "default"


    class PlatformWorkspace(SQLModel, table=True):
        __tablename__ = "platform_workspaces"

        id: str = Field(primary_key=True)
        name: str
        description: str = ""
        active: bool = False
        settings_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
        created_at: str
        updated_at: str

    from .models_wildcards import (
        WildcardSourceFile,
        WildcardEntry,
        WildcardEntryHistory,
        WildcardScanRun,
        WildcardTagIndex,
        WildcardCategoryIndex,
        WildcardCategoryStat,
        WildcardPromptModeIndex,
        WildcardPromptRecipe,
        WildcardTagOverride,
        WildcardTaxonomyRule,
        WildcardTaxonomyMeta,
        WildcardSourceFileStat,
        WildcardLlmJob,
        WildcardTagPolarityIndex,
    )
    
    from .models_cards import (
        CardProject,
        CardCharacter,
        CardLoreEntry,
        CardUserProfile,
        CardGenerationRun,
        CardAppSetting,
        CardImageCandidate,
        CardSharedCharacterVault,
        CardSharedLoreVault,
        CardCompatibilityReport,
    )
    
    from .models_movie import (
        MovieProject,
        MovieStoryScene,
        MovieStoryBeat,
        MovieScene,
        MovieSceneImageVariant,
        MovieSequenceVideoVariant,
        MovieClipAsset,
        MovieJob,
        MovieContinuityReview,
        MovieExportAsset,
        MovieProjectCharacter,
        MovieAppSetting,
    )


def default_data_root() -> Path:
    raw = os.environ.get("STUDIO_DATA_ROOT") or os.environ.get("MOVIE_TOOL_DATA_ROOT")
    if raw:
        return Path(raw)
    if os.environ.get("ENVIRONMENT") == "production" or Path("/.dockerenv").exists():
        return Path("/app/data")
    return Path(__file__).resolve().parents[3] / "data"


def datetime_utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
