from __future__ import annotations

from importlib import import_module

from fastapi import APIRouter

from media_indexer_backend.api.routes import admin, assets, auth, compare, export, health, inbox, modules, scan_jobs, search, shares, sources, tags, timeline
from media_indexer_backend.platform.registry import iter_backend_router_refs


CORE_ROUTERS = [
    health.router,
    auth.router,
    admin.router,
    modules.router,
    sources.router,
    scan_jobs.router,
    assets.router,
    search.router,
    tags.router,
    compare.router,
    timeline.router,
    shares.router,
    export.router,
    inbox.router,
]


def _resolve_router(ref: str):
    module_name, attribute = ref.split(":", 1)
    module = import_module(module_name)
    return getattr(module, attribute)


def build_api_router() -> APIRouter:
    router = APIRouter()
    for core_router in CORE_ROUTERS:
        router.include_router(core_router)
    for ref in iter_backend_router_refs():
        router.include_router(_resolve_router(ref))
    return router


api_router = build_api_router()
