from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable
from uuid import UUID

from sqlalchemy.orm import Session

from media_indexer_backend.platform.service import module_is_enabled


EventHandler = Callable[[Session, dict[str, Any]], None]
_SUBSCRIBERS: dict[str, list[EventHandler]] = defaultdict(list)
_BOOTSTRAPPED = False


def subscribe(event_name: str, handler: EventHandler) -> None:
    _SUBSCRIBERS[event_name].append(handler)


def publish_event(session: Session, event_name: str, payload: dict[str, Any]) -> None:
    for handler in _SUBSCRIBERS.get(event_name, []):
        handler(session, payload)


def ensure_builtin_subscribers() -> None:
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return

    def on_asset_annotated(session: Session, payload: dict[str, Any]) -> None:
        if not module_is_enabled(session, "smart_albums"):
            return
        from media_indexer_backend.services.smart_album_service import sync_smart_albums_for_user

        user_id = payload.get("user_id")
        if user_id:
            sync_smart_albums_for_user(session, UUID(str(user_id)))

    def on_tag_accepted(session: Session, payload: dict[str, Any]) -> None:
        if not module_is_enabled(session, "smart_albums"):
            return
        from media_indexer_backend.services.smart_album_service import sync_smart_albums_for_user

        user_id = payload.get("user_id")
        if user_id:
            sync_smart_albums_for_user(session, UUID(str(user_id)))

    def on_collection_asset_added(session: Session, payload: dict[str, Any]) -> None:
        if not module_is_enabled(session, "smart_albums"):
            return
        from media_indexer_backend.services.smart_album_service import record_collection_add_curation_events, sync_smart_albums_for_user

        user_id = payload.get("user_id")
        collection_id = payload.get("collection_id")
        asset_ids = [UUID(str(item)) for item in payload.get("asset_ids", [])]
        if user_id and collection_id and asset_ids:
            record_collection_add_curation_events(
                session,
                user_id=UUID(str(user_id)),
                collection_id=UUID(str(collection_id)),
                asset_ids=asset_ids,
            )
            sync_smart_albums_for_user(session, UUID(str(user_id)))

    def on_scan_completed(session: Session, payload: dict[str, Any]) -> None:
        source_id = payload.get("source_id")
        if source_id and module_is_enabled(session, "people"):
            from media_indexer_backend.services.people_service import assign_people_for_source

            assign_people_for_source(session, UUID(str(source_id)))
        if module_is_enabled(session, "smart_albums"):
            from media_indexer_backend.services.smart_album_service import sync_all_smart_albums

            sync_all_smart_albums(session)

    def on_module_state_changed(session: Session, payload: dict[str, Any]) -> None:
        changed_module = str(payload.get("module_id", "")).strip()
        if changed_module not in {"people", "geo", "ai_tagging", "smart_albums"}:
            return
        from media_indexer_backend.services.smart_album_service import sync_all_smart_albums

        sync_all_smart_albums(session)

    subscribe("asset.annotated", on_asset_annotated)
    subscribe("tag.accepted", on_tag_accepted)
    subscribe("collection.asset_added", on_collection_asset_added)
    subscribe("scan.completed", on_scan_completed)
    subscribe("module.enabled", on_module_state_changed)
    subscribe("module.disabled", on_module_state_changed)
    _BOOTSTRAPPED = True
