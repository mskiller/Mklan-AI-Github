from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from media_indexer_backend.core.config import get_settings
from media_indexer_backend.models.enums import MatchType
from media_indexer_backend.models.tables import AssetSimilarity, SimilarityLink
from media_indexer_backend.services.clip_embeddings import ClipEmbeddingService
from media_indexer_backend.services.metadata import canonical_pair, hamming_distance
from media_indexer_backend.services.tag_similarity_service import rebuild_tag_similarity_for_asset


logger = logging.getLogger(__name__)


try:
    import cv2
except ImportError:  # pragma: no cover - dependency issue fallback
    cv2 = None


class SimilarityService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.embedder = ClipEmbeddingService()

    def compute_phash(self, path: Path) -> str | None:
        try:
            if cv2 is not None:
                image = cv2.imread(str(path))
                if image is not None:
                    phash = cv2.img_hash.pHash(image).flatten().tolist()
                    return "".join(f"{byte:02x}" for byte in phash)

            with Image.open(path) as image:
                image = image.convert("L").resize((8, 8))
                pixels = np.asarray(image, dtype=np.float32)
                threshold = pixels.mean()
                bits = "".join("1" if value >= threshold else "0" for value in pixels.flatten())
                return f"{int(bits, 2):016x}"
        except Exception as exc:  # noqa: BLE001
            logger.warning("phash computation failed", extra={"path": str(path), "error": str(exc)})
            return None

    def refresh(self, session: Session, asset_id, image_path: Path) -> None:
        session.execute(
            delete(SimilarityLink).where(
                or_(SimilarityLink.asset_id_a == asset_id, SimilarityLink.asset_id_b == asset_id)
            )
        )

        phash = self.compute_phash(image_path)
        embedding = self.embedder.embed_image(image_path)

        record = session.get(AssetSimilarity, asset_id)
        if not record:
            record = AssetSimilarity(asset_id=asset_id)
            session.add(record)
        record.phash = phash
        record.embedding = embedding
        record.embedding_model = self.settings.clip_model_id if embedding else None
        record.computed_at = datetime.now(tz=timezone.utc)
        session.flush()

        if phash:
            self._refresh_duplicate_links(session, asset_id, phash)
        if embedding:
            self._refresh_semantic_links(session, asset_id, embedding)
        rebuild_tag_similarity_for_asset(session, asset_id)

    def refresh_tag_links(self, session: Session, asset_id) -> int:
        return rebuild_tag_similarity_for_asset(session, asset_id)

    def _refresh_duplicate_links(self, session: Session, asset_id, phash: str) -> None:
        rows = session.execute(
            select(AssetSimilarity.asset_id, AssetSimilarity.phash).where(
                AssetSimilarity.asset_id != asset_id,
                AssetSimilarity.phash.is_not(None),
            )
        ).all()
        for candidate_id, candidate_phash in rows:
            distance = hamming_distance(phash, candidate_phash)
            if distance is None or distance > self.settings.duplicate_phash_threshold:
                continue
            left, right = canonical_pair(asset_id, candidate_id)
            session.merge(
                SimilarityLink(
                    asset_id_a=left,
                    asset_id_b=right,
                    match_type=MatchType.DUPLICATE,
                    distance=float(distance),
                )
            )

    def _refresh_semantic_links(self, session: Session, asset_id, embedding: list[float]) -> None:
        distance_expr = AssetSimilarity.embedding.cosine_distance(embedding)
        rows = session.execute(
            select(AssetSimilarity.asset_id, distance_expr.label("distance"))
            .where(
                AssetSimilarity.asset_id != asset_id,
                AssetSimilarity.embedding.is_not(None),
            )
            .order_by(distance_expr)
            .limit(self.settings.semantic_neighbor_limit)
        ).all()
        for candidate_id, distance in rows:
            if distance is None or float(distance) > 1 - self.settings.semantic_similarity_threshold:
                continue
            left, right = canonical_pair(asset_id, candidate_id)
            session.merge(
                SimilarityLink(
                    asset_id_a=left,
                    asset_id_b=right,
                    match_type=MatchType.SEMANTIC,
                    distance=float(distance),
                )
            )
