from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from media_indexer_backend.api.router import api_router
from media_indexer_backend.core.config import get_settings
from media_indexer_backend.core.logging import configure_logging
from media_indexer_backend.db.session import SessionLocal
from media_indexer_backend.platform.bootstrap import bootstrap_platform
from media_indexer_backend.services.scheduler_service import reload_schedules, shutdown_scheduler, start_scheduler
from media_indexer_backend.services.source_service import ensure_system_sources
from media_indexer_backend.services.user_service import ensure_seed_users


configure_logging()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    with SessionLocal() as session:
        ensure_seed_users(session)
        ensure_system_sources(session)
        bootstrap_platform(session, runtime="backend")
        session.commit()
    start_scheduler()
    reload_schedules()
    yield
    shutdown_scheduler()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)
