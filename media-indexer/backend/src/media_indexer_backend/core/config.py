from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Media Indexer"
    app_env: str = "development"
    database_url: str = "postgresql+psycopg://media_indexer:change-me@localhost:5432/media_indexer"
    session_secret: str = "change-me"
    session_cookie_name: str = "media_indexer_session"
    admin_username: str = "admin"
    admin_password: str = "change-me"
    curator_username: str = "curator"
    curator_password: str = "change-me"
    guest_username: str = "guest"
    guest_password: str = "change-me"
    frontend_origin: str = "http://localhost:3000"
    allowed_source_roots: str = "/data/sources"
    windows_host_mount_root: str = "/hostfs"
    upload_source_name: str = "upload"
    upload_source_root: str = "/data/sources/upload"
    generated_source_name: str = "Mklan Studio Generated"
    generated_source_root: str = "/data/sources/generated"
    worker_status_url: str = "http://worker:9000"
    preview_root: str = "/workspace/storage/previews"
    access_token_ttl_seconds: int = 60 * 60 * 24
    cookie_secure: bool = False
    worker_poll_interval_seconds: int = 5
    basic_scan_batch_size: int = 1000
    worker_status_port: int = 9000
    max_thumbnail_size: int = 512
    deepzoom_tile_size: int = 256
    deepzoom_tile_overlap: int = 0
    deepzoom_tile_quality: int = 88
    preview_cache_max_mb: int = 2048
    duplicate_phash_threshold: int = 8
    semantic_neighbor_limit: int = 24
    semantic_similarity_threshold: float = 0.22
    clip_enabled: bool = True
    clip_model_id: str = "openai/clip-vit-base-patch32"
    clip_device: str = "cpu"
    nsfw_detector_enabled: bool = True
    nsfw_model_id: str = "Falconsai/nsfw_image_detection"
    model_cache_dir: str = "/workspace/storage/models"
    image_tagging_enabled: bool = True
    image_tagging_primary_provider: str = "wd_vit_v3"
    image_tagging_fallback_provider: str = "deepghs_wd_embeddings"
    wd_vit_model_id: str = "SmilingWolf/wd-vit-tagger-v3"
    deepghs_embedding_repo_id: str = "deepghs/wd14_tagger_with_embeddings"
    deepghs_embedding_subfolder: str = "SmilingWolf/wd-vit-tagger-v3"
    clip_vocab_threshold: float = 0.2
    tag_suggestion_general_threshold: float = 0.35
    tag_suggestion_meta_threshold: float = 0.45
    tag_suggestion_character_threshold: float = 0.6
    tag_suggestion_copyright_threshold: float = 0.6
    tag_suggestion_max_pending: int = 30
    caption_enabled: bool = True
    caption_model_id: str = "Salesforce/blip-image-captioning-base"
    caption_device: str = "auto"
    ocr_enabled: bool = True
    ocr_max_characters: int = 6000
    vision_llm_endpoint: str = "http://host.docker.internal:5001/v1"
    vision_llm_model: str = "koboldcpp"
    vision_llm_timeout_seconds: int = 180
    inbox_enabled: bool = True
    inbox_path: str = "/data/sources/upload"
    inbox_default_target_source: str = "/data/sources/sample"
    inbox_auto_approve: bool = False
    face_detection_enabled: bool = False
    face_min_size: int = 40
    face_recognition_threshold: float = 0.5
    face_detector_model_id: str = "opencv/face_detection_yunet"
    face_embedder_model_id: str = "opencv/face_recognition_sface"
    smart_album_suggestion_min_events: int = 5
    smart_album_suggestion_min_assets: int = 8
    smart_album_suggestion_lookback_days: int = 90

    @property
    def allowed_source_root_paths(self) -> list[Path]:
        return [
            Path(root.strip()).resolve(strict=False)
            for root in self.allowed_source_roots.split(",")
            if root.strip()
        ]

    @property
    def preview_root_path(self) -> Path:
        return Path(self.preview_root).resolve(strict=False)

    @property
    def windows_host_mount_root_path(self) -> Path:
        return Path(self.windows_host_mount_root).resolve(strict=False)

    @property
    def inbox_path_root(self) -> Path:
        return Path(self.inbox_path).resolve(strict=False)

    @property
    def model_cache_root_path(self) -> Path:
        return Path(self.model_cache_dir).resolve(strict=False)

    @model_validator(mode="after")
    def reject_insecure_defaults(self) -> "Settings":
        if self.app_env != "development" and self.session_secret.strip() in {"", "change-me", "change-me-in-production"}:
            raise ValueError(
                "SESSION_SECRET must be changed before running outside development."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
