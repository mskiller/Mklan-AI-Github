"""placeholder for missing asset_embedding revision

Revision ID: 0008_asset_embedding
Revises: 0007_visual_workflow
Create Date: 2026-04-16 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "0008_asset_embedding"
down_revision = "0007_visual_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The original embedding column already exists on asset_similarity from the
    # initial schema. This placeholder revision is kept only to preserve the
    # migration chain after the file went missing in history.
    return None


def downgrade() -> None:
    return None
