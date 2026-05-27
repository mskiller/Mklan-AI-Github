from __future__ import annotations

from pathlib import Path
from typing import Any

from app.v2.assets import AssetRegistry
from app.v2.audit import AuditLog
from app.v2.jobs import JobManager


async def noop_job(job: dict[str, Any], manager: JobManager) -> dict[str, Any]:
    await manager.update_progress(job["id"], 0.5, "No-op job acknowledged.")
    return {"ok": True, "echo": job["payload"]}


def register_platform_jobs(manager: JobManager) -> None:
    from app.generation import register_generation_jobs
    from app.training import register_training_jobs
    from app.video import register_video_jobs
    from app.v2.workflows import register_workflow_jobs

    register_workflow_jobs(manager)
    register_generation_jobs(manager)
    register_training_jobs(manager)
    register_video_jobs(manager)
    manager.register_handler("system.noop", noop_job)


def create_platform_services(data_path: Path, *, worker_mode: bool = False) -> tuple[AuditLog, AssetRegistry, JobManager]:
    audit = AuditLog(data_path)
    asset_registry = AssetRegistry(data_path)
    asset_registry.initialize()
    job_manager = JobManager(data_path, worker_mode=worker_mode)
    job_manager.asset_registry = asset_registry
    register_platform_jobs(job_manager)
    return audit, asset_registry, job_manager
