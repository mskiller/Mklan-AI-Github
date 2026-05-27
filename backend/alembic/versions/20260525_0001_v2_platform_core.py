"""create V2 platform core tables

Revision ID: 20260525_0001
Revises:
Create Date: 2026-05-25
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260525_0001"
down_revision = None
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _has_index(table: str, name: str) -> bool:
    return any(index.get("name") == name for index in sa.inspect(op.get_bind()).get_indexes(table))


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    if not _has_table("platform_jobs"):
        op.create_table(
            "platform_jobs",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("job_type", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False),
            sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
            sa.Column("payload_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("result_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("error_text", sa.Text()),
            sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.Column("started_at", sa.Text()),
            sa.Column("finished_at", sa.Text()),
        )
    if not _has_index("platform_jobs", "idx_platform_jobs_status_created"):
        op.create_index("idx_platform_jobs_status_created", "platform_jobs", ["status", "created_at"])

    if not _has_table("platform_job_events"):
        op.create_table(
            "platform_job_events",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("job_id", sa.Text(), sa.ForeignKey("platform_jobs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("event_type", sa.Text(), nullable=False),
            sa.Column("message", sa.Text(), nullable=False, server_default=""),
            sa.Column("progress", sa.Float()),
            sa.Column("payload_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("created_at", sa.Text(), nullable=False),
        )
    if not _has_index("platform_job_events", "idx_platform_job_events_job_id"):
        op.create_index("idx_platform_job_events_job_id", "platform_job_events", ["job_id", "id"])

    if not _has_table("platform_assets"):
        op.create_table(
            "platform_assets",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("path", sa.Text(), nullable=False, unique=True),
            sa.Column("url", sa.Text(), nullable=False),
            sa.Column("kind", sa.Text(), nullable=False),
            sa.Column("source_module", sa.Text(), nullable=False),
            sa.Column("source_id", sa.Text()),
            sa.Column("metadata_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("provenance_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("media_indexer_status", sa.Text(), nullable=False, server_default="registered"),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
        )
    if not _has_index("platform_assets", "idx_platform_assets_source"):
        op.create_index("idx_platform_assets_source", "platform_assets", ["source_module", "source_id"])
    if not _has_index("platform_assets", "idx_platform_assets_kind_created"):
        op.create_index("idx_platform_assets_kind_created", "platform_assets", ["kind", "created_at"])

    if not _has_table("platform_audit_events"):
        op.create_table(
            "platform_audit_events",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("timestamp", sa.Text(), nullable=False),
            sa.Column("actor", sa.Text(), nullable=False),
            sa.Column("action", sa.Text(), nullable=False),
            sa.Column("target", sa.Text(), nullable=False, server_default=""),
            sa.Column("payload_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        )
    if not _has_index("platform_audit_events", "idx_platform_audit_action"):
        op.create_index("idx_platform_audit_action", "platform_audit_events", ["action"])


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_platform_audit_action")
    op.execute("DROP TABLE IF EXISTS platform_audit_events")
    op.execute("DROP INDEX IF EXISTS idx_platform_assets_kind_created")
    op.execute("DROP INDEX IF EXISTS idx_platform_assets_source")
    op.execute("DROP TABLE IF EXISTS platform_assets")
    op.execute("DROP INDEX IF EXISTS idx_platform_job_events_job_id")
    op.execute("DROP TABLE IF EXISTS platform_job_events")
    op.execute("DROP INDEX IF EXISTS idx_platform_jobs_status_created")
    op.execute("DROP TABLE IF EXISTS platform_jobs")
