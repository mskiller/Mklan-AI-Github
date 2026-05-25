from __future__ import annotations

import importlib
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_semantic_engine_can_be_disabled_without_loading_models(monkeypatch):
    monkeypatch.setenv("STUDIO_SEMANTIC_SEARCH_ENABLED", "false")

    from app.semantic_search import SemanticSearchEngine

    engine = SemanticSearchEngine()

    assert engine.get_text_embedding("cinematic portrait") is None
    assert "disabled" in engine.unavailable_reason.lower()
    assert engine._loaded is False


def test_backend_app_imports_without_eager_semantic_loading(monkeypatch):
    data_root = REPO_ROOT / "data"
    monkeypatch.setenv("STUDIO_DATA_ROOT", str(data_root))
    monkeypatch.setenv("STUDIO_SEMANTIC_SEARCH_ENABLED", "false")
    sys.modules.pop("app.studio_features", None)
    sys.modules.pop("app.main", None)

    main = importlib.import_module("app.main")

    assert main.generated_dir == data_root / "generated"
    assert main.generated_dir.exists()
    assert {route.path for route in main.app.routes} >= {
        "/health",
        "/wildcards/health",
        "/movie/health",
        "/api/studio/settings",
    }


def test_movie_settings_prefers_existing_plural_model_directory(monkeypatch):
    models_root = Path("/tmp/mklan-models")

    from app.movie.config import _default_model_root

    def fake_exists(path: Path) -> bool:
        return path == models_root / "images"

    monkeypatch.setattr(Path, "exists", fake_exists)

    assert _default_model_root(models_root, "image", "images") == models_root / "images"


def test_media_generation_settings_replaces_legacy_movie_tool_roots(monkeypatch):
    data_root = REPO_ROOT / "data" / "movie"
    monkeypatch.setenv("MOVIE_DATA_DIR", str(data_root))
    monkeypatch.setenv("MOVIE_TOOL_IMAGE_MODEL_ROOT", "/app/data/models/images")
    monkeypatch.setenv("MOVIE_TOOL_VIDEO_MODEL_ROOT", "/app/data/models/video")

    from app.movie import config as movie_config
    from app.movie.media_generation_settings import normalize_media_generation_settings

    movie_config.get_settings.cache_clear()
    try:
        settings = movie_config.get_settings()
        normalized = normalize_media_generation_settings(
            {
                "image": {"checkpoint_root": "/root/.movie-tool/models/image"},
                "video": {"model_root": "/root/.movie-tool/models/video"},
            },
            settings,
        )
    finally:
        movie_config.get_settings.cache_clear()

    assert normalized["image"]["checkpoint_root"] == str(settings.default_image_model_root)
    assert normalized["video"]["model_root"] == str(settings.default_video_model_root)


def test_comfyui_workflow_placeholders_are_typed():
    from app.comfyui_client import build_workflow_from_generation

    workflow, seed = build_workflow_from_generation(
        workflow_json={
            "1": {"class_type": "KSampler", "inputs": {"seed": "%seed%", "steps": "%steps%", "cfg": "%scale%"}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "prefix %prompt%"}},
        },
        prompt="cinematic portrait",
        negative_prompt="blur",
        model="model.safetensors",
        width=832,
        height=1216,
        steps=12,
        cfg_scale=1.5,
        sampler_name="lcm",
        scheduler="simple",
        seed=1234,
    )

    assert seed == 1234
    assert workflow["1"]["inputs"]["seed"] == 1234
    assert workflow["1"]["inputs"]["steps"] == 12
    assert workflow["1"]["inputs"]["cfg"] == 1.5
    assert workflow["2"]["inputs"]["text"] == "prefix cinematic portrait"


def test_movie_media_generation_accepts_comfyui_provider(monkeypatch):
    data_root = REPO_ROOT / "data" / "movie"
    monkeypatch.setenv("MOVIE_DATA_DIR", str(data_root))

    from app.movie import config as movie_config
    from app.movie.media_generation_settings import normalize_media_generation_settings

    movie_config.get_settings.cache_clear()
    try:
        settings = movie_config.get_settings()
        normalized = normalize_media_generation_settings(
            {
                "image": {
                    "provider": "comfyui",
                    "comfy_endpoint": "http://127.0.0.1:8188",
                    "comfy_timeout_s": 120,
                }
            },
            settings,
        )
    finally:
        movie_config.get_settings.cache_clear()

    assert normalized["image"]["provider"] == "comfyui"
    assert normalized["image"]["comfy_endpoint"] == "http://127.0.0.1:8188"
    assert normalized["image"]["comfy_timeout_s"] == 120
