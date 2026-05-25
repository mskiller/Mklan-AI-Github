from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from media_indexer_backend.models.enums import MatchType, MediaType
from media_indexer_backend.models.tables import Asset, AssetMetadata, SimilarityLink
from media_indexer_backend.services.metadata import canonical_pair, compute_prompt_tag_similarity
from media_indexer_backend.services.settings_service import get_tag_similarity_threshold_score


def _normalized_metadata_for_asset(session: Session, asset_id: UUID) -> dict:
    metadata = session.get(AssetMetadata, asset_id)
    return metadata.normalized_json if metadata else {}


def rebuild_tag_similarity_for_asset(session: Session, asset_id: UUID, *, threshold_score: float | None = None) -> int:
    asset = session.get(Asset, asset_id)
    if not asset or asset.media_type != MediaType.IMAGE:
        session.execute(
            delete(SimilarityLink).where(
                SimilarityLink.match_type == MatchType.TAG,
                (SimilarityLink.asset_id_a == asset_id) | (SimilarityLink.asset_id_b == asset_id),
            )
        )
        return 0

    threshold = threshold_score if threshold_score is not None else get_tag_similarity_threshold_score(session)
    session.execute(
        delete(SimilarityLink).where(
            SimilarityLink.match_type == MatchType.TAG,
            (SimilarityLink.asset_id_a == asset_id) | (SimilarityLink.asset_id_b == asset_id),
        )
    )

    target_normalized = _normalized_metadata_for_asset(session, asset_id)
    rows = session.execute(
        select(Asset.id, AssetMetadata.normalized_json)
        .join(AssetMetadata, AssetMetadata.asset_id == Asset.id)
        .where(Asset.id != asset_id, Asset.media_type == MediaType.IMAGE)
    ).all()

    created = 0
    for candidate_id, candidate_normalized in rows:
        score, _, _, _ = compute_prompt_tag_similarity(target_normalized, candidate_normalized or {})
        if score < threshold:
            continue
        left, right = canonical_pair(asset_id, candidate_id)
        session.merge(
            SimilarityLink(
                asset_id_a=left,
                asset_id_b=right,
                match_type=MatchType.TAG,
                distance=float(1.0 - score),
            )
        )
        created += 1
    return created


def rebuild_all_tag_similarity(session: Session) -> tuple[int, int]:
    threshold = get_tag_similarity_threshold_score(session)
    session.execute(delete(SimilarityLink).where(SimilarityLink.match_type == MatchType.TAG))

    assets: list[tuple[UUID, dict]] = list(
        session.execute(
            select(Asset.id, AssetMetadata.normalized_json)
            .join(AssetMetadata, AssetMetadata.asset_id == Asset.id)
            .where(Asset.media_type == MediaType.IMAGE)
            .order_by(Asset.id)
        ).all()
    )

    rebuilt_links = 0
    for index, (asset_id, normalized) in enumerate(assets):
        for candidate_id, candidate_normalized in assets[index + 1 :]:
            score, _, _, _ = compute_prompt_tag_similarity(normalized or {}, candidate_normalized or {})
            if score < threshold:
                continue
            left, right = canonical_pair(asset_id, candidate_id)
            session.merge(
                SimilarityLink(
                    asset_id_a=left,
                    asset_id_b=right,
                    match_type=MatchType.TAG,
                    distance=float(1.0 - score),
                )
            )
            rebuilt_links += 1
    session.flush()
    return len(assets), rebuilt_links
