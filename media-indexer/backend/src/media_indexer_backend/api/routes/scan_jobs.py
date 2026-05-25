from __future__ import annotations

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from media_indexer_backend.api.dependencies import get_session, require_admin, require_authenticated
from media_indexer_backend.models.enums import ScanStatus
from media_indexer_backend.models.tables import ScanJob, ScanJobError, User
from media_indexer_backend.schemas.scan_job import ScanJobCreate, ScanJobErrorEntry, ScanJobRead
from media_indexer_backend.services.audit import record_audit_event
from media_indexer_backend.services.scan_service import (
    cancel_scan_job,
    clear_finished_scan_jobs,
    get_scan_job_or_404,
    list_scan_jobs,
    queue_scan_job,
    scan_status_from_clear_filter,
)


router = APIRouter(prefix="/scan-jobs", tags=["scan-jobs"])

TERMINAL_STATUSES = {ScanStatus.COMPLETED, ScanStatus.FAILED, ScanStatus.CANCELLED}


@router.get("", response_model=list[ScanJobRead])
def get_scan_jobs(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> list[ScanJobRead]:
    return [ScanJobRead.model_validate(job) for job in list_scan_jobs(session)]


@router.post("", response_model=ScanJobRead)
def post_scan_job(
    payload: ScanJobCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> ScanJobRead:
    job = queue_scan_job(session, payload)
    record_audit_event(
        session,
        actor=current_user.username,
        action="scan.requested",
        resource_type="scan_job",
        resource_id=job.id,
        details={
            "source_id": str(job.source_id) if job.source_id else None,
            "collection_id": str(job.collection_id) if job.collection_id else None,
            "target_type": job.target_type,
            "scan_mode": job.scan_mode,
            "path_filter": job.path_filter,
        },
    )
    session.commit()
    return ScanJobRead.model_validate(job)


@router.delete("/finished")
def clear_finished_scans(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> dict[str, int]:
    deleted = clear_finished_scan_jobs(session)
    record_audit_event(
        session,
        actor=current_user.username,
        action="scan_jobs.clear_finished",
        resource_type="scan_job",
        resource_id=None,
        details={"deleted": deleted},
    )
    session.commit()
    return {"deleted": deleted}


@router.delete("/succeeded")
def clear_succeeded_scans(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> dict[str, int]:
    deleted = clear_finished_scan_jobs(session, status_filter=ScanStatus.COMPLETED)
    record_audit_event(
        session,
        actor=current_user.username,
        action="scan_jobs.clear_succeeded",
        resource_type="scan_job",
        resource_id=None,
        details={"deleted": deleted},
    )
    session.commit()
    return {"deleted": deleted}


@router.delete("/failed")
def clear_failed_scans(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> dict[str, int]:
    deleted = clear_finished_scan_jobs(session, status_filter=ScanStatus.FAILED)
    record_audit_event(
        session,
        actor=current_user.username,
        action="scan_jobs.clear_failed",
        resource_type="scan_job",
        resource_id=None,
        details={"deleted": deleted},
    )
    session.commit()
    return {"deleted": deleted}


@router.delete("/cancelled")
def clear_cancelled_scans(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> dict[str, int]:
    deleted = clear_finished_scan_jobs(session, status_filter=ScanStatus.CANCELLED)
    record_audit_event(
        session,
        actor=current_user.username,
        action="scan_jobs.clear_cancelled",
        resource_type="scan_job",
        resource_id=None,
        details={"deleted": deleted},
    )
    session.commit()
    return {"deleted": deleted}


@router.delete("")
def clear_scans_by_status(
    status: str | None = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> dict[str, int]:
    status_filter = scan_status_from_clear_filter(status)
    deleted = clear_finished_scan_jobs(session, status_filter=status_filter)
    record_audit_event(
        session,
        actor=current_user.username,
        action="scan_jobs.clear",
        resource_type="scan_job",
        resource_id=None,
        details={"deleted": deleted, "status": status},
    )
    session.commit()
    return {"deleted": deleted}


@router.get("/{job_id}", response_model=ScanJobRead)
def get_scan_job(
    job_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> ScanJobRead:
    return ScanJobRead.model_validate(get_scan_job_or_404(session, job_id))


@router.get("/{job_id}/errors", response_model=list[ScanJobErrorEntry])
def get_scan_job_errors(
    job_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> list[ScanJobErrorEntry]:
    job = get_scan_job_or_404(session, job_id)
    rows = session.execute(
        select(ScanJobError).where(ScanJobError.job_id == job.id).order_by(ScanJobError.created_at.desc())
    ).scalars().all()
    if rows:
        return [ScanJobErrorEntry.model_validate(row) for row in rows]
    return [ScanJobErrorEntry.model_validate(item) for item in (job.error_details or [])]


@router.get("/{job_id}/stream")
async def stream_scan_job(
    job_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
):
    """SSE endpoint — emits progress events every 1.5 s while job is active."""

    async def event_generator():
        while True:
            # Re-query on each tick so we pick up live updates
            job = session.get(ScanJob, job_id)
            if job is None:
                break

            payload = json.dumps({
                "status": job.status,
                "processed": job.scanned_count,
                "progress_percent": job.progress,
                "total_count": job.total_count,
                "stage": job.stage,
                "message": job.message,
                "new_count": job.new_count,
                "updated_count": job.updated_count,
                "deleted_count": job.deleted_count,
                "error_count": job.error_count,
            })
            yield {"data": payload}

            if job.status in TERMINAL_STATUSES:
                break

            await asyncio.sleep(1.5)

    return EventSourceResponse(event_generator())


@router.post("/{job_id}/cancel", response_model=ScanJobRead)
def cancel_scan(
    job_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> ScanJobRead:
    job = cancel_scan_job(session, job_id)
    record_audit_event(
        session,
        actor=current_user.username,
        action="scan.cancelled",
        resource_type="scan_job",
        resource_id=job.id,
        details={"source_id": str(job.source_id)},
    )
    session.commit()
    return ScanJobRead.model_validate(job)
