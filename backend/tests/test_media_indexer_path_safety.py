from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException


REPO_ROOT = Path(__file__).resolve().parents[2]
MEDIA_INDEXER_SRC = REPO_ROOT / "media-indexer" / "backend" / "src"

if str(MEDIA_INDEXER_SRC) not in sys.path:
    sys.path.insert(0, str(MEDIA_INDEXER_SRC))


def test_validate_source_root_accepts_windows_drive_paths(monkeypatch, tmp_path):
    mount_root = tmp_path / "hostfs"
    allowed_root = mount_root / "j"
    target = allowed_root / "photos" / "set-a"
    target.mkdir(parents=True)

    monkeypatch.setenv("WINDOWS_HOST_MOUNT_ROOT", str(mount_root))
    monkeypatch.setenv("ALLOWED_SOURCE_ROOTS", str(allowed_root))

    from media_indexer_backend.core.config import get_settings
    from media_indexer_backend.services.path_safety import display_source_root, validate_source_root

    get_settings.cache_clear()
    try:
        validated = validate_source_root(r"J:\photos\set-a")
        assert validated == str(target.resolve())
        assert display_source_root(validated) == r"J:\photos\set-a"
    finally:
        get_settings.cache_clear()


def test_validate_source_root_rejects_unc_paths(monkeypatch, tmp_path):
    mount_root = tmp_path / "hostfs"
    allowed_root = mount_root / "z"
    allowed_root.mkdir(parents=True)

    monkeypatch.setenv("WINDOWS_HOST_MOUNT_ROOT", str(mount_root))
    monkeypatch.setenv("ALLOWED_SOURCE_ROOTS", str(allowed_root))

    from media_indexer_backend.core.config import get_settings
    from media_indexer_backend.services.path_safety import validate_source_root

    get_settings.cache_clear()
    try:
        with pytest.raises(HTTPException) as exc:
            validate_source_root(r"\\server\share\folder")
    finally:
        get_settings.cache_clear()

    assert "Map the network share to a Windows drive letter" in str(exc.value.detail)
