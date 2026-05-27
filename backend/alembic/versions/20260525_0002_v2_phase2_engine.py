"""add V2 Phase 2 workspace core

Revision ID: 20260525_0002
Revises: 20260525_0001
Create Date: 2026-05-25
"""

from __future__ import annotations

from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260525_0002"
down_revision = "20260525_0001"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _has_column(table: str, column: str) -> bool:
    return any(item.get("name") == column for item in sa.inspect(op.get_bind()).get_columns(table))


def _has_index(table: str, name: str) -> bool:
    return any(index.get("name") == name for index in sa.inspect(op.get_bind()).get_indexes(table))


def _add_workspace_column(table: str) -> None:
    if _has_table(table) and not _has_column(table, "workspace_id"):
        op.add_column(table, sa.Column("workspace_id", sa.Text(), nullable=False, server_default="default"))


def upgrade() -> None:
    now = datetime.now(UTC).isoformat()
    _add_workspace_column("platform_jobs")
    _add_workspace_column("platform_assets")
    _add_workspace_column("platform_audit_events")

    if _has_table("platform_jobs") and not _has_index("platform_jobs", "idx_platform_jobs_workspace_created"):
        op.create_index("idx_platform_jobs_workspace_created", "platform_jobs", ["workspace_id", "created_at"])
    if _has_table("platform_assets") and not _has_index("platform_assets", "idx_platform_assets_workspace_created"):
        op.create_index("idx_platform_assets_workspace_created", "platform_assets", ["workspace_id", "created_at"])
    if _has_table("platform_audit_events") and not _has_index("platform_audit_events", "idx_platform_audit_workspace_action"):
        op.create_index("idx_platform_audit_workspace_action", "platform_audit_events", ["workspace_id", "action"])

    if not _has_table("platform_workspaces"):
        op.create_table(
            "platform_workspaces",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("settings_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
        )
    if not _has_index("platform_workspaces", "idx_platform_workspaces_active"):
        op.create_index("idx_platform_workspaces_active", "platform_workspaces", ["active"])

    op.execute(
        sa.text(
            """
            INSERT INTO platform_workspaces (id, name, description, active, settings_json, created_at, updated_at)
            VALUES ('default', 'Default Workspace', 'Shared local Studio workspace.', TRUE, '{}'::jsonb, :created_at, :updated_at)
            ON CONFLICT (id) DO NOTHING
            """
        ).bindparams(created_at=now, updated_at=now)
    )
    op.execute(
        sa.text(
            """
            UPDATE platform_workspaces
               SET active = TRUE,
                   updated_at = :updated_at
             WHERE id = 'default'
               AND NOT EXISTS (SELECT 1 FROM platform_workspaces WHERE active = TRUE)
            """
        ).bindparams(updated_at=now)
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_platform_workspaces_active")
    op.execute("DROP TABLE IF EXISTS platform_workspaces")
    op.execute("DROP INDEX IF EXISTS idx_platform_audit_workspace_action")
    op.execute("DROP INDEX IF EXISTS idx_platform_assets_workspace_created")
    op.execute("DROP INDEX IF EXISTS idx_platform_jobs_workspace_created")
    for table in ("platform_audit_events", "platform_assets", "platform_jobs"):
        if _has_table(table) and _has_column(table, "workspace_id"):
            op.drop_column(table, "workspace_id")
