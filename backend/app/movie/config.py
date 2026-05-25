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


def _default_model_root(models_root: Path, singular_name: str, plural_name: str) -> Path:
    singular = models_root / singular_name
    plural = models_root / plural_name
    if not singular.exists() and plural.exists():
        return plural
    return singular


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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    repo_root = Path(__file__).resolve().parents[2] # backend dir
    
    # Check if we are running inside Docker where /app is the repo root
    is_docker = os.environ.get("ENVIRONMENT") == "production" or Path("/.dockerenv").exists()
    
    if is_docker:
        default_data_root = Path("/app/data")
    else:
        # Local development
        default_data_root = repo_root.parent / "data"

    env_data_root = os.getenv("MOVIE_TOOL_DATA_ROOT") or os.getenv("MOVIE_DATA_DIR")
    data_root = Path(env_data_root).resolve() if env_data_root else default_data_root
    projects_root = data_root / "projects"
    models_root = data_root / "models"
    image_models_root = _default_model_root(models_root, "image", "images")
    video_models_root = _default_model_root(models_root, "video", "videos")
    templates_root = data_root / "templates"
    database_path = data_root / "movie_tool.db"

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
        default_image_model_root=Path(os.getenv("MOVIE_TOOL_IMAGE_MODEL_ROOT", image_models_root)).resolve(),
        default_video_model_root=Path(os.getenv("MOVIE_TOOL_VIDEO_MODEL_ROOT", video_models_root)).resolve(),
    )
