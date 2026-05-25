from __future__ import annotations

from pathlib import Path
from uuid import UUID

from media_indexer_backend.core.config import get_settings


DEEPZOOM_ROOT_DIRNAME = "deepzoom"


def _preview_root(preview_root: Path | None = None) -> Path:
    root = (preview_root or get_settings().preview_root_path).resolve(strict=False)
    root.mkdir(parents=True, exist_ok=True)
    return root


def deepzoom_manifest_relative_path(asset_id: UUID) -> Path:
    return Path(DEEPZOOM_ROOT_DIRNAME) / f"{asset_id}.dzi"


def deepzoom_tiles_relative_dir(asset_id: UUID) -> Path:
    return Path(DEEPZOOM_ROOT_DIRNAME) / f"{asset_id}_files"


def deepzoom_manifest_absolute_path(asset_id: UUID, preview_root: Path | None = None) -> Path:
    return (_preview_root(preview_root) / deepzoom_manifest_relative_path(asset_id)).resolve(strict=False)


def deepzoom_tiles_absolute_dir(asset_id: UUID, preview_root: Path | None = None) -> Path:
    return (_preview_root(preview_root) / deepzoom_tiles_relative_dir(asset_id)).resolve(strict=False)


def deepzoom_tile_absolute_path(asset_id: UUID, tile_path: str, preview_root: Path | None = None) -> Path:
    return (deepzoom_tiles_absolute_dir(asset_id, preview_root) / tile_path).resolve(strict=False)


def deepzoom_available(asset_id: UUID, preview_root: Path | None = None) -> bool:
    return deepzoom_manifest_absolute_path(asset_id, preview_root).exists()


def deepzoom_url(asset_id: UUID, preview_root: Path | None = None) -> str | None:
    if not deepzoom_available(asset_id, preview_root):
        return None
    return f"/assets/{asset_id}/deepzoom.dzi"

