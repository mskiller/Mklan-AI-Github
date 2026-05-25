# Mklan Studio Documentation

Mklan Studio is a local-first AI media workspace. It combines Wildcard Workshop,
Movie Script tooling, SDXL training orchestration, ComfyUI-compatible generation,
Media Indexer gallery browsing, SillyTavern card creation, shared jobs, workflow
rendering, and runtime preflight checks.

This public copy is intentionally clean: no private `.env`, databases, generated
media, model weights, screenshots, Hugging Face caches, Postgres volume, or
machine-specific host paths are included.

## Runtime Architecture

```text
Browser
  |
  v
frontend container, port 5173
  Nginx serves React and proxies API paths
  |
  +-- /api/media/*  -> media_indexer_backend:8000
  +-- /api/*        -> backend:8080
  +-- /wildcards/*  -> backend:8080
  +-- /movie/*      -> backend:8080
  +-- /cards/*      -> backend:8080
  +-- /generated/*  -> backend:8080

backend container, port 8080
  FastAPI app, local SQLite stores, shared job manager, file-backed data
  |
  +-- optional host ComfyUI endpoint
  +-- optional host OpenAI-compatible LLM/VLM endpoint
  +-- optional SillyTavern service
```

## Services

| Service | Default port | Purpose |
|---|---:|---|
| `frontend` | `5173` | Nginx-served React app. |
| `backend` | `8080` | FastAPI platform for Studio, Training, Generation, Jobs, Assets, Workflows, Wildcards, Movie, and Cards. |
| `sillytavern` | `8011` | Local SillyTavern runtime used by the Cards module. |
| `media_indexer_backend` | `8000` | Optional Media Indexer API for Gallery and Training imports. |
| `media_db` | internal | PostgreSQL + pgvector for Media Indexer. |
| `media_worker` | internal | Background scanner and enrichment worker. |

## Application Modules

- Dashboard: module status, runtime checks, preflight warnings, and shared job overview.
- Training: dataset creation/import, caption review, caption scan providers, model selection, and queued SDXL training runs.
- Generation: local LLM chat, wildcard expansion preview, image generation jobs, and generated image browsing.
- Gallery: optional Media Indexer source management, scan jobs, search, collections, comparison, metadata inspection, and workflow export.
- Wildcards: source scanning, editing, prompt building, generated image sandbox, duplicate review, recipes, and exports.
- Movie Script: scenario assistant, characters, beats, scenes, image/video prompts, continuity review, and prompt package export.
- SillyTavern Cards: project/card builder, lore, personas, GM cards, compatibility checks, exports, and SillyTavern sync.
- Settings: LLM provider, ComfyUI provider, model inventory/upload, and image sandbox configuration.

## Data Layout

Persistent runtime data lives under `data/`:

```text
data/
  cards/                  SillyTavern card creator database and project assets
  exports/                Wildcard and prompt exports
  generated/              Generated images and sidecar metadata
  integrations/comfyui/   Local ComfyUI custom nodes
  media_previews/         Media Indexer preview files
  models/
    captioning/           BLIP/CLIP caption scan models and tag vocabularies
    images/               Uploaded checkpoints and image models
      Base/               SDXL base checkpoints selectable in Training
      VAE/                SDXL VAE files selectable in Training
    loras/                Saved LoRA outputs
    video/                Optional video models
  movie/                  Movie Script SQLite database and assets
  postgres/               Media Indexer PostgreSQL data
  training/
    datasets/             Training datasets with image/caption pairs
    runs/                 Training run configs, logs, and artifacts
  wildcards/              Wildcard source files and wildcard database
```

Only placeholder files and text-only starter wildcard files are committed. The
runtime creates databases and generated output lazily.

## Configuration

Start from `.env.example`:

```powershell
cp .env.example .env
scripts\check-env.ps1
```

Important settings:

- `STUDIO_API_KEY`: optional guard for newer Studio write APIs.
- `STUDIO_TRAINING_DRY_RUN`: keep `true` for command/config previews when no trainer runtime is available.
- `MOVIE_TOOL_SCENARIO_ASSISTANT_BASE_URL`: optional OpenAI-compatible LLM/VLM endpoint.
- `MOVIE_TOOL_COMFY_ENDPOINT`: optional ComfyUI endpoint.
- `MOVIE_TOOL_IMAGE_DEFAULT_MODEL`: blank by default; set to a model filename you provide locally.
- `MEDIA_INDEXER_POSTGRES_PASSWORD` and `MEDIA_INDEXER_SESSION_SECRET`: required before using the Media Indexer profile.

## Host Media Mounts

The public Compose file does not mount host drives automatically. To index local
media, create an uncommitted `docker-compose.override.yml` and add bind mounts to
both Media Indexer services:

```yaml
services:
  media_indexer_backend:
    volumes:
      - type: bind
        source: /absolute/path/to/media
        target: /data/sources/media
        read_only: true
    environment:
      ALLOWED_SOURCE_ROOTS: /data/sources

  media_worker:
    volumes:
      - type: bind
        source: /absolute/path/to/media
        target: /data/sources/media
        read_only: true
    environment:
      ALLOWED_SOURCE_ROOTS: /data/sources
```

Then add `/data/sources/media` as a source in the Gallery or Media Indexer UI.

## Verification

Use these checks before publishing:

```powershell
scripts\verify-public-release.ps1

cd backend
python -m pytest tests

cd ..\frontend
npm install
npm run build

cd ..
docker compose config
```

The release verification script checks for committed secrets, local environment
files, databases, model weights, generated media, screenshots, build outputs,
dependency folders, and common personal path patterns.

## Security Boundaries

This is a trusted-local-machine tool, not a hardened multi-user SaaS product.
Before exposing it to any untrusted network:

- Set strong values for all secrets in `.env`.
- Restrict CORS and bind addresses.
- Add reverse-proxy authentication/TLS.
- Review SillyTavern and Media Indexer access settings.
- Keep `.env`, generated data, databases, and model weights out of Git.
