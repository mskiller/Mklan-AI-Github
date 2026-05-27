# Mklan Studio

Mklan Studio is a local AI media workspace for prompt libraries, image generation,
SD/SDXL/Flux LoRA training, gallery indexing, movie pre-production, and
SillyTavern card creation.

The project is now a single React application backed by a FastAPI platform and a
Docker Compose stack. It brings together the original Wildcard Workshop and Movie
Script tools, then adds newer platform modules for Training, Generation, Gallery,
SillyTavern Cards, shared jobs, assets, workflow rendering, and runtime health
checks.

## Current Status

Last verified locally on 2026-05-25:

- Backend targeted tests pass: `33 passed` for training, generation, V2 jobs,
  assets, workflows, and route mounting.
- V2 Phase 1 foundation is prepared for local Docker deployment with dedicated
  `studio_db`, `studio_redis`, and `studio_worker` services. The shared platform
  tables can run on Studio Postgres while legacy module SQLite stores remain
  available as the rollback path.
- V2 Phase 2 engine foundation is implemented with workspace profiles,
  ComfyUI workflow templates, Training model families, caption styles, and the
  global Copilot alpha.
- Frontend production build passes: `npm run build`.
- Docker rebuild and restart verified for `backend` and `frontend`.
- Live endpoints verified: `/health`, `/api/studio/manifest`,
  `/api/studio/preflight`, `/api/jobs/overview`, and the frontend on port `5173`.
- Browser QA verified Dashboard, Training Caption Scan, and Training Model
  Settings on desktop, plus mobile screenshots for Dashboard and Training.
- A real one-step SDXL LoRA smoke run completed locally and produced
  `data/models/loras/codex-real-smoke-lora/codex-real-smoke-lora.safetensors`.

This is a working local studio stack. It is still a local-first tool, not a
locked-down multi-user SaaS product. Do not expose it to an untrusted network
without tightening secrets, API keys, CORS, SillyTavern settings, and reverse
proxy access rules.

## Implemented Modules

| Route | Module | What is implemented |
|---|---|---|
| `/` | Dashboard | Control Center showing modules, runtime checks, preflight warnings, and the shared job queue. |
| `/training` | Training | Dataset creation, image upload, ready-dataset ZIP import/export, media collection import, side-by-side caption review, trigger insertion, provider-based caption scan with selectable BLIP/CLIP/KoboldCPP providers, model family profiles for SD 1.5, SDXL, Pony, and Flux, editable training steps, queued training runs, dry-run previews, and artifacts. |
| `/generation` | Generation | LLM chat, wildcard expansion preview, ComfyUI workflow template selection, ComfyUI/integrated image jobs, generated image gallery, and job cleanup. |
| `/gallery` | Gallery | Media Indexer-backed browsing, source management, scan center, metadata search, collections, comparison, image inspector, workflow export, and SillyTavern card scan mode. |
| `/wildcards` | Wildcards | Wildcard library scan, browse/edit, prompt builder, generated image sandbox, duplicate review, LLM assistant jobs, taxonomy, recipes, export, and backups. |
| `/movie` | Movie Script | Scenario assistant, characters, beat board, scenes, image prompts, image jobs, WAN/video prompts, video jobs, continuity review, prompt package export, and assembly export. |
| `/cards` | SillyTavern Cards | Project/card builder for scenarios, characters, lore, user/persona profiles, GM cards, images, compatibility checks, vault reuse, exports, and SillyTavern sync. |
| `/settings` | Settings | LLM provider settings, ComfyUI/image provider settings, model upload/inventory, and image sandbox. |

## Platform Services

| Service | Default port | Purpose |
|---|---:|---|
| `frontend` | `5173` | Nginx-served React app. |
| `backend` | `8080` | FastAPI platform for Studio, Training, Generation, Jobs, Assets, Workflows, Movie, Cards, and Wildcards. |
| `studio_worker` | internal | ARQ worker for shared V2 jobs when `STUDIO_JOBS_BACKEND=arq`. |
| `studio_db` | internal | Dedicated Studio PostgreSQL + pgvector for V2 platform jobs, events, assets, and audit data. |
| `studio_redis` | internal | Redis broker and event bus for ARQ and live job streams. |
| `sillytavern` | `8011` | Local SillyTavern runtime used by the Cards module. |
| `media_indexer_backend` | `8000` | Optional Media Indexer API used by Gallery and Training collection import. |
| `media_db` | internal | PostgreSQL + pgvector for Media Indexer. |
| `media_worker` | internal | Background scanner/enrichment worker for Media Indexer. |

External services are expected to run on the host when enabled:

- ComfyUI: `http://host.docker.internal:8188`
- KoboldCPP/OpenAI-compatible LLM: `http://host.docker.internal:5001/v1`

## Quick Start

```powershell
cp .env.example .env
docker compose --profile media-indexer up -d --build
```

Then open:

- Studio UI: `http://localhost:5173`
- Backend health: `http://localhost:8080/health`
- Media Indexer API: `http://localhost:8000/health`
- SillyTavern: `http://localhost:8011`

For a lighter stack without Media Indexer:

```powershell
docker compose up -d --build
```

Gallery source scanning and Training collection import need the media-indexer
profile.

## Development

Backend:

```powershell
cd backend
python -m uvicorn app.main:app --reload --port 8080
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

The Vite dev server proxies API calls to:

- `http://localhost:8080` for Studio/Wildcards/Movie/Cards/Training/Generation.
- `http://localhost:8000` for `/api/media/*`.

## Important API Groups

| Prefix | Purpose |
|---|---|
| `/api/studio/*` | Settings, manifest, preflight, model upload, generated images, semantic search. |
| `/api/jobs/*` | Shared V2 job create/read/cancel/events/overview. |
| `/api/jobs/{job_id}/events/stream` | Server-Sent Events stream for live job progress with polling fallback in the UI. |
| `/api/workspaces/*` | Workspace profile list/create/activate/update APIs. |
| `/api/copilot/*` | Context-aware Copilot alpha context and chat APIs. |
| `/api/training/*` | Dataset setup, caption review, caption scan, SDXL training queue, artifacts. |
| `/api/generation/*` | Chat, wildcard preview, image jobs, generated images. |
| `/api/assets/*` | Generated asset registry, provenance, Media Indexer sync. |
| `/api/workflows/*` | ComfyUI workflow presets, validation, queued render jobs. |
| `/api/canon/*` | Canon/entity export pack plumbing for shared platform data. |
| `/api/media/*` | Nginx proxy to Media Indexer. |
| `/wildcards/*` and `/wildcards/api/*` | Wildcard Workshop API and compatibility prefix. |
| `/movie/*` | Movie Script API. |
| `/cards/*` | SillyTavern Cards sub-application API. |

## Data Layout

Persistent data lives under `data/`:

```text
data/
  cards/                  # SillyTavern card creator database and project assets
  exports/                # Wildcard and prompt exports
  generated/              # Generated images and sidecar metadata
  integrations/comfyui/   # Local ComfyUI custom nodes and workflow templates
  media_previews/         # Media Indexer previews
  models/captioning/      # BLIP/CLIP captioning models and tag vocabularies
  models/images/          # Uploaded checkpoints
  models/images/Base/     # SDXL base checkpoints selectable in Training
  models/images/Flux/     # Flux base checkpoints selectable in Training
  models/images/Pony/     # Pony/SDXL Pony checkpoints selectable in Training
  models/images/SD15/     # SD 1.5 checkpoints selectable in Training
  models/images/VAE/      # SDXL VAE files selectable in Training
  models/loras/           # Training outputs
  movie/                  # Movie Script database and assets
  postgres/               # Media Indexer PostgreSQL data
  studio_postgres/        # Studio PostgreSQL data
  training/               # Training datasets, configs, runs
  wildcards/              # Wildcard source files and wildcard database
  platform_workspaces.json # SQLite/JSON fallback workspace profiles
```

The Docker Compose file also mounts common Windows drives `C`, `D`, `E`, `F`,
`H`, `I`, and `J` into the Media Indexer containers as read-only paths under
`/hostfs`. Edit `docker-compose.yml` if your media lives elsewhere.

## Documentation Map

- `DOCUMENTATION.md` - detailed architecture, module inventory, API summary,
  runtime status, and known limitations.
- `CHANGELOG.md` - dated record of modifications and upgrades.
- `.env.example` - complete environment template for local Docker deployment.
- `plans/v2-phase-1-local-docker-deploy.md` - V2 Phase 1 local Docker deployment,
  smoke checks, migration dry-run, and rollback notes.
- `plans/v2-phase-2-engine.md` - V2 Phase 2 engine deployment, smoke checks,
  workspace profiles, workflow templates, model families, and Copilot notes.
- `plans/v2-comfyui-image-generator.md` - current ComfyUI integration status
  and next workflow upgrades.
- `data/README.md` - persistent data layout and backup notes.
- `backend/migrations/README.md` - legacy database copy helpers.
- `media-indexer/README.md` - standalone Media Indexer project documentation.

## Verification Commands

```powershell
# Backend targeted tests
cd backend
C:\Python314\python.exe -m pytest tests\test_ai_training_generation.py tests\test_v2_platform.py

# Frontend build
cd ..\frontend
npm run build

# Runtime smoke checks
cd ..
curl.exe -s -o NUL -w "%{http_code}" http://localhost:8080/health
curl.exe -s -o NUL -w "%{http_code}" http://localhost:8080/api/studio/manifest
curl.exe -s -o NUL -w "%{http_code}" http://localhost:8080/api/studio/preflight
curl.exe -s -o NUL -w "%{http_code}" http://localhost:8080/api/jobs/overview
curl.exe -s -o NUL -w "%{http_code}" http://localhost:5173/
```

## Known Boundaries

- Real training requires the GPU backend image and the sd-scripts trainer
  installed by `backend/Dockerfile.gpu`.
- Caption scan supports provider selection: `auto`, selectable local BLIP,
  KoboldCPP/vLLM vision chat, CLIP tagger, or filename fallback. Local BLIP
  models are discovered under `data/models/captioning`; CLIP tagger supports
  DanbooruCLIP, LAION OpenCLIP, FashionCLIP, and OpenAI CLIP with a configurable
  tag vocabulary. Run
  `python scripts/download_caption_models.py --models danbooru-clip fashion-clip openai-clip-large laion-clip`
  to pre-download supported CLIP models.
- Gallery depends on the Media Indexer profile for mounted source browsing,
  scan jobs, semantic search, and SillyTavern card detection.
- The optional `STUDIO_API_KEY` guard currently protects newer `/api/*` write
  routes. Treat legacy `/wildcards`, `/movie`, and `/cards` routes as local
  trusted-network routes unless additional reverse-proxy auth is added.
- Some frontend modules are still large single-file workspaces. They are
  functional, but future work should split them into smaller components and add
  broader E2E coverage.

## Original Project Roots

Mklan Studio started as a merge and expansion of:

- `Mklan-Wildcard-Management`
- `movie-script-gpt`

The current repository is now the broader local Studio platform described above.
