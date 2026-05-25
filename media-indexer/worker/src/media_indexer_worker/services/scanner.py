from __future__ import annotations

import base64
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse
from uuid import UUID

import httpx
import numpy as np
from PIL import Image
from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm.attributes import flag_modified

from media_indexer_backend.core.config import get_settings
from media_indexer_backend.db.session import SessionLocal
from media_indexer_backend.models.enums import MediaType, ScanStatus, SourceStatus
from media_indexer_backend.models.tables import (
    Asset,
    AssetMetadata,
    AssetSearch,
    AssetSimilarity,
    AssetTag,
    CollectionAsset,
    FaceDetection,
    ScanJob,
    ScanJobError,
    Source,
)
from media_indexer_backend.platform.events import publish_event
from media_indexer_backend.platform.runtime import get_ai_tagging_runtime_settings, get_people_runtime_settings
from media_indexer_backend.services.audit import record_audit_event
from media_indexer_backend.services.image_enrichment import get_image_enrichment_service
from media_indexer_backend.services.image_service import ensure_cached_resized_image
from media_indexer_backend.services.metadata import (
    build_search_text,
    build_tags,
    compute_sha256,
    detect_media_type,
    guess_mime_type,
    normalize_metadata,
    parse_datetime,
    sanitize_json_value,
    should_reextract_metadata,
)
from media_indexer_backend.services.path_safety import validate_source_root
from media_indexer_backend.services.source_service import reconcile_source_statuses
from media_indexer_backend.services.webhook_service import dispatch_webhook_event
from media_indexer_worker.services.extractors import extract_exiftool, extract_ffprobe, extract_png_metadata_chunks
from media_indexer_worker.services.faces import FaceEnrichmentService
from media_indexer_worker.services.nsfw import NsfwDetectorService
from media_indexer_worker.services.previews import PreviewGenerator
from media_indexer_worker.services.similarity import SimilarityService


logger = logging.getLogger(__name__)

SCAN_MODES = {
    "basic",
    "metadata",
    "ai",
    "workflow",
    "preview",
    "similarity",
    "caption",
    "ocr",
    "tags",
    "safety_quality",
    "faces",
    "video_intel",
    "vision_llm",
    "sillytavern_card",
}
IMAGE_ONLY_MODES = {"ai", "similarity", "caption", "ocr", "tags", "safety_quality", "faces", "vision_llm", "sillytavern_card"}
METADATA_MODES = {
    "metadata",
    "workflow",
    "ai",
    "preview",
    "similarity",
    "caption",
    "ocr",
    "tags",
    "safety_quality",
    "faces",
    "video_intel",
    "vision_llm",
    "sillytavern_card",
}
TERMINAL_STATUSES = {ScanStatus.COMPLETED, ScanStatus.FAILED, ScanStatus.CANCELLED}
NSFW_SIGNAL_TAGS = {
    "after_sex",
    "anus",
    "areola",
    "bare_breasts",
    "bare_chest",
    "cleft_of_venus",
    "cum",
    "erect_nipples",
    "explicit",
    "fellatio",
    "genitals",
    "hentai",
    "naked",
    "nipples",
    "nsfw",
    "nude",
    "nudity",
    "penis",
    "porn",
    "pubic_hair",
    "pussy",
    "sex",
    "sexual",
    "vagina",
    "vulva",
}
NSFW_SIGNAL_PHRASES = {
    "bare breasts",
    "cleft of venus",
    "erect nipples",
    "genitals",
    "naked",
    "nipples",
    "nsfw",
    "nude",
    "nudity",
    "porn",
    "pubic hair",
    "sexual",
    "vulva",
}


SILLYTAVERN_CHUNK_KEYS = {"chara", "character", "ccv3"}
SILLYTAVERN_TEXT_FIELDS = (
    "name",
    "description",
    "personality",
    "scenario",
    "first_mes",
    "mes_example",
    "creator_notes",
    "system_prompt",
    "post_history_instructions",
)


def _decode_sillytavern_card_payload(value: Any) -> dict[str, Any] | None:
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace").strip()
    else:
        text = str(value or "").strip()
    if not text:
        return None
    candidates = [text]
    if "," in text and text.lower().startswith("data:"):
        candidates.append(text.split(",", 1)[1].strip())
    try:
        decoded = base64.b64decode(candidates[-1], validate=True).decode("utf-8", errors="replace")
        candidates.append(decoded.strip())
    except Exception:
        pass
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _normalize_sillytavern_card(card: dict[str, Any]) -> dict[str, Any] | None:
    data = card.get("data") if isinstance(card.get("data"), dict) else card
    name = str(data.get("name") or card.get("name") or "").strip()
    if not name:
        return None
    normalized_data: dict[str, Any] = {}
    for key in SILLYTAVERN_TEXT_FIELDS:
        value = data.get(key)
        if value is None and key == "first_mes":
            value = data.get("first_message")
        if value is None and key == "mes_example":
            value = data.get("example_dialogue")
        normalized_data[key] = str(value or "").strip()
    tags = data.get("tags", [])
    if isinstance(tags, str):
        tags = [part.strip() for part in tags.replace("\n", ",").split(",") if part.strip()]
    if not isinstance(tags, list):
        tags = []
    greetings = data.get("alternate_greetings", [])
    if not isinstance(greetings, list):
        greetings = []
    normalized_data.update(
        {
            "tags": [str(item).strip() for item in tags if str(item).strip()],
            "alternate_greetings": [str(item).strip() for item in greetings if str(item).strip()],
            "creator": str(data.get("creator") or "").strip(),
            "character_version": str(data.get("character_version") or "").strip(),
            "extensions": data.get("extensions") if isinstance(data.get("extensions"), dict) else {},
        }
    )
    return {
        "spec": str(card.get("spec") or "chara_card_v2"),
        "spec_version": str(card.get("spec_version") or "2.0"),
        "data": normalized_data,
        "raw": card,
    }


def _extract_sillytavern_card(exif: dict[str, Any]) -> dict[str, Any] | None:
    for key, value in exif.items():
        if str(key).strip().lower() not in SILLYTAVERN_CHUNK_KEYS:
            continue
        decoded = _decode_sillytavern_card_payload(value)
        if not decoded:
            continue
        normalized = _normalize_sillytavern_card(decoded)
        if normalized:
            return normalized
    return None


def _sillytavern_tag_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.strip().lower()).strip("_")


@dataclass(slots=True)
class ScanCandidate:
    source_id: UUID
    root: Path
    path: Path
    relative_path: str
    asset_id: UUID | None = None


@dataclass(slots=True)
class ScanPlan:
    job_id: UUID
    scan_mode: str
    target_type: str
    source_id: UUID | None
    source_ids: set[UUID]
    path_filter: str | None
    delete_missing: bool
    candidates: list[ScanCandidate]


class ScanWorker:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.previews = PreviewGenerator()
        self.similarity = SimilarityService()
        self.nsfw_detector = NsfwDetectorService()
        self.image_enrichment = get_image_enrichment_service()
        self.face_enrichment = FaceEnrichmentService()

    def run_forever(self) -> None:
        logger.info("worker loop started")
        while True:
            try:
                processed = self.run_once()
            except Exception as exc:  # noqa: BLE001
                logger.exception("worker loop iteration failed", extra={"error": str(exc)})
                processed = False
            if not processed:
                time.sleep(self.settings.worker_poll_interval_seconds)

    def run_once(self) -> bool:
        with SessionLocal() as session:
            job = session.execute(
                select(ScanJob)
                .where(ScanJob.status == ScanStatus.QUEUED)
                .order_by(ScanJob.created_at)
                .with_for_update(skip_locked=True)
            ).scalars().first()
            if not job:
                if reconcile_source_statuses(session):
                    session.commit()
                    return True
                return False

            now = datetime.now(tz=timezone.utc)
            job.status = ScanStatus.RUNNING
            job.started_at = now
            job.worker_heartbeat_at = now
            job.stage = "starting"
            job.message = "Preparing scan target..."
            if job.source_id:
                source = session.get(Source, job.source_id)
                if source is not None:
                    source.status = SourceStatus.SCANNING
            session.commit()
            job_id = job.id

        self.process_job(job_id)
        return True

    def process_job(self, job_id: UUID) -> None:
        try:
            plan = self._prepare_plan(job_id)
            if plan is None:
                return
            if plan.scan_mode == "basic":
                self._process_basic_plan(plan)
            else:
                self._process_enrichment_plan(plan)
        except Exception as exc:  # noqa: BLE001
            logger.exception("scan job failed", extra={"job_id": str(job_id), "error": str(exc)})
            self._fail_job(job_id, str(exc))

    def _prepare_plan(self, job_id: UUID) -> ScanPlan | None:
        with SessionLocal() as session:
            job = session.get(ScanJob, job_id)
            if job is None or job.status == ScanStatus.CANCELLED:
                return None
            scan_mode = str(job.scan_mode or "basic").lower()
            if scan_mode == "full_ai":
                scan_mode = "ai"
            if scan_mode not in SCAN_MODES:
                scan_mode = "basic"
            target_type = str(job.target_type or "source").lower()
            if target_type not in {"source", "collection", "assets"}:
                target_type = "source"

            if target_type == "source":
                if job.source_id is None:
                    raise RuntimeError("Source scan job is missing source_id.")
                source = session.get(Source, job.source_id)
                if source is None:
                    raise RuntimeError("Source no longer exists.")
                root = Path(validate_source_root(source.root_path)).resolve(strict=False)
                target_root = self._resolve_scan_target(root, job.path_filter)
                candidates = self._source_candidates(session, source, root, target_root, job.path_filter, scan_mode)
                source_ids = {source.id}
                delete_missing = job.path_filter is None
            else:
                candidates = self._asset_target_candidates(session, job, scan_mode)
                source_ids = {candidate.source_id for candidate in candidates}
                delete_missing = False

            job.scan_mode = scan_mode
            job.target_type = target_type
            job.total_count = len(candidates)
            job.progress = 0
            job.stage = "queued"
            job.worker_heartbeat_at = datetime.now(tz=timezone.utc)
            job.message = f"Prepared {len(candidates)} candidate(s) for {scan_mode} scan."
            record_audit_event(
                session,
                actor="worker",
                action="scan.started",
                resource_type="scan_job",
                resource_id=job.id,
                details={
                    "source_id": str(job.source_id) if job.source_id else None,
                    "target_type": target_type,
                    "candidate_count": len(candidates),
                    "scan_mode": scan_mode,
                },
            )
            dispatch_webhook_event(
                "scan.started",
                {"job_id": str(job.id), "source_id": str(job.source_id) if job.source_id else None, "target_type": target_type},
            )
            session.commit()

            return ScanPlan(
                job_id=job.id,
                scan_mode=scan_mode,
                target_type=target_type,
                source_id=job.source_id,
                source_ids=source_ids,
                path_filter=job.path_filter,
                delete_missing=delete_missing,
                candidates=candidates,
            )

    def _source_candidates(
        self,
        session,
        source: Source,
        root: Path,
        target_root: Path,
        path_filter: str | None,
        scan_mode: str,
    ) -> list[ScanCandidate]:
        if scan_mode == "ai":
            indexed_paths = self._discover_indexed_image_candidates(session, source, root, path_filter)
            if indexed_paths:
                return [ScanCandidate(source.id, root, path, path.relative_to(root).as_posix()) for path in indexed_paths]

        candidates: list[ScanCandidate] = []
        for path in self._discover_candidates(root, target_root):
            media_type = detect_media_type(path, guess_mime_type(path))
            if not self._mode_accepts_media(scan_mode, media_type):
                continue
            candidates.append(ScanCandidate(source.id, root, path, path.relative_to(root).as_posix()))
        return candidates

    def _asset_target_candidates(self, session, job: ScanJob, scan_mode: str) -> list[ScanCandidate]:
        asset_ids = [UUID(str(asset_id)) for asset_id in (job.asset_ids_json or [])]
        if job.target_type == "collection":
            collection_query = (
                select(Asset.id)
                .join(CollectionAsset, CollectionAsset.asset_id == Asset.id)
                .where(CollectionAsset.collection_id == job.collection_id)
                .order_by(Asset.relative_path)
            )
            asset_ids = list(session.execute(collection_query).scalars().all())
            job.asset_ids_json = [str(asset_id) for asset_id in asset_ids]
        if not asset_ids:
            return []

        rows = session.execute(
            select(Asset, Source)
            .join(Source, Source.id == Asset.source_id)
            .where(Asset.id.in_(asset_ids))
            .order_by(Asset.relative_path)
        ).all()
        candidates: list[ScanCandidate] = []
        for asset, source in rows:
            if not self._mode_accepts_media(scan_mode, asset.media_type):
                continue
            root = Path(validate_source_root(source.root_path)).resolve(strict=False)
            path = (root / Path(*asset.relative_path.split("/"))).resolve(strict=False)
            candidates.append(ScanCandidate(source.id, root, path, asset.relative_path, asset.id))
        return candidates

    def _mode_accepts_media(self, scan_mode: str, media_type: MediaType) -> bool:
        if scan_mode in IMAGE_ONLY_MODES:
            return media_type == MediaType.IMAGE
        if scan_mode == "video_intel":
            return media_type == MediaType.VIDEO
        return media_type != MediaType.UNKNOWN

    def _resolve_scan_target(self, root: Path, path_filter: str | None) -> Path:
        if not path_filter:
            return root
        target = (root / path_filter).resolve(strict=False)
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise RuntimeError("Scan path must stay inside the source root.") from exc
        if not target.exists():
            raise RuntimeError(f"Scan path does not exist: {path_filter}")
        return target

    def _discover_candidates(self, root: Path, target: Path) -> list[Path]:
        return [path for path, _mime_type, _media_type in self._iter_candidate_entries(root, target)]

    def _discover_indexed_image_candidates(self, session, source: Source, root: Path, path_filter: str | None) -> list[Path]:
        query = select(Asset.relative_path).where(
            Asset.source_id == source.id,
            Asset.media_type == MediaType.IMAGE,
        )
        if path_filter:
            normalized_filter = path_filter.replace("\\", "/").strip("/")
            if normalized_filter:
                query = query.where(
                    or_(
                        Asset.relative_path == normalized_filter,
                        Asset.relative_path.like(f"{normalized_filter}/%"),
                    )
                )
        paths: list[Path] = []
        for relative_path in session.execute(query.order_by(Asset.relative_path)).scalars():
            candidate = (root / Path(*relative_path.split("/"))).resolve(strict=False)
            try:
                candidate.relative_to(root)
            except ValueError:
                continue
            if candidate.exists() and candidate.is_file():
                paths.append(candidate)
        return paths

    def _iter_candidate_entries(self, root: Path, target: Path):
        if target.is_file():
            mime_type = guess_mime_type(target)
            media_type = detect_media_type(target, mime_type)
            if media_type != MediaType.UNKNOWN:
                yield target, mime_type, media_type
            return

        for path in target.rglob("*"):
            if not path.is_file():
                continue
            mime_type = guess_mime_type(path)
            media_type = detect_media_type(path, mime_type)
            if media_type == MediaType.UNKNOWN:
                continue
            yield path, mime_type, media_type

    def _process_basic_plan(self, plan: ScanPlan) -> None:
        batch_size = max(100, int(getattr(self.settings, "basic_scan_batch_size", 1000) or 1000))
        discovered_paths: set[str] = set()
        batch: list[dict[str, Any]] = []

        for index, candidate in enumerate(plan.candidates, start=1):
            if self._job_cancelled(plan.job_id):
                self._finish_cancelled(plan)
                return
            discovered_paths.add(candidate.relative_path)
            try:
                stat = candidate.path.stat()
                mime_type = guess_mime_type(candidate.path)
                media_type = detect_media_type(candidate.path, mime_type)
            except Exception as exc:  # noqa: BLE001
                self._record_file_error(plan.job_id, candidate, exc, stage="basic")
                self._update_progress(plan.job_id, index, len(plan.candidates), "basic", f"Basic scan skipped {candidate.relative_path}")
                continue

            batch.append(
                {
                    "source_id": candidate.source_id,
                    "relative_path": candidate.relative_path,
                    "filename": candidate.path.name,
                    "extension": candidate.path.suffix.lower(),
                    "media_type": media_type,
                    "mime_type": mime_type,
                    "size_bytes": stat.st_size,
                    "checksum": f"stat:{stat.st_size}:{stat.st_mtime_ns}",
                    "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                    "created_at": datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc),
                }
            )
            if len(batch) >= batch_size:
                if not self._flush_basic_batch(plan.job_id, batch, index, len(plan.candidates)):
                    self._finish_cancelled(plan)
                    return
                batch.clear()

        if batch and not self._flush_basic_batch(plan.job_id, batch, len(plan.candidates), len(plan.candidates)):
            self._finish_cancelled(plan)
            return

        deleted_count = 0
        if plan.delete_missing and plan.source_id:
            self._update_job(plan.job_id, stage="reconcile", message="Reconciling deleted files...")
            deleted_count = self._delete_missing_assets_for_source(plan.source_id, discovered_paths)
        self._complete_job(plan, deleted_count=deleted_count)

    def _flush_basic_batch(self, job_id: UUID, batch: list[dict[str, Any]], scanned_total: int, total: int) -> bool:
        with SessionLocal() as session:
            job = session.get(ScanJob, job_id)
            if job is None:
                return False
            if job.status == ScanStatus.CANCELLED:
                session.commit()
                return False

            relative_by_source: dict[UUID, list[str]] = {}
            for item in batch:
                relative_by_source.setdefault(item["source_id"], []).append(item["relative_path"])
            existing_assets: dict[tuple[UUID, str], Asset] = {}
            for source_id, relative_paths in relative_by_source.items():
                for asset in session.execute(
                    select(Asset).where(Asset.source_id == source_id, Asset.relative_path.in_(relative_paths))
                ).scalars():
                    existing_assets[(asset.source_id, asset.relative_path)] = asset

            indexed_at = datetime.now(tz=timezone.utc)
            for item in batch:
                existing = existing_assets.get((item["source_id"], item["relative_path"]))
                content_changed = not (
                    existing
                    and existing.size_bytes == item["size_bytes"]
                    and existing.modified_at == item["modified_at"]
                )
                if existing and not content_changed:
                    continue
                if existing:
                    existing.filename = item["filename"]
                    existing.extension = item["extension"]
                    existing.media_type = item["media_type"]
                    existing.mime_type = item["mime_type"]
                    existing.size_bytes = item["size_bytes"]
                    existing.checksum = item["checksum"]
                    existing.modified_at = item["modified_at"]
                    existing.created_at = existing.created_at or item["created_at"]
                    existing.indexed_at = indexed_at
                    job.updated_count += 1
                else:
                    session.add(
                        Asset(
                            source_id=item["source_id"],
                            relative_path=item["relative_path"],
                            filename=item["filename"],
                            extension=item["extension"],
                            media_type=item["media_type"],
                            mime_type=item["mime_type"],
                            size_bytes=item["size_bytes"],
                            checksum=item["checksum"],
                            modified_at=item["modified_at"],
                            created_at=item["created_at"],
                            indexed_at=indexed_at,
                        )
                    )
                    job.new_count += 1

            job.scanned_count = scanned_total
            job.progress = int((scanned_total / total) * 100) if total else 100
            job.total_count = total
            job.stage = "basic"
            job.worker_heartbeat_at = datetime.now(tz=timezone.utc)
            job.message = (
                f"Basic scan indexed {scanned_total}/{total} files "
                f"(new={job.new_count}, updated={job.updated_count}, errors={job.error_count})"
            )
            session.commit()
            return True

    def _process_enrichment_plan(self, plan: ScanPlan) -> None:
        discovered_paths: set[str] = set()
        total = len(plan.candidates)
        for index, candidate in enumerate(plan.candidates, start=1):
            if self._job_cancelled(plan.job_id):
                self._finish_cancelled(plan)
                return
            discovered_paths.add(candidate.relative_path)
            self._update_progress(
                plan.job_id,
                index - 1,
                total,
                plan.scan_mode,
                f"{plan.scan_mode.title()} scan {index}/{total}: {candidate.relative_path}",
            )
            try:
                self._process_candidate(plan.job_id, candidate, plan.scan_mode)
            except Exception as exc:  # noqa: BLE001
                logger.exception("failed to process candidate", extra={"path": str(candidate.path), "error": str(exc)})
                self._record_file_error(plan.job_id, candidate, exc, stage=plan.scan_mode)
            finally:
                self._update_progress(plan.job_id, index, total, plan.scan_mode, f"Processed {index}/{total}: {candidate.relative_path}")

        deleted_count = 0
        if plan.delete_missing and plan.source_id:
            self._update_job(plan.job_id, stage="reconcile", message="Reconciling deleted files...")
            deleted_count = self._delete_missing_assets_for_source(plan.source_id, discovered_paths)
        self._complete_job(plan, deleted_count=deleted_count)

    def _process_candidate(self, job_id: UUID, candidate: ScanCandidate, scan_mode: str) -> None:
        with SessionLocal() as session:
            job = session.get(ScanJob, job_id)
            if job is None or job.status == ScanStatus.CANCELLED:
                return
            source = session.get(Source, candidate.source_id)
            if source is None:
                raise RuntimeError("Candidate source no longer exists.")
            self._process_candidate_in_session(session, job, source, candidate.path, candidate.relative_path, scan_mode)

    def _process_candidate_in_session(
        self,
        session,
        job: ScanJob,
        source: Source,
        path: Path,
        relative_path: str,
        scan_mode: str,
    ) -> None:
        stat = path.stat()
        mime_type = guess_mime_type(path)
        media_type = detect_media_type(path, mime_type)
        if not self._mode_accepts_media(scan_mode, media_type):
            return

        modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        filesystem_created_at = datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc)
        existing = session.execute(
            select(Asset).where(Asset.source_id == source.id, Asset.relative_path == relative_path)
        ).scalar_one_or_none()
        existing_metadata_record = session.get(AssetMetadata, existing.id) if existing else None
        content_changed = not (
            existing
            and existing.size_bytes == stat.st_size
            and existing.modified_at == modified_at
        )
        needs_metadata_refresh = should_reextract_metadata(
            existing_size_bytes=existing.size_bytes if existing else None,
            existing_modified_at=existing.modified_at if existing else None,
            existing_normalized_json=existing_metadata_record.normalized_json if existing_metadata_record else None,
            file_size_bytes=stat.st_size,
            file_modified_at=modified_at,
        )

        if scan_mode == "basic":
            self._upsert_basic_asset(session, job, source, path, relative_path, stat, mime_type, media_type, modified_at, filesystem_created_at, existing, content_changed)
            session.commit()
            return

        if scan_mode in {"metadata", "workflow"} and existing and not needs_metadata_refresh:
            return

        job.stage = "metadata" if scan_mode in METADATA_MODES else scan_mode
        job.message = f"Extracting metadata: {relative_path}"
        job.worker_heartbeat_at = datetime.now(tz=timezone.utc)
        session.commit()

        raw_json: dict[str, Any]
        if existing_metadata_record and not needs_metadata_refresh and scan_mode != "sillytavern_card":
            checksum = existing.checksum if existing and existing.checksum and not existing.checksum.startswith("stat:") else compute_sha256(path)
            normalized = dict(existing_metadata_record.normalized_json or {})
            raw_json = existing_metadata_record.raw_json if isinstance(existing_metadata_record.raw_json, dict) else {}
            exif = raw_json.get("exiftool", {}) if isinstance(raw_json.get("exiftool"), dict) else {}
            ffprobe = raw_json.get("ffprobe", {}) if isinstance(raw_json.get("ffprobe"), dict) else {}
            created_at = existing.created_at if existing and existing.created_at else filesystem_created_at
        else:
            checksum = (
                existing.checksum
                if existing and not content_changed and existing.checksum and not existing.checksum.startswith("stat:")
                else compute_sha256(path)
            )
            exif = extract_exiftool(path)
            if path.suffix.lower() == ".png":
                for key, value in extract_png_metadata_chunks(path).items():
                    exif.setdefault(key, value)
            ffprobe = extract_ffprobe(path) if media_type == MediaType.VIDEO else {}
            exif = sanitize_json_value(exif)
            ffprobe = sanitize_json_value(ffprobe)
            normalized = sanitize_json_value(normalize_metadata(media_type=media_type, exif=exif, ffprobe=ffprobe))
            raw_json = sanitize_json_value({"exiftool": exif, "ffprobe": ffprobe})
            created_at = parse_datetime(normalized.get("created_at")) or filesystem_created_at

        asset = self._upsert_rich_asset(
            session,
            job,
            source,
            path,
            relative_path,
            stat,
            mime_type,
            media_type,
            checksum,
            modified_at,
            created_at,
            existing,
            content_changed,
        )
        session.flush()

        metadata_record = session.get(AssetMetadata, asset.id)
        if metadata_record:
            metadata_record.raw_json = raw_json
            metadata_record.normalized_json = normalized
            metadata_record.extracted_at = datetime.now(tz=timezone.utc)
        else:
            metadata_record = AssetMetadata(
                asset_id=asset.id,
                raw_json=raw_json,
                normalized_json=normalized,
                extracted_at=datetime.now(tz=timezone.utc),
            )
            asset.metadata_record = metadata_record
            session.add(metadata_record)

        old_tags = list(session.execute(select(AssetTag.tag).where(AssetTag.asset_id == asset.id)).scalars().all())
        session.execute(delete(AssetTag).where(AssetTag.asset_id == asset.id))

        sillytavern_card = None
        if scan_mode in {"sillytavern_card", "ai"} and media_type == MediaType.IMAGE:
            sillytavern_card = _extract_sillytavern_card(exif)
            normalized = dict(normalized)
            if sillytavern_card:
                card_data = sillytavern_card.get("data", {})
                normalized.update(
                    sanitize_json_value(
                        {
                            "sillytavern_card_detected": True,
                            "sillytavern_card_scanned_at": datetime.now(tz=timezone.utc).isoformat(),
                            "sillytavern_card_name": card_data.get("name"),
                            "sillytavern_card_tags": card_data.get("tags", []),
                            "sillytavern_card_spec": sillytavern_card.get("spec"),
                            "sillytavern_card": sillytavern_card,
                        }
                    )
                )
            elif scan_mode == "sillytavern_card":
                normalized.update(
                    {
                        "sillytavern_card_detected": False,
                        "sillytavern_card_scanned_at": datetime.now(tz=timezone.utc).isoformat(),
                    }
                )
            metadata_record.normalized_json = sanitize_json_value(dict(normalized))
            flag_modified(metadata_record, "normalized_json")

        tags = build_tags(normalized, exif)
        if sillytavern_card:
            if "sillytavern_card" not in tags:
                tags.append("sillytavern_card")
            card_name = str((sillytavern_card.get("data") or {}).get("name") or "")
            name_tag = _sillytavern_tag_slug(card_name)
            if name_tag and f"card_{name_tag}" not in tags:
                tags.append(f"card_{name_tag}")

        if scan_mode in {"ai", "safety_quality"} and media_type == MediaType.IMAGE:
            normalized.update(self._quality_metadata(path, normalized))
            job.stage = "safety_quality"
            job.message = f"Checking safety and quality: {relative_path}"
            job.worker_heartbeat_at = datetime.now(tz=timezone.utc)
            session.commit()
            nsfw_result = self.nsfw_detector.classify(path)
            prompt_signal = self._metadata_nsfw_signal(normalized, tags)
            model_detected = bool(nsfw_result.get("detected"))
            nsfw_detected = model_detected or prompt_signal or "nsfw" in old_tags
            normalized.update(
                sanitize_json_value(
                    {
                        "safety_quality_scanned_at": datetime.now(tz=timezone.utc).isoformat(),
                        "nsfw_detected": nsfw_detected,
                        "nsfw_model_detected": model_detected,
                        "nsfw_prompt_flagged": prompt_signal,
                        "nsfw_detector_available": bool(nsfw_result.get("available")),
                        "nsfw_score": nsfw_result.get("score"),
                        "nsfw_label": nsfw_result.get("label"),
                        "nsfw_model": nsfw_result.get("model"),
                        "nsfw_error": nsfw_result.get("error"),
                    }
                )
            )
            if nsfw_detected and "nsfw" not in tags:
                tags.append("nsfw")
            metadata_record.normalized_json = sanitize_json_value(dict(normalized))
            flag_modified(metadata_record, "normalized_json")

        if tags:
            session.add_all([AssetTag(asset_id=asset.id, tag=tag) for tag in tags])

        search_text = build_search_text(asset.filename, asset.relative_path, normalized, tags)
        session.execute(
            insert(AssetSearch)
            .values(asset_id=asset.id, document=func.to_tsvector("simple", search_text))
            .on_conflict_do_update(
                index_elements=[AssetSearch.asset_id],
                set_={"document": func.to_tsvector("simple", search_text)},
            )
        )
        session.flush()

        if scan_mode in {"ai", "preview", "video_intel"}:
            self._refresh_preview(session, job, asset, media_type, path, normalized, relative_path, content_changed)

        if scan_mode in {"ai", "similarity"} and media_type == MediaType.IMAGE:
            self._refresh_similarity(session, job, asset, path, relative_path, content_changed)
        elif media_type == MediaType.IMAGE:
            self._refresh_tag_links(session, asset.id, relative_path)

        if scan_mode in {"ai", "caption", "ocr", "tags"} and media_type == MediaType.IMAGE:
            job.stage = "enrichment"
            job.message = f"Enriching image: {relative_path}"
            job.worker_heartbeat_at = datetime.now(tz=timezone.utc)
            session.commit()
            self.image_enrichment.enrich_asset(session, asset, path)

        if scan_mode in {"ai", "faces"} and media_type == MediaType.IMAGE:
            self._refresh_faces(session, job, asset, path, relative_path, content_changed, existing is None)

        if scan_mode == "vision_llm" and media_type == MediaType.IMAGE:
            self._refresh_vision_llm(session, job, asset, relative_path)

        dispatch_webhook_event(
            "asset.updated" if existing else "asset.indexed",
            {"asset_id": str(asset.id), "source_id": str(source.id), "filename": asset.filename},
        )
        session.commit()

    def _upsert_basic_asset(
        self,
        session,
        job: ScanJob,
        source: Source,
        path: Path,
        relative_path: str,
        stat,
        mime_type: str,
        media_type: MediaType,
        modified_at: datetime,
        filesystem_created_at: datetime,
        existing: Asset | None,
        content_changed: bool,
    ) -> Asset | None:
        if existing and not content_changed:
            return existing
        fast_checksum = existing.checksum if existing and not content_changed and existing.checksum else f"stat:{stat.st_size}:{stat.st_mtime_ns}"
        created_at = existing.created_at if existing and existing.created_at else filesystem_created_at
        if existing:
            asset = existing
            asset.filename = path.name
            asset.extension = path.suffix.lower()
            asset.media_type = media_type
            asset.mime_type = mime_type
            asset.size_bytes = stat.st_size
            asset.checksum = fast_checksum
            asset.modified_at = modified_at
            asset.created_at = created_at
            asset.indexed_at = datetime.now(tz=timezone.utc)
            job.updated_count += 1
        else:
            asset = Asset(
                source_id=source.id,
                relative_path=relative_path,
                filename=path.name,
                extension=path.suffix.lower(),
                media_type=media_type,
                mime_type=mime_type,
                size_bytes=stat.st_size,
                checksum=fast_checksum,
                modified_at=modified_at,
                created_at=created_at,
                indexed_at=datetime.now(tz=timezone.utc),
            )
            session.add(asset)
            job.new_count += 1
        dispatch_webhook_event(
            "asset.updated" if existing else "asset.indexed",
            {"asset_id": str(asset.id), "source_id": str(source.id), "filename": asset.filename},
        )
        return asset

    def _upsert_rich_asset(
        self,
        session,
        job: ScanJob,
        source: Source,
        path: Path,
        relative_path: str,
        stat,
        mime_type: str,
        media_type: MediaType,
        checksum: str,
        modified_at: datetime,
        created_at: datetime,
        existing: Asset | None,
        content_changed: bool,
    ) -> Asset:
        if existing:
            asset = existing
            asset.filename = path.name
            asset.extension = path.suffix.lower()
            asset.media_type = media_type
            asset.mime_type = mime_type
            asset.size_bytes = stat.st_size
            asset.checksum = checksum
            asset.modified_at = modified_at
            asset.created_at = created_at
            asset.indexed_at = datetime.now(tz=timezone.utc)
            if content_changed:
                job.updated_count += 1
        else:
            asset = Asset(
                source_id=source.id,
                relative_path=relative_path,
                filename=path.name,
                extension=path.suffix.lower(),
                media_type=media_type,
                mime_type=mime_type,
                size_bytes=stat.st_size,
                checksum=checksum,
                modified_at=modified_at,
                created_at=created_at,
                indexed_at=datetime.now(tz=timezone.utc),
            )
            session.add(asset)
            job.new_count += 1
        return asset

    def _refresh_preview(
        self,
        session,
        job: ScanJob,
        asset: Asset,
        media_type: MediaType,
        path: Path,
        normalized: dict[str, Any],
        relative_path: str,
        content_changed: bool,
    ) -> None:
        preview_root = self.settings.preview_root_path
        preview_exists = bool(asset.preview_path and (preview_root / asset.preview_path).exists())
        if not (content_changed or not preview_exists or (media_type == MediaType.IMAGE and not asset.blur_hash) or media_type == MediaType.VIDEO):
            return
        job.stage = "preview"
        job.message = f"Generating preview: {relative_path}"
        job.worker_heartbeat_at = datetime.now(tz=timezone.utc)
        session.commit()
        video_timestamp = None
        if media_type == MediaType.VIDEO:
            duration_seconds = normalized.get("duration_seconds")
            if isinstance(duration_seconds, (int, float)) and duration_seconds > 0:
                video_timestamp = float(duration_seconds) * 0.1
        asset.preview_path, asset.blur_hash = self.previews.generate(asset.id, media_type, path, video_timestamp_seconds=video_timestamp)
        if media_type == MediaType.VIDEO:
            waveform_path, keyframes = self.previews.generate_video_artifacts(
                asset.id,
                path,
                duration_seconds=normalized.get("duration_seconds") if isinstance(normalized.get("duration_seconds"), (int, float)) else None,
            )
            asset.waveform_preview_path = waveform_path
            asset.video_keyframes = keyframes or None

    def _refresh_similarity(self, session, job: ScanJob, asset: Asset, path: Path, relative_path: str, content_changed: bool) -> None:
        similarity_record = session.get(AssetSimilarity, asset.id)
        ai_runtime = get_ai_tagging_runtime_settings()
        needs_similarity_refresh = (
            content_changed
            or similarity_record is None
            or similarity_record.phash is None
            or (ai_runtime.clip_enabled and similarity_record.embedding is None)
        )
        if needs_similarity_refresh:
            job.stage = "similarity"
            job.message = f"Computing similarity: {relative_path}"
            job.worker_heartbeat_at = datetime.now(tz=timezone.utc)
            session.commit()
            self.similarity.refresh(session, asset.id, path)
        else:
            self._refresh_tag_links(session, asset.id, relative_path)

    def _refresh_faces(self, session, job: ScanJob, asset: Asset, path: Path, relative_path: str, content_changed: bool, is_new: bool) -> None:
        people_runtime = get_people_runtime_settings()
        if not people_runtime.face_detection_enabled:
            return
        existing_face_count = session.execute(
            select(func.count(FaceDetection.id)).where(FaceDetection.asset_id == asset.id)
        ).scalar_one()
        if not (content_changed or is_new or existing_face_count == 0):
            return
        job.stage = "faces"
        job.message = f"Detecting faces: {relative_path}"
        job.worker_heartbeat_at = datetime.now(tz=timezone.utc)
        session.commit()
        self.face_enrichment.refresh_asset_faces(session, asset, path)

    def _quality_metadata(self, path: Path, normalized: dict[str, Any]) -> dict[str, Any]:
        warnings: list[str] = []
        payload: dict[str, Any] = {}
        try:
            with Image.open(path) as image:
                width, height = image.size
                payload["quality_width"] = width
                payload["quality_height"] = height
                if min(width, height) < 512:
                    warnings.append("low_resolution")
                if max(width, height) / max(1, min(width, height)) > 3.0:
                    warnings.append("extreme_aspect_ratio")
                gray = image.convert("L")
                gray.thumbnail((512, 512))
                values = np.asarray(gray, dtype=np.float32)
                if values.size:
                    dx = np.diff(values, axis=1)
                    dy = np.diff(values, axis=0)
                    sharpness = float(dx.var() + dy.var())
                    payload["quality_sharpness_score"] = round(sharpness, 4)
                    if sharpness < 15:
                        warnings.append("possibly_blurry")
        except Exception as exc:  # noqa: BLE001
            warnings.append("unreadable_image")
            payload["quality_error"] = str(exc)
        payload["quality_warnings"] = sorted(set([*normalized.get("quality_warnings", []), *warnings])) if isinstance(normalized.get("quality_warnings"), list) else sorted(set(warnings))
        payload["quality_scanned_at"] = datetime.now(tz=timezone.utc).isoformat()
        return sanitize_json_value(payload)

    def _metadata_nsfw_signal(self, normalized: dict[str, Any], tags: list[str]) -> bool:
        normalized_tags = {str(tag).strip().lower().replace(" ", "_") for tag in tags if str(tag).strip()}
        if normalized_tags & NSFW_SIGNAL_TAGS:
            return True
        prompt_parts = [
            normalized.get("processed_prompt"),
            normalized.get("prompt"),
            normalized.get("raw_prompt"),
            normalized.get("caption"),
        ]
        prompt_text = " ".join(value for value in prompt_parts if isinstance(value, str)).lower().replace("_", " ")
        return any(phrase in prompt_text for phrase in NSFW_SIGNAL_PHRASES)

    def _refresh_tag_links(self, session, asset_id: UUID, relative_path: str) -> None:
        try:
            self.similarity.refresh_tag_links(session, asset_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "tag similarity refresh failed",
                extra={"asset_id": str(asset_id), "relative_path": relative_path, "error": str(exc)},
                exc_info=True,
            )

    def _refresh_vision_llm(self, session, job: ScanJob, asset: Asset, relative_path: str) -> None:
        job.stage = "vision_llm"
        job.message = f"Asking Vision LLM: {relative_path}"
        job.worker_heartbeat_at = datetime.now(tz=timezone.utc)
        session.commit()
        settings = self.settings
        base_url = self._normalize_openai_base_url(settings.vision_llm_endpoint)
        image_path = ensure_cached_resized_image(asset, asset.source, width=1536, height=1536, quality=82, fmt="jpeg")
        image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
        body = {
            "model": settings.vision_llm_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Analyze this image for a media library. Return concise, useful details for search and curation: "
                                "visible subjects, scene, style, mood, notable objects, quality issues, and any text you can read. "
                                "If it appears to be AI generated, mention generation clues. Keep the answer under 180 words."
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    ],
                }
            ],
            "temperature": 0.2,
            "max_tokens": 320,
        }
        with httpx.Client(timeout=settings.vision_llm_timeout_seconds) as client:
            response = client.post(f"{base_url}/chat/completions", json=body)
            response.raise_for_status()
            payload = response.json()
        analysis = self._extract_chat_text(payload)
        if not analysis:
            raise RuntimeError("Vision LLM did not return readable text.")
        metadata_record = asset.metadata_record or session.get(AssetMetadata, asset.id)
        normalized = dict(metadata_record.normalized_json if metadata_record else {})
        normalized.update(
            sanitize_json_value(
                {
                    "vision_llm_analysis": analysis,
                    "vision_llm_source": f"koboldcpp:{settings.vision_llm_model}",
                    "vision_llm_endpoint": base_url,
                    "vision_llm_updated_at": datetime.now(tz=timezone.utc).isoformat(),
                }
            )
        )
        if metadata_record is None:
            metadata_record = AssetMetadata(asset_id=asset.id, raw_json={}, normalized_json=normalized, extracted_at=datetime.now(tz=timezone.utc))
            asset.metadata_record = metadata_record
            session.add(metadata_record)
        else:
            metadata_record.normalized_json = normalized
            metadata_record.extracted_at = datetime.now(tz=timezone.utc)
        search_text = build_search_text(asset.filename, asset.relative_path, normalized, [tag.tag for tag in asset.tags])
        session.execute(
            insert(AssetSearch)
            .values(asset_id=asset.id, document=func.to_tsvector("simple", search_text))
            .on_conflict_do_update(
                index_elements=[AssetSearch.asset_id],
                set_={"document": func.to_tsvector("simple", search_text)},
            )
        )

    def _normalize_openai_base_url(self, endpoint: str) -> str:
        parsed = urlparse((endpoint or "").strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RuntimeError("Vision LLM endpoint must be an http(s) URL.")
        hostname = (parsed.hostname or "").lower()
        netloc = parsed.netloc
        if Path("/.dockerenv").exists() and hostname in {"127.0.0.1", "localhost"}:
            netloc = parsed.netloc.replace(parsed.hostname or hostname, "host.docker.internal", 1)
        return urlunparse((parsed.scheme, netloc, parsed.path.rstrip("/"), "", "", "")).rstrip("/")

    def _extract_chat_text(self, payload: dict[str, Any]) -> str | None:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return None
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message") if isinstance(first, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            return content.strip() or None
        if isinstance(content, list):
            parts = [part.get("text") for part in content if isinstance(part, dict) and isinstance(part.get("text"), str)]
            text = "\n".join(part.strip() for part in parts if part.strip())
            return text or None
        return None

    def _job_cancelled(self, job_id: UUID) -> bool:
        with SessionLocal() as session:
            job = session.get(ScanJob, job_id)
            return job is None or job.status == ScanStatus.CANCELLED

    def _update_job(self, job_id: UUID, **values: Any) -> None:
        with SessionLocal() as session:
            job = session.get(ScanJob, job_id)
            if job is None or job.status in TERMINAL_STATUSES:
                return
            for key, value in values.items():
                setattr(job, key, value)
            job.worker_heartbeat_at = datetime.now(tz=timezone.utc)
            session.commit()

    def _update_progress(self, job_id: UUID, scanned: int, total: int, stage: str, message: str) -> None:
        progress = int((scanned / total) * 100) if total else 100
        self._update_job(
            job_id,
            scanned_count=scanned,
            total_count=total,
            progress=max(0, min(99 if scanned < total else 100, progress)),
            stage=stage,
            message=message,
        )

    def _record_file_error(self, job_id: UUID, candidate: ScanCandidate, exc: Exception, *, stage: str) -> None:
        with SessionLocal() as session:
            job = session.get(ScanJob, job_id)
            if job is None:
                return
            text = str(exc)
            job.error_count += 1
            job.worker_heartbeat_at = datetime.now(tz=timezone.utc)
            job.stage = stage
            job.message = f"{stage} error on {candidate.relative_path}: {text[:180]}"
            error_details = list(job.error_details or [])
            error_details.append({"path": candidate.relative_path, "error": text, "stage": stage, "at": datetime.now(tz=timezone.utc).isoformat()})
            job.error_details = error_details[-200:]
            session.add(
                ScanJobError(
                    job_id=job.id,
                    source_id=candidate.source_id,
                    asset_id=candidate.asset_id,
                    relative_path=candidate.relative_path,
                    stage=stage,
                    error=text,
                    created_at=datetime.now(tz=timezone.utc),
                )
            )
            session.commit()

    def _finish_cancelled(self, plan: ScanPlan) -> None:
        with SessionLocal() as session:
            job = session.get(ScanJob, plan.job_id)
            if job is not None:
                job.status = ScanStatus.CANCELLED
                job.stage = "cancelled"
                job.finished_at = job.finished_at or datetime.now(tz=timezone.utc)
                job.worker_heartbeat_at = datetime.now(tz=timezone.utc)
                job.message = "Scan cancelled."
            for source_id in plan.source_ids:
                source = session.get(Source, source_id)
                if source is not None and source.status == SourceStatus.SCANNING:
                    source.status = SourceStatus.READY
            session.commit()

    def _complete_job(self, plan: ScanPlan, *, deleted_count: int = 0) -> None:
        with SessionLocal() as session:
            job = session.get(ScanJob, plan.job_id)
            if job is None:
                return
            if job.status == ScanStatus.CANCELLED:
                session.commit()
                self._finish_cancelled(plan)
                return
            job.deleted_count += deleted_count
            job.status = ScanStatus.COMPLETED
            job.progress = 100
            job.total_count = len(plan.candidates)
            job.scanned_count = len(plan.candidates)
            job.stage = "completed"
            job.finished_at = datetime.now(tz=timezone.utc)
            job.worker_heartbeat_at = datetime.now(tz=timezone.utc)
            job.message = (
                f"{plan.scan_mode.title()} scan complete. scanned={job.scanned_count} new={job.new_count} "
                f"updated={job.updated_count} deleted={job.deleted_count} errors={job.error_count}"
            )
            for source_id in plan.source_ids:
                source = session.get(Source, source_id)
                if source is not None:
                    source.status = SourceStatus.READY
                    source.last_scan_at = datetime.now(tz=timezone.utc)
            if plan.source_id:
                publish_event(session, "scan.completed", {"source_id": str(plan.source_id), "job_id": str(job.id)})
            record_audit_event(
                session,
                actor="worker",
                action="scan.completed",
                resource_type="scan_job",
                resource_id=job.id,
                details={
                    "source_id": str(plan.source_id) if plan.source_id else None,
                    "target_type": plan.target_type,
                    "new_count": job.new_count,
                    "updated_count": job.updated_count,
                    "deleted_count": job.deleted_count,
                    "error_count": job.error_count,
                },
            )
            dispatch_webhook_event(
                "scan.completed",
                {
                    "job_id": str(job.id),
                    "source_id": str(plan.source_id) if plan.source_id else None,
                    "target_type": plan.target_type,
                    "new_count": job.new_count,
                    "updated_count": job.updated_count,
                    "deleted_count": job.deleted_count,
                    "error_count": job.error_count,
                },
            )
            session.commit()

    def _fail_job(self, job_id: UUID, error: str) -> None:
        with SessionLocal() as session:
            job = session.get(ScanJob, job_id)
            if job is None:
                return
            job.status = ScanStatus.FAILED
            job.stage = "failed"
            job.message = error
            job.finished_at = datetime.now(tz=timezone.utc)
            job.worker_heartbeat_at = datetime.now(tz=timezone.utc)
            if job.source_id:
                source = session.get(Source, job.source_id)
                if source is not None:
                    source.status = SourceStatus.ERROR
            record_audit_event(
                session,
                actor="worker",
                action="scan.failed",
                resource_type="scan_job",
                resource_id=job.id,
                details={"error": error, "target_type": job.target_type},
            )
            dispatch_webhook_event(
                "scan.failed",
                {"job_id": str(job.id), "source_id": str(job.source_id) if job.source_id else None, "error": error},
            )
            session.commit()

    def _delete_missing_assets_for_source(self, source_id: UUID, discovered_paths: set[str]) -> int:
        deleted_count = 0
        with SessionLocal() as session:
            assets = session.execute(select(Asset).where(Asset.source_id == source_id)).scalars()
            for asset in assets:
                if asset.relative_path in discovered_paths:
                    continue
                self.previews.cleanup(asset.id, asset.preview_path)
                self.face_enrichment.delete_asset_faces(session, asset.id)
                session.delete(asset)
                deleted_count += 1
                if deleted_count % 1000 == 0:
                    session.commit()
            session.commit()
        return deleted_count
