from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import os


def _env_flag(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    repo_root: Path
    data_root: Path
    projects_root: Path
    models_root: Path
    templates_root: Path
    database_path: Path
    ffmpeg_binary: str
    ollama_url: str
    ollama_model: str
    scenario_assistant_provider: str
    scenario_assistant_base_url: str
    scenario_assistant_model: str
    scenario_assistant_api_key: str | None
    scenario_assistant_timeout_s: int
    allow_placeholder_renderer: bool
    supported_min_vram_gb: int
    default_width: int
    default_height: int
    default_fps: int
    default_target_duration_s: int
    default_image_model_root: Path
    default_video_model_root: Path
    sillytavern_enabled: bool
    sillytavern_public_url: str
    sillytavern_internal_url: str
    sillytavern_data_root: Path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    repo_root = Path(__file__).resolve().parents[2]
    is_docker = os.environ.get("ENVIRONMENT") == "production" or Path("/.dockerenv").exists()
    if is_docker:
        default_data_root = Path("/app/data/cards")
    else:
        default_data_root = repo_root.parent / "data" / "cards"
    data_root = Path(os.getenv("CARDS_DATA_DIR", os.getenv("MOVIE_TOOL_CARDS_DATA_ROOT", default_data_root))).resolve()
    projects_root = data_root / "projects"
    models_root = data_root / "models"
    image_models_root = models_root / "image"
    repo_image_models_root = repo_root / ".movie-tool-smoke" / "image-models"
    default_image_models_root = repo_image_models_root if repo_image_models_root.exists() else image_models_root
    video_models_root = models_root / "video"
    templates_root = data_root / "templates"
    database_path = Path(os.getenv("CARDS_DB", data_root / "card_creator.db")).resolve()

    sillytavern_data_root = Path(
        os.getenv(
            "CARDS_SILLYTAVERN_DATA_ROOT",
            os.getenv("SILLYTAVERN_DATA_ROOT", data_root / "sillytavern-data"),
        )
    ).resolve()

    return Settings(
        repo_root=repo_root,
        data_root=data_root,
        projects_root=projects_root,
        models_root=models_root,
        templates_root=templates_root,
        database_path=database_path,
        ffmpeg_binary=os.getenv("MOVIE_TOOL_FFMPEG_BINARY", "ffmpeg"),
        ollama_url=os.getenv("MOVIE_TOOL_OLLAMA_URL", "http://127.0.0.1:11434"),
        ollama_model=os.getenv("MOVIE_TOOL_OLLAMA_MODEL", "llama3.1:8b"),
        scenario_assistant_provider=os.getenv("MOVIE_TOOL_SCENARIO_ASSISTANT_PROVIDER", "ollama"),
        scenario_assistant_base_url=os.getenv(
            "MOVIE_TOOL_SCENARIO_ASSISTANT_BASE_URL",
            os.getenv("MOVIE_TOOL_OLLAMA_URL", "http://127.0.0.1:11434"),
        ),
        scenario_assistant_model=os.getenv(
            "MOVIE_TOOL_SCENARIO_ASSISTANT_MODEL",
            os.getenv("MOVIE_TOOL_OLLAMA_MODEL", "llama3.1:8b"),
        ),
        scenario_assistant_api_key=os.getenv("MOVIE_TOOL_SCENARIO_ASSISTANT_API_KEY"),
        scenario_assistant_timeout_s=int(os.getenv("MOVIE_TOOL_SCENARIO_ASSISTANT_TIMEOUT_S", "120")),
        allow_placeholder_renderer=_env_flag("MOVIE_TOOL_ALLOW_PLACEHOLDER_RENDERER", True),
        supported_min_vram_gb=int(os.getenv("MOVIE_TOOL_SUPPORTED_MIN_VRAM_GB", "16")),
        default_width=int(os.getenv("MOVIE_TOOL_DEFAULT_WIDTH", "1280")),
        default_height=int(os.getenv("MOVIE_TOOL_DEFAULT_HEIGHT", "720")),
        default_fps=int(os.getenv("MOVIE_TOOL_DEFAULT_FPS", "24")),
        default_target_duration_s=int(os.getenv("MOVIE_TOOL_DEFAULT_TARGET_DURATION_S", "240")),
        default_image_model_root=Path(os.getenv("MOVIE_TOOL_IMAGE_MODEL_ROOT", str(default_image_models_root))).resolve(),
        default_video_model_root=Path(os.getenv("MOVIE_TOOL_VIDEO_MODEL_ROOT", video_models_root)).resolve(),
        sillytavern_enabled=_env_flag("CARDS_SILLYTAVERN_ENABLED", True),
        sillytavern_public_url=os.getenv("SILLYTAVERN_PUBLIC_URL", "http://localhost:8011"),
        sillytavern_internal_url=os.getenv("SILLYTAVERN_INTERNAL_URL", "http://sillytavern:8000"),
        sillytavern_data_root=sillytavern_data_root,
    )
