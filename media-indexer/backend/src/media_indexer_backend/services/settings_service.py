from __future__ import annotations

from sqlalchemy.orm import Session

from media_indexer_backend.core.config import get_settings
from media_indexer_backend.models.tables import AppSetting
from media_indexer_backend.schemas.settings import AdminSettings, AdminSettingsUpdateRequest


SETTING_DEFAULTS = {
    "tag_similarity_threshold_percent": 75,
    "max_thumbnail_size": lambda: get_settings().max_thumbnail_size,
    "duplicate_phash_threshold": lambda: get_settings().duplicate_phash_threshold,
    "semantic_similarity_threshold": lambda: get_settings().semantic_similarity_threshold,
    "semantic_neighbor_limit": lambda: get_settings().semantic_neighbor_limit,
    "clip_enabled": lambda: get_settings().clip_enabled,
    "preview_cache_max_mb": lambda: get_settings().preview_cache_max_mb,
    "worker_poll_interval_seconds": lambda: get_settings().worker_poll_interval_seconds,
}


def _resolve_default(key: str):
    value = SETTING_DEFAULTS[key]
    return value() if callable(value) else value


def _get_setting_row(session: Session, key: str) -> AppSetting | None:
    return session.get(AppSetting, key)


def get_setting_value(session: Session, key: str):
    row = _get_setting_row(session, key)
    if row is None:
        return _resolve_default(key)
    value = row.value_json.get("value") if isinstance(row.value_json, dict) else None
    return _resolve_default(key) if value is None else value


def set_setting_value(session: Session, key: str, value) -> AppSetting:
    row = _get_setting_row(session, key)
    if row is None:
        row = AppSetting(key=key, value_json={"value": value})
        session.add(row)
    else:
        row.value_json = {"value": value}
    session.flush()
    return row


def get_admin_settings(session: Session) -> AdminSettings:
    return AdminSettings(
        tag_similarity_threshold_percent=int(get_setting_value(session, "tag_similarity_threshold_percent")),
        max_thumbnail_size=int(get_setting_value(session, "max_thumbnail_size")),
        duplicate_phash_threshold=int(get_setting_value(session, "duplicate_phash_threshold")),
        semantic_similarity_threshold=float(get_setting_value(session, "semantic_similarity_threshold")),
        semantic_neighbor_limit=int(get_setting_value(session, "semantic_neighbor_limit")),
        clip_enabled=bool(get_setting_value(session, "clip_enabled")),
        preview_cache_max_mb=int(get_setting_value(session, "preview_cache_max_mb")),
        worker_poll_interval_seconds=int(get_setting_value(session, "worker_poll_interval_seconds")),
    )


def update_admin_settings(session: Session, payload: AdminSettingsUpdateRequest) -> AdminSettings:
    for key, value in payload.model_dump().items():
        set_setting_value(session, key, value)
    return get_admin_settings(session)


def get_tag_similarity_threshold_percent(session: Session) -> int:
    return int(get_setting_value(session, "tag_similarity_threshold_percent"))


def get_tag_similarity_threshold_score(session: Session) -> float:
    return max(0.01, min(1.0, get_tag_similarity_threshold_percent(session) / 100.0))
