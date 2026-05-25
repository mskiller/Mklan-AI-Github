from __future__ import annotations

import os
from typing import Any

import requests


def _truthy_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}

class SemanticSearchEngine:
    def __init__(self):
        self.model_id = os.getenv("STUDIO_SEMANTIC_MODEL", "media-indexer/pgvector")
        self.enabled = _truthy_env("STUDIO_SEMANTIC_SEARCH_ENABLED", True)
        self.media_indexer_url = os.getenv("MEDIA_INDEXER_INTERNAL_URL", "http://media_indexer_backend:8000").rstrip("/")
        self.timeout_s = float(os.getenv("MEDIA_INDEXER_TIMEOUT_S", "3"))
        self.device = "media-indexer"
        self.model: Any | None = None
        self.processor: Any | None = None
        self._loaded = False
        self._load_error: str | None = None
        self._embeddings_cache = {}

    @property
    def unavailable_reason(self) -> str:
        if not self.enabled:
            return "Semantic search is disabled by STUDIO_SEMANTIC_SEARCH_ENABLED."
        return self._load_error or "Semantic search is delegated to Media Indexer pgvector."

    def _load(self) -> bool:
        return False

    def get_text_embedding(self, text: str):
        return None

    def get_image_embedding(self, image_path: str):
        return None

    def search(self, text: str, *, limit: int = 50) -> dict[str, Any]:
        """Query persistent embeddings through Media Indexer.

        The Studio backend no longer loads CLIP or keeps per-process image
        embeddings. Media Indexer owns CLIP, pHash, pgvector, collections, and
        smart-album metadata; this method is a thin compatibility bridge for
        older Studio routes.
        """
        query = text.strip()
        if not query:
            return {"ok": True, "status": "empty", "items": [], "total": 0}
        if not self.enabled:
            return {"ok": False, "status": "disabled", "items": [], "error": self.unavailable_reason}
        if not self.media_indexer_url:
            self._load_error = "MEDIA_INDEXER_INTERNAL_URL is not configured."
            return {"ok": False, "status": "disabled", "items": [], "error": self._load_error}

        try:
            response = requests.get(
                f"{self.media_indexer_url}/search/nl",
                params={"q": query, "limit": max(1, min(int(limit), 200))},
                timeout=self.timeout_s,
            )
            response.raise_for_status()
            payload = response.json()
            self._load_error = None
            return {
                "ok": True,
                "status": "available",
                "base_url": self.media_indexer_url,
                "items": payload.get("items", []) if isinstance(payload, dict) else [],
                "total": payload.get("total", 0) if isinstance(payload, dict) else 0,
                "raw": payload,
            }
        except Exception as exc:
            self._load_error = str(exc)
            return {
                "ok": False,
                "status": "unavailable",
                "base_url": self.media_indexer_url,
                "items": [],
                "error": str(exc),
            }
