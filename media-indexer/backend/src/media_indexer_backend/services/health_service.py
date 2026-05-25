from __future__ import annotations

import math
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from media_indexer_backend.core.config import get_settings
from media_indexer_backend.db.session import engine
from media_indexer_backend.models.enums import ScanStatus
from media_indexer_backend.models.tables import ScanJob, ScheduledScan, Source
from media_indexer_backend.schemas.health import (
    AdminHealthResponse,
    HealthDbStats,
    HealthDiskSource,
    HealthDiskStats,
    HealthModelState,
    HealthScheduleRead,
    HealthWorkerQueueStats,
)


def _gb(value: int) -> float:
    return round(value / (1024 ** 3), 2)


def _disk_usage(path: Path) -> tuple[float, float]:
    try:
        import psutil

        usage = psutil.disk_usage(str(path))
        return (_gb(usage.free), _gb(usage.total))
    except Exception:
        return (0.0, 0.0)


def _worker_status():
    settings = get_settings()
    try:
        import httpx

        response = httpx.get(f"{settings.worker_status_url.rstrip('/')}/status", timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception:
        return None


def build_admin_health(session: Session) -> AdminHealthResponse:
    pool = engine.pool
    worker_status = _worker_status()
    pending_jobs = session.execute(select(func.count(ScanJob.id)).where(ScanJob.status == ScanStatus.QUEUED)).scalar_one()
    running_jobs = session.execute(select(func.count(ScanJob.id)).where(ScanJob.status == ScanStatus.RUNNING)).scalar_one()
    sources = session.execute(select(Source).order_by(Source.name)).scalars().all()
    schedules = session.execute(select(ScheduledScan).join(Source).order_by(Source.name)).scalars().all()

    disk_sources: list[HealthDiskSource] = []
    for source in sources:
        source_path = Path(source.root_path).resolve(strict=False)
        free_gb, total_gb = _disk_usage(source_path)
        disk_sources.append(
            HealthDiskSource(
                source_id=source.id,
                name=source.name,
                path=str(source_path),
                free_gb=free_gb,
                total_gb=total_gb,
            )
        )

    preview_root = get_settings().preview_root_path
    previews_gb = 0.0
    if preview_root.exists():
        previews_gb = round(
            sum(file.stat().st_size for file in preview_root.rglob("*") if file.is_file()) / (1024 ** 3),
            3,
        )

    schedules_payload = [
        HealthScheduleRead(
            schedule_id=schedule.id,
            source_id=schedule.source_id,
            source_name=schedule.source.name if schedule.source is not None else "Unknown",
            cron_expression=schedule.cron_expression,
            enabled=schedule.enabled,
            last_run=schedule.last_triggered_at,
            last_job_id=schedule.last_job_id,
            status="ok" if schedule.enabled else "disabled",
        )
        for schedule in schedules
    ]
    degraded = worker_status is None
    models = {
        "clip": HealthModelState(
            loaded=bool(worker_status and worker_status.get("clip_loaded")),
            model_id=worker_status.get("clip_model_id") if worker_status else get_settings().clip_model_id,
        ),
        "wd_tagger": HealthModelState(loaded=bool(worker_status and worker_status.get("wd_tagger_loaded"))),
        "caption": HealthModelState(loaded=bool(worker_status and worker_status.get("caption_loaded"))),
    }
    status_value = "degraded" if degraded else "ok"
    return AdminHealthResponse(
        status=status_value,
        db=HealthDbStats(
            connected=True,
            pool_size=getattr(pool, "size", lambda: 0)(),
            checked_out=getattr(pool, "checkedout", lambda: 0)(),
        ),
        worker_queue=HealthWorkerQueueStats(
            pending_jobs=int(pending_jobs or 0),
            running_jobs=int(running_jobs or 0),
        ),
        disk=HealthDiskStats(
            sources=disk_sources,
            previews_gb=0.0 if math.isnan(previews_gb) else previews_gb,
        ),
        models=models,
        schedules=schedules_payload,
    )
