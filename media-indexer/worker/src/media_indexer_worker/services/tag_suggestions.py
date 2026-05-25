from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from media_indexer_backend.services.clip_embeddings import ClipEmbeddingService
from media_indexer_backend.services.image_enrichment import ClipVocabularyTagger


class TagSuggestionService:
    def __init__(self, embedder: ClipEmbeddingService) -> None:
        self._clip_vocab = ClipVocabularyTagger(embedder)

    def suggest_tags(self, session: Session, asset_id: Any, threshold: float = 0.2) -> None:
        self._clip_vocab.replace_pending_suggestions(session, asset_id, threshold=threshold)
