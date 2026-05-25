from __future__ import annotations

from pathlib import Path

from PIL import Image

from media_indexer_backend.core.config import get_settings
from media_indexer_backend.models.tables import Asset, Source
from media_indexer_backend.services.path_safety import resolve_asset_path


def _cache_root() -> Path:
    root = get_settings().preview_root_path / "cache"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _evict_lru_cache(root: Path, max_mb: int) -> None:
    files = [path for path in root.glob("*") if path.is_file()]
    total_size = sum(path.stat().st_size for path in files)
    max_bytes = max_mb * 1024 * 1024
    if total_size <= max_bytes:
        return
    for path in sorted(files, key=lambda item: item.stat().st_mtime):
        size = path.stat().st_size
        path.unlink(missing_ok=True)
        total_size -= size
        if total_size <= max_bytes:
            break


def ensure_cached_resized_image(
    asset: Asset,
    source: Source,
    *,
    width: int | None,
    height: int | None,
    quality: int,
    fmt: str,
) -> Path:
    source_path = resolve_asset_path(source.root_path, asset.relative_path)
    cache_root = _cache_root()
    cache_key = f"{asset.id}_{width or 0}x{height or 0}_q{quality}.{fmt}"
    cache_path = cache_root / cache_key
    if cache_path.exists():
        return cache_path

    with Image.open(source_path) as image:
        image = image.convert("RGB")
        if width or height:
            image.thumbnail((width or image.width, height or image.height), Image.Resampling.LANCZOS)
        if fmt == "webp":
            image.save(cache_path, format="WEBP", quality=quality, method=4)
        else:
            image.save(cache_path, format="JPEG", quality=quality, optimize=True)

    _evict_lru_cache(cache_root, get_settings().preview_cache_max_mb)
    return cache_path
