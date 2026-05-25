from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from ..config import Settings


class MediaModelDownloadService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def download(self, *, request: dict[str, Any], media_settings: dict[str, Any]) -> dict[str, Any]:
        repo_id = str(request.get("repo_id") or "").strip()
        if not repo_id:
            raise RuntimeError("A Hugging Face repo ID is required.")
        target = str(request.get("target") or "").strip().lower()
        if target not in {"image", "video"}:
            raise RuntimeError(f"Unsupported media download target: {target}")

        destination_root = self._resolve_destination_root(target=target, request=request, media_settings=media_settings)
        destination_root.mkdir(parents=True, exist_ok=True)

        revision = str(request.get("revision") or "").strip() or None
        token = str(request.get("token") or "").strip() or None
        filename = str(request.get("filename") or "").strip()
        include_patterns = self._normalize_patterns(request.get("include_patterns"))
        ignore_patterns = self._normalize_patterns(request.get("ignore_patterns"))

        try:
            from huggingface_hub import hf_hub_download, snapshot_download
        except Exception as exc:
            raise RuntimeError(
                f"huggingface_hub is not installed: {exc}. Rebuild the backend image after updating dependencies."
            ) from exc

        if filename:
            downloaded_path = Path(
                hf_hub_download(
                    repo_id=repo_id,
                    filename=filename,
                    revision=revision,
                    token=token,
                    local_dir=str(destination_root),
                )
            )
            settings_root = destination_root
            default_model = downloaded_path.name if target == "image" else ""
        else:
            downloaded_path = Path(
                snapshot_download(
                    repo_id=repo_id,
                    revision=revision,
                    token=token,
                    local_dir=str(destination_root),
                    allow_patterns=include_patterns or None,
                    ignore_patterns=ignore_patterns or None,
                )
            )
            settings_root = downloaded_path.parent if target == "image" else downloaded_path
            default_model = downloaded_path.name if target == "image" else ""

        return {
            "target": target,
            "repo_id": repo_id,
            "revision": revision or "",
            "filename": filename,
            "destination_path": destination_root.as_posix(),
            "downloaded_path": downloaded_path.as_posix(),
            "settings_path": settings_root.as_posix(),
            "default_model": default_model,
        }

    def _resolve_destination_root(self, *, target: str, request: dict[str, Any], media_settings: dict[str, Any]) -> Path:
        target_settings = media_settings.get(target, {})
        if target == "image":
            configured_root = Path(target_settings.get("checkpoint_root") or self.settings.default_image_model_root)
        else:
            configured_root = Path(target_settings.get("model_root") or self.settings.default_video_model_root)

        if configured_root.suffix:
            configured_root = configured_root.parent
        if not configured_root.is_absolute():
            configured_root = configured_root.resolve()

        destination_name = str(request.get("destination_name") or "").strip()
        if not destination_name:
            repo_slug = repo_id_slug(str(request.get("repo_id") or "model"))
            destination_name = repo_slug
        safe_name = sanitize_destination_name(destination_name)
        return configured_root / safe_name

    def _normalize_patterns(self, raw_value: Any) -> list[str]:
        if raw_value is None:
            return []
        if isinstance(raw_value, str):
            chunks = re.split(r"[\r\n,;]+", raw_value)
            return [chunk.strip() for chunk in chunks if chunk.strip()]
        if isinstance(raw_value, list):
            return [str(item).strip() for item in raw_value if str(item).strip()]
        return [str(raw_value).strip()]


def repo_id_slug(repo_id: str) -> str:
    return sanitize_destination_name(repo_id.split("/")[-1] or "model")


def sanitize_destination_name(name: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", name).strip("-")
    return safe or "model"
