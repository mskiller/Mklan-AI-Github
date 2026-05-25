from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from fastapi import HTTPException, status

from media_indexer_backend.core.config import get_settings

WINDOWS_DRIVE_PATTERN = re.compile(r"^(?P<drive>[A-Za-z]):(?:[\\/](?P<rest>.*))?$")
WINDOWS_UNC_PATTERN = re.compile(r"^[\\/]{2}(?P<server>[^\\/]+)[\\/](?P<share>[^\\/]+)(?:[\\/](?P<rest>.*))?$")


def _strip_wrapping_quotes(value: str) -> str:
    return value.strip().strip('"').strip("'")


def _normalized_windows_parts(raw_path: str) -> tuple[str, list[str]] | None:
    cleaned = _strip_wrapping_quotes(raw_path)
    match = WINDOWS_DRIVE_PATTERN.match(cleaned)
    if not match:
        return None

    drive = match.group("drive").lower()
    rest = match.group("rest") or ""
    parts = [part for part in re.split(r"[\\/]+", rest) if part not in {"", "."}]
    if any(part == ".." for part in parts):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Source root escapes the mounted Windows drive.")
    return drive, parts


def _translate_windows_drive_path(root_path: str) -> str | None:
    normalized = _normalized_windows_parts(root_path)
    if normalized is None:
        return None

    settings = get_settings()
    drive, parts = normalized
    target = settings.windows_host_mount_root_path / drive
    for part in parts:
        target /= part
    return str(target.resolve(strict=False))


def _windows_drive_mount_detail(root_path: str) -> tuple[str, Path, Path] | None:
    normalized = _normalized_windows_parts(root_path)
    if normalized is None:
        return None

    settings = get_settings()
    drive, parts = normalized
    mount_root = settings.windows_host_mount_root_path / drive
    candidate = mount_root
    for part in parts:
        candidate /= part
    return drive, mount_root, candidate.resolve(strict=False)


def display_source_root(root_path: str) -> str:
    settings = get_settings()
    resolved = Path(root_path).resolve(strict=False)
    mount_root = settings.windows_host_mount_root_path

    try:
        relative = resolved.relative_to(mount_root)
    except ValueError:
        return root_path

    parts = relative.parts
    if not parts:
        return root_path

    drive = parts[0]
    if len(drive) != 1 or not drive.isalpha():
        return root_path

    remainder = "\\".join(parts[1:])
    return f"{drive.upper()}:\\{remainder}" if remainder else f"{drive.upper()}:\\"


def validate_source_root(root_path: str) -> str:
    settings = get_settings()
    cleaned = _strip_wrapping_quotes(root_path)
    windows_detail = _windows_drive_mount_detail(cleaned)
    if windows_detail is not None:
        drive, mount_root, candidate = windows_detail
        if not mount_root.exists():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Windows drive {drive.upper()}: is not mounted in the media indexer containers. "
                    f"Add the Docker bind mount {drive.upper()}:\\:/hostfs/{drive}:ro to both "
                    "media_indexer_backend and media_worker, then restart the media-indexer profile."
                ),
            )
    else:
        unc_match = WINDOWS_UNC_PATTERN.match(cleaned)
        if unc_match:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Direct UNC paths are not available inside the Dockerized indexer. "
                    "Map the network share to a Windows drive letter such as Z:\\ and add that mapped path instead."
                ),
            )
        candidate = Path(cleaned).expanduser()
    if not candidate.is_absolute():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Source root must be an absolute path. "
                "Use a server path such as /data/sources/photos or a Windows path such as C:\\Photos."
            ),
        )

    resolved = candidate.resolve(strict=False)
    if not resolved.exists() or not resolved.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Source root does not exist on the server. "
                "If you are using Docker, make sure the host drive is mounted into the backend and worker containers "
                "and then use the Windows drive path or the matching container path."
            ),
        )

    allowed = settings.allowed_source_root_paths
    if not any(resolved == base or resolved.is_relative_to(base) for base in allowed):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Source root is outside the approved server roots. "
                f"Allowed roots: {', '.join(str(base) for base in allowed)}."
            ),
        )
    return str(resolved)


def normalize_relative_path(relative_path: str | None) -> str:
    if not relative_path:
        return ""

    normalized = relative_path.replace("\\", "/").strip()
    parts: list[str] = []
    for part in PurePosixPath(normalized).parts:
        if part in {"", "."}:
            continue
        if part == "..":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Relative path escapes the approved root.")
        parts.append(part)
    return "/".join(parts)


def _resolve_source_path(root_path: str, relative_path: str | None) -> tuple[Path, str]:
    root = Path(validate_source_root(root_path)).resolve(strict=True)
    normalized = normalize_relative_path(relative_path)
    candidate = (root / Path(*normalized.split("/"))).resolve(strict=True) if normalized else root
    if not candidate.is_relative_to(root):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Asset path escapes the approved root.")
    return candidate, normalized


def resolve_directory_path(root_path: str, relative_path: str | None) -> tuple[Path, str]:
    directory_path, normalized = _resolve_source_path(root_path, relative_path)
    if not directory_path.is_dir():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found.")
    return directory_path, normalized


def resolve_asset_path(root_path: str, relative_path: str) -> Path:
    asset_path, _ = _resolve_source_path(root_path, relative_path)
    if not asset_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset file not found.")
    return asset_path


def resolve_writable_directory_path(root_path: str, relative_path: str | None) -> tuple[Path, str]:
    root = Path(validate_source_root(root_path)).resolve(strict=True)
    normalized = normalize_relative_path(relative_path)
    candidate = (root / Path(*normalized.split("/"))).resolve(strict=False) if normalized else root
    if not candidate.is_relative_to(root):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Asset path escapes the approved root.")
    if candidate.exists() and not candidate.is_dir():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Upload folder path is not a directory.")
    return candidate, normalized
