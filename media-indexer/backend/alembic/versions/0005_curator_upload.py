"""add curator role for uploads and collection management

Revision ID: 0005_curator_upload
Revises: 0004_v4_collections
Create Date: 2026-04-11 15:20:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "0005_curator_upload"
down_revision = "0004_v4_collections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'curator'")


def downgrade() -> None:
    # PostgreSQL enum values are not removed safely in place.
    pass
