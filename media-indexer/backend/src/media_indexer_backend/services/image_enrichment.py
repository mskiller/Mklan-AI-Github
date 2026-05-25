from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from media_indexer_backend.core.config import get_settings
from media_indexer_backend.models.tables import Asset, AssetMetadata, AssetSearch, AssetSimilarity, AssetTag, TagSuggestion, TagVocabularyEntry
from media_indexer_backend.platform.runtime import get_ai_tagging_runtime_settings
from media_indexer_backend.services.clip_embeddings import ClipEmbeddingService
from media_indexer_backend.services.metadata import build_search_text, canonicalize_tag


logger = logging.getLogger(__name__)


GROUP_ORDER = {
    "rating": 0,
    "general": 1,
    "meta": 2,
    "character": 3,
    "copyright": 4,
    "curated": 5,
}


@dataclass(slots=True)
class TagSuggestionCandidate:
    tag: str
    group: str
    score: float
    rank: int
    source_model: str
    raw_tag: str
    raw_score: float | None = None
    threshold_used: float | None = None
    source_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProviderStatus:
    key: str
    label: str
    status: str
    device: str
    source_model: str
    warm: bool
    detail: str | None = None


@dataclass(slots=True)
class RelatedTag:
    tag: str
    score: float
    group: str
    source_model: str


def _first_present(row: dict[str, Any], *candidates: str) -> Any:
    lowered = {str(key).strip().lower(): value for key, value in row.items()}
    for candidate in candidates:
        value = lowered.get(candidate.lower())
        if value not in (None, ""):
            return value
    return None


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _tag_group_from_values(raw_tag: str, category_value: Any) -> str:
    lowered = str(raw_tag).strip().lower()
    if lowered.startswith("rating:"):
        return "rating"
    category_text = str(category_value).strip().lower() if category_value is not None else ""
    category_int = _safe_int(category_value)
    if category_text in {"rating", "ratings"} or category_int == 9:
        return "rating"
    if category_text in {"general", "tag"} or category_int == 0:
        return "general"
    if category_text in {"character"} or category_int == 4:
        return "character"
    if category_text in {"copyright", "series"} or category_int == 3:
        return "copyright"
    if category_text in {"meta", "artist"} or category_int in {1, 5}:
        return "meta"
    return "general"


def _onnx_provider_order() -> tuple[list[str], str]:
    try:
        import onnxruntime as ort

        available = set(ort.get_available_providers())
    except Exception:
        return (["CPUExecutionProvider"], "cpu")
    ordered = [provider for provider in ("CUDAExecutionProvider", "CPUExecutionProvider") if provider in available]
    if not ordered:
        ordered = ["CPUExecutionProvider"]
    device = "cuda" if "CUDAExecutionProvider" in ordered else "cpu"
    return ordered, device


class WdTaggerProvider:
    def __init__(
        self,
        *,
        key: str,
        label: str,
        repo_id: str,
        source_model: str,
        tag_file: str,
        subfolder: str | None = None,
        has_embeddings: bool = False,
    ) -> None:
        self.settings = get_settings()
        self.key = key
        self.label = label
        self.repo_id = repo_id
        self.source_model = source_model
        self.tag_file = tag_file
        self.subfolder = subfolder
        self.has_embeddings = has_embeddings
        self._session = None
        self._input_name: str | None = None
        self._input_hw: tuple[int, int] | None = None
        self._input_layout = "nhwc"
        self._tags: list[tuple[str, str, str]] = []
        self._inverse_vectors: np.ndarray | None = None
        self._last_error: str | None = None
        self._device = "cpu"

    def _download(self, filename: str, *, local_only: bool) -> Path:
        from huggingface_hub import hf_hub_download

        kwargs: dict[str, Any] = {
            "repo_id": self.repo_id,
            "filename": filename,
            "local_files_only": local_only,
            "cache_dir": str(self.settings.model_cache_root_path),
        }
        if self.subfolder:
            kwargs["subfolder"] = self.subfolder
        return Path(hf_hub_download(**kwargs))

    def _load_tags(self, csv_path: Path) -> None:
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            parsed: list[tuple[str, str, str]] = []
            for row in reader:
                raw_name = str(_first_present(row, "name", "tag", "label", "tag_name") or "").strip()
                if not raw_name:
                    continue
                canonical = canonicalize_tag(raw_name)
                if not canonical:
                    continue
                group = _tag_group_from_values(raw_name, _first_present(row, "category", "tag_category", "type"))
                parsed.append((canonical, raw_name, group))
        self._tags = parsed

    def _load_inverse_vectors(self, inverse_path: Path) -> None:
        try:
            with np.load(inverse_path) as payload:
                tag_count = len(self._tags)
                candidate: np.ndarray | None = None
                for key in payload.files:
                    values = np.asarray(payload[key])
                    if values.ndim != 2:
                        continue
                    if values.shape[0] == tag_count:
                        candidate = values.astype(np.float32)
                        break
                    if values.shape[1] == tag_count:
                        candidate = values.T.astype(np.float32)
                        break
                if candidate is None:
                    self._inverse_vectors = None
                    return
                norms = np.linalg.norm(candidate, axis=1, keepdims=True)
                norms[norms == 0] = 1.0
                self._inverse_vectors = candidate / norms
        except Exception as exc:  # noqa: BLE001
            logger.warning("unable to load related-tag vectors for %s: %s", self.key, exc)
            self._inverse_vectors = None

    def warm(self, *, local_only: bool) -> bool:
        if self._session is not None and self._input_name and self._tags:
            return True
        try:
            import onnxruntime as ort

            model_path = self._download("model.onnx", local_only=local_only)
            tag_path = self._download(self.tag_file, local_only=local_only)
            if self.has_embeddings:
                try:
                    inverse_path = self._download("inv.npz", local_only=local_only)
                except Exception:  # noqa: BLE001
                    inverse_path = None
            else:
                inverse_path = None

            provider_order, device = _onnx_provider_order()
            session = ort.InferenceSession(str(model_path), providers=provider_order)
            input_tensor = session.get_inputs()[0]
            shape = input_tensor.shape
            if len(shape) != 4:
                raise ValueError(f"Unsupported input shape for {self.key}: {shape!r}")
            if shape[1] == 3:
                self._input_layout = "nchw"
                self._input_hw = (int(shape[2]), int(shape[3]))
            else:
                self._input_layout = "nhwc"
                self._input_hw = (int(shape[1]), int(shape[2]))
            self._session = session
            self._input_name = input_tensor.name
            self._device = device
            self._load_tags(tag_path)
            if inverse_path is not None:
                self._load_inverse_vectors(inverse_path)
            self._last_error = None
            return True
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            logger.warning("unable to warm %s: %s", self.key, exc, exc_info=True)
            return False

    def status(self) -> ProviderStatus:
        if self._session is not None and self._input_name and self._tags:
            return ProviderStatus(
                key=self.key,
                label=self.label,
                status="ready",
                device=self._device,
                source_model=self.source_model,
                warm=True,
                detail=None,
            )
        if self.warm(local_only=True):
            return ProviderStatus(
                key=self.key,
                label=self.label,
                status="cached",
                device=self._device,
                source_model=self.source_model,
                warm=True,
                detail=None,
            )
        if self._last_error:
            return ProviderStatus(
                key=self.key,
                label=self.label,
                status="cold",
                device="cpu",
                source_model=self.source_model,
                warm=False,
                detail=self._last_error,
            )
        return ProviderStatus(
            key=self.key,
            label=self.label,
            status="cold",
            device="cpu",
            source_model=self.source_model,
            warm=False,
            detail=None,
        )

    def preload(self) -> ProviderStatus:
        self.warm(local_only=False)
        return self.status()

    def _prepare_image(self, image_path: Path) -> np.ndarray:
        assert self._input_hw is not None
        width, height = self._input_hw[1], self._input_hw[0]
        with Image.open(image_path) as image:
            image = image.convert("RGBA")
            white_background = Image.new("RGBA", image.size, (255, 255, 255, 255))
            image = Image.alpha_composite(white_background, image).convert("RGB")
            canvas_size = max(image.width, image.height)
            padded = Image.new("RGB", (canvas_size, canvas_size), (255, 255, 255))
            padded.paste(image, ((canvas_size - image.width) // 2, (canvas_size - image.height) // 2))
            resized = padded.resize((width, height), Image.BICUBIC)
        values = np.asarray(resized, dtype=np.float32)[:, :, ::-1]
        if self._input_layout == "nchw":
            values = np.transpose(values, (2, 0, 1))
        return np.expand_dims(values, axis=0)

    def predict(self, image_path: Path) -> list[TagSuggestionCandidate]:
        if not self.warm(local_only=False):
            return []
        assert self._session is not None
        assert self._input_name is not None
        try:
            outputs = [np.asarray(item) for item in self._session.run(None, {self._input_name: self._prepare_image(image_path)})]
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            logger.warning("wd tagger inference failed for %s: %s", image_path, exc, exc_info=True)
            return []

        if not outputs:
            return []

        tag_scores = max(outputs, key=lambda item: item.shape[-1] if item.ndim >= 2 else 0)
        if tag_scores.ndim == 1:
            scores = tag_scores.astype(np.float32)
        else:
            scores = tag_scores[0].astype(np.float32)

        thresholds = {
            "general": self.settings.tag_suggestion_general_threshold,
            "meta": self.settings.tag_suggestion_meta_threshold,
            "character": self.settings.tag_suggestion_character_threshold,
            "copyright": self.settings.tag_suggestion_copyright_threshold,
        }
        results: list[TagSuggestionCandidate] = []
        rating_candidates: list[tuple[str, str, float]] = []

        for index, (canonical, raw_name, group) in enumerate(self._tags):
            if index >= len(scores):
                break
            score = float(scores[index])
            if group == "rating":
                rating_candidates.append((canonical, raw_name, score))
                continue
            threshold = thresholds.get(group, self.settings.tag_suggestion_general_threshold)
            if score < threshold:
                continue
            results.append(
                TagSuggestionCandidate(
                    tag=canonical,
                    group=group,
                    score=score,
                    rank=0,
                    source_model=self.key,
                    raw_tag=raw_name,
                    raw_score=score,
                    threshold_used=threshold,
                    source_payload={"provider": self.key, "raw_tag": raw_name},
                )
            )

        if rating_candidates:
            top_rating = max(rating_candidates, key=lambda item: item[2])
            results.append(
                TagSuggestionCandidate(
                    tag=top_rating[0],
                    group="rating",
                    score=top_rating[2],
                    rank=0,
                    source_model=self.key,
                    raw_tag=top_rating[1],
                    raw_score=top_rating[2],
                    threshold_used=None,
                    source_payload={"provider": self.key, "raw_tag": top_rating[1]},
                )
            )

        results.sort(key=lambda item: (GROUP_ORDER.get(item.group, 99), -item.score, item.tag))
        for rank, item in enumerate(results, start=1):
            item.rank = rank
        return results

    def related_tags(self, tag: str, limit: int = 12) -> list[RelatedTag]:
        if not self.has_embeddings:
            return []
        if not self.warm(local_only=False):
            return []
        if self._inverse_vectors is None:
            return []
        normalized = canonicalize_tag(tag)
        if not normalized:
            return []
        tag_index = next((index for index, (name, _, _) in enumerate(self._tags) if name == normalized), None)
        if tag_index is None:
            return []
        anchor = self._inverse_vectors[tag_index]
        scores = self._inverse_vectors @ anchor
        results: list[RelatedTag] = []
        for index, score in enumerate(scores):
            if index == tag_index:
                continue
            canonical, _, group = self._tags[index]
            results.append(RelatedTag(tag=canonical, score=float(score), group=group, source_model=self.key))
        results.sort(key=lambda item: item.score, reverse=True)
        return results[:limit]


class CaptioningService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._processor = None
        self._model = None
        self._device = "cpu"
        self._load_failed = False

    def _resolved_device(self) -> str:
        if self.settings.caption_device != "auto":
            return self.settings.caption_device
        try:
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"

    def warm(self, *, local_only: bool) -> bool:
        if not get_ai_tagging_runtime_settings().caption_enabled:
            return False
        if self._model is not None and self._processor is not None:
            return True
        if self._load_failed and local_only:
            return False
        try:
            from transformers import AutoProcessor, BlipForConditionalGeneration

            self._device = self._resolved_device()
            kwargs = {"local_files_only": local_only, "cache_dir": str(self.settings.model_cache_root_path)}
            self._processor = AutoProcessor.from_pretrained(self.settings.caption_model_id, **kwargs)
            self._model = BlipForConditionalGeneration.from_pretrained(self.settings.caption_model_id, **kwargs)
            if self._device != "cpu":
                self._model = self._model.to(self._device)
            self._load_failed = False
            return True
        except Exception as exc:  # noqa: BLE001
            self._load_failed = True
            logger.warning("caption model unavailable: %s", exc)
            return False

    def caption(self, image_path: Path) -> tuple[str | None, str | None]:
        if not self.warm(local_only=False):
            return (None, None)
        assert self._processor is not None
        assert self._model is not None
        try:
            import torch

            with Image.open(image_path) as image:
                image = image.convert("RGB")
                inputs = self._processor(images=image, return_tensors="pt")
            if self._device != "cpu":
                inputs = {key: value.to(self._device) for key, value in inputs.items()}
            with torch.no_grad():
                output = self._model.generate(**inputs, max_new_tokens=48)
            caption = self._processor.batch_decode(output, skip_special_tokens=True)[0].strip()
            return (caption or None, self.settings.caption_model_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("caption generation failed for %s: %s", image_path, exc)
            return (None, None)


class OcrService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def extract(self, image_path: Path) -> tuple[str | None, float | None]:
        if not get_ai_tagging_runtime_settings().ocr_enabled:
            return (None, None)
        try:
            import pytesseract
        except Exception:
            return (None, None)

        try:
            with Image.open(image_path) as image:
                image = image.convert("RGB")
                payload = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ocr extraction failed for %s: %s", image_path, exc)
            return (None, None)

        words: list[str] = []
        confidences: list[float] = []
        for raw_text, raw_confidence in zip(payload.get("text", []), payload.get("conf", []), strict=False):
            text = str(raw_text).strip()
            confidence = _safe_float(raw_confidence)
            if not text:
                continue
            if confidence is not None and confidence < 20:
                continue
            words.append(text)
            if confidence is not None and confidence >= 0:
                confidences.append(confidence)
        if not words:
            return (None, None)
        text = " ".join(words).strip()
        if not text:
            return (None, None)
        if len(text) > self.settings.ocr_max_characters:
            text = text[: self.settings.ocr_max_characters].rstrip()
        confidence = round(sum(confidences) / (len(confidences) * 100), 3) if confidences else None
        return (text, confidence)


class ClipVocabularyTagger:
    def __init__(self, embedder: ClipEmbeddingService | None = None) -> None:
        self.settings = get_settings()
        self.embedder = embedder or ClipEmbeddingService()
        self._vocab_cache: dict[int, np.ndarray] = {}
        self._vocab_tags: dict[int, str] = {}
        self._vocab_signature: tuple[tuple[int, str, str, bool], ...] = ()

    def _refresh_vocab(self, session: Session) -> None:
        entries = session.execute(
            select(TagVocabularyEntry).where(TagVocabularyEntry.enabled == True)
        ).scalars().all()
        signature = tuple(
            sorted((int(entry.id), str(entry.tag), str(entry.clip_prompt), bool(entry.enabled)) for entry in entries)
        )
        if signature == self._vocab_signature and self._vocab_cache:
            return
        next_cache: dict[int, np.ndarray] = {}
        next_tags: dict[int, str] = {}
        for entry in entries:
            tag = canonicalize_tag(entry.tag)
            if not tag:
                continue
            embedding = self.embedder.embed_text(entry.clip_prompt)
            if embedding is None:
                continue
            vector = np.asarray(embedding, dtype=np.float32)
            norm = np.linalg.norm(vector)
            if norm == 0:
                continue
            next_cache[entry.id] = vector / norm
            next_tags[entry.id] = tag
        self._vocab_cache = next_cache
        self._vocab_tags = next_tags
        self._vocab_signature = signature

    def suggest_for_asset(
        self,
        session: Session,
        asset_id: Any,
        *,
        image_path: Path | None = None,
        asset_embedding: list[float] | None = None,
        threshold: float | None = None,
    ) -> list[TagSuggestionCandidate]:
        self._refresh_vocab(session)
        if not self._vocab_cache:
            return []

        similarity_record = session.get(AssetSimilarity, asset_id)
        embedding = asset_embedding or (similarity_record.embedding if similarity_record else None)
        if embedding is None and image_path is not None:
            embedding = self.embedder.embed_image(image_path)
        if embedding is None:
            return []

        existing_tags: set[str] = set()
        for existing_tag in session.execute(select(AssetTag.tag).where(AssetTag.asset_id == asset_id)).scalars().all():
            normalized_tag = canonicalize_tag(existing_tag)
            if normalized_tag:
                existing_tags.add(normalized_tag)
        threshold_value = threshold if threshold is not None else self.settings.clip_vocab_threshold
        asset_vector = np.asarray(embedding, dtype=np.float32)
        asset_norm = np.linalg.norm(asset_vector)
        if asset_norm == 0:
            return []
        asset_vector = asset_vector / asset_norm

        results: list[TagSuggestionCandidate] = []
        for vocab_id, vocab_embedding in self._vocab_cache.items():
            tag = self._vocab_tags[vocab_id]
            if tag in existing_tags:
                continue
            score = float(np.dot(asset_vector, vocab_embedding))
            if score < threshold_value:
                continue
            results.append(
                TagSuggestionCandidate(
                    tag=tag,
                    group="curated",
                    score=score,
                    rank=0,
                    source_model="clip_vocab",
                    raw_tag=tag,
                    raw_score=score,
                    threshold_used=threshold_value,
                    source_payload={"provider": "clip_vocab", "vocabulary_id": vocab_id},
                )
            )
        results.sort(key=lambda item: (-item.score, item.tag))
        for rank, item in enumerate(results, start=1):
            item.rank = rank
        return results

    def replace_pending_suggestions(self, session: Session, asset_id: Any, *, threshold: float | None = None) -> None:
        suggestions = self.suggest_for_asset(session, asset_id, threshold=threshold)
        session.execute(delete(TagSuggestion).where(TagSuggestion.asset_id == asset_id, TagSuggestion.status == "pending"))
        if suggestions:
            session.add_all(
                [
                    TagSuggestion(
                        asset_id=asset_id,
                        tag=item.tag,
                        tag_group=item.group,
                        confidence=item.score,
                        source_model=item.source_model,
                        rank=item.rank,
                        raw_score=item.raw_score,
                        threshold_used=item.threshold_used,
                        source_payload=item.source_payload,
                        status="pending",
                    )
                    for item in suggestions
                ]
            )


class ImageEnrichmentService:
    def __init__(self, clip_embedder: ClipEmbeddingService | None = None) -> None:
        self.settings = get_settings()
        self.clip_embedder = clip_embedder or ClipEmbeddingService()
        self.captioning = CaptioningService()
        self.ocr = OcrService()
        self.clip_vocab = ClipVocabularyTagger(self.clip_embedder)
        self.providers = {
            "wd_vit_v3": WdTaggerProvider(
                key="wd_vit_v3",
                label="WD ViT Tagger v3",
                repo_id=self.settings.wd_vit_model_id,
                source_model=self.settings.wd_vit_model_id,
                tag_file="selected_tags.csv",
            ),
            "deepghs_wd_embeddings": WdTaggerProvider(
                key="deepghs_wd_embeddings",
                label="DeepGHS WD Embeddings",
                repo_id=self.settings.deepghs_embedding_repo_id,
                subfolder=self.settings.deepghs_embedding_subfolder,
                source_model=f"{self.settings.deepghs_embedding_repo_id}/{self.settings.deepghs_embedding_subfolder}",
                tag_file="tags_info.csv",
                has_embeddings=True,
            ),
        }

    def provider_statuses(self) -> list[ProviderStatus]:
        runtime = get_ai_tagging_runtime_settings()
        if runtime.image_tagging_enabled:
            statuses = [self.providers[key].status() for key in ("wd_vit_v3", "deepghs_wd_embeddings")]
        else:
            statuses = [
                ProviderStatus(
                    key=provider.key,
                    label=provider.label,
                    status="disabled",
                    device="cpu",
                    source_model=provider.source_model,
                    warm=False,
                    detail=None,
                )
                for provider in (self.providers["wd_vit_v3"], self.providers["deepghs_wd_embeddings"])
            ]
        statuses.append(
            ProviderStatus(
                key="clip_vocab",
                label="CLIP Vocabulary",
                status="ready" if self.clip_embedder.is_loaded else ("cold" if runtime.clip_enabled else "disabled"),
                device=self.settings.clip_device,
                source_model=self.settings.clip_model_id,
                warm=self.clip_embedder.is_loaded,
                detail=None,
            )
        )
        return statuses

    def preload(self) -> list[ProviderStatus]:
        if get_ai_tagging_runtime_settings().image_tagging_enabled:
            for key in ("wd_vit_v3", "deepghs_wd_embeddings"):
                self.providers[key].preload()
        self.clip_embedder.warm()
        self.captioning.warm(local_only=False)
        return self.provider_statuses()

    def related_tags(self, tag: str, limit: int = 12) -> list[RelatedTag]:
        return self.providers["deepghs_wd_embeddings"].related_tags(tag, limit=limit)

    def _provider_order(self, provider_override: str | None, compare_mode: bool) -> list[str]:
        if provider_override and provider_override in self.providers:
            if compare_mode and provider_override != "deepghs_wd_embeddings":
                return [provider_override, "deepghs_wd_embeddings"]
            return [provider_override]
        primary = self.settings.image_tagging_primary_provider
        fallback = self.settings.image_tagging_fallback_provider
        if compare_mode:
            ordered = [key for key in (primary, fallback) if key in self.providers]
            deduped: list[str] = []
            for key in ordered:
                if key not in deduped:
                    deduped.append(key)
            return deduped
        if primary in self.providers:
            return [primary]
        if fallback in self.providers:
            return [fallback]
        return []

    def _generate_wd_suggestions(
        self,
        image_path: Path,
        *,
        existing_tags: set[str],
        provider_override: str | None,
        compare_mode: bool,
    ) -> tuple[list[TagSuggestionCandidate], bool]:
        if not get_ai_tagging_runtime_settings().image_tagging_enabled:
            return ([], False)
        provider_keys = self._provider_order(provider_override, compare_mode)
        wd_results: list[TagSuggestionCandidate] = []
        attempted = bool(provider_keys)
        fallback_candidates: list[TagSuggestionCandidate] = []
        seen_non_compare = set(existing_tags)

        for index, provider_key in enumerate(provider_keys):
            provider = self.providers[provider_key]
            candidates = provider.predict(image_path)
            if not candidates:
                continue
            if compare_mode:
                provider_seen: set[tuple[str, str]] = set()
                for candidate in candidates:
                    key = (candidate.tag, candidate.source_model)
                    if key in provider_seen or candidate.tag in existing_tags:
                        continue
                    provider_seen.add(key)
                    wd_results.append(candidate)
                continue

            unique_candidates: list[TagSuggestionCandidate] = []
            for candidate in candidates:
                if candidate.tag in seen_non_compare:
                    continue
                seen_non_compare.add(candidate.tag)
                unique_candidates.append(candidate)

            if index == 0 and unique_candidates:
                wd_results.extend(unique_candidates)
                break
            fallback_candidates.extend(unique_candidates)

        if not compare_mode and not wd_results and fallback_candidates:
            wd_results.extend(fallback_candidates)
        return wd_results, attempted

    def _clip_vocab_suggestions(
        self,
        session: Session,
        asset_id: Any,
        *,
        image_path: Path,
        existing_tags: set[str],
        wd_tags: set[str],
    ) -> list[TagSuggestionCandidate]:
        if not get_ai_tagging_runtime_settings().clip_enabled:
            return []
        clip_candidates = self.clip_vocab.suggest_for_asset(session, asset_id, image_path=image_path)
        results: list[TagSuggestionCandidate] = []
        for candidate in clip_candidates:
            if candidate.tag in existing_tags or candidate.tag in wd_tags:
                continue
            results.append(candidate)
        return results

    def _caption_metadata(self, image_path: Path) -> dict[str, Any]:
        caption, source = self.captioning.caption(image_path)
        return {
            "caption": caption,
            "caption_source": source,
        }

    def _ocr_metadata(self, image_path: Path) -> dict[str, Any]:
        text, confidence = self.ocr.extract(image_path)
        return {
            "ocr_text": text,
            "ocr_confidence": confidence,
        }

    def enrich_asset(
        self,
        session: Session,
        asset: Asset,
        image_path: Path,
        *,
        compare_mode: bool = False,
        provider_override: str | None = None,
    ) -> dict[str, int]:
        metadata_record = asset.metadata_record or session.get(AssetMetadata, asset.id)
        normalized = dict(metadata_record.normalized_json if metadata_record else {})
        normalized.update(self._caption_metadata(image_path))
        normalized.update(self._ocr_metadata(image_path))

        current_manual_tags: list[str] = []
        for existing_tag in session.execute(select(AssetTag.tag).where(AssetTag.asset_id == asset.id)).scalars().all():
            normalized_tag = canonicalize_tag(existing_tag)
            if normalized_tag:
                current_manual_tags.append(normalized_tag)
        existing_tags = set(current_manual_tags)

        wd_candidates, attempted = self._generate_wd_suggestions(
            image_path,
            existing_tags=existing_tags,
            provider_override=provider_override,
            compare_mode=compare_mode,
        )
        wd_tags = {candidate.tag for candidate in wd_candidates}
        clip_candidates = self._clip_vocab_suggestions(
            session,
            asset.id,
            image_path=image_path,
            existing_tags=existing_tags,
            wd_tags=wd_tags,
        )
        attempted = attempted or get_ai_tagging_runtime_settings().clip_enabled

        combined = wd_candidates + clip_candidates
        combined.sort(key=lambda item: (GROUP_ORDER.get(item.group, 99), -item.score, item.tag, item.source_model))
        if len(combined) > self.settings.tag_suggestion_max_pending:
            ratings = [item for item in combined if item.group == "rating"][:1]
            non_ratings = [item for item in combined if item.group != "rating"]
            remaining = max(0, self.settings.tag_suggestion_max_pending - len(ratings))
            combined = ratings + non_ratings[:remaining]
        for rank, item in enumerate(combined, start=1):
            item.rank = rank

        if metadata_record is not None:
            metadata_record.normalized_json = normalized
            metadata_record.extracted_at = datetime.now(tz=timezone.utc)
        else:
            metadata_record = AssetMetadata(
                asset_id=asset.id,
                raw_json={},
                normalized_json=normalized,
                extracted_at=datetime.now(tz=timezone.utc),
            )
            asset.metadata_record = metadata_record
            session.add(metadata_record)

        search_text = build_search_text(asset.filename, asset.relative_path, normalized, current_manual_tags)
        session.execute(
            insert(AssetSearch)
            .values(asset_id=asset.id, document=func.to_tsvector("simple", search_text))
            .on_conflict_do_update(
                index_elements=[AssetSearch.asset_id],
                set_={"document": func.to_tsvector("simple", search_text)},
            )
        )

        if attempted:
            session.execute(delete(TagSuggestion).where(TagSuggestion.asset_id == asset.id, TagSuggestion.status == "pending"))
            if combined:
                session.add_all(
                    [
                        TagSuggestion(
                            asset_id=asset.id,
                            tag=item.tag,
                            tag_group=item.group,
                            confidence=item.score,
                            source_model=item.source_model,
                            rank=item.rank,
                            raw_score=item.raw_score,
                            threshold_used=item.threshold_used,
                            source_payload=item.source_payload,
                            status="pending",
                        )
                        for item in combined
                    ]
                )

        return {
            "suggestion_count": len(combined),
            "updated_search": 1,
        }


_IMAGE_ENRICHMENT_SERVICE: ImageEnrichmentService | None = None


def get_image_enrichment_service() -> ImageEnrichmentService:
    global _IMAGE_ENRICHMENT_SERVICE
    if _IMAGE_ENRICHMENT_SERVICE is None:
        _IMAGE_ENRICHMENT_SERVICE = ImageEnrichmentService()
    return _IMAGE_ENRICHMENT_SERVICE
