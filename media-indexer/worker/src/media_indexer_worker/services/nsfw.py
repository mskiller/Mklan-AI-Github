from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from media_indexer_backend.core.config import get_settings

logger = logging.getLogger(__name__)

UNSAFE_LABEL_HINTS = {"nsfw", "unsafe", "porn", "hentai", "sexy", "explicit", "sexual", "nudity", "nude"}
NSFW_THRESHOLD = 0.6


class NsfwDetectorService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._pipeline = None
        self._load_failed = False

    def _load(self) -> bool:
        if not self.settings.nsfw_detector_enabled:
            return False
        if self._load_failed:
            return False
        if self._pipeline is not None:
            return True
        try:
            from transformers import pipeline

            # pipeline will automatically download the model on first launch
            self._pipeline = pipeline("image-classification", model=self.settings.nsfw_model_id)
            return True
        except Exception as exc:  # noqa: BLE001
            self._load_failed = True
            logger.warning("nsfw model unavailable: %s", exc, extra={"error": str(exc)}, exc_info=True)
            return False

    def classify(self, path: Path) -> dict[str, Any]:
        if not self._load():
            return {
                "available": False,
                "detected": False,
                "score": None,
                "label": None,
                "model": self.settings.nsfw_model_id,
            }
        assert self._pipeline is not None
        try:
            from PIL import Image

            with Image.open(path) as image:
                image = image.convert("RGB")
                results = self._pipeline(image)
            labels = [
                {
                    "label": str(result.get("label", "")),
                    "score": float(result.get("score", 0.0) or 0.0),
                }
                for result in results
                if isinstance(result, dict)
            ]
            top = max(labels, key=lambda item: item["score"], default={"label": None, "score": None})
            unsafe_score = max(
                (
                    item["score"]
                    for item in labels
                    if any(hint in item["label"].lower() for hint in UNSAFE_LABEL_HINTS)
                ),
                default=0.0,
            )
            return {
                "available": True,
                "detected": unsafe_score >= NSFW_THRESHOLD,
                "score": round(float(unsafe_score), 6),
                "label": top["label"],
                "model": self.settings.nsfw_model_id,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("nsfw detection failed: %s", exc, extra={"path": str(path), "error": str(exc)}, exc_info=True)
            return {
                "available": False,
                "detected": False,
                "score": None,
                "label": None,
                "model": self.settings.nsfw_model_id,
                "error": str(exc),
            }

    def detect_nsfw(self, path: Path) -> bool:
        return bool(self.classify(path).get("detected"))
