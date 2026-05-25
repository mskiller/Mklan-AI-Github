"""share_links table

Revision ID: 0009_share_links
Revises: 0008_asset_embedding
Create Date: 2026-04-16 18:20:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0009_share_links"
down_revision = "0008_asset_embedding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "share_links",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("created_by", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("target_type", sa.String, nullable=False),
        sa.Column("target_id", sa.String, nullable=False),
        sa.Column("label", sa.String, nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("allow_download", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("view_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_share_links_created_by", "share_links", ["created_by"])


def downgrade() -> None:
    op.drop_index("ix_share_links_created_by", table_name="share_links")
    op.drop_table("share_links")
