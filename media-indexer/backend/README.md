# Backend

FastAPI exposes the admin/session API, source management, job status, search, similarity lookup, compare data, and backend-served previews/original media.

## Highlights

- Cookie-backed admin session for browser-friendly image loading
- PostgreSQL full-text search through `asset_search`
- pgvector-backed semantic similarity storage
- Audit log records for source and compare actions
- Media streaming through the API so the browser never reads network shares directly

## Commands

```powershell
pip install -e ./backend[dev]
alembic -c backend/alembic.ini upgrade head
uvicorn media_indexer_backend.main:app --reload --app-dir backend/src
pytest backend/tests
```

