from __future__ import annotations

from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from media_indexer_backend.models.enums import ScanStatus, SourceStatus
from media_indexer_backend.models.tables import Asset, Collection, CollectionAsset, ScanJob, Source
from media_indexer_backend.schemas.scan_job import ScanJobCreate
from media_indexer_backend.services.source_service import get_source_or_404, reconcile_source_statuses


VALID_SCAN_MODES = {
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
TERMINAL_STATUSES = {ScanStatus.COMPLETED, ScanStatus.FAILED, ScanStatus.CANCELLED}
ACTIVE_STATUSES = {ScanStatus.QUEUED, ScanStatus.RUNNING}


def _clean_path_filter(path_filter: str | None) -> str | None:
    cleaned = str(path_filter or "").replace("\\", "/").strip().strip("/")
    if not cleaned:
        return None
    if cleaned.startswith("../") or "/../" in f"/{cleaned}/":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Scan path must stay inside the source root.")
    return cleaned


def normalize_scan_mode(scan_mode: str | None) -> str:
    normalized_mode = str(scan_mode or "basic").strip().lower()
    if normalized_mode == "full_ai":
        normalized_mode = "ai"
    if normalized_mode not in VALID_SCAN_MODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"scan_mode must be one of: {', '.join(sorted(VALID_SCAN_MODES))}.",
        )
    return normalized_mode


def queue_scan(session: Session, source_id, *, scan_mode: str = "basic", path_filter: str | None = None) -> ScanJob:
    return queue_source_scan(session, source_id, scan_mode=scan_mode, path_filter=path_filter)


def queue_source_scan(session: Session, source_id, *, scan_mode: str = "basic", path_filter: str | None = None) -> ScanJob:
    reconcile_source_statuses(session)
    source = get_source_or_404(session, source_id)
    normalized_mode = normalize_scan_mode(scan_mode)
    normalized_path = _clean_path_filter(path_filter)
    if source.status == SourceStatus.SCANNING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This source is already scanning or finishing a cancellation request.",
        )
    existing = session.execute(
        select(ScanJob).where(
            ScanJob.source_id == source_id,
            ScanJob.status.in_([ScanStatus.QUEUED, ScanStatus.RUNNING]),
        )
    ).scalar_one_or_none()
    if existing:
        return existing

    job = ScanJob(
        source_id=source_id,
        status=ScanStatus.QUEUED,
        scan_mode=normalized_mode,
        target_type="source",
        path_filter=normalized_path,
        message=f"Queued {normalized_mode} scan" + (f" for {normalized_path}" if normalized_path else "."),
    )
    session.add(job)
    session.flush()
    return job


def queue_scan_job(session: Session, payload: ScanJobCreate) -> ScanJob:
    target = payload.target
    if target is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Generic scan jobs require a target.")

    normalized_mode = normalize_scan_mode(payload.scan_mode)
    if target.type == "source":
        return queue_source_scan(
            session,
            target.source_id,
            scan_mode=normalized_mode,
            path_filter=target.path_filter if target.path_filter is not None else payload.path_filter,
        )

    reconcile_source_statuses(session)
    if target.type == "collection":
        collection = session.get(Collection, target.collection_id)
        if collection is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found.")
        asset_rows = session.execute(
            select(Asset.id, Asset.source_id)
            .join(CollectionAsset, CollectionAsset.asset_id == Asset.id)
            .where(CollectionAsset.collection_id == collection.id)
            .order_by(Asset.relative_path)
        ).all()
        if not asset_rows:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Collection has no indexed assets to scan.")
        existing = session.execute(
            select(ScanJob).where(
                ScanJob.target_type == "collection",
                ScanJob.collection_id == collection.id,
                ScanJob.status.in_([ScanStatus.QUEUED, ScanStatus.RUNNING]),
            )
        ).scalar_one_or_none()
        if existing:
            return existing
        job = ScanJob(
            source_id=asset_rows[0].source_id,
            target_type="collection",
            collection_id=collection.id,
            asset_ids_json=[str(row.id) for row in asset_rows],
            status=ScanStatus.QUEUED,
            scan_mode=normalized_mode,
            options_json=payload.options,
            message=f"Queued {normalized_mode} scan for collection {collection.name}.",
        )
        session.add(job)
        session.flush()
        return job

    if target.type == "assets":
        unique_asset_ids = list(dict.fromkeys(target.asset_ids))
        rows = session.execute(
            select(Asset.id, Asset.source_id).where(Asset.id.in_(unique_asset_ids)).order_by(Asset.relative_path)
        ).all()
        found_ids = {row.id for row in rows}
        missing = [asset_id for asset_id in unique_asset_ids if asset_id not in found_ids]
        if missing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{len(missing)} asset(s) were not found.")
        job = ScanJob(
            source_id=rows[0].source_id if rows else None,
            target_type="assets",
            asset_ids_json=[str(row.id) for row in rows],
            status=ScanStatus.QUEUED,
            scan_mode=normalized_mode,
            options_json=payload.options,
            message=f"Queued {normalized_mode} scan for {len(rows)} selected asset(s).",
        )
        session.add(job)
        session.flush()
        return job

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported scan target.")


def cancel_scan_job(session: Session, job_id) -> ScanJob:
    job = get_scan_job_or_404(session, job_id)
    if job.status in TERMINAL_STATUSES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only queued or running jobs can be cancelled.")

    was_running = job.status == ScanStatus.RUNNING
    job.status = ScanStatus.CANCELLED
    job.finished_at = datetime.now(tz=timezone.utc)
    job.worker_heartbeat_at = datetime.now(tz=timezone.utc)
    job.stage = "cancelled"
    job.message = "Scan cancellation requested by admin." if was_running else "Queued scan cancelled by admin."

    source = session.get(Source, job.source_id) if job.source_id else None
    if source is not None:
        source.status = SourceStatus.SCANNING if was_running else SourceStatus.READY
    session.flush()
    return job


def list_scan_jobs(session: Session, limit: int = 50) -> list[ScanJob]:
    return session.execute(select(ScanJob).order_by(desc(ScanJob.created_at)).limit(limit)).scalars().all()


def clear_finished_scan_jobs(session: Session, *, status_filter: ScanStatus | None = None, grace_seconds: int = 180) -> int:
    statuses = [status_filter] if status_filter else list(TERMINAL_STATUSES)
    now = datetime.now(tz=timezone.utc)
    cutoff = now - timedelta(seconds=grace_seconds)
    jobs = session.execute(select(ScanJob).where(ScanJob.status.in_(statuses))).scalars().all()
    deleted = 0
    for job in jobs:
        if job.finished_at is None or job.finished_at > cutoff:
            continue
        if job.worker_heartbeat_at is not None and job.worker_heartbeat_at > cutoff:
            continue
        session.delete(job)
        deleted += 1
    session.flush()
    return deleted


def scan_status_from_clear_filter(status_name: str | None) -> ScanStatus | None:
    if not status_name:
        return None
    normalized = status_name.strip().lower()
    aliases = {"succeeded": "completed", "success": "completed"}
    normalized = aliases.get(normalized, normalized)
    try:
        scan_status = ScanStatus(normalized)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown scan job status filter.") from exc
    if scan_status not in TERMINAL_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only terminal scan job statuses can be cleared.")
    return scan_status


def get_scan_job_or_404(session: Session, job_id) -> ScanJob:
    job = session.get(ScanJob, job_id)
    if not job:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan job not found.")
    return job
