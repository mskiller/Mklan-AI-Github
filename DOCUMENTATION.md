# Mklan Studio Documentation

Version: current local platform documentation
Last verified: 2026-05-25
Status: working local-first studio stack

Mklan Studio is a local AI media workspace. It combines the original Wildcard
Workshop and Movie Script tools with newer modules for SDXL LoRA training,
ComfyUI/KoboldCPP generation, Media Indexer gallery browsing, SillyTavern card
creation, shared jobs, workflow rendering, workspace profiles, and runtime
preflight checks.

The project is designed for a trusted local machine or LAN. It is not hardened
as a public multi-user service. V2 Phase 1 adds local Docker infrastructure for
dedicated Studio Postgres, Redis, and an ARQ worker, but keeps legacy module
SQLite data paths active while migration validation continues. V2 Phase 2 adds
the first engine layer: workspace profiles, ComfyUI workflow templates, model
families for Training, caption styles, and the global Copilot alpha.

## Where The Project Is Now

The current app is a single React frontend served by Nginx and backed by a
FastAPI platform. Docker Compose can run the core Studio stack, optional
SillyTavern, and an optional Media Indexer profile with PostgreSQL/pgvector.

Verified locally on 2026-05-25:

- Backend Training/Generation/V2 platform targeted tests: `33 passed`.
- Frontend production build: `npm run build` passed.
- Docker rebuild/restart: `backend` and `frontend` verified.
- Runtime endpoints: `/health`, `/api/studio/manifest`,
  `/api/studio/preflight`, `/api/jobs/overview`, and `/` returned HTTP 200.
- Browser QA: Dashboard, Training Caption Scan, and Training Model Settings
  checked on desktop; Dashboard and Training checked on mobile screenshots.
- Real SDXL LoRA smoke run: one CUDA training step completed and saved
  `data/models/loras/codex-real-smoke-lora/codex-real-smoke-lora.safetensors`.

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
  FastAPI app, local SQLite stores, shared V2 job manager, file-backed data
  |
  +-- optional host ComfyUI:    http://host.docker.internal:8188
  +-- optional host KoboldCPP:  http://host.docker.internal:5001/v1
  +-- optional SillyTavern:     http://sillytavern:8000
```

### Services

| Service | Default port | Purpose |
|---|---:|---|
| `frontend` | `5173` | Nginx-served React app. |
| `backend` | `8080` | FastAPI platform for Studio, Training, Generation, Jobs, Assets, Workflows, Wildcards, Movie, and Cards. |
| `studio_worker` | internal | ARQ worker for shared V2 jobs when `STUDIO_JOBS_BACKEND=arq`. |
| `studio_db` | internal | Dedicated Studio PostgreSQL + pgvector for V2 platform jobs, events, assets, and audit data. |
| `studio_redis` | internal | Redis broker and event bus for ARQ jobs and live job notifications. |
| `sillytavern` | `8011` | Local SillyTavern runtime used by the Cards module. |
| `media_indexer_backend` | `8000` | Optional Media Indexer API for Gallery and Training imports. |
| `media_db` | internal | PostgreSQL + pgvector for Media Indexer. |
| `media_worker` | internal | Background scanner and enrichment worker. |

## Frontend Routes

| Route | Page | Status |
|---|---|---|
| `/` | Dashboard | Implemented. |
| `/training` | Training | Implemented. |
| `/generation` | Generation | Implemented. |
| `/gallery` | Gallery | Implemented with Media Indexer proxy. |
| `/wildcards/*` | Wildcard Workshop | Implemented. |
| `/movie/*` | Movie Script | Implemented. |
| `/cards/*` | SillyTavern Cards | Implemented. |
| `/settings` | Studio Settings | Implemented. |

## Application Modules

### Dashboard

The Dashboard is the Studio control center. It calls the backend manifest,
preflight, and job overview APIs to show:

- Active modules and routes.
- Runtime readiness checks.
- Connection warnings for optional services.
- Shared V2 job queue summary.
- Quick actions into Training, Generation, Gallery, Wildcards, Movie, Cards,
  and Settings.

### Training

The Training page is focused on local LoRA and related fine-tuning workflows
across SD 1.5, SDXL, Pony-style SDXL, and Flux profiles.
Implemented tabs:

- Dataset Setup
- Dataset Review
- Caption Scan
- Model Settings
- Training Runs
- Save Models

Implemented dataset tools:

- Create datasets under `data/training/datasets`.
- Upload images.
- Upload a ready dataset ZIP containing image/caption pairs.
- Import images from Media Indexer collections.
- Review every image and caption side by side.
- Save per-image caption edits.
- Add a trigger word to the beginning of captions.
- Export a dataset as ZIP with normalized paired files:
  `001.png`, `001.txt`, `002.png`, `002.txt`, and so on.

Implemented caption scan tools:

- Scan a dataset and generate captions.
- Configure maximum caption words.
- Choose the caption provider: `auto`, local BLIP, KoboldCPP/vLLM, CLIP tagger,
  or filename fallback.
- Choose the caption style: SDXL tags, Pony tags, or natural language for Flux.
- Select a discovered local BLIP model from `data/models/captioning`.
- Select a CLIP tag model for tag scoring:
  `OysterQAQ/DanbooruCLIP`, `laion/CLIP-ViT-B-32-laion2B-s34B-b79K`,
  `patrickjohncyh/fashion-clip`, or `openai/clip-vit-large-patch14`.
- Record per-image diagnostics.
- Report caption source counts, including skipped existing captions, local BLIP,
  KoboldCPP/vLLM, CLIP tagger, and filename fallback.
- Fall back to filename-based captions only when the selected image caption
  provider is unavailable or explicitly selected.

Caption model storage:

- Put local BLIP models in `data/models/captioning/<model-folder>`. The Training
  page discovers folders that contain a BLIP `config.json`.
- BLIP folders with `model.safetensors` use safetensors. BLIP folders with only
  `pytorch_model.bin` are supported for local trusted model folders through a
  direct state-dict load, which avoids the Transformers torch-load guard that
  appears with torch versions below 2.6.
- CLIP models can be downloaded with
  `python scripts/download_caption_models.py --models danbooru-clip fashion-clip openai-clip-large laion-clip`.
- CLIP tagger captions are not free-form descriptions. The model ranks candidate
  tags from `STUDIO_CAPTION_CLIP_TAGS_PATH`; the bundled default vocabulary is
  `backend/app/resources/caption_tags_default.txt`, and the downloader can copy
  it to `data/models/captioning/tag_vocab/default_tags.txt`.
- LAION's CLIP model uses OpenCLIP and requires the GPU backend dependency
  `open_clip_torch`, now included in `backend/requirements-gpu.txt`.

Implemented training tools:

- Queue training runs.
- Preview generated trainer command/configuration.
- Cancel queued or running jobs.
- Track run status and artifacts.
- Save produced LoRA artifacts under the Studio model folders.
- Select base checkpoints from `data/models/images/Base`,
  `data/models/images/Pony`, `data/models/images/Flux`,
  `data/models/images/SD15`, or the image model root.
- Select SDXL VAE files from `data/models/images/VAE`.
- Edit max training steps directly while still showing the calculated dataset
  steps.
- Show trainer readiness and whether Docker has forced dry-run mode.
- Responsive Training panels avoid horizontal overflow on desktop and mobile
  browser sizes.

Implemented model settings:

- Model family selector for SD 1.5, SDXL, SDXL Pony, and Flux.
- Base model and optional VAE selectors backed by local `.safetensors`
  inventory.
- Presets for SD 1.5 LoRA, SDXL LoRA, SDXL Pony LoRA, SDXL fine-tune, Flux
  LoRA, Anima, and Z-Image style workflows.
- Epochs, repeats, max train steps, resolution, and seed.
- LoRA type: `lora`, `locon`, `loha`, `lokr`.
- Bucket options, shuffle captions, keep tokens, clip skip, and flip
  augmentation.
- UNet/text encoder learning rates, scheduler, scheduler cycles, optimizer,
  mixed precision, save interval, sample prompt, min SNR gamma, network
  dimension, network alpha, and noise offset.
- Model component mapping and extra trainer arguments for advanced workflows.

Real GPU training requires the GPU backend image and the trainer path configured
through environment variables. Flux LoRA uses a guarded SimpleTuner-compatible
command path through `STUDIO_SIMPLETUNER_ROOT` or `STUDIO_FLUX_TRAIN_SCRIPT`.

### Generation

The Generation page provides:

- Local LLM chat through an OpenAI-compatible endpoint.
- Wildcard prompt preview and expansion.
- ComfyUI workflow template selection from
  `data/integrations/comfyui/workflow_templates`.
- Image generation jobs through Studio settings and ComfyUI-compatible flows.
- Generated image browsing.
- Job statistics and cleanup.

Generation jobs use the shared V2 job infrastructure where possible, so the
Dashboard and `/api/jobs/*` APIs can see queued and completed work.

### Workspaces And Copilot

Workspace profiles are available through the top bar and persist either in
Studio Postgres or `data/platform_workspaces.json` when the SQLite fallback path
is active. New jobs, generated assets, and audit records carry a `workspace_id`
so Phase 2 data can be filtered without cutting over legacy module SQLite stores.

The Copilot alpha is available globally from the shell. It builds context from
the active route, active workspace, current UI selection, and configured LLM or
image integrations. If no LLM endpoint is configured, it returns deterministic
module-aware fallback guidance instead of failing.

### Gallery

The Gallery page is backed by the optional Media Indexer profile. It provides:

- Source registration and scanning.
- Browse/search/filter over indexed media.
- Metadata and prompt inspection.
- Collections.
- Compare and deep-zoom style image viewing.
- Workflow export from images with embedded metadata.
- Scan modes, including SillyTavern card detection.

When a source contains SillyTavern cards, the scan can parse card information
and expose it in the image details UI. The card data can then be exported toward
the SillyTavern card creator workflow.

### Wildcards

Wildcard Workshop remains available under `/wildcards/*`. Implemented tools:

- Scan wildcard source files.
- Browse, filter, edit, and tag wildcard entries.
- Build prompts from wildcard slots.
- Save prompt recipes.
- Run image sandbox generation.
- Review duplicates.
- Run local LLM assistant jobs for cleanup or conversion tasks.
- Export wildcard libraries and prompt packages.
- Create backups.

### Movie Script

The Movie module remains available under `/movie/*`. Implemented tools:

- Project and scenario management.
- Character roster and portrait handling.
- Beat board and scene planning.
- Scene prompts and continuity review.
- Image generation jobs.
- Sequence and video prompt planning.
- WAN/video job plumbing.
- Prompt package and assembly export tools.

### SillyTavern Cards

The Cards module remains available under `/cards/*`. Implemented tools:

- Scenario, character, lore, and user/persona editing.
- GM cards and supporting images.
- Compatibility checks.
- Project vault reuse.
- Export and sync paths for SillyTavern.

### Settings

The Settings page provides:

- LLM provider settings.
- ComfyUI/image provider settings.
- Connection tests.
- Uploaded model inventory.
- Model upload.
- Image sandbox generation.

The old `ComfyNodes` visual workflow component still exists in the source tree,
but it is not part of the current top-level navigation. The active workflow
integration is through backend workflow presets, validation, rendering jobs, and
stored workflow JSON settings.

## Backend API Map

| Prefix | Purpose |
|---|---|
| `/health` | Basic backend health. |
| `/api/studio/*` | Settings, manifest, preflight, model upload, generated images, semantic search, image sandbox. |
| `/api/jobs/*` | Shared V2 job create/read/cancel/events/overview plus SSE stream at `/api/jobs/{job_id}/events/stream`. |
| `/api/workspaces/*` | Workspace profile list/create/activate/update APIs. |
| `/api/copilot/*` | Context-aware Copilot alpha APIs. |
| `/api/training/*` | Dataset setup, caption review, caption scan, training queue, artifacts. |
| `/api/generation/*` | Chat, wildcard preview, image jobs, generated images. |
| `/api/assets/*` | Generated asset registry, provenance, Media Indexer sync. |
| `/api/workflows/*` | ComfyUI workflow presets, validation, queued render jobs. |
| `/api/canon/*` | Shared canon/entity export pack plumbing. |
| `/api/suggester/*` | Prompt suggestion helper. |
| `/wildcards/*` and `/wildcards/api/*` | Wildcard Workshop API and compatibility prefix. |
| `/movie/*` | Movie Script API. |
| `/cards/*` | SillyTavern Cards sub-application API. |
| `/generated/*` | Static generated image files. |

Important Studio endpoints:

```text
GET  /api/studio/manifest
GET  /api/studio/preflight
GET  /api/jobs/overview
GET  /api/workspaces
POST /api/copilot/chat
GET  /api/workflows/presets
POST /api/workflows/validate
POST /api/workflows/render
```

## Data And Storage

Mutable data lives under `data/` and is mounted into the containers.

```text
data/
  cards/                  SillyTavern card creator database and assets
  exports/                Wildcard and prompt exports
  generated/              Generated images and metadata
  integrations/comfyui/   Local ComfyUI custom nodes and workflow templates
  models/captioning/      BLIP/CLIP caption models and CLIP tag vocabularies
  media_previews/         Media Indexer preview files
  models/images/          Uploaded checkpoints and image models
  models/images/Base/     SDXL base checkpoints selectable in Training
  models/images/Flux/     Flux checkpoints selectable in Training
  models/images/Pony/     Pony checkpoints selectable in Training
  models/images/SD15/     SD 1.5 checkpoints selectable in Training
  models/images/VAE/      SDXL VAE files selectable in Training
  models/loras/           Saved LoRA outputs
  movie/                  Movie Script database and assets
  postgres/               Media Indexer PostgreSQL data
  studio_postgres/        Studio PostgreSQL data
  training/               Training datasets, configs, runs, artifacts
  wildcards/              Wildcard source files and database
```

Back up `data/` before large migrations, source rescans, or trainer changes.

## Configuration

Start from `.env.example`:

```powershell
cp .env.example .env
```

Key configuration groups:

- `STUDIO_*`: shared backend data root, CORS, API key, upload limits, caption
  scan provider/model behavior, CLIP tagger vocabulary, trainer paths, V2
  database URL, Redis URL, and job backend selection.
- `STUDIO_JOBS_BACKEND`: `arq` for Docker Redis/worker execution, or `sqlite`
  to roll back to the previous in-process queue path.
- `STUDIO_DATABASE_URL`: enables dedicated Studio Postgres platform tables.
  Leave empty with `STUDIO_JOBS_BACKEND=sqlite` for local fallback.
- `STUDIO_REDIS_URL`: Redis broker/event URL used by ARQ and live job streams.
- `STUDIO_TRAINING_DRY_RUN`: when `true`, queued training jobs only write a
  command log and placeholder artifact. The Docker default is now `false` so
  Training can run real sd-scripts jobs when the GPU backend is available.
- `WILDCARD_*`: wildcard source, database, and export folders.
- `MOVIE_*`: movie data, LLM provider, ComfyUI provider, and model folders.
- `CARDS_*` and `SILLYTAVERN_*`: card database and SillyTavern integration.
- `COMFYUI_CUSTOM_NODES_DIR`: bundled custom node path.
- `MEDIA_INDEXER_*`: Media Indexer database, security, and generated asset sync.

Change default secrets before exposing any service beyond a trusted local
machine.

## ComfyUI Integration

Current ComfyUI support includes:

- Connection testing through Studio settings.
- Stored API-format workflow JSON.
- Placeholder injection for prompts, dimensions, seed, sampler, scheduler,
  model, CFG, steps, and denoise.
- Built-in fallback txt2img workflow.
- Studio image generation through `/api/studio/generate-image`.
- Workflow preset listing, validation, and queued rendering through
  `/api/workflows/*`.
- Use from Wildcards, Generation, Training previews, and Movie media jobs where
  applicable.

See `plans/v2-comfyui-image-generator.md` for current status and next work.

## Development Commands

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

Docker:

```powershell
docker compose up -d --build
docker compose --profile media-indexer up -d --build
```

## Verification Commands

```powershell
cd backend
C:\Python314\python.exe -m pytest tests\test_ai_training_generation.py tests\test_v2_platform.py
```

```powershell
cd frontend
npm run build
```

```powershell
curl.exe -s -o NUL -w "%{http_code}" http://localhost:8080/health
curl.exe -s -o NUL -w "%{http_code}" http://localhost:8080/api/studio/manifest
curl.exe -s -o NUL -w "%{http_code}" http://localhost:8080/api/studio/preflight
curl.exe -s -o NUL -w "%{http_code}" http://localhost:8080/api/jobs/overview
curl.exe -s -o NUL -w "%{http_code}" http://localhost:5173/
```

## Known Boundaries

- The app is local-first. Add stronger reverse proxy auth before exposing it
  outside a trusted environment.
- Optional external services must be running separately: ComfyUI, KoboldCPP or
  another OpenAI-compatible LLM, and Media Indexer if Gallery scanning is needed.
- Real training requires GPU support and a configured sd-scripts installation.
- Caption scan can use a local BLIP model, a KoboldCPP/vLLM OpenAI-compatible
  vision chat endpoint, or CLIP tag scoring. Set
  `STUDIO_CAPTION_ALLOW_DOWNLOAD=true` once to let the backend download a BLIP
  model, or put BLIP folders under
  `/app/data/models/captioning/blip-image-captioning-base`. Set
  `STUDIO_CAPTION_PROVIDER=koboldcpp_vlm` to force the KoboldCPP/vLLM path or
  `STUDIO_CAPTION_PROVIDER=clip_tagger` to force CLIP tag scoring. Filename
  fallback remains available but is intended as a last resort.
- Media Indexer is documented separately under `media-indexer/README.md`.
- Some frontend modules are still large workspaces and should be split as the
  platform grows.
- Broader E2E coverage should be added around mobile Gallery inspection,
  dataset ZIP import/export, and real ComfyUI render jobs.

## Documentation Map

- `README.md`: quick overview and current status.
- `DOCUMENTATION.md`: this detailed platform document.
- `CHANGELOG.md`: dated record of modifications and upgrades.
- `.env.example`: environment template.
- `data/README.md`: persistent data layout and backup guidance.
- `backend/migrations/README.md`: legacy database copy helpers.
- `plans/v2-phase-1-local-docker-deploy.md`: V2 Phase 1 local Docker deploy,
  migration dry-run, smoke checks, and rollback instructions.
- `plans/v2-comfyui-image-generator.md`: ComfyUI integration status.
- `media-indexer/README.md`: standalone Media Indexer documentation.
