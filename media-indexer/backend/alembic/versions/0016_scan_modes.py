"""scan modes and scoped scan jobs

Revision ID: 0016_scan_modes
Revises: 0015_platform_modules
Create Date: 2026-05-18 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0016_scan_modes"
down_revision = "0015_platform_modules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scan_jobs", sa.Column("scan_mode", sa.String(length=32), nullable=False, server_default="basic"))
    op.add_column("scan_jobs", sa.Column("path_filter", sa.Text(), nullable=True))
    op.create_index("ix_scan_jobs_scan_mode", "scan_jobs", ["scan_mode"])


def downgrade() -> None:
    op.drop_index("ix_scan_jobs_scan_mode", table_name="scan_jobs")
    op.drop_column("scan_jobs", "path_filter")
    op.drop_column("scan_jobs", "scan_mode")
