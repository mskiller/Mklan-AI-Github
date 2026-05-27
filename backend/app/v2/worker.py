from __future__ import annotations

import os
from typing import Any

from app.v2.core_db import default_data_root
from app.v2.runtime import create_platform_services


async def startup(ctx: dict[str, Any]) -> None:
    _, _, manager = create_platform_services(default_data_root(), worker_mode=True)
    manager.initialize()
    ctx["job_manager"] = manager


async def shutdown(ctx: dict[str, Any]) -> None:
    manager = ctx.get("job_manager")
    if manager is not None:
        await manager.stop()


async def run_studio_job(ctx: dict[str, Any], job_id: str) -> None:
    manager = ctx["job_manager"]
    await manager.process_one(job_id)


def _redis_settings():
    from arq.connections import RedisSettings

    url = os.getenv("STUDIO_REDIS_URL", "redis://studio_redis:6379/0")
    return RedisSettings.from_dsn(url)


class WorkerSettings:
    functions = [run_studio_job]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = _redis_settings()
    max_jobs = int(os.getenv("STUDIO_WORKER_MAX_JOBS", "1") or "1")
    job_timeout = int(os.getenv("STUDIO_WORKER_JOB_TIMEOUT_S", "21600") or "21600")
