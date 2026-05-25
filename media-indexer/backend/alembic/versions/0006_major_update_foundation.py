"""major update foundation: annotations, groups, blur hash, and scan errors

Revision ID: 0006_major_update_foundation
Revises: 0005_curator_upload
Create Date: 2026-04-12 02:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0006_major_update_foundation"
down_revision = "0005_curator_upload"
branch_labels = None
depends_on = None


review_status_enum = postgresql.ENUM(
    "unreviewed",
    "approved",
    "rejected",
    "favorite",
    name="review_status",
    create_type=False,
)


def upgrade() -> None:
    op.execute("ALTER TYPE user_status ADD VALUE IF NOT EXISTS 'locked'")
    op.execute("ALTER TYPE user_status ADD VALUE IF NOT EXISTS 'banned'")

    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("ban_reason", sa.Text(), nullable=True))

    op.add_column("assets", sa.Column("blur_hash", sa.String(length=128), nullable=True))
    op.add_column(
        "scan_jobs",
        sa.Column(
            "error_details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    op.create_table(
        "groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "permissions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name", name="uq_groups_name"),
    )

    op.create_table(
        "user_groups",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "group_id"),
    )

    review_status_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "asset_annotations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rating", sa.SmallInteger(), nullable=True),
        sa.Column(
            "review_status",
            review_status_enum,
            nullable=False,
            server_default="unreviewed",
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("flagged", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("asset_id", "user_id", name="uq_asset_annotations_asset_user"),
    )
    op.create_index("ix_asset_annotations_asset_id", "asset_annotations", ["asset_id"])
    op.create_index("ix_asset_annotations_rating", "asset_annotations", ["rating"])
    op.create_index("ix_asset_annotations_review_status", "asset_annotations", ["review_status"])
    op.create_index("ix_asset_annotations_flagged", "asset_annotations", ["flagged"])


def downgrade() -> None:
    op.drop_index("ix_asset_annotations_flagged", table_name="asset_annotations")
    op.drop_index("ix_asset_annotations_review_status", table_name="asset_annotations")
    op.drop_index("ix_asset_annotations_rating", table_name="asset_annotations")
    op.drop_index("ix_asset_annotations_asset_id", table_name="asset_annotations")
    op.drop_table("asset_annotations")
    review_status_enum.drop(op.get_bind(), checkfirst=True)

    op.drop_table("user_groups")
    op.drop_table("groups")

    op.drop_column("scan_jobs", "error_details")
    op.drop_column("assets", "blur_hash")
    op.drop_column("users", "ban_reason")
    op.drop_column("users", "locked_until")

    # PostgreSQL enum values are not removed safely in place.
