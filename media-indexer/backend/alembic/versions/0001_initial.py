"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-10 21:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


source_type_enum = postgresql.ENUM("mounted_fs", "smb", "nfs", "agent", name="source_type", create_type=False)
source_status_enum = postgresql.ENUM("ready", "scanning", "error", "disabled", name="source_status", create_type=False)
scan_status_enum = postgresql.ENUM("queued", "running", "completed", "failed", "cancelled", name="scan_status", create_type=False)
media_type_enum = postgresql.ENUM("image", "video", "unknown", name="media_type", create_type=False)
match_type_enum = postgresql.ENUM("duplicate", "semantic", name="match_type", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    source_type_enum.create(bind, checkfirst=True)
    source_status_enum.create(bind, checkfirst=True)
    scan_status_enum.create(bind, checkfirst=True)
    media_type_enum.create(bind, checkfirst=True)
    match_type_enum.create(bind, checkfirst=True)

    op.create_table(
        "sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("type", source_type_enum, nullable=False),
        sa.Column("root_path", sa.Text(), nullable=False),
        sa.Column("status", source_status_enum, nullable=False, server_default="ready"),
        sa.Column("last_scan_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("root_path"),
    )

    op.create_table(
        "scan_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("status", scan_status_enum, nullable=False, server_default="queued"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("scanned_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deleted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("extension", sa.String(length=32), nullable=False),
        sa.Column("media_type", media_type_enum, nullable=False, server_default="unknown"),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("modified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("preview_path", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "relative_path", name="uq_assets_source_path"),
    )

    op.create_table(
        "asset_metadata",
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("normalized_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("asset_id"),
    )

    op.create_table(
        "asset_tags",
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("tag", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("asset_id", "tag"),
    )

    op.create_table(
        "asset_search",
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("document", postgresql.TSVECTOR(), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("asset_id"),
    )

    op.create_table(
        "asset_similarity",
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("phash", sa.String(length=64), nullable=True),
        sa.Column("embedding", Vector(dim=512), nullable=True),
        sa.Column("embedding_model", sa.String(length=255), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("asset_id"),
    )

    op.create_table(
        "similarity_links",
        sa.Column("asset_id_a", sa.Uuid(), nullable=False),
        sa.Column("asset_id_b", sa.Uuid(), nullable=False),
        sa.Column("match_type", match_type_enum, nullable=False),
        sa.Column("distance", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["asset_id_a"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id_b"], ["assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("asset_id_a", "asset_id_b", "match_type"),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=255), nullable=False),
        sa.Column("resource_type", sa.String(length=255), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_assets_source_id", "assets", ["source_id"])
    op.create_index("ix_assets_media_type", "assets", ["media_type"])
    op.create_index("ix_assets_modified_at", "assets", ["modified_at"])
    op.create_index("ix_scan_jobs_source_id", "scan_jobs", ["source_id"])
    op.create_index("ix_scan_jobs_status", "scan_jobs", ["status"])
    op.create_index("ix_asset_tags_tag", "asset_tags", ["tag"])
    op.create_index("ix_similarity_links_match_type", "similarity_links", ["match_type"])
    op.execute("CREATE INDEX ix_asset_search_document ON asset_search USING GIN (document)")
    op.execute(
        "CREATE INDEX ix_asset_similarity_embedding ON asset_similarity "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    op.drop_index("ix_asset_similarity_embedding", table_name="asset_similarity")
    op.drop_index("ix_asset_search_document", table_name="asset_search")
    op.drop_index("ix_similarity_links_match_type", table_name="similarity_links")
    op.drop_index("ix_asset_tags_tag", table_name="asset_tags")
    op.drop_index("ix_scan_jobs_status", table_name="scan_jobs")
    op.drop_index("ix_scan_jobs_source_id", table_name="scan_jobs")
    op.drop_index("ix_assets_modified_at", table_name="assets")
    op.drop_index("ix_assets_media_type", table_name="assets")
    op.drop_index("ix_assets_source_id", table_name="assets")

    op.drop_table("audit_logs")
    op.drop_table("similarity_links")
    op.drop_table("asset_similarity")
    op.drop_table("asset_search")
    op.drop_table("asset_tags")
    op.drop_table("asset_metadata")
    op.drop_table("assets")
    op.drop_table("scan_jobs")
    op.drop_table("sources")

    bind = op.get_bind()
    match_type_enum.drop(bind, checkfirst=True)
    media_type_enum.drop(bind, checkfirst=True)
    scan_status_enum.drop(bind, checkfirst=True)
    source_status_enum.drop(bind, checkfirst=True)
    source_type_enum.drop(bind, checkfirst=True)
