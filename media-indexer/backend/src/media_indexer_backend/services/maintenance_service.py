from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from media_indexer_backend.core.config import get_settings
from media_indexer_backend.models.enums import ScanStatus, SourceStatus
from media_indexer_backend.models.tables import AppSetting, Asset, AuditLog, Collection, ScanJob, Source
from media_indexer_backend.services.source_service import reconcile_source_statuses


def _reset_preview_directory(preview_root: Path) -> None:
    if preview_root.exists():
        shutil.rmtree(preview_root, ignore_errors=True)
    preview_root.mkdir(parents=True, exist_ok=True)


def reset_application_data(session: Session, *, delete_sources: bool) -> dict[str, int]:
    reconcile_source_statuses(session)

    active_jobs = session.execute(
        select(func.count(ScanJob.id)).where(ScanJob.status.in_([ScanStatus.QUEUED, ScanStatus.RUNNING]))
    ).scalar_one()
    if active_jobs:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cancel active scan jobs before clearing indexed data.",
        )

    scanning_sources = session.execute(
        select(func.count(Source.id)).where(Source.status == SourceStatus.SCANNING)
    ).scalar_one()
    if scanning_sources:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A source is still finishing a scan or cancellation. Wait a moment and try again.",
        )

    deleted_assets = session.execute(select(func.count(Asset.id))).scalar_one()
    deleted_jobs = session.execute(select(func.count(ScanJob.id))).scalar_one()
    deleted_sources = session.execute(select(func.count(Source.id))).scalar_one() if delete_sources else 0
    deleted_audit_logs = session.execute(select(func.count(AuditLog.id))).scalar_one()
    deleted_collections = session.execute(select(func.count(Collection.id))).scalar_one() if delete_sources else 0
    deleted_settings = session.execute(select(func.count(AppSetting.key))).scalar_one() if delete_sources else 0

    session.execute(delete(ScanJob))
    session.execute(delete(Asset))
    session.execute(delete(AuditLog))

    if delete_sources:
        session.execute(delete(Collection))
        session.execute(delete(AppSetting))
        session.execute(delete(Source))
    else:
        session.execute(
            update(Source).values(
                status=SourceStatus.READY,
                last_scan_at=None,
            )
        )

    session.commit()
    _reset_preview_directory(get_settings().preview_root_path)

    return {
        "deleted_assets": deleted_assets,
        "deleted_scan_jobs": deleted_jobs,
        "deleted_sources": deleted_sources,
        "deleted_audit_logs": deleted_audit_logs,
        "deleted_collections": deleted_collections,
        "deleted_settings": deleted_settings,
    }


def purge_deepzoom_tiles(preview_root: Path) -> dict[str, int]:
    deepzoom_root = preview_root / "deepzoom"
    if not deepzoom_root.exists():
        return {"deleted_tile_directories": 0, "deleted_manifests": 0}

    deleted_tile_directories = 0
    deleted_manifests = 0
    for dzi in deepzoom_root.glob("*.dzi"):
        tile_dir = deepzoom_root / f"{dzi.stem}_files"
        dzi.unlink(missing_ok=True)
        deleted_manifests += 1
        if tile_dir.exists():
            shutil.rmtree(tile_dir, ignore_errors=True)
            deleted_tile_directories += 1

    return {
        "deleted_tile_directories": deleted_tile_directories,
        "deleted_manifests": deleted_manifests,
    }
