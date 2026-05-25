from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class HealthDbStats(BaseModel):
    connected: bool
    pool_size: int
    checked_out: int


class HealthWorkerQueueStats(BaseModel):
    pending_jobs: int
    running_jobs: int


class HealthDiskSource(BaseModel):
    source_id: UUID
    name: str
    path: str
    free_gb: float
    total_gb: float


class HealthDiskStats(BaseModel):
    sources: list[HealthDiskSource]
    previews_gb: float


class HealthModelState(BaseModel):
    loaded: bool
    model_id: str | None = None


class HealthScheduleRead(BaseModel):
    schedule_id: UUID
    source_id: UUID
    source_name: str
    cron_expression: str
    enabled: bool
    last_run: datetime | None = None
    last_job_id: UUID | None = None
    status: str


class AdminHealthResponse(BaseModel):
    status: str
    db: HealthDbStats
    worker_queue: HealthWorkerQueueStats
    disk: HealthDiskStats
    models: dict[str, HealthModelState]
    schedules: list[HealthScheduleRead]
