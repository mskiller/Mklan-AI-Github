"""platform modules foundation

Revision ID: 0015_platform_modules
Revises: 0014_increase_tag_length
Create Date: 2026-04-18 04:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0015_platform_modules"
down_revision = "0014_increase_tag_length"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_modules",
        sa.Column("module_id", sa.String(length=128), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="builtin"),
        sa.Column("version", sa.String(length=64), nullable=False, server_default="0.0.0"),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("settings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.add_column("smart_albums", sa.Column("status", sa.String(length=32), nullable=False, server_default="active"))
    op.add_column("smart_albums", sa.Column("degraded_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("smart_albums", "degraded_reason")
    op.drop_column("smart_albums", "status")
    op.drop_table("platform_modules")
