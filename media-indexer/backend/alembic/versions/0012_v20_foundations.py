"""add v2.0 foundation tables and artifacts

Revision ID: 0012_v20_foundations
Revises: 0011_tag_suggestion_metadata
Create Date: 2026-04-17 21:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


revision = "0012_v20_foundations"
down_revision = "0011_tag_suggestion_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("waveform_preview_path", sa.Text(), nullable=True))
    op.add_column("assets", sa.Column("video_keyframes", sa.dialects.postgresql.JSONB(), nullable=True))

    op.create_table(
        "scheduled_scans",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("cron_expression", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_job_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["last_job_id"], ["scan_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scheduled_scans_source_id", "scheduled_scans", ["source_id"], unique=False)

    op.create_table(
        "webhook_endpoints",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("secret", sa.Text(), nullable=False),
        sa.Column("events", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status_code", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "api_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("token_prefix", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_api_tokens_token_prefix", "api_tokens", ["token_prefix"], unique=False)

    op.create_table(
        "inbox_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("inbox_path", sa.Text(), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("phash", sa.String(length=64), nullable=True),
        sa.Column("clip_distance_min", sa.Float(), nullable=True),
        sa.Column("nearest_asset_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("target_source_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.UUID(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["nearest_asset_id"], ["assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_source_id"], ["sources.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("inbox_path"),
    )
    op.create_index("ix_inbox_items_status", "inbox_items", ["status"], unique=False)

    op.create_table(
        "face_people",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("cover_face_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "face_detections",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("asset_id", sa.UUID(), nullable=False),
        sa.Column("person_id", sa.UUID(), nullable=True),
        sa.Column("bbox_x1", sa.Integer(), nullable=False),
        sa.Column("bbox_y1", sa.Integer(), nullable=False),
        sa.Column("bbox_x2", sa.Integer(), nullable=False),
        sa.Column("bbox_y2", sa.Integer(), nullable=False),
        sa.Column("det_score", sa.Float(), nullable=False),
        sa.Column("embedding", Vector(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id"], ["face_people.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_face_detections_asset_id", "face_detections", ["asset_id"], unique=False)
    op.create_foreign_key(
        "fk_face_people_cover_face_id",
        "face_people",
        "face_detections",
        ["cover_face_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "smart_albums",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("rule_json", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("asset_count", sa.Integer(), nullable=False),
        sa.Column("cover_asset_id", sa.UUID(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["cover_asset_id"], ["assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_smart_albums_owner_id", "smart_albums", ["owner_id"], unique=False)

    op.create_table(
        "curation_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("asset_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_curation_events_user_id", "curation_events", ["user_id"], unique=False)
    op.create_index("ix_curation_events_asset_id", "curation_events", ["asset_id"], unique=False)
    op.create_index("ix_curation_events_event_type", "curation_events", ["event_type"], unique=False)
    op.create_index("ix_curation_events_created_at", "curation_events", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_curation_events_created_at", table_name="curation_events")
    op.drop_index("ix_curation_events_event_type", table_name="curation_events")
    op.drop_index("ix_curation_events_asset_id", table_name="curation_events")
    op.drop_index("ix_curation_events_user_id", table_name="curation_events")
    op.drop_table("curation_events")
    op.drop_index("ix_smart_albums_owner_id", table_name="smart_albums")
    op.drop_table("smart_albums")
    op.drop_constraint("fk_face_people_cover_face_id", "face_people", type_="foreignkey")
    op.drop_index("ix_face_detections_asset_id", table_name="face_detections")
    op.drop_table("face_detections")
    op.drop_table("face_people")
    op.drop_index("ix_inbox_items_status", table_name="inbox_items")
    op.drop_table("inbox_items")
    op.drop_index("ix_api_tokens_token_prefix", table_name="api_tokens")
    op.drop_table("api_tokens")
    op.drop_table("webhook_endpoints")
    op.drop_index("ix_scheduled_scans_source_id", table_name="scheduled_scans")
    op.drop_table("scheduled_scans")
    op.drop_column("assets", "video_keyframes")
    op.drop_column("assets", "waveform_preview_path")
