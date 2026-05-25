"""tag_vocabulary and tag_suggestions tables

Revision ID: 0010_tag_vocabulary
Revises: 0009_share_links
Create Date: 2026-04-16 18:25:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0010_tag_vocabulary"
down_revision = "0009_share_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tag_vocabulary",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tag", sa.String, nullable=False),
        sa.Column("description", sa.String, nullable=True),
        sa.Column("clip_prompt", sa.String, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_by", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
    )
    op.create_index("ix_tag_vocabulary_tag", "tag_vocabulary", ["tag"], unique=True)
    
    op.create_table(
        "tag_suggestions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("asset_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tag", sa.String, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default="'pending'"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_tag_suggestions_asset_id", "tag_suggestions", ["asset_id"])
    op.create_index("ix_tag_suggestions_tag", "tag_suggestions", ["tag"])


def downgrade() -> None:
    op.drop_index("ix_tag_suggestions_tag", table_name="tag_suggestions")
    op.drop_index("ix_tag_suggestions_asset_id", table_name="tag_suggestions")
    op.drop_table("tag_suggestions")
    
    op.drop_index("ix_tag_vocabulary_tag", table_name="tag_vocabulary")
    op.drop_table("tag_vocabulary")
