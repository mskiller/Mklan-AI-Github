"""add collections settings and tag similarity

Revision ID: 0004_v4_collections
Revises: 0003_users_and_roles
Create Date: 2026-04-11 23:45:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0004_v4_collections"
down_revision = "0003_users_and_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE match_type ADD VALUE IF NOT EXISTS 'tag'")

    op.create_table(
        "collections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_collections_updated_at", "collections", ["updated_at"])

    op.create_table(
        "collection_assets",
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("added_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["added_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("collection_id", "asset_id"),
        sa.UniqueConstraint("collection_id", "asset_id", name="uq_collection_assets_collection_asset"),
    )
    op.create_index("ix_collection_assets_asset_id", "collection_assets", ["asset_id"])

    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("value_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )

    op.execute(
        """
        INSERT INTO app_settings (key, value_json, updated_at)
        VALUES ('tag_similarity_threshold_percent', '{"value": 75}'::jsonb, NOW())
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_index("ix_collection_assets_asset_id", table_name="collection_assets")
    op.drop_table("collection_assets")
    op.drop_index("ix_collections_updated_at", table_name="collections")
    op.drop_table("collections")
    # PostgreSQL enum values are not removed safely in place.
