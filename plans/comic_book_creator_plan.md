# 🎨 Comic Book Creator — Full Project Plan

> A Dockerized, AI-powered comic book creation suite connecting to local KoboldCPP (LLM) and local ComfyUI (image generation), with API LLM fallback support.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Tech Stack](#2-tech-stack)
3. [Architecture](#3-architecture)
4. [Docker Setup](#4-docker-setup)
5. [Module Breakdown](#5-module-breakdown)
   - 5.1 [Scenario Input & Generation](#51-tab-1--scenario-input--generation)
   - 5.2 [Storyboard Builder](#52-tab-2--storyboard-builder)
   - 5.3 [Image Generation](#53-tab-3--image-generation)
   - 5.4 [Comic Editor](#54-tab-4--comic-editor)
   - 5.5 [Review & Export](#55-tab-5--review--export)
6. [LLM Integration Layer](#6-llm-integration-layer)
7. [ComfyUI Integration Layer](#7-comfyui-integration-layer)
8. [Data Model & Project File Structure](#8-data-model--project-file-structure)
9. [API Design (Backend)](#9-api-design-backend)
10. [Frontend Architecture](#10-frontend-architecture)
11. [Implementation Phases & Roadmap](#11-implementation-phases--roadmap)
12. [Directory Structure](#12-directory-structure)
13. [Key Technical Challenges & Solutions](#13-key-technical-challenges--solutions)

---

## 1. Project Overview

**Comic Book Creator** is a fully local, self-hosted web application that guides a user from a raw story idea all the way to a finished, exportable comic book. It leverages:

- A **local LLM** (via KoboldCPP) or any **API-compatible LLM** (OpenAI, Mistral, etc.) for scenario writing and vision checking.
- A **local ComfyUI** instance for AI image generation, supporting both **natural language** and **Danbooru tag** prompting styles.
- A rich in-browser **comic editor** for page layout, speech bubbles, and text formatting.
- Final export to **PDF**, **CBZ**, **PNG** (per page), and **ZIP** (full project with raws).

The entire application runs inside **Docker**, with the frontend served via a web UI and the backend as a REST/WebSocket API server.

---

## 2. Tech Stack

| Layer | Technology | Rationale |
|---|---|---|
| **Frontend** | React + Vite + TypeScript | Fast, component-based UI |
| **UI Components** | Tailwind CSS + shadcn/ui | Clean, accessible design system |
| **Canvas/Editor** | Konva.js / Fabric.js | Rich 2D canvas for comic layout & bubble editing |
| **Backend** | FastAPI (Python) | Async, easy WebSocket support, fast |
| **LLM Client** | KoboldCPP API + OpenAI-compatible SDK | Dual local/API mode |
| **Image Gen Client** | ComfyUI HTTP API + WebSocket | Workflow-based image generation |
| **Database** | SQLite (via SQLModel) | Simple, file-based, no extra container needed |
| **File Storage** | Local volume mounts | All assets stored on host via Docker volumes |
| **Export** | WeasyPrint (PDF) + zipfile + cbz | Native Python libraries |
| **Containerization** | Docker + Docker Compose | Single `docker compose up` launch |

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Network                           │
│                                                                 │
│  ┌──────────────────┐        ┌──────────────────────────────┐  │
│  │   Frontend       │◄──────►│   Backend (FastAPI)          │  │
│  │   React / Vite   │  REST  │   - Project Manager          │  │
│  │   Port: 3000     │  +WS   │   - LLM Orchestrator         │  │
│  └──────────────────┘        │   - ComfyUI Client           │  │
│                              │   - Export Engine            │  │
│                              │   Port: 8000                 │  │
│                              └──────────┬───────────────────┘  │
│                                         │                       │
│              ┌──────────────────────────┼──────────────┐        │
│              │                          │              │        │
│    ┌─────────▼──────────┐   ┌──────────▼──────────┐   │        │
│    │  KoboldCPP (Local) │   │  ComfyUI (Local)    │   │        │
│    │  Host: host.docker │   │  Host: host.docker  │   │        │
│    │  Port: 5001        │   │  Port: 8188          │   │        │
│    └────────────────────┘   └─────────────────────┘   │        │
│              │                                         │        │
│    ┌─────────▼──────────────────────────────────────┐  │        │
│    │  External LLM API (Optional)                   │  │        │
│    │  OpenAI / Mistral / Anthropic / etc.            │  │        │
│    └────────────────────────────────────────────────┘  │        │
│                                                         │        │
│  ┌──────────────────────────────────────────────────┐  │        │
│  │  Persistent Volume: /data                        │  │        │
│  │  - projects/  - exports/  - generated_images/   │  │        │
│  └──────────────────────────────────────────────────┘  │        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Docker Setup

### `docker-compose.yml`

```yaml
version: "3.9"

services:
  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    depends_on:
      - backend
    environment:
      - VITE_API_URL=http://localhost:8000

  backend:
    build: ./backend
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
    environment:
      - KOBOLDCPP_URL=http://host.docker.internal:5001
      - COMFYUI_URL=http://host.docker.internal:8188
      - DATA_DIR=/app/data
      # Optional API keys (leave empty to use local only)
      - OPENAI_API_KEY=
      - MISTRAL_API_KEY=
      - ANTHROPIC_API_KEY=
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

### Notes

- `host.docker.internal` resolves to the host machine, allowing the container to reach KoboldCPP and ComfyUI running natively on the host.
- The `./data` volume persists all projects, images, and exports between container restarts.
- Running `docker compose up --build` is the only command needed to start the full stack.

---

## 5. Module Breakdown

### 5.1 Tab 1 — Scenario Input & Generation

**Goal:** Transform a short user idea into a fully structured comic scenario.

#### UI Elements
- **Project name** field
- **Genre** selector (Action, Horror, Romance, Sci-Fi, Fantasy, Slice-of-Life, etc.)
- **Target length** selector: Short (1–8 pages), Medium (8–24 pages), Long (24–48 pages)
- **Tone** selector (Serious, Humorous, Dark, All-Ages, etc.)
- **Scenario idea** — large text area (free input, a few sentences to a paragraph)
- **LLM provider selector** — KoboldCPP Local / API (dropdown with configured providers)
- **Generate Scenario** button
- **Results panel** — editable structured output divided into:
  - **Synopsis** (overall story summary)
  - **Characters** (name, role, visual description)
  - **Acts** (e.g., Act 1 / 2 / 3)
  - **Scenes** (within each act, with location and mood)
  - **Sequences** (atomic story beats within each scene — these map 1:1 to comic pages/panels)

#### LLM Prompting Strategy
The backend sends a structured system prompt instructing the LLM to output valid JSON:

```
System: You are a professional comic book scriptwriter. Given a story idea, produce a complete comic scenario in JSON format with the following structure:
{
  "synopsis": "...",
  "characters": [...],
  "acts": [
    {
      "title": "...",
      "scenes": [
        {
          "location": "...",
          "mood": "...",
          "sequences": [
            {
              "id": "seq_001",
              "description": "...",
              "dialogue": [...],
              "action": "..."
            }
          ]
        }
      ]
    }
  ]
}
Return only valid JSON. No markdown, no preamble.
```

#### Editing
- All generated content is fully editable in place (rich text or simple fields)
- User can add/remove/reorder acts, scenes, and sequences manually
- "Regenerate" button per section (regenerate just that part)
- **Save & Continue** locks the scenario and advances to Tab 2

---

### 5.2 Tab 2 — Storyboard Builder

**Goal:** Plan the visual layout of the comic before generating any images.

#### UI Elements
- Page grid view — each card represents one comic page
- Each page contains one or more **sequences** (assigned from Tab 1)
- **Panel layout picker** per page: predefined templates (1 panel full, 2×1, 1×2, 3 across, 2+1, magazine layout, etc.)
- **Image ratio** indicator per panel (1:1, 4:3, 16:9, 2:3 portrait, 3:4, etc.) — recommended by LLM, editable
- **Key image suggestion** per panel — a short visual description generated by LLM
- **Visual style** global settings (manga B&W, western color, semi-realistic, etc.) — used to prefix all image prompts later

#### Storyboard Generation Flow
1. LLM receives all sequences and outputs a storyboard JSON:
   - Page assignments
   - Panel layout per page
   - Key image description per panel (visual action moment)
   - Suggested image ratio per panel
2. User reviews, drags panels to reorder, adjusts layouts
3. Character visual references (text descriptions from Tab 1) are attached to the project for prompt consistency

#### Drag & Drop
- Pages can be reordered
- Sequences can be moved between pages
- Panel layout can be changed at any time (reverts generated image assignments)

#### Save & Continue
- Locks page/panel structure
- Moves to Tab 3 with all panels ready for prompt generation

---

### 5.3 Tab 3 — Image Generation

**Goal:** Generate all comic panel images via ComfyUI, one by one, with review.

#### Sub-Sections

##### 3.1 — Global Generation Settings
- **Prompting mode**: Natural Language | Danbooru Tags
- **Model selector**: dropdown populated from ComfyUI available checkpoints
- **LoRA/embedding manager**: add character LoRAs, style embeddings
- **Global style prefix**: e.g., `"comic book art, ink lines, flat colors"` or `"masterpiece, best quality, 1girl"`
- **Negative prompt global**: shared base negative across all panels
- **Sampler / Steps / CFG / Seed** defaults
- **ComfyUI workflow selector**: use a built-in workflow template or upload a custom `.json`

##### 3.2 — Panel Prompt Editor
Each panel shows:
- The storyboard key image description (from Tab 2) as a reference
- **Generated prompt** (auto-built from scene description + character refs + style + prompting mode)
- Fully editable prompt text area
- Per-panel **negative prompt** (inherits global, overridable)
- Per-panel model override option
- **Generate** button (single panel)
- **Status badge**: Pending / Generating / Review / Approved / Rejected

##### 3.3 — Generation Queue
- **Generate All** button: queues all pending panels
- Progress bar and panel-by-panel status
- WebSocket connection to backend for real-time updates
- Estimated time remaining

##### 3.4 — Review Mode
After generation, each panel enters review:

**Option A — Manual Review**
- Full-size preview
- Approve ✅ / Reject & Regenerate 🔄 / Reject & Edit Prompt ✏️

**Option B — Vision Auto-Review** (if a vision-capable LLM is configured)
- Backend sends panel image + original sequence description to vision LLM
- LLM returns pass/fail + reasoning
- Score shown to user; user can override

##### 3.5 — Variation & Inpainting
- Re-roll with new seed
- Generate 2–4 variations (grid view, pick one)
- Optional: inpaint area (send mask + image back to ComfyUI img2img workflow)

---

### 5.4 Tab 4 — Comic Editor

**Goal:** Assemble approved images into comic pages and add speech bubbles, captions, and text.

#### Page Canvas (Konva.js / Fabric.js)
- Each page rendered at A4/Letter/custom resolution on an HTML5 canvas
- Generated images placed and auto-fitted into their panel slots (respecting crop/fit rules)
- Image pan & zoom within panel (double-click to enter crop mode)
- Panel border thickness and style (none, thin, thick, custom color)
- Page background color

#### Speech Bubble Toolbox
- **Bubble types**: Round, Thought (cloud), Rectangular (caption box), Jagged (shout/explosion), Whisper (dashed border), Narrative box
- Click-to-place on canvas
- Resize handles
- Tail direction: drag anchor point to position the tail toward the speaker
- Bubble fill color & border color
- **Text inside bubble**:
  - Font family selector (bundled comic fonts: Bangers, Comic Neue, Anime Ace, Komika, etc.)
  - Font size
  - Bold / Italic / Underline / All Caps
  - Text alignment (center default)
  - Letter spacing
  - Auto-text-resize to fit bubble

#### Caption / Narration Boxes
- Flat rectangle (no tail)
- Positioned at top or bottom of panel
- Same text editing options as bubbles

#### Layer Management
- Layers panel: images (bottom), panel borders, speech bubbles, captions (top)
- Show/hide layers
- Lock layers

#### Undo / Redo
- Full undo/redo stack (Ctrl+Z / Ctrl+Y)

#### Auto-populate Dialogues
- Button: "Fill dialogue from scenario" — pulls dialogue strings from Tab 1 sequences and pre-populates bubbles (user then positions them)

---

### 5.5 Tab 5 — Review & Export

**Goal:** Final full-comic review and multi-format export.

#### Review Panel
- Full comic reader view: click through pages like a real comic
- Page thumbnails strip at bottom
- Last chance to jump back to edit any page (opens Tab 4 on that page)

#### Export Options

| Format | Description |
|---|---|
| **PDF** | All pages combined, print-ready, configurable DPI (150 / 300 dpi), A4 / Letter / Custom size |
| **CBZ** | Comic Book Archive (ZIP of numbered PNG pages), compatible with all comic readers |
| **PNG per page** | Export each page individually as a full-resolution PNG |
| **ZIP (full project)** | All rush/raw generated images + final page PNGs + project JSON file + all prompts |

#### Export Settings
- DPI selector
- Page size selector
- Color profile (RGB / CMYK hint for print)
- Filename prefix
- Include metadata (title, author, creation date) embedded in PDF

#### Project Save/Load
- Save project to a `.cbc` file (Comic Book Creator project — JSON + asset refs zipped)
- Load existing `.cbc` project from disk
- Auto-save every N minutes (configurable)

---

## 6. LLM Integration Layer

### Abstraction Interface

The backend exposes a unified `LLMClient` class with a single `complete(prompt, system, json_mode)` method, routing to the configured provider.

### Supported Providers

| Provider | Type | Notes |
|---|---|---|
| **KoboldCPP** | Local | HTTP POST to `/api/v1/generate` or `/v1/chat/completions` (OpenAI-compat mode) |
| **OpenAI** | API | GPT-4o, GPT-4-turbo, etc. |
| **Mistral AI** | API | Mistral Large, etc. |
| **Anthropic** | API | Claude 3.5+, supports vision |
| **LM Studio** | Local | OpenAI-compat endpoint |
| **Ollama** | Local | OpenAI-compat endpoint |
| **Any OpenAI-compat** | Local/API | Custom base URL + API key |

### Vision Support
- If selected provider supports vision (GPT-4o, Claude, LLaVA via KoboldCPP), panel review and character consistency checks can use it.
- Backend detects vision capability from provider config.

### Configuration UI
- Settings page / modal in the app
- Test connection button per provider
- Active provider badge visible in every LLM-dependent tab

---

## 7. ComfyUI Integration Layer

### Connection
- Backend connects to ComfyUI via HTTP REST + WebSocket (port 8188 default, configurable)
- Uses the `/prompt` endpoint to queue workflows
- WebSocket `/ws` for progress events (node execution, preview images)

### Workflow Templates (bundled)
- `txt2img_standard.json` — Basic txt2img, SDXL or SD1.5 compatible
- `txt2img_danbooru.json` — Same but with anime-tuned sampler defaults
- `img2img_variation.json` — For panel variations / inpainting
- `upscale_4x.json` — Post-generation upscale

### Dynamic Prompt Injection
The backend dynamically patches the workflow JSON before submission:
- Injects `positive_prompt`, `negative_prompt`, `width`, `height`, `seed`, `steps`, `cfg`, `checkpoint_name` into the relevant nodes.
- This avoids hardcoding node IDs by using a node-tagging convention (nodes tagged `_CBC_POSITIVE_`, `_CBC_NEGATIVE_`, etc. in the template titles).

### Model Discovery
- On startup, backend queries ComfyUI `/object_info` to get available checkpoints, LoRAs, VAEs, and samplers.
- These populate dropdowns in the frontend.

---

## 8. Data Model & Project File Structure

### SQLite Tables

```sql
-- Projects
CREATE TABLE project (
  id TEXT PRIMARY KEY,
  name TEXT,
  created_at DATETIME,
  updated_at DATETIME,
  status TEXT,          -- draft | in_progress | complete
  scenario_json TEXT,   -- full scenario from Tab 1
  storyboard_json TEXT, -- full storyboard from Tab 2
  settings_json TEXT    -- generation settings, style, etc.
);

-- Pages
CREATE TABLE page (
  id TEXT PRIMARY KEY,
  project_id TEXT REFERENCES project(id),
  page_number INTEGER,
  layout_json TEXT,     -- panel layout definition
  canvas_json TEXT      -- Konva/Fabric canvas state JSON
);

-- Panels
CREATE TABLE panel (
  id TEXT PRIMARY KEY,
  page_id TEXT REFERENCES page(id),
  sequence_id TEXT,
  position_json TEXT,   -- x, y, w, h, ratio
  prompt TEXT,
  negative_prompt TEXT,
  image_path TEXT,      -- path to approved generated image
  status TEXT,          -- pending | generating | review | approved | rejected
  generation_meta TEXT  -- seed, model, steps, cfg used
);

-- Bubbles
CREATE TABLE bubble (
  id TEXT PRIMARY KEY,
  panel_id TEXT REFERENCES panel(id),
  page_id TEXT REFERENCES page(id),
  type TEXT,            -- round | thought | caption | shout | whisper | narrative
  text TEXT,
  style_json TEXT,      -- font, size, bold, italic, colors, position
  position_json TEXT    -- x, y, w, h, tail_x, tail_y
);
```

### Filesystem Layout (inside `/data` volume)

```
/data/
├── projects/
│   └── {project_id}/
│       ├── project.db              # SQLite database
│       ├── generated/              # Raw ComfyUI outputs (all attempts)
│       │   └── panel_{id}_{seed}.png
│       ├── approved/               # Final approved images per panel
│       │   └── panel_{id}.png
│       └── export/                 # Export outputs
│           ├── comic.pdf
│           ├── comic.cbz
│           ├── pages/
│           │   ├── page_001.png
│           │   └── ...
│           └── full_project.zip
└── settings.json                   # Global app settings (providers, defaults)
```

---

## 9. API Design (Backend)

### Projects

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/projects` | List all projects |
| `POST` | `/projects` | Create new project |
| `GET` | `/projects/{id}` | Get full project data |
| `DELETE` | `/projects/{id}` | Delete project |
| `POST` | `/projects/{id}/export` | Trigger export (returns download URL) |

### Scenario

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/projects/{id}/scenario/generate` | Generate scenario from idea (streaming) |
| `PUT` | `/projects/{id}/scenario` | Save edited scenario |

### Storyboard

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/projects/{id}/storyboard/generate` | Generate storyboard from scenario |
| `PUT` | `/projects/{id}/storyboard` | Save storyboard edits |

### Image Generation

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/projects/{id}/panels/{panel_id}/generate` | Queue single panel generation |
| `POST` | `/projects/{id}/panels/generate-all` | Queue all pending panels |
| `GET` | `/projects/{id}/panels/{panel_id}/status` | Get panel generation status |
| `POST` | `/projects/{id}/panels/{panel_id}/review` | Submit review decision (approve/reject) |
| `GET` | `/comfyui/models` | List available ComfyUI checkpoints/LoRAs |

### Canvas & Bubbles

| Method | Endpoint | Description |
|---|---|---|
| `PUT` | `/projects/{id}/pages/{page_id}/canvas` | Save canvas state |
| `POST` | `/projects/{id}/pages/{page_id}/bubbles` | Add speech bubble |
| `PUT` | `/projects/{id}/pages/{page_id}/bubbles/{bubble_id}` | Update bubble |
| `DELETE` | `/projects/{id}/pages/{page_id}/bubbles/{bubble_id}` | Delete bubble |

### WebSocket

| Path | Description |
|---|---|
| `ws://host/ws/projects/{id}` | Real-time generation progress, preview images, status updates |

---

## 10. Frontend Architecture

### Tab Structure

```
App
├── Header (project name, save indicator, settings button)
├── Tab Bar
│   ├── Tab 1: Scenario        [lock icon when complete]
│   ├── Tab 2: Storyboard      [lock icon when complete]
│   ├── Tab 3: Image Gen       [progress counter N/total]
│   ├── Tab 4: Comic Editor
│   └── Tab 5: Review & Export
└── Footer (LLM provider indicator, ComfyUI status dot)
```

### State Management
- **Zustand** for global project state (lightweight, no boilerplate)
- React Query for server-state (API calls, caching, invalidation)
- WebSocket handler hooked into Zustand store for live updates

### Key Components
- `<ScenarioEditor />` — collapsible tree of acts > scenes > sequences with inline editing
- `<StoryboardGrid />` — drag-and-drop page/panel layout builder
- `<PanelPromptCard />` — prompt editing + status badge + generation controls
- `<GenerationQueue />` — live queue status with WebSocket updates
- `<ComicCanvas />` — Konva.js-powered page editor
- `<BubbleToolbar />` — floating toolbar for bubble/text editing
- `<ComicReader />` — full-page review slideshow
- `<ExportPanel />` — export format selection + download

---

## 11. Implementation Phases & Roadmap

### Phase 1 — Foundation (Weeks 1–2)
- [ ] Docker Compose skeleton (frontend + backend containers)
- [ ] FastAPI backend with health check, CORS, static file serving
- [ ] React + Vite + Tailwind frontend scaffold with tab routing
- [ ] SQLite schema + SQLModel models
- [ ] LLM client abstraction (KoboldCPP + OpenAI-compat)
- [ ] Settings page: configure LLM providers, test connection
- [ ] Basic project create/list/load/delete

### Phase 2 — Scenario Generation (Week 3)
- [ ] Tab 1 UI: idea input form + settings
- [ ] Backend: scenario generation endpoint with streaming response
- [ ] Scenario JSON parser + display in editable tree
- [ ] Character list extraction and display
- [ ] Manual editing and saving of all scenario fields

### Phase 3 — Storyboard (Week 4)
- [ ] Tab 2 UI: page grid + panel layout picker
- [ ] LLM storyboard generation (page/panel/key image assignment)
- [ ] Drag-and-drop page reordering (dnd-kit)
- [ ] Panel layout templates (6–8 common layouts)
- [ ] Image ratio display per panel
- [ ] Save storyboard state

### Phase 4 — Image Generation (Weeks 5–6)
- [ ] ComfyUI client (HTTP + WebSocket)
- [ ] Dynamic workflow JSON patching
- [ ] Model/LoRA discovery from ComfyUI
- [ ] Tab 3 UI: global settings + prompt editor per panel
- [ ] Natural language / Danbooru mode toggle with prompt auto-generation
- [ ] Single panel generation + status tracking
- [ ] Generate-all queue with real-time WebSocket progress
- [ ] Manual review flow (approve/reject/edit)
- [ ] Vision review integration (optional)
- [ ] Variation generation (multi-seed grid)

### Phase 5 — Comic Editor (Weeks 7–8)
- [ ] Tab 4 UI: Konva.js canvas setup with panel grid
- [ ] Image placement and crop/pan within panels
- [ ] Panel border rendering
- [ ] Speech bubble creation (all types) and placement
- [ ] Bubble tail drag-to-position
- [ ] Text editor inside bubbles (font, size, bold, italic, align)
- [ ] Bundle comic fonts
- [ ] Caption/narration boxes
- [ ] Layer management
- [ ] Undo/redo stack
- [ ] Auto-populate dialogue from scenario

### Phase 6 — Export (Week 9)
- [ ] Tab 5 UI: comic reader slideshow
- [ ] PDF export (WeasyPrint or reportlab)
- [ ] CBZ export (numbered PNGs in ZIP)
- [ ] Per-page PNG export
- [ ] Full project ZIP (raws + finals + project JSON)
- [ ] `.cbc` project save/load

### Phase 7 — Polish & QA (Week 10)
- [ ] Loading states, error toasts, empty state screens
- [ ] Mobile-responsive layout (at least for review/export tabs)
- [ ] Settings persistence across sessions
- [ ] Auto-save
- [ ] Documentation: README, configuration guide
- [ ] End-to-end test: idea → exported PDF

---

## 12. Directory Structure

```
comic-book-creator/
├── docker-compose.yml
├── .env.example
├── data/                          # Git-ignored; persisted via volume
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                    # FastAPI entrypoint
│   ├── settings.py                # Pydantic settings (reads env vars)
│   ├── database.py                # SQLite + SQLModel setup
│   ├── models/
│   │   ├── project.py
│   │   ├── page.py
│   │   ├── panel.py
│   │   └── bubble.py
│   ├── routers/
│   │   ├── projects.py
│   │   ├── scenario.py
│   │   ├── storyboard.py
│   │   ├── generation.py
│   │   ├── canvas.py
│   │   └── export.py
│   ├── services/
│   │   ├── llm/
│   │   │   ├── base.py            # Abstract LLMClient
│   │   │   ├── koboldcpp.py
│   │   │   ├── openai_compat.py   # Handles OpenAI, Mistral, LM Studio, Ollama
│   │   │   └── anthropic.py
│   │   ├── comfyui/
│   │   │   ├── client.py          # HTTP + WebSocket ComfyUI client
│   │   │   ├── workflow_patcher.py
│   │   │   └── workflows/         # Bundled .json workflow templates
│   │   ├── scenario_service.py
│   │   ├── storyboard_service.py
│   │   ├── generation_service.py
│   │   └── export_service.py
│   └── websocket_manager.py
│
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── store/                 # Zustand stores
│   │   ├── hooks/                 # React Query hooks + WS hook
│   │   ├── api/                   # API client functions
│   │   ├── components/
│   │   │   ├── ui/                # shadcn/ui base components
│   │   │   ├── scenario/
│   │   │   ├── storyboard/
│   │   │   ├── generation/
│   │   │   ├── editor/
│   │   │   └── export/
│   │   ├── pages/                 # Tab-level page components
│   │   ├── types/                 # TypeScript types
│   │   └── assets/
│   │       └── fonts/             # Bundled comic fonts
│   └── public/
│
└── README.md
```

---

## 13. Key Technical Challenges & Solutions

### Challenge 1 — LLM JSON Reliability
**Problem:** LLMs don't always output valid JSON, especially for long structured outputs.
**Solution:**
- Use a robust JSON extraction function that strips markdown fences and finds the outermost `{` / `[`.
- Implement retries (up to 3) with an explicit error message fed back to the LLM: *"Your previous response was not valid JSON. Return only JSON. Error: [parse error]"*
- Consider using grammar-constrained generation if KoboldCPP supports it (GBNF grammars).

### Challenge 2 — ComfyUI Workflow Compatibility
**Problem:** ComfyUI workflows differ drastically between model types (SD1.5, SDXL, Flux).
**Solution:**
- Maintain separate workflow templates per model family.
- Detect model family from checkpoint filename heuristics.
- Provide a workflow editor in settings for power users to customize.

### Challenge 3 — Canvas Export Fidelity
**Problem:** Exporting the Konva/Fabric canvas at print resolution while preserving all layers.
**Solution:**
- Export canvas at 2× or 3× the display resolution using Konva's `.toDataURL({ pixelRatio: 3 })`.
- Composite approved panel images at full resolution server-side using Pillow before final PDF rendering to avoid browser memory limits.

### Challenge 4 — Danbooru vs Natural Language Prompting
**Problem:** The LLM needs to generate fundamentally different prompt formats.
**Solution:**
- Two distinct LLM system prompts: one instructing natural language description, one instructing comma-separated Danbooru tags with standard quality tags.
- Global style prefix and negative prompt templates vary per mode.
- User can switch modes per panel or globally.

### Challenge 5 — Character Visual Consistency
**Problem:** Maintaining the same character appearance across many generated panels.
**Solution:**
- Character descriptions from Tab 1 are stored and prepended to every panel prompt where that character appears.
- LoRA support: users can assign a character LoRA per character in the character list.
- Optional: seed locking for style consistency (global style seed, per-scene character seed).

### Challenge 6 — Large Project Performance
**Problem:** Projects with 40+ pages and 100+ panels can become slow in the canvas editor.
**Solution:**
- Virtualize the page list (only render visible pages).
- Lazy-load panel images in the canvas editor.
- Store canvas state as JSON, only hydrate active page into Konva/Fabric.

---

*Document generated for the Comic Book Creator project. Version 1.0 — Initial planning.*
