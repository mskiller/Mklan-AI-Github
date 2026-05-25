from __future__ import annotations

from importlib import import_module

from sqlalchemy.orm import Session

from media_indexer_backend.platform.events import ensure_builtin_subscribers
from media_indexer_backend.platform.registry import iter_backend_entrypoints, iter_worker_entrypoints
from media_indexer_backend.platform.service import ensure_platform_modules_synced


_LOADED_ENTRYPOINTS: set[tuple[str, str]] = set()


def _load_entrypoint(ref: str, *, runtime: str) -> None:
    cache_key = (runtime, ref)
    if cache_key in _LOADED_ENTRYPOINTS:
        return
    if ":" in ref:
        module_name, attribute = ref.split(":", 1)
        value = getattr(import_module(module_name), attribute)
        if callable(value):
            value()
    else:
        import_module(ref)
    _LOADED_ENTRYPOINTS.add(cache_key)


def bootstrap_platform(session: Session, *, runtime: str = "backend") -> None:
    ensure_builtin_subscribers()
    ensure_platform_modules_synced(session)
    refs = iter_backend_entrypoints() if runtime == "backend" else iter_worker_entrypoints()
    for ref in refs:
        _load_entrypoint(ref, runtime=runtime)
