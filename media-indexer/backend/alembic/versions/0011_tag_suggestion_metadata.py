"""extend tag_suggestions metadata

Revision ID: 0011_tag_suggestion_metadata
Revises: 0010_tag_vocabulary
Create Date: 2026-04-17 11:20:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_tag_suggestion_metadata"
down_revision = "0010_tag_vocabulary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tag_suggestions", sa.Column("tag_group", sa.String(length=32), nullable=True))
    op.add_column("tag_suggestions", sa.Column("source_model", sa.String(length=255), nullable=True))
    op.add_column("tag_suggestions", sa.Column("rank", sa.Integer(), nullable=True))
    op.add_column("tag_suggestions", sa.Column("raw_score", sa.Float(), nullable=True))
    op.add_column("tag_suggestions", sa.Column("threshold_used", sa.Float(), nullable=True))
    op.add_column("tag_suggestions", sa.Column("source_payload", sa.dialects.postgresql.JSONB(), nullable=True))
    op.create_index("ix_tag_suggestions_source_model", "tag_suggestions", ["source_model"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_tag_suggestions_source_model", table_name="tag_suggestions")
    op.drop_column("tag_suggestions", "source_payload")
    op.drop_column("tag_suggestions", "threshold_used")
    op.drop_column("tag_suggestions", "raw_score")
    op.drop_column("tag_suggestions", "rank")
    op.drop_column("tag_suggestions", "source_model")
    op.drop_column("tag_suggestions", "tag_group")
