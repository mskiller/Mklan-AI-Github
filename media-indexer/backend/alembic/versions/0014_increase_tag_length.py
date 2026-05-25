"""increase tag length

Revision ID: 0014_increase_tag_length
Revises: 0013_v20_people_smart_albums
Create Date: 2026-04-17 22:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0014_increase_tag_length"
down_revision = "0013_v20_people_smart_albums"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Increase length of tag column in asset_tags
    op.alter_column("asset_tags", "tag",
               existing_type=sa.String(length=255),
               type_=sa.String(length=1024),
               existing_nullable=False)


def downgrade() -> None:
    # Downgrade might fail if there are tags longer than 255
    op.alter_column("asset_tags", "tag",
               existing_type=sa.String(length=1024),
               type_=sa.String(length=255),
               existing_nullable=False)
