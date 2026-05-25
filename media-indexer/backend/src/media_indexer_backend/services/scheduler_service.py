from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from media_indexer_backend.db.session import SessionLocal
from media_indexer_backend.models.tables import ScheduledScan
from media_indexer_backend.platform.service import live_module_enabled
from media_indexer_backend.services.scan_service import queue_scan
from media_indexer_backend.services.smart_album_service import generate_smart_album_suggestions


logger = logging.getLogger(__name__)

_scheduler: Any | None = None


def _get_scheduler():
    global _scheduler
    if _scheduler is None:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


def validate_cron_expression(expr: str) -> None:
    from apscheduler.triggers.cron import CronTrigger

    CronTrigger.from_crontab(expr)


def start_scheduler() -> None:
    scheduler = _get_scheduler()
    if not scheduler.running:
        scheduler.start()


def shutdown_scheduler() -> None:
    scheduler = _get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)


def reload_schedules() -> None:
    scheduler = _get_scheduler()
    for job in list(scheduler.get_jobs()):
        scheduler.remove_job(job.id)

    _register_nightly_jobs()

    with SessionLocal() as session:
        schedules = session.execute(
            select(ScheduledScan).where(ScheduledScan.enabled == True)  # noqa: E712
        ).scalars().all()
        for schedule in schedules:
            _register_schedule(session, schedule)


def _register_nightly_jobs() -> None:
    from apscheduler.triggers.cron import CronTrigger

    if not live_module_enabled("smart_albums", default=True):
        return
    scheduler = _get_scheduler()
    scheduler.add_job(
        _run_nightly_suggestions,
        CronTrigger(hour=3, minute=15),
        id="smart_album_suggestions_nightly",
        replace_existing=True,
    )


def _register_schedule(session: Session, schedule: ScheduledScan) -> None:
    from apscheduler.triggers.cron import CronTrigger

    scheduler = _get_scheduler()
    validate_cron_expression(schedule.cron_expression)
    scheduler.add_job(
        _trigger_schedule,
        CronTrigger.from_crontab(schedule.cron_expression),
        id=str(schedule.id),
        replace_existing=True,
        args=[str(schedule.id), str(schedule.source_id)],
    )


def _trigger_schedule(schedule_id: str, source_id: str) -> None:
    with SessionLocal() as session:
        schedule = session.get(ScheduledScan, UUID(schedule_id))
        if schedule is None or not schedule.enabled:
            return
        try:
            job = queue_scan(session, UUID(source_id))
            schedule.last_triggered_at = job.created_at
            schedule.last_job_id = job.id
            session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("scheduled scan trigger failed", extra={"schedule_id": schedule_id, "error": str(exc)})
            session.rollback()


def _run_nightly_suggestions() -> None:
    with SessionLocal() as session:
        try:
            generate_smart_album_suggestions(session)
            session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("smart album suggestion job failed", extra={"error": str(exc)})
            session.rollback()
