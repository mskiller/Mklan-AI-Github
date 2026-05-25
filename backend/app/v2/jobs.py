from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
from typing import Any
import uuid

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field


TERMINAL_STATUSES = {"succeeded", "failed", "canceled"}
JobHandler = Callable[[dict[str, Any], "JobManager"], Awaitable[dict[str, Any] | None]]


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


class JobCanceled(RuntimeError):
    pass


class JobCreateRequest(BaseModel):
    job_type: str = Field(min_length=1, max_length=120)
    payload: dict[str, Any] = Field(default_factory=dict)


class JobRead(BaseModel):
    id: str
    job_type: str
    status: str
    progress: float
    payload: dict[str, Any]
    result: dict[str, Any]
    error_text: str | None = None
    cancel_requested: bool = False
    created_at: str
    updated_at: str
    started_at: str | None = None
    finished_at: str | None = None


class JobEventRead(BaseModel):
    id: int
    job_id: str
    event_type: str
    message: str
    progress: float | None = None
    payload: dict[str, Any]
    created_at: str


class JobCreateResponse(BaseModel):
    job: JobRead
    events_url: str


class JobOverviewItem(JobRead):
    source: str
    label: str
    cancelable: bool


class JobsOverviewResponse(BaseModel):
    generated_at: str
    counts: dict[str, int]
    jobs: list[JobOverviewItem]


class JobManager:
    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root
        self.db_path = data_root / "platform_jobs.db"
        self.handlers: dict[str, JobHandler] = {}
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._conditions: dict[str, asyncio.Condition] = {}

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    job_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress REAL NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    result_json TEXT NOT NULL DEFAULT '{}',
                    error_text TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_platform_jobs_status_created ON jobs(status, created_at);

                CREATE TABLE IF NOT EXISTS job_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL DEFAULT '',
                    progress REAL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_platform_job_events_job_id ON job_events(job_id, id);
                """
            )
            now = utc_now_iso()
            conn.execute(
                """
                UPDATE jobs
                   SET status = 'failed',
                       error_text = COALESCE(error_text, 'Job interrupted by application restart.'),
                       updated_at = ?,
                       finished_at = COALESCE(finished_at, ?)
                 WHERE status = 'running'
                """,
                (now, now),
            )
            conn.commit()

    async def start(self) -> None:
        self.initialize()
        self._worker_task = asyncio.create_task(self._worker(), name="mklan-v2-job-worker")
        for job_id in self.queued_job_ids():
            await self.enqueue(job_id)

    async def stop(self) -> None:
        await self._queue.put(None)
        if self._worker_task is not None:
            await self._worker_task

    def register_handler(self, job_type: str, handler: JobHandler) -> None:
        self.handlers[job_type] = handler

    def queued_job_ids(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT id FROM jobs WHERE status = 'queued' ORDER BY created_at").fetchall()
            return [str(row["id"]) for row in rows]

    def list_jobs(self, *, limit: int = 100, statuses: list[str] | None = None) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        with self._connect() as conn:
            if statuses:
                placeholders = ",".join("?" for _ in statuses)
                rows = conn.execute(
                    f"""
                    SELECT * FROM jobs
                     WHERE status IN ({placeholders})
                     ORDER BY created_at DESC
                     LIMIT ?
                    """,
                    [*statuses, limit],
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM jobs
                     ORDER BY created_at DESC
                     LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [self._job_from_row(row) for row in rows]

    async def enqueue(self, job_id: str) -> None:
        await self._queue.put(job_id)

    async def create_job(self, job_type: str, payload: dict[str, Any], *, enqueue: bool = True) -> dict[str, Any]:
        if job_type not in self.handlers:
            raise HTTPException(status_code=400, detail=f"No V2 job handler registered for {job_type!r}.")
        job_id = uuid.uuid4().hex
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, job_type, status, progress, payload_json, result_json,
                    created_at, updated_at
                ) VALUES (?, ?, 'queued', 0, ?, '{}', ?, ?)
                """,
                (job_id, job_type, _json_dumps(payload), now, now),
            )
            conn.commit()
        await self.emit_event(job_id, "queued", "Job queued.", progress=0)
        if enqueue:
            await self.enqueue(job_id)
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        return self._job_from_row(row)

    def list_events(self, job_id: str, *, after_id: int = 0) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM job_events
                 WHERE job_id = ? AND id > ?
                 ORDER BY id ASC
                """,
                (job_id, after_id),
            ).fetchall()
        return [self._event_from_row(row) for row in rows]

    async def wait_for_event(self, job_id: str, *, timeout_s: float = 30.0) -> None:
        condition = self._conditions.setdefault(job_id, asyncio.Condition())
        try:
            async with condition:
                await asyncio.wait_for(condition.wait(), timeout=timeout_s)
        except asyncio.TimeoutError:
            return

    async def cancel_job(self, job_id: str) -> dict[str, Any]:
        job = self.get_job(job_id)
        now = utc_now_iso()
        if job["status"] == "queued":
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE jobs
                       SET status = 'canceled',
                           cancel_requested = 1,
                           updated_at = ?,
                           finished_at = ?
                     WHERE id = ?
                    """,
                    (now, now, job_id),
                )
                conn.commit()
            await self.emit_event(job_id, "canceled", "Queued job canceled.", progress=job["progress"])
        elif job["status"] not in TERMINAL_STATUSES:
            self._update_job(job_id, cancel_requested=True)
            await self.emit_event(job_id, "cancel_requested", "Cancellation requested.", progress=job["progress"])
        return self.get_job(job_id)

    async def raise_if_canceled(self, job_id: str) -> None:
        if self.get_job(job_id)["cancel_requested"]:
            raise JobCanceled("Job cancellation requested.")

    async def update_progress(
        self,
        job_id: str,
        progress: float,
        message: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> None:
        progress = max(0.0, min(1.0, float(progress)))
        self._update_job(job_id, progress=progress)
        await self.emit_event(job_id, "progress", message, progress=progress, payload=payload)

    async def complete_job(self, job_id: str, result: dict[str, Any] | None = None) -> dict[str, Any]:
        now = utc_now_iso()
        self._update_job(job_id, status="succeeded", progress=1.0, result=result or {}, finished_at=now)
        await self.emit_event(job_id, "succeeded", "Job succeeded.", progress=1.0, payload=result or {})
        return self.get_job(job_id)

    async def fail_job(self, job_id: str, error_text: str) -> dict[str, Any]:
        now = utc_now_iso()
        self._update_job(job_id, status="failed", error_text=error_text, finished_at=now)
        await self.emit_event(job_id, "failed", error_text, payload={"error_text": error_text})
        return self.get_job(job_id)

    async def mark_canceled(self, job_id: str, message: str = "Job canceled.") -> dict[str, Any]:
        now = utc_now_iso()
        self._update_job(job_id, status="canceled", cancel_requested=True, finished_at=now)
        await self.emit_event(job_id, "canceled", message)
        return self.get_job(job_id)

    async def emit_event(
        self,
        job_id: str,
        event_type: str,
        message: str,
        *,
        progress: float | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO job_events (job_id, event_type, message, progress, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (job_id, event_type, message, progress, _json_dumps(payload or {}), now),
            )
            conn.commit()
            event_id = int(cursor.lastrowid)
            row = conn.execute("SELECT * FROM job_events WHERE id = ?", (event_id,)).fetchone()
        condition = self._conditions.setdefault(job_id, asyncio.Condition())
        async with condition:
            condition.notify_all()
        return self._event_from_row(row)

    async def _worker(self) -> None:
        while True:
            job_id = await self._queue.get()
            if job_id is None:
                break
            await self._process(job_id)

    async def _process(self, job_id: str) -> None:
        job = self.get_job(job_id)
        if job["status"] != "queued":
            return
        now = utc_now_iso()
        self._update_job(job_id, status="running", started_at=now, progress=max(job["progress"], 0.01))
        await self.emit_event(job_id, "running", "Job started.", progress=max(job["progress"], 0.01))
        handler = self.handlers[job["job_type"]]
        try:
            await self.raise_if_canceled(job_id)
            result = await handler(self.get_job(job_id), self)
            await self.raise_if_canceled(job_id)
            await self.complete_job(job_id, result or {})
        except JobCanceled as exc:
            await self.mark_canceled(job_id, str(exc))
        except Exception as exc:
            await self.fail_job(job_id, str(exc))

    def _update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        progress: float | None = None,
        result: dict[str, Any] | None = None,
        error_text: str | None = None,
        cancel_requested: bool | None = None,
        started_at: str | None = None,
        finished_at: str | None = None,
    ) -> None:
        assignments = ["updated_at = ?"]
        values: list[Any] = [utc_now_iso()]
        if status is not None:
            assignments.append("status = ?")
            values.append(status)
        if progress is not None:
            assignments.append("progress = ?")
            values.append(max(0.0, min(1.0, float(progress))))
        if result is not None:
            assignments.append("result_json = ?")
            values.append(_json_dumps(result))
        if error_text is not None:
            assignments.append("error_text = ?")
            values.append(error_text)
        if cancel_requested is not None:
            assignments.append("cancel_requested = ?")
            values.append(1 if cancel_requested else 0)
        if started_at is not None:
            assignments.append("started_at = COALESCE(started_at, ?)")
            values.append(started_at)
        if finished_at is not None:
            assignments.append("finished_at = ?")
            values.append(finished_at)
        values.append(job_id)
        with self._connect() as conn:
            conn.execute(f"UPDATE jobs SET {', '.join(assignments)} WHERE id = ?", values)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _job_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "job_type": row["job_type"],
            "status": row["status"],
            "progress": float(row["progress"]),
            "payload": _json_loads(row["payload_json"], {}),
            "result": _json_loads(row["result_json"], {}),
            "error_text": row["error_text"],
            "cancel_requested": bool(row["cancel_requested"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
        }

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "job_id": row["job_id"],
            "event_type": row["event_type"],
            "message": row["message"],
            "progress": row["progress"],
            "payload": _json_loads(row["payload_json"], {}),
            "created_at": row["created_at"],
        }


router = APIRouter(prefix="/jobs", tags=["v2-jobs"])


def get_job_manager(request: Request) -> JobManager:
    manager = getattr(request.app.state, "v2_jobs", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="V2 job manager is not available.")
    return manager


def _job_source(job_type: str) -> str:
    prefix = job_type.split(".", 1)[0].strip().lower()
    if prefix in {"training", "generation", "workflow", "asset"}:
        return prefix
    return "system"


def _job_label(job: dict[str, Any]) -> str:
    payload = job.get("payload") or {}
    for key in ("output_name", "name", "prompt", "dataset_id", "collection_name"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            text = value.strip()
            return text[:82] + "..." if len(text) > 85 else text
    return str(job.get("job_type") or "Job").replace(".", " ")


@router.post("", response_model=JobCreateResponse, status_code=202)
async def create_job(payload: JobCreateRequest, request: Request) -> JobCreateResponse:
    manager = get_job_manager(request)
    job = await manager.create_job(payload.job_type, payload.payload)
    return JobCreateResponse(job=JobRead.model_validate(job), events_url=f"/api/jobs/{job['id']}/events")


@router.get("/overview", response_model=JobsOverviewResponse)
def get_jobs_overview(request: Request, limit: int = 80) -> JobsOverviewResponse:
    manager = get_job_manager(request)
    jobs = manager.list_jobs(limit=limit)
    counts: dict[str, int] = {}
    overview: list[JobOverviewItem] = []
    for job in jobs:
        status = str(job.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
        overview.append(
            JobOverviewItem.model_validate(
                {
                    **job,
                    "source": _job_source(str(job.get("job_type") or "")),
                    "label": _job_label(job),
                    "cancelable": status not in TERMINAL_STATUSES,
                }
            )
        )
    return JobsOverviewResponse(generated_at=utc_now_iso(), counts=counts, jobs=overview)


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: str, request: Request) -> JobRead:
    return JobRead.model_validate(get_job_manager(request).get_job(job_id))


@router.post("/{job_id}/cancel", response_model=JobRead)
async def cancel_job(job_id: str, request: Request) -> JobRead:
    return JobRead.model_validate(await get_job_manager(request).cancel_job(job_id))


@router.get("/{job_id}/events", response_model=list[JobEventRead])
def get_job_events(job_id: str, request: Request, after_id: int = 0) -> list[JobEventRead]:
    manager = get_job_manager(request)
    manager.get_job(job_id)
    return [JobEventRead.model_validate(event) for event in manager.list_events(job_id, after_id=after_id)]


@router.websocket("/{job_id}/events")
async def job_events_socket(websocket: WebSocket, job_id: str) -> None:
    manager = getattr(websocket.app.state, "v2_jobs", None)
    if manager is None:
        await websocket.close(code=1011)
        return
    await websocket.accept()
    last_id = 0
    try:
        job = manager.get_job(job_id)
        await websocket.send_json({"type": "snapshot", "job": job})
        while True:
            events = manager.list_events(job_id, after_id=last_id)
            for event in events:
                last_id = max(last_id, int(event["id"]))
                await websocket.send_json({"type": "event", "event": event})
            job = manager.get_job(job_id)
            if job["status"] in TERMINAL_STATUSES and not manager.list_events(job_id, after_id=last_id):
                await websocket.send_json({"type": "snapshot", "job": job})
                break
            await manager.wait_for_event(job_id)
    except WebSocketDisconnect:
        return
    except HTTPException:
        await websocket.close(code=1008)
