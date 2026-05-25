from __future__ import annotations

from media_indexer_backend.core.config import get_settings
from media_indexer_backend.services.clip_embeddings import ClipEmbeddingService


async def embed_text(text: str) -> list[float]:
    settings = get_settings()
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{settings.worker_status_url.rstrip('/')}/embed/text",
                json={"text": text},
            )
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload.get("embedding"), list):
                return [float(value) for value in payload["embedding"]]
    except Exception:
        embedder = ClipEmbeddingService()
        vector = embedder.embed_text(text)
        if vector:
            return vector
    return []
