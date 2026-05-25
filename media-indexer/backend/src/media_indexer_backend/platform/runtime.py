from __future__ import annotations

from dataclasses import dataclass

from media_indexer_backend.core.config import get_settings
from media_indexer_backend.platform.service import get_live_module_setting, live_module_enabled


@dataclass(slots=True)
class AiTaggingRuntimeSettings:
    module_enabled: bool
    clip_enabled: bool
    image_tagging_enabled: bool
    caption_enabled: bool
    ocr_enabled: bool


@dataclass(slots=True)
class PeopleRuntimeSettings:
    module_enabled: bool
    face_detection_enabled: bool


@dataclass(slots=True)
class SmartAlbumRuntimeSettings:
    module_enabled: bool
    suggestion_min_events: int
    suggestion_min_assets: int
    suggestion_lookback_days: int


def get_ai_tagging_runtime_settings() -> AiTaggingRuntimeSettings:
    settings = get_settings()
    module_enabled = live_module_enabled("ai_tagging", default=True)
    return AiTaggingRuntimeSettings(
        module_enabled=module_enabled,
        clip_enabled=module_enabled and bool(get_live_module_setting("ai_tagging", "clip_enabled", settings.clip_enabled)),
        image_tagging_enabled=module_enabled and bool(get_live_module_setting("ai_tagging", "image_tagging_enabled", settings.image_tagging_enabled)),
        caption_enabled=module_enabled and bool(get_live_module_setting("ai_tagging", "caption_enabled", settings.caption_enabled)),
        ocr_enabled=module_enabled and bool(get_live_module_setting("ai_tagging", "ocr_enabled", settings.ocr_enabled)),
    )


def get_people_runtime_settings() -> PeopleRuntimeSettings:
    settings = get_settings()
    module_enabled = live_module_enabled("people", default=settings.face_detection_enabled)
    return PeopleRuntimeSettings(
        module_enabled=module_enabled,
        face_detection_enabled=module_enabled and bool(get_live_module_setting("people", "face_detection_enabled", settings.face_detection_enabled)),
    )


def get_smart_album_runtime_settings() -> SmartAlbumRuntimeSettings:
    settings = get_settings()
    module_enabled = live_module_enabled("smart_albums", default=True)
    return SmartAlbumRuntimeSettings(
        module_enabled=module_enabled,
        suggestion_min_events=int(get_live_module_setting("smart_albums", "smart_album_suggestion_min_events", settings.smart_album_suggestion_min_events)),
        suggestion_min_assets=int(get_live_module_setting("smart_albums", "smart_album_suggestion_min_assets", settings.smart_album_suggestion_min_assets)),
        suggestion_lookback_days=int(get_live_module_setting("smart_albums", "smart_album_suggestion_lookback_days", settings.smart_album_suggestion_lookback_days)),
    )
