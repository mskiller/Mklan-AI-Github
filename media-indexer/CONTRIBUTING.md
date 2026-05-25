# Contributing to MKLanLocal

Thank you for your interest in contributing! This is a self-hosted tool built for local network use. Contributions that improve robustness, performance, and usability are very welcome.

## Getting Started

1. Fork the repo and clone your fork.
2. Copy `.env.example` to `.env` and fill in the values.
3. Start the stack: `docker compose -f infra/docker-compose.yml up --build`
4. The backend reloads on file changes (`--reload` in dev mode).

## Project Layout

```
backend/   FastAPI application + Alembic migrations
worker/    Scan worker (metadata, previews, CLIP)
frontend/  Next.js 14 app (App Router, TypeScript)
infra/     Dockerfiles + docker-compose.yml
```

## Code Style

- **Python** — `ruff` for linting, `black`-compatible formatting. Run `ruff check .` before committing.
- **TypeScript** — standard Next.js ESLint config. Run `npm run lint` in `frontend/`.
- No new `any` casts without a comment explaining why.

## Adding a Database Column

1. Create a new migration in `backend/alembic/versions/` using sequential numbering (`0007_...`).
2. Update the SQLAlchemy model in `backend/src/.../models/tables.py`.
3. Update the Pydantic schema in `backend/src/.../schemas/`.
4. Update the TypeScript types in `frontend/lib/types.ts`.

## Running Tests

```bash
cd backend
pytest tests/
```

## Pull Request Checklist

- [ ] `ruff check .` passes (backend)
- [ ] `npm run lint` passes (frontend)
- [ ] New migration file included if schema changed
- [ ] TypeScript types updated to match new API response shapes
- [ ] No credentials or personal paths committed (`bash scripts/check-env.sh` passes)
- [ ] `CHANGELOG.md` updated with a summary of the change

## Security

If you find a security issue, please open a private issue or email the maintainer directly rather than posting a public issue.
