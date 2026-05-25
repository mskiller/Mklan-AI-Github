"""pgvector runtime indexes for generated asset search

Revision ID: 0017_pgvector_runtime_indexes
Revises: 0016_scan_modes
Create Date: 2026-05-22 00:00:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "0017_pgvector_runtime_indexes"
down_revision = "0016_scan_modes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_asset_similarity_embedding_hnsw "
        "ON asset_similarity USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_asset_similarity_phash_present "
        "ON asset_similarity (phash) WHERE phash IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_assets_source_modified_desc "
        "ON assets (source_id, modified_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_asset_metadata_normalized_gin "
        "ON asset_metadata USING GIN (normalized_json jsonb_path_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_asset_metadata_normalized_gin")
    op.execute("DROP INDEX IF EXISTS ix_assets_source_modified_desc")
    op.execute("DROP INDEX IF EXISTS ix_asset_similarity_phash_present")
    op.execute("DROP INDEX IF EXISTS ix_asset_similarity_embedding_hnsw")
