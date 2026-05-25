"""add cancelled scan status

Revision ID: 0002_scan_cancelled
Revises: 0001_initial
Create Date: 2026-04-11 00:20:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "0002_scan_cancelled"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE scan_status ADD VALUE IF NOT EXISTS 'cancelled'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values safely in place.
    pass
