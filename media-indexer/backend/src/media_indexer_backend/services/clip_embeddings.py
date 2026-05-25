from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PIL import Image

from media_indexer_backend.core.config import get_settings
from media_indexer_backend.platform.runtime import get_ai_tagging_runtime_settings


logger = logging.getLogger(__name__)


class ClipEmbeddingService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._processor = None
        self._model = None
        self._torch = None
        self._load_failed = False

    @property
    def is_loaded(self) -> bool:
        return self._model is not None and self._processor is not None and self._torch is not None

    def warm(self) -> bool:
        return self._load()

    def _load(self) -> bool:
        if not get_ai_tagging_runtime_settings().clip_enabled:
            return False
        if self.is_loaded:
            return True
        if self._load_failed:
            return False
        try:
            import torch
            from transformers import CLIPModel, CLIPProcessor

            self._torch = torch
            self._processor = CLIPProcessor.from_pretrained(self.settings.clip_model_id)
            self._model = CLIPModel.from_pretrained(self.settings.clip_model_id).to(self.settings.clip_device)
            self._model.eval()
            self._load_failed = False
            return True
        except Exception as exc:  # noqa: BLE001
            self._load_failed = True
            logger.warning("clip model unavailable: %s", exc, extra={"error": str(exc)}, exc_info=True)
            return False

    def _resolve_embedding_tensor(self, output, *, kind: str):
        assert self._torch is not None
        if isinstance(output, self._torch.Tensor):
            return output
        for attribute in (
            f"{kind}_embeds",
            "image_embeds",
            "text_embeds",
            "pooler_output",
            "last_hidden_state",
        ):
            value = getattr(output, attribute, None)
            if isinstance(value, self._torch.Tensor):
                if attribute == "last_hidden_state" and value.ndim >= 3:
                    return value[:, 0, :]
                return value
        raise AttributeError(f"Cannot extract embedding tensor from {type(output).__name__}")

    def embed_image(self, path: Path) -> list[float] | None:
        if not self._load():
            return None
        assert self._processor is not None
        assert self._model is not None
        assert self._torch is not None
        try:
            with Image.open(path) as image:
                image = image.convert("RGB")
                inputs = self._processor(images=image, return_tensors="pt")
                inputs = {key: value.to(self.settings.clip_device) for key, value in inputs.items()}
                with self._torch.no_grad():
                    output = self._model.get_image_features(**inputs)
                    embedding = self._resolve_embedding_tensor(output, kind="image")
                    embedding = embedding / embedding.norm(dim=-1, keepdim=True)
                return embedding[0].detach().cpu().numpy().astype(np.float32).tolist()
        except Exception as exc:  # noqa: BLE001
            logger.warning("clip embedding failed: %s", exc, extra={"path": str(path), "error": str(exc)}, exc_info=True)
            return None

    def embed_text(self, text: str) -> list[float] | None:
        if not self._load():
            return None
        assert self._processor is not None
        assert self._model is not None
        assert self._torch is not None
        try:
            inputs = self._processor(text=[text], return_tensors="pt", padding=True)
            inputs = {key: value.to(self.settings.clip_device) for key, value in inputs.items()}
            with self._torch.no_grad():
                output = self._model.get_text_features(**inputs)
                output = self._resolve_embedding_tensor(output, kind="text")
                embedding = output / output.norm(dim=-1, keepdim=True)
            return embedding[0].detach().cpu().numpy().astype(np.float32).tolist()
        except Exception as exc:  # noqa: BLE001
            logger.warning("clip text embedding failed: %s", exc, extra={"text": text, "error": str(exc)}, exc_info=True)
            return None
