# Mklan Studio V2 Phase 2 Engine Deploy

Last updated: 2026-05-25

## What This Deploy Adds

Phase 2 builds on the local Docker platform from Phase 1 and adds the first
engine-facing Studio features:

- Workspace profiles with active workspace selection in the Studio shell.
- `workspace_id` persistence for V2 platform jobs, generated assets, and audit
  records.
- ComfyUI workflow template library under
  `data/integrations/comfyui/workflow_templates`.
- Generation workflow preset selection routed through queued image jobs.
- Training model families for SD 1.5, SDXL, SDXL Pony, and Flux.
- Caption styles for SDXL tags, Pony tags, and Flux-friendly natural language.
- Guarded SimpleTuner-compatible Flux LoRA command preview and dry-run path.
- Global context-aware Copilot alpha with deterministic fallback when no LLM is
  configured.

Legacy Wildcards, Movie, Cards, and module SQLite stores remain active. Phase 2
does not cut over those module databases.

## Local Deployment

Back up `data/` first:

```powershell
Copy-Item -Recurse -Force .\data .\data.backup-v2-phase2
```

Run migrations and rebuild the local stack:

```powershell
docker compose up -d --build
docker compose exec backend alembic upgrade head
```

Optional Media Indexer profile:

```powershell
docker compose --profile media-indexer up -d --build
```

## New Data Paths

```text
data/
  integrations/comfyui/workflow_templates/  # seeded and custom workflow JSON
  models/images/SD15/                       # SD 1.5 checkpoints
  models/images/Base/                       # SDXL checkpoints
  models/images/Pony/                       # Pony checkpoints
  models/images/Flux/                       # Flux checkpoints
  platform_workspaces.json                  # JSON fallback workspace profiles
  studio_postgres/                          # Studio Postgres data
```

## New Env Vars

```text
STUDIO_SIMPLETUNER_ROOT=/app/trainers/SimpleTuner
STUDIO_FLUX_TRAIN_SCRIPT=
STUDIO_COPILOT_TIMEOUT_S=8
```

Flux dry-run command preview works without the script existing. A real Flux run
requires `STUDIO_FLUX_TRAIN_SCRIPT` or a SimpleTuner `train.py` path in the GPU
backend image.

## Smoke Checks

```powershell
curl.exe -s http://localhost:8080/api/workspaces
curl.exe -s http://localhost:8080/api/workflows/presets
curl.exe -s http://localhost:8080/api/training/model-families
curl.exe -s -X POST http://localhost:8080/api/copilot/chat `
  -H "Content-Type: application/json" `
  -d "{\"route\":\"/training\",\"module\":\"training\",\"message\":\"phase 2 smoke\"}"
curl.exe -s -o NUL -w "%{http_code}" http://localhost:5173/
```

Training smoke:

1. Open `/training`.
2. Select a model family.
3. Create or select a dataset.
4. Preview a command with dry-run enabled.
5. Queue a dry-run training job and confirm SSE progress updates.

Generation smoke:

1. Open `/generation`.
2. Select a workflow template.
3. Preview wildcards.
4. Queue a ComfyUI image job when ComfyUI is configured.

Workspace smoke:

1. Create a workspace from the top bar.
2. Queue a no-op or dry-run job.
3. Switch back to Default Workspace.
4. Confirm job lists show the active workspace by default.

## Rollback

Set:

```powershell
STUDIO_JOBS_BACKEND=sqlite
STUDIO_DATABASE_URL=
```

Then rebuild/restart the backend. The JSON fallback keeps workspace profile
selection available while shared V2 jobs return to the SQLite path.
