"""extend people and smart album support

Revision ID: 0013_v20_people_smart_albums
Revises: 0012_v20_foundations
Create Date: 2026-04-17 23:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_v20_people_smart_albums"
down_revision = "0012_v20_foundations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("face_detections", sa.Column("crop_preview_path", sa.Text(), nullable=True))
    op.add_column("smart_albums", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE smart_albums SET updated_at = created_at WHERE updated_at IS NULL")
    op.alter_column("smart_albums", "updated_at", nullable=False)
    op.add_column("curation_events", sa.Column("details_json", sa.dialects.postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("curation_events", "details_json")
    op.drop_column("smart_albums", "updated_at")
    op.drop_column("face_detections", "crop_preview_path")
