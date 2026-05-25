from __future__ import annotations

from copy import deepcopy
import os
from typing import Any

from .config import Settings
from .schemas import (
    ImageGenerationSettings,
    MediaGenerationSettingsRead,
    VideoGenerationSettings,
)


MEDIA_GENERATION_SETTINGS_KEY = "media_generation_settings_json"


def _is_legacy_movie_tool_path(value: Any) -> bool:
    text = str(value or "").replace("\\", "/")
    return "/.movie-tool/" in text or text.startswith("/root/.movie-tool/")


def _replace_legacy_model_roots(merged: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    if _is_legacy_movie_tool_path(merged["image"].get("checkpoint_root")):
        merged["image"]["checkpoint_root"] = defaults["image"]["checkpoint_root"]
    if _is_legacy_movie_tool_path(merged["video"].get("model_root")):
        merged["video"]["model_root"] = defaults["video"]["model_root"]
    return merged


def build_default_media_generation_settings(settings: Settings) -> dict[str, Any]:
    image = ImageGenerationSettings(
        enabled=True,
        provider=os.getenv("MOVIE_TOOL_IMAGE_PROVIDER", "mock"),
        checkpoint_root=str(settings.default_image_model_root),
        default_model=os.getenv("MOVIE_TOOL_IMAGE_DEFAULT_MODEL", "sdxl-local"),
        comfy_endpoint=os.getenv("MOVIE_TOOL_COMFY_ENDPOINT", "http://host.docker.internal:8188"),
        comfy_timeout_s=int(os.getenv("MOVIE_TOOL_COMFY_TIMEOUT_S", "300")),
        device="auto",
        sampler=os.getenv("MOVIE_TOOL_IMAGE_SAMPLER", "res_multistep"),
        scheduler=os.getenv("MOVIE_TOOL_IMAGE_SCHEDULER", "simple"),
        steps=int(os.getenv("MOVIE_TOOL_IMAGE_STEPS", "24")),
        cfg_scale=float(os.getenv("MOVIE_TOOL_IMAGE_CFG_SCALE", "6.5")),
        width=1024,
        height=1024,
        variant_count=1,
    )
    video = VideoGenerationSettings(
        enabled=True,
        provider="mock",
        model_root=str(settings.default_video_model_root),
        model_class="wan2.2_i2v",
        attention_mode="sage_attn2",
        infer_steps=4,
        native_height=480,
        native_width=832,
        native_frame_count=49,
        target_output_fps=settings.default_fps,
        seed_mode="random",
    )
    return MediaGenerationSettingsRead(image=image, video=video).model_dump()


def normalize_media_generation_settings(raw_settings: dict[str, Any] | None, settings: Settings) -> dict[str, Any]:
    payload = deepcopy(raw_settings or {})
    defaults = build_default_media_generation_settings(settings)
    merged = {
        "image": {
            **defaults["image"],
            **(payload.get("image") or {}),
        },
        "video": {
            **defaults["video"],
            **(payload.get("video") or {}),
        },
    }
    merged = _replace_legacy_model_roots(merged, defaults)
    normalized = MediaGenerationSettingsRead.model_validate(merged)
    return normalized.model_dump()
