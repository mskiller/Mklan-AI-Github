from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from fastapi import HTTPException, UploadFile


MODEL_EXTENSIONS = {".safetensors", ".ckpt", ".pt", ".bin", ".gguf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
IMAGE_MAGIC = {
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".webp": (b"RIFF",),
}


def max_model_upload_bytes() -> int:
    return int(os.getenv("STUDIO_MODEL_UPLOAD_MAX_BYTES", str(32 * 1024 * 1024 * 1024)))


def max_image_upload_bytes() -> int:
    return int(os.getenv("STUDIO_IMAGE_UPLOAD_MAX_BYTES", str(100 * 1024 * 1024)))


def safe_upload_name(filename: str | None, *, allowed_extensions: Iterable[str]) -> str:
    if not filename:
        raise HTTPException(status_code=400, detail="Uploaded file must have a filename.")
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Uploaded filename must not contain path components.")
    safe_name = Path(filename).name
    if safe_name in {"", ".", ".."}:
        raise HTTPException(status_code=400, detail="Uploaded filename must not contain path components.")
    suffix = Path(safe_name).suffix.lower()
    if suffix not in set(allowed_extensions):
        allowed = ", ".join(sorted(allowed_extensions))
        raise HTTPException(status_code=400, detail=f"Unsupported file extension. Allowed: {allowed}.")
    return safe_name


def _validate_magic(filename: str, first_chunk: bytes) -> None:
    suffix = Path(filename).suffix.lower()
    signatures = IMAGE_MAGIC.get(suffix)
    if not signatures:
        return
    if suffix == ".webp":
        if not (first_chunk.startswith(b"RIFF") and first_chunk[8:12] == b"WEBP"):
            raise HTTPException(status_code=400, detail="Uploaded WebP file signature is invalid.")
        return
    if not any(first_chunk.startswith(signature) for signature in signatures):
        raise HTTPException(status_code=400, detail="Uploaded image file signature is invalid.")


def save_upload_with_limits(
    file: UploadFile,
    target: Path,
    *,
    allowed_extensions: Iterable[str],
    max_bytes: int,
    validate_image_magic: bool = False,
) -> str:
    safe_name = safe_upload_name(file.filename, allowed_extensions=allowed_extensions)
    target.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    first_chunk = b""
    try:
        with target.open("wb") as output:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                if not first_chunk:
                    first_chunk = chunk[:16]
                    if validate_image_magic:
                        _validate_magic(safe_name, first_chunk)
                total += len(chunk)
                if total > max_bytes:
                    target.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail=f"Uploaded file exceeds the {max_bytes} byte limit.")
                output.write(chunk)
    finally:
        file.file.close()
    if validate_image_magic and not first_chunk:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    return safe_name
