# Mklan Studio V2 Phase 1 Local Docker Deploy

Last updated: 2026-05-25

## What This Deploy Adds

Phase 1 moves the shared V2 platform layer onto deployable local infrastructure
without cutting over legacy module databases.

- Dedicated Studio PostgreSQL/pgvector service: `studio_db`.
- Dedicated Redis broker: `studio_redis`.
- ARQ worker container: `studio_worker`.
- Postgres-backed platform tables for jobs, job events, generated assets, and
  audit events when `STUDIO_DATABASE_URL` is set.
- SSE job event stream at `GET /api/jobs/{job_id}/events/stream`.
- SQLite rollback path through `STUDIO_JOBS_BACKEND=sqlite` and an empty
  `STUDIO_DATABASE_URL`.

Wildcards, Movie, and Cards still use their existing SQLite stores in Phase 1.

## Local Deployment

Back up `data/` first:

```powershell
Copy-Item -Recurse -Force .\data .\data.backup-v2-phase1
```

Start or rebuild the local stack:

```powershell
docker compose up -d --build
```

Optional Media Indexer profile:

```powershell
docker compose --profile media-indexer up -d --build
```

Run Alembic migrations manually when needed:

```powershell
docker compose exec backend alembic upgrade head
```

The backend also creates the same platform tables at startup, so Alembic is the
explicit operational path while startup remains forgiving during local testing.

## Smoke Checks

```powershell
curl.exe -s -o NUL -w "%{http_code}" http://localhost:8080/health
curl.exe -s -o NUL -w "%{http_code}" http://localhost:8080/api/jobs/overview
curl.exe -s -o NUL -w "%{http_code}" http://localhost:5173/
```

Queue a no-op job:

```powershell
curl.exe -s -X POST http://localhost:8080/api/jobs `
  -H "Content-Type: application/json" `
  -d "{\"job_type\":\"system.noop\",\"payload\":{\"smoke\":true}}"
```

Then open the returned job in the SSE stream:

```powershell
curl.exe -N http://localhost:8080/api/jobs/<job-id>/events/stream
```

## Migration Dry Run

Preview source SQLite row counts and target platform table counts:

```powershell
cd backend
python -m migrations.dry_run_core_postgres --data-root ..\data
```

This command does not modify source SQLite databases and does not enable legacy
module cutover.

## Rollback

Set:

```powershell
STUDIO_JOBS_BACKEND=sqlite
STUDIO_DATABASE_URL=
```

Then rebuild/restart the backend. This restores the previous in-process
SQLite-backed job path for local troubleshooting.
