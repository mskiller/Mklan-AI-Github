from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from media_indexer_backend.models.enums import MediaType
from media_indexer_backend.models.tables import User
from media_indexer_backend.schemas.asset import CompareAsset, CompareDiffEntry, CompareResponse
from media_indexer_backend.services.asset_service import get_asset_or_404
from media_indexer_backend.services.metadata import compute_prompt_tag_overlap, hamming_distance, normalized_metadata_for_api


COMPARE_FIELDS = [
    "width",
    "height",
    "camera_make",
    "camera_model",
    "lens",
    "created_at",
    "duration_seconds",
    "codec",
]


def _compare_asset_payload(asset) -> CompareAsset:
    normalized = normalized_metadata_for_api(asset.metadata_record.normalized_json if asset.metadata_record else {})
    return CompareAsset(
        id=asset.id,
        filename=asset.filename,
        preview_url=f"/assets/{asset.id}/preview" if asset.preview_path else None,
        content_url=f"/assets/{asset.id}/content",
        deepzoom_available=False,
        deepzoom_url=None,
        size_bytes=asset.size_bytes,
        created_at=asset.created_at,
        modified_at=asset.modified_at,
        normalized_metadata=normalized,
        tags=sorted(tag.tag for tag in asset.tags),
    )


def _diff(normalized_a: dict[str, Any], normalized_b: dict[str, Any], size_a: int, size_b: int) -> list[CompareDiffEntry]:
    differences = []
    if size_a != size_b:
        differences.append(CompareDiffEntry(field="size_bytes", left=size_a, right=size_b))
    for field in COMPARE_FIELDS:
        left = normalized_a.get(field)
        right = normalized_b.get(field)
        if left != right:
            differences.append(CompareDiffEntry(field=field, left=left, right=right))
    return differences


def compare_assets(session: Session, asset_id_a: UUID, asset_id_b: UUID, current_user: User | None = None) -> CompareResponse:
    if asset_id_a == asset_id_b:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Choose two different images to compare.",
        )
    asset_a = get_asset_or_404(session, asset_id_a, current_user=current_user)
    asset_b = get_asset_or_404(session, asset_id_b, current_user=current_user)
    if asset_a.media_type != MediaType.IMAGE or asset_b.media_type != MediaType.IMAGE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The MVP compare view supports images only.")

    normalized_a = normalized_metadata_for_api(asset_a.metadata_record.normalized_json if asset_a.metadata_record else {})
    normalized_b = normalized_metadata_for_api(asset_b.metadata_record.normalized_json if asset_b.metadata_record else {})
    prompt_tag_overlap, shared_prompt_tags, left_only_prompt_tags, right_only_prompt_tags = compute_prompt_tag_overlap(
        normalized_a,
        normalized_b,
    )
    phash_distance = hamming_distance(asset_a.similarity.phash if asset_a.similarity else None, asset_b.similarity.phash if asset_b.similarity else None)

    semantic_row = session.execute(
        text(
            """
            SELECT 1 - (a.embedding <=> b.embedding) AS similarity
            FROM asset_similarity a
            JOIN asset_similarity b ON b.asset_id = :asset_id_b
            WHERE a.asset_id = :asset_id_a
              AND a.embedding IS NOT NULL
              AND b.embedding IS NOT NULL
            """
        ),
        {"asset_id_a": asset_id_a, "asset_id_b": asset_id_b},
    ).first()
    semantic_similarity = float(semantic_row.similarity) if semantic_row and semantic_row.similarity is not None else None

    return CompareResponse(
        asset_a=_compare_asset_payload(asset_a),
        asset_b=_compare_asset_payload(asset_b),
        phash_distance=phash_distance,
        semantic_similarity=semantic_similarity,
        prompt_tag_overlap=prompt_tag_overlap,
        shared_prompt_tags=shared_prompt_tags,
        left_only_prompt_tags=left_only_prompt_tags,
        right_only_prompt_tags=right_only_prompt_tags,
        metadata_diff=_diff(normalized_a, normalized_b, asset_a.size_bytes, asset_b.size_bytes),
    )
