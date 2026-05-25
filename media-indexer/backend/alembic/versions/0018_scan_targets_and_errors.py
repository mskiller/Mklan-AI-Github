"""scan targets and per-file errors

Revision ID: 0018_scan_targets_and_errors
Revises: 0017_pgvector_runtime_indexes
Create Date: 2026-05-22 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0018_scan_targets_and_errors"
down_revision = "0017_pgvector_runtime_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("scan_jobs", "source_id", existing_type=postgresql.UUID(), nullable=True)
    op.drop_constraint("scan_jobs_source_id_fkey", "scan_jobs", type_="foreignkey")
    op.create_foreign_key("scan_jobs_source_id_fkey", "scan_jobs", "sources", ["source_id"], ["id"], ondelete="SET NULL")

    op.add_column("scan_jobs", sa.Column("target_type", sa.String(length=32), nullable=False, server_default="source"))
    op.add_column("scan_jobs", sa.Column("collection_id", postgresql.UUID(), nullable=True))
    op.add_column("scan_jobs", sa.Column("asset_ids_json", postgresql.JSONB(), nullable=True))
    op.add_column("scan_jobs", sa.Column("options_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("scan_jobs", sa.Column("total_count", sa.Integer(), nullable=True))
    op.add_column("scan_jobs", sa.Column("stage", sa.String(length=64), nullable=True))
    op.add_column("scan_jobs", sa.Column("worker_heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key("scan_jobs_collection_id_fkey", "scan_jobs", "collections", ["collection_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_scan_jobs_target_type", "scan_jobs", ["target_type"])
    op.create_index("ix_scan_jobs_collection_id", "scan_jobs", ["collection_id"])

    op.create_table(
        "scan_job_errors",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("job_id", postgresql.UUID(), nullable=False),
        sa.Column("source_id", postgresql.UUID(), nullable=True),
        sa.Column("asset_id", postgresql.UUID(), nullable=True),
        sa.Column("relative_path", sa.Text(), nullable=True),
        sa.Column("stage", sa.String(length=64), nullable=True),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_id"], ["scan_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scan_job_errors_job_id", "scan_job_errors", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_scan_job_errors_job_id", table_name="scan_job_errors")
    op.drop_table("scan_job_errors")

    op.drop_index("ix_scan_jobs_collection_id", table_name="scan_jobs")
    op.drop_index("ix_scan_jobs_target_type", table_name="scan_jobs")
    op.drop_constraint("scan_jobs_collection_id_fkey", "scan_jobs", type_="foreignkey")
    op.drop_column("scan_jobs", "worker_heartbeat_at")
    op.drop_column("scan_jobs", "stage")
    op.drop_column("scan_jobs", "total_count")
    op.drop_column("scan_jobs", "options_json")
    op.drop_column("scan_jobs", "asset_ids_json")
    op.drop_column("scan_jobs", "collection_id")
    op.drop_column("scan_jobs", "target_type")

    op.drop_constraint("scan_jobs_source_id_fkey", "scan_jobs", type_="foreignkey")
    op.create_foreign_key("scan_jobs_source_id_fkey", "scan_jobs", "sources", ["source_id"], ["id"], ondelete="CASCADE")
    op.alter_column("scan_jobs", "source_id", existing_type=postgresql.UUID(), nullable=False)
