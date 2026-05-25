# Mklan Studio

Mklan Studio is a local-first AI media workspace for prompt libraries, image
generation, SDXL LoRA training, gallery indexing, movie pre-production, and
SillyTavern card creation.

The project ships as a React frontend, a FastAPI backend, Docker Compose
services, and an optional Media Indexer stack. This public repository contains
source code and text-only starter data only. It does not include model weights,
generated media, local databases, personal prompt libraries, credentials, or
machine-specific paths.

## Modules

| Route | Module | Purpose |
|---|---|---|
| `/` | Dashboard | Runtime checks, module status, and shared job overview. |
| `/training` | Training | Dataset setup, caption review, caption scan, and SDXL LoRA job orchestration. |
| `/generation` | Generation | Local LLM chat, wildcard preview, ComfyUI-compatible image jobs, and generated image browsing. |
| `/gallery` | Gallery | Optional Media Indexer-backed browsing, scan management, search, comparison, and metadata inspection. |
| `/wildcards` | Wildcards | Wildcard library scan, editing, prompt building, recipes, exports, and backups. |
| `/movie` | Movie Script | Scenario assistance, characters, beats, scenes, prompts, image/video jobs, and exports. |
| `/cards` | SillyTavern Cards | Project/card builder, compatibility checks, exports, vault reuse, and SillyTavern sync. |
| `/settings` | Settings | LLM, ComfyUI, model inventory, upload, and sandbox settings. |

## Quick Start

Requirements:

- Docker Desktop or Docker Engine with the Compose plugin.
- Node.js 20+ for frontend development outside Docker.
- Python 3.11+ for backend development outside Docker.
- Optional NVIDIA GPU support for real training workloads.

```powershell
cp .env.example .env
scripts\check-env.ps1
docker compose up -d --build
```

Then open:

- Studio UI: `http://localhost:5173`
- Backend health: `http://localhost:8080/health`
- SillyTavern: `http://localhost:8011`

To include the optional Media Indexer profile:

```powershell
docker compose --profile media-indexer up -d --build
```

Media Indexer API health will be available at `http://localhost:8000/health`.

## Development

Backend:

```powershell
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8080
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

The Vite dev server proxies Studio API calls to `http://localhost:8080` and
Media Indexer calls to `http://localhost:8000`.

## Data And Models

Runtime data belongs under `data/`. This repository keeps only README files,
placeholder directories, and a tiny text-only wildcard starter set. The app will
create databases and additional folders on first use.

Bring your own local assets:

- Image checkpoints: `data/models/images/`
- SDXL base checkpoints: `data/models/images/Base/`
- VAE files: `data/models/images/VAE/`
- LoRA outputs: `data/models/loras/`
- Captioning models/cache: `data/models/captioning/`
- Generated images: `data/generated/`
- Training datasets: `data/training/datasets/`

Large local artifacts are intentionally ignored by Git. Do not commit model
weights, generated media, training datasets, databases, or caches.

## Optional Integrations

External services can run on the host and be configured through `.env` or the
Settings page:

- ComfyUI endpoint: `MOVIE_TOOL_COMFY_ENDPOINT`
- OpenAI-compatible LLM or vision endpoint: `MOVIE_TOOL_SCENARIO_ASSISTANT_BASE_URL`
- SillyTavern runtime: included as a Docker service by default.
- Media Indexer: enabled with the `media-indexer` Compose profile.

The public Compose file does not mount your host drives automatically. Add
machine-specific media paths in a local `docker-compose.override.yml`, then keep
that override uncommitted.

## Useful Commands

```powershell
# Public release hygiene scan
scripts\verify-public-release.ps1

# Backend tests
cd backend
python -m pytest tests

# Frontend build
cd ..\frontend
npm run build

# Compose validation
cd ..
docker compose config
```

## Documentation Map

- `DOCUMENTATION.md` - architecture, services, data layout, and public setup notes.
- `.env.example` - sanitized environment template.
- `data/README.md` - runtime storage layout.
- `backend/migrations/README.md` - legacy database copy helpers.
- `media-indexer/README.md` - standalone Media Indexer documentation.
- `plans/v2-comfyui-image-generator.md` - ComfyUI integration planning notes.

## Security Notes

Mklan Studio is designed for a trusted local machine or LAN. Before exposing any
service beyond your own machine, set strong secrets, restrict CORS, configure
reverse-proxy authentication, and review SillyTavern and Media Indexer access
rules.

## License

MIT. See `LICENSE`.
