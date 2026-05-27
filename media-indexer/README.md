# MKLanLocal

> A self-hosted media indexer for your local photo and video library.  
> Search, curate, and explore tens of thousands of images — all on your own hardware.

**Stack:** FastAPI · Next.js · PostgreSQL + pgvector · Docker Compose

---

## Screenshots

### Browse Indexed — Gallery view
Browse and curate your entire indexed library with filters, sort options, bulk-select, and collection shortcuts. Hover or long-press any tile for quick actions.

![Browse Indexed gallery view](docs/screenshots/browse-indexed.png)

### Asset Explorer — Detail & Inspector panel
Click any image to open the full-screen explorer with a filmstrip, zoom controls, and an inspector panel showing the prompt, dimensions, file size, and modification date. Stage assets directly for side-by-side comparison.

![Asset explorer with inspector panel](docs/screenshots/explorer-detail.png)

### Scan Jobs — Real-time progress tracking
Monitor all scan jobs in near real time: running, cancelled, and completed — with per-job counters for scanned, new, updated, deleted, and error counts.

![Scan jobs dashboard](docs/screenshots/scan-jobs.png)

---

## What's new in v2.0

- **Platform modules** — Pluggable module system with built-in modules for AI tagging, collections, geo, people, and smart albums. Enable, configure, and inspect each module live from Admin → Modules.
- **Addon / plugin layer** — External addons declared in `addons.toml` and synced via `scripts/sync-addons`. A scaffold for building your own addon lives in `addons/example-addon/`.
- **Smart albums** — Rule-based auto-populating albums refreshed incrementally on every scan.
- **People & faces** — Full face detection, clustering, named-identity management, and a dedicated People browse page.
- **Scheduled scans** — Cron-based auto-scans per source, set up in the Admin UI.
- **Video foundations** — Waveform preview paths and keyframe metadata stored per asset.
- **Inbox & upload review** — Curators review uploaded assets in an inbox before they enter the main library.
- **API tokens & audit log** — Machine-to-machine tokens and a structured audit trail for admin actions.
- **Webhook dispatcher** — Outbound webhooks on post-scan and post-enrichment events.

_Previous highlights (v1.9): Local AI enrichment (WD taggers, BLIP, OCR), Timeline view, Public share links, Collection suggestions, Search enrichment filters._

---

## Features

| | |
|---|---|
| 📁 **Source management** | Mount any number of local folders as named sources |
| 🔍 **Full-text + faceted search** | Filter by camera, year, dimensions, duration, tags, rating, review status |
| 🗓️ **Timeline navigation** | Drill down through year, month, and day for photo-library style browsing |
| 🔁 **Near-duplicate detection** | Perceptual hash (pHash) with configurable threshold |
| 🧠 **Semantic similarity** | CLIP embeddings in pgvector — "find visually similar" on any image |
| 🤖 **Local AI enrichment** | WD taggers, CLIP vocabulary tagging, BLIP captions, and OCR all run locally after initial model download |
| ⚖️ **Side-by-side comparison** | Pixel-locked pan/zoom sync, overlay diff, metadata diff table |
| 🗂️ **Collections** | Named groups; bulk add/remove from gallery or search |
| 🪄 **Collection suggestions** | Generate proposed collections from existing CLIP embeddings in the Admin UI |
| 🔗 **Public sharing** | Time-limited share links for assets or collections with optional download access |
| ⭐ **Asset annotations** | Per-user rating, review status, curator notes, flagged toggle |
| ✅ **Bulk curation** | Multi-select with right-click / long-press context menu |
| 👥 **User management** | Admin / curator / guest roles; groups with fine-grained permissions |
| 🔒 **Lock & ban** | Time-limited locks (auto-lift) or permanent bans with a reason |
| 💾 **Backup & restore** | Streams a ZIP with pg_dump + SHA256 manifest; dry-run supported |
| 🖼️ **BlurHash previews** | Instant placeholders while gallery thumbnails load |
| 🔬 **Deep Zoom viewer** | Tile-based viewer for gigapixel images |
| 📱 **Touch support** | Swipe navigation in the image explorer |
| 📊 **Virtualized gallery** | 10 000+ images with no jank |
| 📋 **Structured JSON logging** | All services emit newline-delimited JSON |

---

## Requirements

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine + Compose plugin)
- 4 GB RAM recommended for the worker (CLIP runs on CPU by default)
- The CLIP model (~600 MB) downloads from HuggingFace on first start and is cached persistently
- Optional local AI enrichment downloads additional Hugging Face assets (WD taggers, embedding pack, caption model) the first time those features are used

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/mskiller/mklanlocal.git
cd mklanlocal

# 2. Create your environment file
cp .env.example .env
```

Open `.env` and set **every value marked `CHANGE_ME`**:

```bash
# Generate a strong session secret
openssl rand -hex 32
# Paste the output as SESSION_SECRET in .env

# Set strong passwords for ADMIN_PASSWORD, CURATOR_PASSWORD, POSTGRES_PASSWORD
```

```bash
# 3. Validate your .env before starting (recommended)
bash scripts/check-env.sh

# 4. (Optional) Mount your media folders — see "Adding Sources" below

# 5. Build and start
docker compose -f infra/docker-compose.yml up --build

# 5. Open the app
open http://localhost:3000
# Log in with your ADMIN_USERNAME / ADMIN_PASSWORD from .env
```

> **First run:** The stack takes ~2–3 minutes to build. The CLIP model downloads on the first scan (~600 MB, cached after that). Subsequent starts are fast.

---

## Adding Sources (Your Media Folders)

Media folders must be bind-mounted into both the `backend` and `worker` containers. Edit `infra/docker-compose.yml` and add your folders in both services:

```yaml
services:
  backend:
    volumes:
      # ... existing volumes ...
      - type: bind
        source: /absolute/path/to/your/photos   # host path
        target: /data/sources/photos            # container path (must start with /data/sources/)
        read_only: true

  worker:
    volumes:
      # ... existing volumes ...
      - type: bind
        source: /absolute/path/to/your/photos   # same host path
        target: /data/sources/photos            # same container path
        read_only: true
```

**Windows paths** use forward slashes or escaped backslashes:

```yaml
source: C:/Users/YourName/Pictures
# or
source: C:\\Users\\YourName\\Pictures
```

After editing the compose file, restart the stack:

```bash
docker compose -f infra/docker-compose.yml up --build
```

Then go to **Admin → Sources → Add Source**, enter the container path (e.g. `/data/sources/photos`), and click **Scan**.

Tip: keep personal bind mounts in a local `infra/docker-compose.override.yml` instead of editing the tracked compose file directly.

---

## Configuration

All settings live in `.env`. The most important ones:

| Variable | Description |
|---|---|
| `SESSION_SECRET` | **Required.** Generate with `openssl rand -hex 32`. Server won't start without it. |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | Seed admin account created on first startup |
| `CURATOR_USERNAME` / `CURATOR_PASSWORD` | Seed curator account |
| `GUEST_USERNAME` / `GUEST_PASSWORD` | Seed guest account (read-only) |
| `POSTGRES_PASSWORD` | Database password |
| `CLIP_ENABLED` | `true` / `false` — disable if you don't need semantic search |
| `CLIP_DEVICE` | `cpu` (default) or `cuda` if you have an NVIDIA GPU |
| `CLIP_MODEL_ID` | HuggingFace model ID (default: `openai/clip-vit-base-patch32`) |
| `MAX_THUMBNAIL_SIZE` | Max thumbnail dimension in pixels (default: `512`) |
| `DUPLICATE_PHASH_THRESHOLD` | Hamming distance for duplicate detection (default: `8`) |

Runtime settings (thumbnail size, CLIP thresholds, cache limits, poll interval) can also be adjusted live via **Admin → Settings** without restarting.

---

## Architecture

```
Browser
  └─▶ Next.js  :3000  (standalone output)
        └─▶ FastAPI  :8000  (proxied via Next.js rewrites)
              ├─▶ PostgreSQL :5432  (pgvector extension)
              └─▶ Worker  (scan · pHash · CLIP · previews · BlurHash)
                    └─▶ Mounted source folders  (read-only)
```

All four services run in Docker. The worker polls for pending scan jobs and processes files asynchronously — the UI stays responsive while large libraries index.

---

## User Roles

| Role | Can do |
|---|---|
| **admin** | Everything: sources, scans, users, groups, settings, backup/restore |
| **curator** | Browse, search, annotate, rate, review, manage collections, upload |
| **guest** | Browse and search only (read-only) |

Groups can override role permissions on a per-source basis (e.g. give a curator access to specific sources only).

---

## GPU Acceleration (optional)

If you have an NVIDIA GPU:

1. Install the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
2. Set `CLIP_DEVICE=cuda` in `.env`
3. Add to the `worker` service in `docker-compose.yml`:

```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: 1
          capabilities: [gpu]
```

---

## Development

### Backend (FastAPI + Python 3.12)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# Start a local Postgres first (or use the Docker one on port 5432)
uvicorn media_indexer_backend.main:app --reload --port 8000
```

Run migrations:

```bash
alembic upgrade head
```

Run tests:

```bash
pytest tests/
```

### Worker

```bash
cd worker
pip install -e .
python -m media_indexer_worker.main
```

### Frontend (Next.js + TypeScript)

```bash
cd frontend
npm install
npm run dev     # http://localhost:3000
npm run lint
npm run build   # production build check
```

---

## Backup & Restore

**Create a backup** (downloads as a ZIP):

```
GET /admin/backup
```

Or from the Admin UI: **Admin → Maintenance → Download Backup**.

The ZIP contains:
- `dump.sql` — full pg_dump
- `manifest.json` — alembic revision, app version, timestamps
- `checksums.sha256` — SHA256 of every file in the archive

**Restore:**

```
POST /admin/restore          # validates checksums then restores
POST /admin/restore?dry_run=true   # validate only, no changes
```

> ⚠️ Restore drops and recreates the database. Back up first.

---

## Upgrading

```bash
git pull
docker compose -f infra/docker-compose.yml up --build
```

Alembic migrations run automatically on backend startup. They are idempotent and safe to re-run.

---

## Security Notes

### Pre-flight check
Run before every first deployment or after editing `.env`:
```bash
bash scripts/check-env.sh
```
This validates that all `CHANGE_ME` placeholders have been replaced and that passwords meet minimum length requirements.

### Secrets & passwords
- `SESSION_SECRET` **must** be set to a strong random value — generate with `openssl rand -hex 32`. The server refuses to start with the default in any non-development environment.
- Passwords are hashed with **Argon2** (argon2-cffi). Plain-text passwords are never stored.
- Login is rate-limited to 10 attempts per minute per IP.

### Network exposure
- **PostgreSQL (port 5432)** is exposed on `0.0.0.0` by default in `docker-compose.yml`. On a LAN-only machine this is usually fine, but you should either restrict it to localhost or remove the port mapping entirely if you don't need direct DB access from outside the container network:
  ```yaml
  # Restrict to localhost only:
  ports:
    - "127.0.0.1:5432:5432"
  ```
- The backend (port 8000) and frontend (port 3000) are similarly LAN-exposed. If you need to serve over the internet, put them behind a reverse proxy (nginx, Caddy, Tailscale) with TLS and set `COOKIE_SECURE=true` in `.env`.

### Source path safety
- File paths are validated against `ALLOWED_SOURCE_ROOTS` on every request — path traversal outside mounted folders is rejected at the application layer.

### Backups
- `GET /admin/backup` produces a ZIP containing `dump.sql` — **this file contains all your data including hashed passwords**. Treat backup files like credentials:
  - Store them encrypted or in an access-controlled location.
  - Do not commit them to git (the `backup/` folder is already in `.gitignore`).
  - Delete old backups you no longer need.
- Backups include a `checksums.sha256` manifest. The restore endpoint validates all checksums before touching the database.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). In short:

1. Fork and clone
2. `cp .env.example .env` and fill in values
3. `docker compose -f infra/docker-compose.yml up --build`
4. Make your changes, run `ruff check .` (backend) and `npm run lint` (frontend)
5. Open a PR with a CHANGELOG entry

---

> **Note from the author:** This project was built with AI assistance (Claude + ChatGPT) as an exploration. The code and docs are a collaborative output — rough around the edges in places, but functional. Feedback and contributions welcome!

## License

MIT — see [LICENSE](LICENSE)
