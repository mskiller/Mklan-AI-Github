from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
import inspect
import json
import os
from pathlib import Path
import sqlite3
from typing import Any
from urllib.parse import urlparse
import uuid

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.v2.core_db import connect_core_db, core_db_enabled, initialize_core_db
from app.v2.workspaces import DEFAULT_WORKSPACE_ID, active_workspace_id

try:
    from arq import create_pool
    from arq.connections import RedisSettings
except Exception:  # pragma: no cover - SQLite fallback does not need ARQ installed.
    create_pool = None  # type: ignore[assignment]
    RedisSettings = None  # type: ignore[assignment]

try:
    import redis.asyncio as redis_async
except Exception:  # pragma: no cover - SQLite fallback does not need Redis installed.
    redis_async = None  # type: ignore[assignment]


TERMINAL_STATUSES = {"succeeded", "failed", "canceled"}
JobHandler = Callable[[dict[str, Any], "JobManager"], Awaitable[dict[str, Any] | None]]


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


def _json_loads(value: Any, fallback: Any) -> Any:
    if value is None or value == "":
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return fallback


def _row_get(row: Any, key: str) -> Any:
    return row[key]


def _row_get_optional(row: Any, key: str, default: Any = None) -> Any:
    try:
        return row[key]
    except Exception:
        return default


def _redis_settings_from_url(url: str):
    if RedisSettings is None:
        raise RuntimeError("arq is required when STUDIO_JOBS_BACKEND=arq.")
    if hasattr(RedisSettings, "from_dsn"):
        return RedisSettings.from_dsn(url)
    parsed = urlparse(url)
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        database=int((parsed.path or "/0").strip("/") or "0"),
        password=parsed.password,
    )


class JobCanceled(RuntimeError):
    pass


class JobCreateRequest(BaseModel):
    job_type: str = Field(min_length=1, max_length=120)
    payload: dict[str, Any] = Field(default_factory=dict)
    workspace_id: str | None = Field(default=None, max_length=120)


class JobRead(BaseModel):
    id: str
    job_type: str
    status: str
    progress: float
    payload: dict[str, Any]
    result: dict[str, Any]
    error_text: str | None = None
    cancel_requested: bool = False
    workspace_id: str = DEFAULT_WORKSPACE_ID
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
    def __init__(
        self,
        data_root: Path,
        *,
        queue_backend: str | None = None,
        database_url: str | None = None,
        redis_url: str | None = None,
        worker_mode: bool = False,
    ) -> None:
        self.data_root = data_root
        self.db_path = data_root / "platform_jobs.db"
        self.handlers: dict[str, JobHandler] = {}
        self.queue_backend = (queue_backend or os.getenv("STUDIO_JOBS_BACKEND", "sqlite")).strip().lower() or "sqlite"
        self.database_url = (database_url if database_url is not None else os.getenv("STUDIO_DATABASE_URL", "")).strip()
        self.redis_url = (redis_url if redis_url is not None else os.getenv("STUDIO_REDIS_URL", "redis://studio_redis:6379/0")).strip()
        self.worker_mode = worker_mode
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._conditions: dict[str, asyncio.Condition] = {}
        self._arq_pool: Any | None = None

    @property
    def storage_backend(self) -> str:
        return "postgres" if self.database_url else "sqlite"

    def initialize(self, *, mark_running_failed: bool | None = None) -> None:
        mark_running = self.queue_backend == "sqlite" if mark_running_failed is None else mark_running_failed
        if self.storage_backend == "postgres":
            initialize_core_db()
            if mark_running:
                now = utc_now_iso()
                with connect_core_db() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            """
                            UPDATE platform_jobs
                               SET status = 'failed',
                                   error_text = COALESCE(error_text, 'Job interrupted by application restart.'),
                                   updated_at = %s,
                                   finished_at = COALESCE(finished_at, %s)
                             WHERE status = 'running'
                            """,
                            (now, now),
                        )
                    conn.commit()
            return

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
                    finished_at TEXT,
                    workspace_id TEXT NOT NULL DEFAULT 'default'
                );
                CREATE INDEX IF NOT EXISTS idx_platform_jobs_status_created ON jobs(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_platform_jobs_workspace_created ON jobs(workspace_id, created_at DESC);

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
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
            if "workspace_id" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN workspace_id TEXT NOT NULL DEFAULT 'default'")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_platform_jobs_workspace_created ON jobs(workspace_id, created_at DESC)")
            if mark_running:
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
        self.initialize(mark_running_failed=self.queue_backend == "sqlite")
        if self.queue_backend == "sqlite":
            self._worker_task = asyncio.create_task(self._worker(), name="mklan-v2-job-worker")
        if not self.worker_mode:
            for job_id in self.queued_job_ids():
                await self.enqueue(job_id)

    async def stop(self) -> None:
        if self._worker_task is not None:
            await self._queue.put(None)
            await self._worker_task
        if self._arq_pool is not None:
            close = getattr(self._arq_pool, "close", None)
            if close is not None:
                result = close()
                if inspect.isawaitable(result):
                    await result
            self._arq_pool = None

    def register_handler(self, job_type: str, handler: JobHandler) -> None:
        self.handlers[job_type] = handler

    def queued_job_ids(self) -> list[str]:
        if self.storage_backend == "postgres":
            with connect_core_db() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT id FROM platform_jobs WHERE status = 'queued' ORDER BY created_at")
                    rows = cursor.fetchall()
            return [str(row["id"]) for row in rows]
        with self._connect() as conn:
            rows = conn.execute("SELECT id FROM jobs WHERE status = 'queued' ORDER BY created_at").fetchall()
            return [str(row["id"]) for row in rows]

    def list_jobs(
        self,
        *,
        limit: int = 100,
        statuses: list[str] | None = None,
        prefix: str | None = None,
        workspace_id: str | None = None,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        scoped_workspace_id = active_workspace_id(self.data_root) if workspace_id is None else workspace_id
        if self.storage_backend == "postgres":
            clauses: list[str] = []
            values: list[Any] = []
            if scoped_workspace_id and scoped_workspace_id != "__all__":
                clauses.append("workspace_id = %s")
                values.append(scoped_workspace_id)
            if statuses:
                clauses.append("status = ANY(%s)")
                values.append(statuses)
            if prefix:
                clauses.append("job_type LIKE %s")
                values.append(f"{prefix}%")
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            with connect_core_db() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        f"SELECT * FROM platform_jobs {where} ORDER BY created_at DESC LIMIT %s",
                        (*values, limit),
                    )
                    rows = cursor.fetchall()
            return [self._job_from_row(row) for row in rows]

        with self._connect() as conn:
            clauses = []
            values = []
            if scoped_workspace_id and scoped_workspace_id != "__all__":
                clauses.append("workspace_id = ?")
                values.append(scoped_workspace_id)
            if statuses:
                placeholders = ",".join("?" for _ in statuses)
                clauses.append(f"status IN ({placeholders})")
                values.extend(statuses)
            if prefix:
                clauses.append("job_type LIKE ?")
                values.append(f"{prefix}%")
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            rows = conn.execute(
                f"SELECT * FROM jobs {where} ORDER BY created_at DESC LIMIT ?",
                (*values, limit),
            ).fetchall()
        return [self._job_from_row(row) for row in rows]

    async def enqueue(self, job_id: str) -> None:
        if self.queue_backend == "arq":
            if self.worker_mode:
                return
            await self._enqueue_arq(job_id)
            return
        await self._queue.put(job_id)

    async def _enqueue_arq(self, job_id: str) -> None:
        if create_pool is None:
            raise RuntimeError("arq is required when STUDIO_JOBS_BACKEND=arq.")
        if self._arq_pool is None:
            self._arq_pool = await create_pool(_redis_settings_from_url(self.redis_url))
        await self._arq_pool.enqueue_job("run_studio_job", job_id)

    async def create_job(
        self,
        job_type: str,
        payload: dict[str, Any],
        *,
        enqueue: bool = True,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        if job_type not in self.handlers:
            raise HTTPException(status_code=400, detail=f"No V2 job handler registered for {job_type!r}.")
        job_id = uuid.uuid4().hex
        now = utc_now_iso()
        scoped_workspace_id = workspace_id or str(payload.get("workspace_id") or "").strip() or active_workspace_id(self.data_root)
        payload = {**payload, "workspace_id": scoped_workspace_id}
        if self.storage_backend == "postgres":
            with connect_core_db() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO platform_jobs (
                            id, job_type, status, progress, payload_json, result_json,
                            created_at, updated_at, workspace_id
                        ) VALUES (%s, %s, 'queued', 0, %s::jsonb, '{}'::jsonb, %s, %s, %s)
                        """,
                        (job_id, job_type, _json_dumps(payload), now, now, scoped_workspace_id),
                    )
                conn.commit()
        else:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO jobs (
                        id, job_type, status, progress, payload_json, result_json,
                        created_at, updated_at, workspace_id
                    ) VALUES (?, ?, 'queued', 0, ?, '{}', ?, ?, ?)
                    """,
                    (job_id, job_type, _json_dumps(payload), now, now, scoped_workspace_id),
                )
                conn.commit()
        await self.emit_event(job_id, "queued", "Job queued.", progress=0)
        if enqueue:
            await self.enqueue(job_id)
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> dict[str, Any]:
        if self.storage_backend == "postgres":
            with connect_core_db() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT * FROM platform_jobs WHERE id = %s", (job_id,))
                    row = cursor.fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="Job not found.")
            return self._job_from_row(row)
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        return self._job_from_row(row)

    def list_events(self, job_id: str, *, after_id: int = 0) -> list[dict[str, Any]]:
        if self.storage_backend == "postgres":
            with connect_core_db() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT * FROM platform_job_events
                         WHERE job_id = %s AND id > %s
                         ORDER BY id ASC
                        """,
                        (job_id, after_id),
                    )
                    rows = cursor.fetchall()
            return [self._event_from_row(row) for row in rows]
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
        if self.redis_url and redis_async is not None:
            try:
                await asyncio.wait_for(self._wait_for_redis_event(job_id), timeout=timeout_s)
                return
            except asyncio.TimeoutError:
                return
            except Exception:
                pass
        condition = self._conditions.setdefault(job_id, asyncio.Condition())
        try:
            async with condition:
                await asyncio.wait_for(condition.wait(), timeout=timeout_s)
        except asyncio.TimeoutError:
            return

    async def _wait_for_redis_event(self, job_id: str) -> None:
        client = redis_async.from_url(self.redis_url, decode_responses=True)
        pubsub = client.pubsub()
        try:
            await pubsub.subscribe(f"studio:jobs:{job_id}")
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=5)
                if message is not None:
                    return
                await asyncio.sleep(0.05)
        finally:
            await pubsub.unsubscribe(f"studio:jobs:{job_id}")
            await pubsub.close()
            await client.aclose()

    async def cancel_job(self, job_id: str) -> dict[str, Any]:
        job = self.get_job(job_id)
        now = utc_now_iso()
        if job["status"] == "queued":
            self._update_job(job_id, status="canceled", cancel_requested=True, finished_at=now)
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
        if self.storage_backend == "postgres":
            with connect_core_db() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO platform_job_events (job_id, event_type, message, progress, payload_json, created_at)
                        VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                        RETURNING *
                        """,
                        (job_id, event_type, message, progress, _json_dumps(payload or {}), now),
                    )
                    row = cursor.fetchone()
                conn.commit()
        else:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO job_events (job_id, event_type, message, progress, payload_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (job_id, event_type, message, progress, _json_dumps(payload or {}), now),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM job_events WHERE id = ?", (int(cursor.lastrowid),)).fetchone()
        event = self._event_from_row(row)
        condition = self._conditions.setdefault(job_id, asyncio.Condition())
        async with condition:
            condition.notify_all()
        await self._publish_event(job_id, event)
        return event

    async def _publish_event(self, job_id: str, event: dict[str, Any]) -> None:
        if not self.redis_url or redis_async is None:
            return
        try:
            client = redis_async.from_url(self.redis_url, decode_responses=True)
            await client.publish(f"studio:jobs:{job_id}", _json_dumps(event))
            await client.aclose()
        except Exception:
            return

    async def process_one(self, job_id: str) -> None:
        await self._process(job_id)

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
        pg_assignments = ["updated_at = %s"]
        pg_values: list[Any] = [values[0]]
        if status is not None:
            assignments.append("status = ?")
            values.append(status)
            pg_assignments.append("status = %s")
            pg_values.append(status)
        if progress is not None:
            sanitized_progress = max(0.0, min(1.0, float(progress)))
            assignments.append("progress = ?")
            values.append(sanitized_progress)
            pg_assignments.append("progress = %s")
            pg_values.append(sanitized_progress)
        if result is not None:
            assignments.append("result_json = ?")
            values.append(_json_dumps(result))
            pg_assignments.append("result_json = %s::jsonb")
            pg_values.append(_json_dumps(result))
        if error_text is not None:
            assignments.append("error_text = ?")
            values.append(error_text)
            pg_assignments.append("error_text = %s")
            pg_values.append(error_text)
        if cancel_requested is not None:
            assignments.append("cancel_requested = ?")
            values.append(1 if cancel_requested else 0)
            pg_assignments.append("cancel_requested = %s")
            pg_values.append(cancel_requested)
        if started_at is not None:
            assignments.append("started_at = COALESCE(started_at, ?)")
            values.append(started_at)
            pg_assignments.append("started_at = COALESCE(started_at, %s)")
            pg_values.append(started_at)
        if finished_at is not None:
            assignments.append("finished_at = ?")
            values.append(finished_at)
            pg_assignments.append("finished_at = %s")
            pg_values.append(finished_at)
        if self.storage_backend == "postgres":
            pg_values.append(job_id)
            with connect_core_db() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(f"UPDATE platform_jobs SET {', '.join(pg_assignments)} WHERE id = %s", pg_values)
                conn.commit()
            return
        values.append(job_id)
        with self._connect() as conn:
            conn.execute(f"UPDATE jobs SET {', '.join(assignments)} WHERE id = ?", values)
            conn.commit()

    def delete_terminal_jobs(self, *, status: str, prefix: str | None = None, workspace_id: str | None = None) -> int:
        if status not in {"failed", "succeeded"}:
            raise HTTPException(status_code=400, detail="Only failed or succeeded jobs can be cleared.")
        scoped_workspace_id = active_workspace_id(self.data_root) if workspace_id is None else workspace_id
        if self.storage_backend == "postgres":
            clauses = ["status = %s"]
            values: list[Any] = [status]
            if scoped_workspace_id and scoped_workspace_id != "__all__":
                clauses.append("workspace_id = %s")
                values.append(scoped_workspace_id)
            if prefix:
                clauses.append("job_type LIKE %s")
                values.append(f"{prefix}%")
            where = " AND ".join(clauses)
            with connect_core_db() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(f"SELECT id FROM platform_jobs WHERE {where}", values)
                    job_ids = [row["id"] for row in cursor.fetchall()]
                    if not job_ids:
                        return 0
                    cursor.execute("DELETE FROM platform_jobs WHERE id = ANY(%s)", (job_ids,))
                conn.commit()
            return len(job_ids)
        clauses = ["status = ?"]
        values = [status]
        if scoped_workspace_id and scoped_workspace_id != "__all__":
            clauses.append("workspace_id = ?")
            values.append(scoped_workspace_id)
        if prefix:
            clauses.append("job_type LIKE ?")
            values.append(f"{prefix}%")
        where = " AND ".join(clauses)
        with self._connect() as conn:
            rows = conn.execute(f"SELECT id FROM jobs WHERE {where}", values).fetchall()
            job_ids = [row["id"] for row in rows]
            if not job_ids:
                return 0
            placeholders = ",".join("?" for _ in job_ids)
            conn.execute(f"DELETE FROM job_events WHERE job_id IN ({placeholders})", job_ids)
            conn.execute(f"DELETE FROM jobs WHERE id IN ({placeholders})", job_ids)
            conn.commit()
        return len(job_ids)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _job_from_row(row: Any) -> dict[str, Any]:
        return {
            "id": _row_get(row, "id"),
            "job_type": _row_get(row, "job_type"),
            "status": _row_get(row, "status"),
            "progress": float(_row_get(row, "progress")),
            "payload": _json_loads(_row_get(row, "payload_json"), {}),
            "result": _json_loads(_row_get(row, "result_json"), {}),
            "error_text": _row_get(row, "error_text"),
            "cancel_requested": bool(_row_get(row, "cancel_requested")),
            "workspace_id": _row_get_optional(row, "workspace_id", DEFAULT_WORKSPACE_ID) or DEFAULT_WORKSPACE_ID,
            "created_at": _row_get(row, "created_at"),
            "updated_at": _row_get(row, "updated_at"),
            "started_at": _row_get(row, "started_at"),
            "finished_at": _row_get(row, "finished_at"),
        }

    @staticmethod
    def _event_from_row(row: Any) -> dict[str, Any]:
        return {
            "id": int(_row_get(row, "id")),
            "job_id": _row_get(row, "job_id"),
            "event_type": _row_get(row, "event_type"),
            "message": _row_get(row, "message"),
            "progress": _row_get(row, "progress"),
            "payload": _json_loads(_row_get(row, "payload_json"), {}),
            "created_at": _row_get(row, "created_at"),
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


def _sse(event: str, payload: dict[str, Any], *, event_id: int | None = None) -> str:
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    lines.append(f"data: {_json_dumps(payload)}")
    return "\n".join(lines) + "\n\n"


@router.post("", response_model=JobCreateResponse, status_code=202)
async def create_job(payload: JobCreateRequest, request: Request) -> JobCreateResponse:
    manager = get_job_manager(request)
    job = await manager.create_job(payload.job_type, payload.payload, workspace_id=payload.workspace_id)
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


@router.get("/{job_id}/events/stream")
async def stream_job_events(job_id: str, request: Request, after_id: int = 0) -> StreamingResponse:
    manager = get_job_manager(request)
    manager.get_job(job_id)

    async def event_stream():
        last_id = max(0, int(after_id))
        yield _sse("snapshot", {"job": manager.get_job(job_id)})
        while True:
            if await request.is_disconnected():
                break
            events = manager.list_events(job_id, after_id=last_id)
            for event in events:
                last_id = max(last_id, int(event["id"]))
                yield _sse("job_event", {"event": event}, event_id=int(event["id"]))
            job = manager.get_job(job_id)
            if job["status"] in TERMINAL_STATUSES and not manager.list_events(job_id, after_id=last_id):
                yield _sse("snapshot", {"job": job})
                break
            await manager.wait_for_event(job_id, timeout_s=15)
            yield ": keep-alive\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
