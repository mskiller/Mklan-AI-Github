"""
Mklan Studio — Unified Backend
Combines Wildcard Workshop and Movie Scripting backends under one FastAPI instance.

Phase 2: Backend Integration + Refactoring
- Wildcard backend: mounted at /wildcards (refactored to use APIRouter)
- Movie backend: mounted at /movie (refactored to use APIRouter)
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles


from .wildcards import router as wildcards_router
from .movie.router import router as movie_router
from .database import init_wildcard_db
from .movie.database import Database as MovieDatabase
from .studio_features import router as studio_router
from .suggester import router as suggester_router
from .generation import router as generation_router
from .training import router as training_router
from .video import router as video_router
from .cards.main import create_app as create_cards_app
from .v2.assets import router as assets_router
from .v2.canon import router as canon_router
from .v2.copilot import router as copilot_router
from .v2.jobs import router as jobs_router
from .v2.runtime import create_platform_services
from .v2.workflows import router as workflows_router
from .v2.workspaces import router as workspaces_router


def _default_data_root() -> Path:
    if os.environ.get("ENVIRONMENT") == "production" or Path("/.dockerenv").exists():
        return Path("/app/data")
    return Path(__file__).resolve().parents[2] / "data"


def _cors_origins() -> list[str]:
    raw = os.getenv("STUDIO_CORS_ORIGINS", "").strip()
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    if os.getenv("ENVIRONMENT", "development").strip().lower() == "development":
        return ["*"]
    return ["http://localhost:5173", "http://127.0.0.1:5173"]


_env_data = os.environ.get("STUDIO_DATA_ROOT") or os.environ.get("MOVIE_TOOL_DATA_ROOT")
data_path = Path(_env_data) if _env_data else _default_data_root()
generated_dir = data_path / "generated"
generated_dir.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialise both backends."""
    # Wildcard DB init
    init_wildcard_db()

    # Movie DB init + state setup
    movie_db_path = Path(os.getenv("MOVIE_DB", str(Path(__file__).resolve().parents[2] / "data" / "movie" / "movie_tool.db")))
    movie_db = MovieDatabase(movie_db_path)
    movie_db.initialize()

    # Import and call Movie's init to populate app.state
    from .movie.init_state import init_movie_app_state
    init_movie_app_state(app, movie_db)

    audit, asset_registry, job_manager = create_platform_services(data_path)

    app.state.data_root = data_path
    app.state.v2_audit = audit
    app.state.v2_assets = asset_registry
    app.state.v2_jobs = job_manager
    await job_manager.start()

    try:
        yield
    finally:
        await job_manager.stop()


# === Unified FastAPI Application ===
app = FastAPI(
    title="Mklan Studio API",
    description="Unified backend: Wildcard Workshop + Movie Scripting",
    version="0.1.0",
    lifespan=lifespan,
)

cors_origins = _cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials="*" not in cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def optional_studio_api_key_guard(request: Request, call_next):
    api_key = os.getenv("STUDIO_API_KEY", "").strip()
    protected_prefixes = (
        "/api/jobs",
        "/api/assets",
        "/api/workflows",
        "/api/workspaces",
        "/api/canon",
        "/api/copilot",
        "/api/studio",
        "/api/generation",
        "/api/training",
        "/api/video",
    )
    if api_key and request.method not in {"GET", "HEAD", "OPTIONS"} and request.url.path.startswith(protected_prefixes):
        provided = request.headers.get("x-studio-api-key", "")
        if provided != api_key:
            return JSONResponse({"detail": "Missing or invalid X-Studio-Api-Key header."}, status_code=401)
    return await call_next(request)

# Include wildcard routes at /wildcards/*
app.include_router(wildcards_router, prefix="/wildcards", tags=["wildcards"])
# Legacy compatibility for frontend paths expecting /wildcards/api/*
app.include_router(wildcards_router, prefix="/wildcards/api", tags=["wildcards-api"])

# Include movie routes at /movie/*
app.include_router(movie_router, prefix="/movie", tags=["movie"])

# Mount SillyTavern Cards as a sub-application.
app.mount("/cards", create_cards_app(), name="cards")


# === Health check at root ===
@app.get("/health")
async def root_health():
    return {
        "status": "ok",
        "service": "mklan-studio",
        "modules": ["wildcards", "movie", "cards", "training", "generation", "video", "v2-jobs", "v2-assets", "v2-workflows", "v2-workspaces", "v2-copilot", "v2-canon"],
    }

app.include_router(studio_router, prefix="/api")
app.include_router(generation_router, prefix="/api")
app.include_router(training_router, prefix="/api")
app.include_router(video_router, prefix="/api")
app.include_router(suggester_router, prefix="/api/suggester")
app.include_router(jobs_router, prefix="/api")
app.include_router(assets_router, prefix="/api")
app.include_router(workflows_router, prefix="/api")
app.include_router(workspaces_router, prefix="/api")
app.include_router(copilot_router, prefix="/api")
app.include_router(canon_router, prefix="/api")

# Serve generated images statically at /generated
app.mount("/generated", StaticFiles(directory=str(generated_dir)), name="generated")


@app.get("/")
async def root():
    return {"service":"mklan-studio","status":"ok"}
