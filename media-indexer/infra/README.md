# Infrastructure

## Local development

The default flow is:

```powershell
docker compose -f infra/docker-compose.yml up --build
```

This boots:

- PostgreSQL with pgvector
- FastAPI backend on `:8000`
- Python worker
- Next.js frontend on `:3000`

## Mounted sources

The dev stack binds [sample_media](/E:/LocalMklan/sample_media) into the containers at `/data/sources/sample`.
To add real mounted shares, add extra bind mounts in [docker-compose.yml](/E:/LocalMklan/infra/docker-compose.yml) and keep `ALLOWED_SOURCE_ROOTS` aligned with the container paths you want the app to accept.

## First-run notes

- The worker downloads the configured CLIP model the first time embeddings are enabled.
- ExifTool and ffmpeg are installed inside the worker image.
- The backend applies Alembic migrations automatically when the container starts.

## Reverse proxy

The MVP Compose stack does not bundle a reverse proxy so the app stays easy to inspect locally. The frontend and backend are designed to sit behind an existing reverse proxy in self-hosted deployments.

