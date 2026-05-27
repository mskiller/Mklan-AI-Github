from __future__ import annotations

import asyncio
import base64
from datetime import UTC, datetime
import io
import json
import mimetypes
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import signal
import sys
from typing import Any, Literal
from urllib.parse import urljoin, urlparse, urlunparse
import uuid
import zipfile

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
import requests

from app.studio_features import DATA
from app.v2.jobs import JobCanceled, JobManager, JobRead
from app.v2.upload_security import IMAGE_EXTENSIONS, max_image_upload_bytes, safe_upload_name, save_upload_with_limits


router = APIRouter(prefix="/training", tags=["training"])

TRAINING_ROOT = DATA / "training"
DATASETS_ROOT = TRAINING_ROOT / "datasets"
RUNS_ROOT = TRAINING_ROOT / "runs"
TRAINING_OUTPUT_ROOT = DATA / "models" / "loras"

DATASETS_ROOT.mkdir(parents=True, exist_ok=True)
RUNS_ROOT.mkdir(parents=True, exist_ok=True)
TRAINING_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

TRAINING_JOB_TYPES = {
    "sd15_lora": "training.sd15_lora",
    "sdxl_lora": "training.sdxl_lora",
    "sdxl_pony_lora": "training.sdxl_pony_lora",
    "sdxl_finetune": "training.sdxl_finetune",
    "flux_lora": "training.flux_lora",
    "anima_lora": "training.anima_lora",
    "z_image_lora": "training.z_image_lora",
}
CAPTION_SCAN_JOB_TYPE = "training.caption_scan"

LORA_NETWORK_MODULES = {
    "lora": "networks.lora",
    "locon": "lycoris.kohya",
    "loha": "lycoris.kohya",
    "lokr": "lycoris.kohya",
}
LORA_NETWORK_ARGS = {
    "locon": ["algo=locon"],
    "loha": ["algo=loha"],
    "lokr": ["algo=lokr"],
}
ZIP_EXTENSIONS = {".zip"}
CAPTION_MODEL_ROOT = DATA / "models" / "captioning"
DEFAULT_CLIP_TAGS_FILE = Path(__file__).resolve().parent / "resources" / "caption_tags_default.txt"
CAPTION_CLIP_MODELS = {
    "OysterQAQ/DanbooruCLIP": "DanbooruCLIP",
    "laion/CLIP-ViT-B-32-laion2B-s34B-b79K": "LAION CLIP ViT-B/32",
    "patrickjohncyh/fashion-clip": "FashionCLIP",
    "openai/clip-vit-large-patch14": "OpenAI CLIP ViT-L/14",
}
OPEN_CLIP_MODEL_IDS = {"laion/CLIP-ViT-B-32-laion2B-s34B-b79K"}

MODEL_FAMILY_PROFILES: dict[str, dict[str, Any]] = {
    "sd15": {
        "id": "sd15",
        "label": "SD 1.5",
        "default_preset": "sd15_lora",
        "model_root": "SD15",
        "resolution": 768,
        "caption_style": "sdxl_tags",
        "trainer": "kohya-ss sd-scripts",
        "notes": "Classic LoRA stack for SD 1.5 checkpoints.",
    },
    "sdxl": {
        "id": "sdxl",
        "label": "SDXL",
        "default_preset": "sdxl_lora",
        "model_root": "Base",
        "resolution": 1024,
        "caption_style": "sdxl_tags",
        "trainer": "kohya-ss sd-scripts",
        "notes": "Default SDXL LoRA path.",
    },
    "sdxl_pony": {
        "id": "sdxl_pony",
        "label": "SDXL Pony",
        "default_preset": "sdxl_pony_lora",
        "model_root": "Pony",
        "resolution": 1024,
        "caption_style": "pony_tags",
        "trainer": "kohya-ss sd-scripts",
        "notes": "Pony-style tag captions and SDXL LoRA command defaults.",
    },
    "flux": {
        "id": "flux",
        "label": "Flux.1",
        "default_preset": "flux_lora",
        "model_root": "Flux",
        "resolution": 1024,
        "caption_style": "natural_language",
        "trainer": "SimpleTuner / Flux external script",
        "notes": "Natural-language captions and a guarded SimpleTuner-compatible command path.",
    },
}


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def slugify(value: str, fallback: str = "item") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("-._").lower()
    return cleaned[:80] or fallback


class DatasetCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    trigger_token: str = Field(default="", max_length=80)
    class_tokens: str = Field(default="person", max_length=160)
    resolution: int = Field(default=1024, ge=256, le=2048)
    batch_size: int = Field(default=1, ge=1, le=16)
    num_repeats: int = Field(default=7, ge=1, le=1000)
    caption_extension: str = ".txt"
    enable_bucket: bool = True
    bucket_no_upscale: bool = True
    shuffle_caption: bool = False
    keep_tokens: int = Field(default=0, ge=0, le=255)


class CollectionDatasetImportRequest(BaseModel):
    collection_id: str = Field(min_length=1, max_length=160)
    name: str | None = Field(default=None, max_length=120)
    trigger_token: str = Field(default="", max_length=80)
    class_tokens: str = Field(default="person", max_length=160)
    resolution: int = Field(default=1024, ge=256, le=2048)
    batch_size: int = Field(default=1, ge=1, le=16)
    num_repeats: int = Field(default=7, ge=1, le=1000)
    caption_extension: str = ".txt"
    enable_bucket: bool = True
    bucket_no_upscale: bool = True
    shuffle_caption: bool = False
    keep_tokens: int = Field(default=0, ge=0, le=255)
    max_items: int = Field(default=500, ge=1, le=5000)


class CaptionUpdateRequest(BaseModel):
    filename: str
    caption: str = ""


class TriggerCaptionApplyRequest(BaseModel):
    trigger_word: str = Field(min_length=1, max_length=80)
    separator: str = Field(default=", ", max_length=8)
    create_missing: bool = True


class CaptionScanRequest(BaseModel):
    max_words: int = Field(default=40, ge=1, le=200)
    overwrite: bool = False
    prepend_trigger: bool = True
    trigger_word: str | None = Field(default=None, max_length=80)
    provider: Literal["auto", "local_blip", "koboldcpp_vlm", "clip_tagger", "florence2", "filename_fallback"] = "auto"
    caption_style: Literal["sdxl_tags", "pony_tags", "natural_language"] = "sdxl_tags"
    local_model_id: str | None = Field(default=None, max_length=240)
    clip_model_id: str | None = Field(default=None, max_length=240)


class DatasetRead(BaseModel):
    id: str
    name: str
    path: str
    image_count: int
    caption_count: int
    config_file: str | None = None
    settings: dict[str, Any]
    created_at: str
    updated_at: str


class DatasetItemRead(BaseModel):
    filename: str
    image_url: str
    caption: str
    caption_file: str | None = None
    has_caption: bool
    size: int
    modified_at: str


class DatasetConfigResponse(BaseModel):
    dataset: DatasetRead
    config_file: str
    toml: str


class DatasetTriggerApplyResponse(BaseModel):
    dataset: DatasetRead
    items: list[DatasetItemRead]
    updated: int
    unchanged: int


class DatasetZipImportResponse(BaseModel):
    dataset: DatasetRead
    items: list[DatasetItemRead]
    imported: int
    captions: int
    skipped: int


class CollectionDatasetImportResponse(BaseModel):
    dataset: DatasetRead
    imported: int
    skipped: int
    collection_id: str
    collection_name: str


class TrainingModelFileRead(BaseModel):
    name: str
    path: str
    size: int
    kind: Literal["base", "vae"]
    family: str = "sdxl"
    modified_at: str


class TrainingModelFilesResponse(BaseModel):
    families: list[dict[str, Any]]
    base_models: list[TrainingModelFileRead]
    vae_models: list[TrainingModelFileRead]
    dry_run_forced: bool
    sd_scripts_root: str
    sd_scripts_ready: bool
    accelerate_bin: str


class CaptionScanResponse(BaseModel):
    job: JobRead
    events_url: str


class TrainingRunRequest(BaseModel):
    dataset_id: str
    model_family: Literal["sd15", "sdxl", "sdxl_pony", "flux"] = "sdxl"
    preset: Literal["sd15_lora", "sdxl_lora", "sdxl_pony_lora", "sdxl_finetune", "flux_lora", "anima_lora", "z_image_lora"] = "sdxl_lora"
    output_name: str = Field(default="mklan-sdxl-lora", max_length=120)
    base_model: str = Field(default="", max_length=500)
    vae: str = Field(default="", max_length=500)
    epochs: int = Field(default=10, ge=1, le=10_000)
    num_repeats: int = Field(default=7, ge=1, le=1000)
    max_train_steps: int = Field(default=800, ge=1, le=2_000_000)
    resolution: int = Field(default=1024, ge=256, le=2048)
    lora_type: Literal["lora", "locon", "loha", "lokr"] = "lora"
    enable_bucket: bool = True
    bucket_no_upscale: bool = True
    shuffle_caption: bool = False
    keep_tokens: int = Field(default=0, ge=0, le=255)
    clip_skip: int = Field(default=1, ge=1, le=12)
    flip_aug: bool = False
    learning_rate: float = Field(default=1e-4, gt=0, le=1)
    unet_lr: float = Field(default=5e-4, gt=0, le=1)
    text_encoder_lr: float = Field(default=5e-5, ge=0, le=1)
    lr_scheduler: str = Field(default="cosine", max_length=80)
    lr_scheduler_num_cycles: int = Field(default=3, ge=1, le=100)
    min_snr_gamma: float = Field(default=5, ge=0, le=100)
    network_dim: int = Field(default=16, ge=1, le=1024)
    network_alpha: int = Field(default=8, ge=1, le=1024)
    noise_offset: float = Field(default=0.1, ge=0, le=10)
    optimizer_type: str = Field(default="Adafactor", max_length=80)
    mixed_precision: Literal["auto", "bf16", "fp16", "no"] = "auto"
    save_every_n_epochs: int = Field(default=1, ge=1, le=100)
    sample_prompt: str = ""
    dry_run: bool = False
    model_components: dict[str, str] = Field(default_factory=dict)
    extra_args: dict[str, str | int | float | bool] = Field(default_factory=dict)


class TrainingCommandPreview(BaseModel):
    preset: str
    script: str
    working_dir: str
    command: list[str]
    display_command: str
    dataset_config: str
    output_dir: str


class TrainingRunResponse(BaseModel):
    job: JobRead
    events_url: str
    command: TrainingCommandPreview | None = None


class ArtifactRead(BaseModel):
    name: str
    path: str
    size: int
    modified_at: str
    kind: str


def register_training_jobs(manager: JobManager) -> None:
    for job_type in TRAINING_JOB_TYPES.values():
        manager.register_handler(job_type, run_training_job)
    manager.register_handler(CAPTION_SCAN_JOB_TYPE, run_caption_scan_job)


def _metadata_path(dataset_id: str) -> Path:
    return DATASETS_ROOT / dataset_id / "metadata.json"


def _load_dataset(dataset_id: str) -> dict[str, Any]:
    metadata_path = _metadata_path(slugify(dataset_id))
    if not metadata_path.exists():
        raise HTTPException(status_code=404, detail="Training dataset not found.")
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def _write_dataset(metadata: dict[str, Any]) -> None:
    now = utc_now_iso()
    metadata["updated_at"] = now
    metadata_path = _metadata_path(metadata["id"])
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def _dataset_counts(dataset_dir: Path, caption_extension: str) -> tuple[int, int]:
    image_dir = dataset_dir / "images"
    image_count = sum(1 for path in image_dir.glob("*") if path.suffix.lower() in IMAGE_EXTENSIONS and path.is_file())
    caption_count = sum(1 for path in image_dir.glob(f"*{caption_extension}") if path.is_file())
    return image_count, caption_count


def _caption_extension(settings: dict[str, Any]) -> str:
    extension = str(settings.get("caption_extension") or ".txt").strip() or ".txt"
    if not extension.startswith("."):
        extension = f".{extension}"
    if "/" in extension or "\\" in extension or extension in {".", ".."}:
        raise HTTPException(status_code=400, detail="Caption extension is invalid.")
    return extension


def _dataset_image_dir(metadata: dict[str, Any]) -> Path:
    return Path(metadata["path"]) / "images"


def _caption_path_for_image(image_path: Path, settings: dict[str, Any]) -> Path:
    return image_path.with_suffix(_caption_extension(settings))


def _read_caption(caption_path: Path) -> str:
    if not caption_path.exists() or not caption_path.is_file():
        return ""
    return caption_path.read_text(encoding="utf-8", errors="replace").strip()


def _dataset_items(metadata: dict[str, Any]) -> list[DatasetItemRead]:
    settings = metadata.get("settings") or {}
    image_dir = _dataset_image_dir(metadata)
    if not image_dir.exists():
        return []
    items = []
    for image_path in sorted(image_dir.glob("*"), key=lambda item: item.name.lower()):
        if not image_path.is_file() or image_path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        caption_path = _caption_path_for_image(image_path, settings)
        stat = image_path.stat()
        items.append(
            DatasetItemRead(
                filename=image_path.name,
                image_url=f"/api/training/datasets/{metadata['id']}/images/{image_path.name}",
                caption=_read_caption(caption_path),
                caption_file=str(caption_path) if caption_path.exists() else None,
                has_caption=caption_path.exists(),
                size=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
            )
        )
    return items


def _dataset_read(metadata: dict[str, Any]) -> DatasetRead:
    dataset_dir = Path(metadata["path"])
    settings = metadata.get("settings") or {}
    image_count, caption_count = _dataset_counts(dataset_dir, _caption_extension(settings))
    config_file = metadata.get("config_file")
    return DatasetRead(
        id=metadata["id"],
        name=metadata["name"],
        path=str(dataset_dir),
        image_count=image_count,
        caption_count=caption_count,
        config_file=config_file if config_file and Path(config_file).exists() else None,
        settings=settings,
        created_at=metadata["created_at"],
        updated_at=metadata["updated_at"],
    )


def _toml_string(value: str) -> str:
    return json.dumps(value)


def _build_dataset_toml(metadata: dict[str, Any], overrides: dict[str, Any] | None = None) -> str:
    settings = dict(metadata.get("settings") or {})
    for key in (
        "resolution",
        "batch_size",
        "num_repeats",
        "caption_extension",
        "enable_bucket",
        "bucket_no_upscale",
        "shuffle_caption",
        "keep_tokens",
    ):
        if overrides and overrides.get(key) is not None:
            settings[key] = overrides[key]
    image_dir = _dataset_image_dir(metadata)
    caption_extension = _caption_extension(settings)
    class_tokens = " ".join(item for item in [settings.get("trigger_token", ""), settings.get("class_tokens", "")] if item).strip()
    lines = [
        "[general]",
        f"shuffle_caption = {str(bool(settings.get('shuffle_caption', False))).lower()}",
        f"caption_extension = {_toml_string(caption_extension)}",
        f"keep_tokens = {int(settings.get('keep_tokens') or 0)}",
        "",
        "[[datasets]]",
        f"resolution = {int(settings.get('resolution') or 1024)}",
        f"batch_size = {int(settings.get('batch_size') or 1)}",
        f"enable_bucket = {str(bool(settings.get('enable_bucket', True))).lower()}",
        f"bucket_no_upscale = {str(bool(settings.get('bucket_no_upscale', True))).lower()}",
        "",
        "  [[datasets.subsets]]",
        f"  image_dir = {_toml_string(str(image_dir))}",
        f"  num_repeats = {int(settings.get('num_repeats') or 7)}",
        f"  caption_extension = {_toml_string(caption_extension)}",
        f"  class_tokens = {_toml_string(class_tokens)}",
        "",
    ]
    return "\n".join(lines)


def build_dataset_config(dataset_id: str, overrides: dict[str, Any] | None = None) -> DatasetConfigResponse:
    metadata = _load_dataset(dataset_id)
    toml = _build_dataset_toml(metadata, overrides=overrides)
    config_path = Path(metadata["path"]) / "dataset_config.toml"
    config_path.write_text(toml, encoding="utf-8")
    metadata["config_file"] = str(config_path)
    _write_dataset(metadata)
    return DatasetConfigResponse(dataset=_dataset_read(metadata), config_file=str(config_path), toml=toml)


def _media_indexer_base_url() -> str:
    return os.getenv("MEDIA_INDEXER_INTERNAL_URL", "http://media_indexer_backend:8000").rstrip("/")


def _media_indexer_timeout_s() -> float:
    return float(os.getenv("MEDIA_INDEXER_TIMEOUT_S", "60"))


def _media_indexer_url(path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return urljoin(f"{_media_indexer_base_url()}/", path.lstrip("/"))


def _collection_caption(item: dict[str, Any], settings: dict[str, Any]) -> str:
    for key in ("caption", "prompt_tag_string", "prompt_excerpt", "ocr_text"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    prompt_tags = item.get("prompt_tags")
    if isinstance(prompt_tags, list):
        tags = ", ".join(str(tag).strip() for tag in prompt_tags if str(tag).strip())
        if tags:
            return tags
    return " ".join(item for item in [settings.get("trigger_token", ""), settings.get("class_tokens", "")] if item).strip()


def _settings_dict() -> dict[str, Any]:
    try:
        from app.studio_features import load_settings

        return load_settings()
    except Exception:
        return {}


def _caption_starts_with_trigger(caption: str, trigger_word: str) -> bool:
    normalized = caption.lstrip()
    trigger = trigger_word.strip()
    return (
        normalized == trigger
        or normalized.startswith(f"{trigger} ")
        or normalized.startswith(f"{trigger},")
        or normalized.startswith(f"{trigger}:")
    )


def _prepend_trigger(caption: str, trigger_word: str, separator: str) -> tuple[str, bool]:
    trigger = trigger_word.strip()
    normalized_separator = separator if separator else " "
    stripped = caption.strip()
    if _caption_starts_with_trigger(stripped, trigger):
        return stripped, False
    if not stripped:
        return trigger, True
    return f"{trigger}{normalized_separator}{stripped}", True


def _collection_image_name(item: dict[str, Any]) -> str | None:
    filename = str(item.get("filename") or "").strip()
    if filename and Path(filename).suffix.lower() in IMAGE_EXTENSIONS:
        return filename
    relative_path = str(item.get("relative_path") or "").strip()
    if relative_path and Path(relative_path).suffix.lower() in IMAGE_EXTENSIONS:
        return Path(relative_path).name
    content_url = str(item.get("content_url") or item.get("preview_url") or "").strip()
    if content_url and Path(content_url).suffix.lower() in IMAGE_EXTENSIONS:
        return Path(content_url).name
    asset_id = str(item.get("id") or "").strip()
    return f"{asset_id or uuid.uuid4().hex}.png"


def _dataset_zip_max_bytes() -> int:
    return int(os.getenv("STUDIO_DATASET_ZIP_MAX_BYTES", str(1024 * 1024 * 1024)))


def _read_upload_bytes_with_limit(upload: UploadFile, max_bytes: int) -> bytes:
    total = 0
    chunks: list[bytes] = []
    try:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise HTTPException(status_code=413, detail=f"Uploaded file exceeds the {max_bytes} byte limit.")
            chunks.append(chunk)
    finally:
        upload.file.close()
    if not chunks:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    return b"".join(chunks)


def _validate_image_bytes(filename: str, payload: bytes) -> None:
    try:
        from PIL import Image

        with Image.open(io.BytesIO(payload)) as image:
            image.verify()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"{filename} is not a readable image.") from exc


def _write_png_to_zip(archive: zipfile.ZipFile, archive_name: str, image_path: Path) -> None:
    try:
        from PIL import Image

        with Image.open(image_path) as image:
            if image.mode not in {"RGB", "RGBA", "L", "LA"}:
                image = image.convert("RGB")
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            archive.writestr(archive_name, buffer.getvalue())
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Unable to export {image_path.name} as PNG.") from exc


def _dataset_zip_bytes(dataset_id: str) -> tuple[bytes, str]:
    metadata = _load_dataset(dataset_id)
    items = _dataset_items(metadata)
    width = max(3, len(str(len(items) or 1)))
    buffer = io.BytesIO()
    image_dir = _dataset_image_dir(metadata)
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, item in enumerate(items, start=1):
            stem = f"{index:0{width}d}"
            _write_png_to_zip(archive, f"{stem}.png", image_dir / item.filename)
            archive.writestr(f"{stem}.txt", item.caption or "")
    filename = f"{slugify(metadata.get('name', 'dataset'), 'dataset')}-training-dataset.zip"
    return buffer.getvalue(), filename


def _limit_caption_words(caption: str, max_words: int) -> str:
    words = [word for word in re.split(r"\s+", caption.strip()) if word]
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words])


_FILENAME_CAPTION_STOPWORDS = {
    "openart",
    "image",
    "raw",
    "output",
    "generated",
    "generation",
    "img",
    "photo",
    "picture",
}


def _useful_caption_context(value: str | None) -> str:
    cleaned = re.sub(r"[_\-.]+", " ", str(value or "")).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        return ""
    lowered = cleaned.lower()
    if re.fullmatch(r"(test\d*|dataset|training dataset|zip dataset|caption scan|dry run)", lowered):
        return ""
    return cleaned


def _caption_context_from_zip(file_name: str, root_labels: set[str]) -> str:
    candidates = [_useful_caption_context(label) for label in sorted(root_labels, key=len, reverse=True)]
    candidates.append(_useful_caption_context(Path(file_name).stem))
    return next((candidate for candidate in candidates if candidate), "")


def _caption_fallback_context(metadata: dict[str, Any]) -> str:
    direct = _useful_caption_context(str(metadata.get("caption_context") or ""))
    if direct:
        return direct
    imports = metadata.get("source_archives")
    if isinstance(imports, list):
        for item in reversed(imports):
            if isinstance(item, dict):
                context = _useful_caption_context(str(item.get("caption_context") or ""))
                if context:
                    return context
    return _useful_caption_context(str(metadata.get("name") or ""))


def _fallback_caption_from_filename(path: Path, max_words: int, context: str = "") -> str:
    tokens = re.split(r"[\s_\-.]+", path.stem)
    useful_tokens: list[str] = []
    for token in tokens:
        cleaned = re.sub(r"[^a-zA-Z]+", "", token).strip()
        lowered = cleaned.lower()
        if not lowered or lowered in _FILENAME_CAPTION_STOPWORDS:
            continue
        if len(token) >= 6 and any(char.isdigit() for char in token):
            continue
        if re.fullmatch(r"\d+", token):
            continue
        useful_tokens.append(cleaned)
    parts = []
    useful_context = _useful_caption_context(context)
    if useful_context:
        parts.append(useful_context)
    if useful_tokens:
        parts.append(" ".join(useful_tokens))
    caption = re.sub(r"\s+", " ", ", ".join(parts)).strip(" ,") or "image"
    return _limit_caption_words(caption, max_words)


def _caption_as_natural_language(caption: str, max_words: int) -> str:
    cleaned = re.sub(r"\s+", " ", caption.replace("_", " ")).strip(" ,")
    if not cleaned:
        return "A training image."
    if re.search(r"[.!?]$", cleaned) and "," not in cleaned:
        return _limit_caption_words(cleaned, max_words)
    tags = [part.strip(" .") for part in cleaned.split(",") if part.strip(" .")]
    if not tags:
        return _limit_caption_words(cleaned, max_words)
    sentence = "A training image showing " + ", ".join(tags[:12]) + "."
    return _limit_caption_words(sentence, max_words)


def _apply_caption_style(caption: str, caption_style: str, max_words: int) -> str:
    if caption_style == "natural_language":
        return _caption_as_natural_language(caption, max_words)
    return _limit_caption_words(caption, max_words)


_CAPTIONING_MODEL_CACHE: dict[str, tuple[Any, Any, str] | Literal[False]] = {}
_CAPTION_CLIP_MODEL_CACHE: dict[tuple[str, str], tuple[Any, ...] | Literal[False]] = {}
_CAPTION_CLIP_TAG_CACHE: dict[str, tuple[float, list[str]]] = {}


def _caption_model_id(model_id: str | None = None) -> str:
    candidate = (model_id or os.getenv("STUDIO_CAPTION_MODEL_ID", "")).strip()
    return candidate or "Salesforce/blip-image-captioning-base"


def _caption_local_model_ref(model_id: str) -> str:
    if Path(model_id).exists():
        return model_id
    local_dir = CAPTION_MODEL_ROOT / _safe_model_dir_name(model_id)
    if local_dir.exists():
        return str(local_dir)
    bare_local_dir = CAPTION_MODEL_ROOT / model_id
    if bare_local_dir.exists():
        return str(bare_local_dir)
    return model_id


def _caption_download_allowed() -> bool:
    return os.getenv("STUDIO_CAPTION_ALLOW_DOWNLOAD", "").lower() in {"1", "true", "yes", "on"}


def _captioning_disabled() -> bool:
    return os.getenv("STUDIO_DISABLE_LOCAL_CAPTIONING", "").lower() in {"1", "true", "yes", "on"}


def _safe_model_dir_name(model_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", model_id.strip()).strip("-._") or "model"


def _caption_clip_model_id(model_id: str | None = None) -> str:
    candidate = (model_id or os.getenv("STUDIO_CAPTION_CLIP_MODEL_ID", "")).strip()
    return candidate or "OysterQAQ/DanbooruCLIP"


def _caption_clip_model_source(model_id: str) -> str:
    configured = os.getenv("STUDIO_CAPTION_CLIP_MODEL_SOURCE", "auto").strip().lower() or "auto"
    if configured in {"transformers", "open_clip"}:
        return configured
    return "open_clip" if model_id in OPEN_CLIP_MODEL_IDS else "transformers"


def _caption_clip_allow_download() -> bool:
    explicit = os.getenv("STUDIO_CAPTION_CLIP_ALLOW_DOWNLOAD", "").strip().lower()
    if explicit:
        return explicit in {"1", "true", "yes", "on"}
    return _caption_download_allowed()


def _caption_clip_top_k(max_words: int) -> int:
    try:
        configured = int(os.getenv("STUDIO_CAPTION_CLIP_TOP_K", "24") or "24")
    except ValueError:
        configured = 24
    return max(1, min(configured, max_words, 80))


def _caption_clip_threshold() -> float:
    try:
        return max(0.0, float(os.getenv("STUDIO_CAPTION_CLIP_THRESHOLD", "0") or "0"))
    except ValueError:
        return 0.0


def _caption_clip_max_candidates() -> int:
    try:
        return max(16, min(int(os.getenv("STUDIO_CAPTION_CLIP_MAX_CANDIDATES", "256") or "256"), 4096))
    except ValueError:
        return 256


def _caption_clip_tags_path() -> Path:
    configured = os.getenv("STUDIO_CAPTION_CLIP_TAGS_PATH", "").strip()
    return Path(configured) if configured else DEFAULT_CLIP_TAGS_FILE


def _caption_clip_cache_dir() -> Path:
    return Path(os.getenv("STUDIO_CAPTION_CLIP_CACHE_DIR", str(CAPTION_MODEL_ROOT / "hf-cache")))


def _caption_clip_prompt_template() -> str:
    return os.getenv("STUDIO_CAPTION_CLIP_PROMPT_TEMPLATE", "{tag}").strip() or "{tag}"


def _caption_clip_model_ref(model_id: str) -> str:
    if Path(model_id).exists():
        return model_id
    local_dir = CAPTION_MODEL_ROOT / _safe_model_dir_name(model_id)
    return str(local_dir) if local_dir.exists() else model_id


def _clip_candidate_tags() -> list[str]:
    tags_path = _caption_clip_tags_path()
    cache_key = str(tags_path)
    mtime = tags_path.stat().st_mtime if tags_path.exists() else -1
    cached = _CAPTION_CLIP_TAG_CACHE.get(cache_key)
    if cached and cached[0] == mtime:
        return cached[1]
    raw_lines: list[str]
    if tags_path.exists():
        raw_lines = tags_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    elif DEFAULT_CLIP_TAGS_FILE.exists():
        raw_lines = DEFAULT_CLIP_TAGS_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
    else:
        raw_lines = ["portrait", "person", "standing", "indoors", "outdoors", "close-up", "anime style"]
    tags: list[str] = []
    seen: set[str] = set()
    for raw_line in raw_lines:
        tag = raw_line.split("#", 1)[0].strip().strip(",")
        if not tag:
            continue
        normalized = re.sub(r"\s+", " ", tag.replace("_", " ")).strip().lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        tags.append(tag)
        if len(tags) >= _caption_clip_max_candidates():
            break
    _CAPTION_CLIP_TAG_CACHE[cache_key] = (mtime, tags)
    return tags


def _clip_text_for_tag(tag: str) -> str:
    normalized = re.sub(r"\s+", " ", tag.replace("_", " ")).strip()
    template = _caption_clip_prompt_template()
    return template.replace("{tag}", normalized)


def _caption_from_scored_tags(tags: list[str], scores: list[float], max_words: int) -> str:
    top_k = _caption_clip_top_k(max_words)
    threshold = _caption_clip_threshold()
    ranked = sorted(zip(tags, scores), key=lambda item: item[1], reverse=True)
    selected: list[str] = []
    for tag, score in ranked:
        if threshold and score < threshold:
            continue
        cleaned = re.sub(r"\s+", " ", tag.replace("_", " ")).strip(" ,")
        if not cleaned:
            continue
        selected.append(cleaned)
        if len(selected) >= top_k:
            break
    if not selected and ranked:
        selected = [re.sub(r"\s+", " ", tag.replace("_", " ")).strip(" ,") for tag, _ in ranked[:top_k]]
    return _limit_caption_words(", ".join(tag for tag in selected if tag), max_words)


def _caption_image_with_transformers_clip(path: Path, max_words: int, model_id: str, diagnostics: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    global _CAPTION_CLIP_MODEL_CACHE
    source = "transformers"
    model_ref = _caption_clip_model_ref(model_id)
    cache_key = (model_ref, source)
    if _CAPTION_CLIP_MODEL_CACHE.get(cache_key) is False:
        return None, {**diagnostics, "source": "clip_unavailable", "fallback_reason": "CLIP tagger model is unavailable after a previous load failure."}
    try:
        from PIL import Image
        import torch
        from transformers import AutoProcessor, CLIPModel

        if cache_key not in _CAPTION_CLIP_MODEL_CACHE:
            processor = AutoProcessor.from_pretrained(model_ref, local_files_only=not _caption_clip_allow_download())
            model = CLIPModel.from_pretrained(model_ref, local_files_only=not _caption_clip_allow_download())
            device = "cuda" if torch.cuda.is_available() else "cpu"
            model.to(device)
            model.eval()
            _CAPTION_CLIP_MODEL_CACHE[cache_key] = (processor, model, device)
        processor, model, device = _CAPTION_CLIP_MODEL_CACHE[cache_key]  # type: ignore[misc]
        tags = _clip_candidate_tags()
        if not tags:
            return None, {**diagnostics, "source": "clip_unconfigured", "fallback_reason": "No CLIP candidate tags are configured."}
        texts = [_clip_text_for_tag(tag) for tag in tags]
        with Image.open(path) as image:
            inputs = processor(text=texts, images=image.convert("RGB"), return_tensors="pt", padding=True, truncation=True)
        inputs = {key: value.to(device) for key, value in inputs.items()}
        with torch.no_grad():
            logits = model(**inputs).logits_per_image[0]
            probabilities = logits.softmax(dim=0).detach().cpu().tolist()
        caption = _caption_from_scored_tags(tags, [float(score) for score in probabilities], max_words)
        if not caption:
            return None, {**diagnostics, "source": "clip_empty", "fallback_reason": "CLIP tagger produced no caption."}
        return caption, {**diagnostics, "source": "clip_tagger", "runtime": source, "model_ref": model_ref, "device": device, "tag_count": len(tags)}
    except Exception as exc:
        _CAPTION_CLIP_MODEL_CACHE[cache_key] = False
        return None, {
            **diagnostics,
            "source": "clip_error",
            "runtime": source,
            "model_ref": model_ref,
            "fallback_reason": "CLIP tagger failed; fallback was used.",
            "error": f"{type(exc).__name__}: {exc}",
        }


def _caption_image_with_open_clip(path: Path, max_words: int, model_id: str, diagnostics: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    global _CAPTION_CLIP_MODEL_CACHE
    source = "open_clip"
    cache_key = (model_id, source)
    if _CAPTION_CLIP_MODEL_CACHE.get(cache_key) is False:
        return None, {**diagnostics, "source": "clip_unavailable", "fallback_reason": "OpenCLIP tagger model is unavailable after a previous load failure."}
    try:
        os.environ.setdefault("HF_HOME", str(_caption_clip_cache_dir()))
        os.environ.setdefault("HF_HUB_CACHE", str(_caption_clip_cache_dir()))
        from PIL import Image
        import torch
        import open_clip
        from huggingface_hub import snapshot_download

        if cache_key not in _CAPTION_CLIP_MODEL_CACHE:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            snapshot_download(
                repo_id=model_id,
                cache_dir=str(_caption_clip_cache_dir()),
                local_files_only=not _caption_clip_allow_download(),
            )
            model, _, preprocess = open_clip.create_model_and_transforms(f"hf-hub:{model_id}", device=device)
            tokenizer = open_clip.get_tokenizer(f"hf-hub:{model_id}")
            model.eval()
            _CAPTION_CLIP_MODEL_CACHE[cache_key] = (model, preprocess, tokenizer, device)
        model, preprocess, tokenizer, device = _CAPTION_CLIP_MODEL_CACHE[cache_key]  # type: ignore[misc]
        tags = _clip_candidate_tags()
        if not tags:
            return None, {**diagnostics, "source": "clip_unconfigured", "fallback_reason": "No CLIP candidate tags are configured."}
        texts = [_clip_text_for_tag(tag) for tag in tags]
        with Image.open(path) as image:
            image_tensor = preprocess(image.convert("RGB")).unsqueeze(0).to(device)
        text_tokens = tokenizer(texts).to(device)
        with torch.no_grad():
            image_features = model.encode_image(image_tensor)
            text_features = model.encode_text(text_tokens)
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)
            text_features = text_features / text_features.norm(dim=-1, keepdim=True)
            probabilities = (100.0 * image_features @ text_features.T).softmax(dim=-1)[0].detach().cpu().tolist()
        caption = _caption_from_scored_tags(tags, [float(score) for score in probabilities], max_words)
        if not caption:
            return None, {**diagnostics, "source": "clip_empty", "fallback_reason": "OpenCLIP tagger produced no caption."}
        return caption, {**diagnostics, "source": "clip_tagger", "runtime": source, "device": device, "tag_count": len(tags)}
    except Exception as exc:
        _CAPTION_CLIP_MODEL_CACHE[cache_key] = False
        return None, {
            **diagnostics,
            "source": "clip_error",
            "runtime": source,
            "fallback_reason": "OpenCLIP tagger failed; fallback was used.",
            "error": f"{type(exc).__name__}: {exc}",
        }


def _caption_image_with_clip_result(path: Path, max_words: int, model_id: str | None = None) -> tuple[str | None, dict[str, Any]]:
    selected_model = _caption_clip_model_id(model_id)
    source = _caption_clip_model_source(selected_model)
    diagnostics = {
        "source": "clip_tagger",
        "model_id": selected_model,
        "model_source": source,
        "download_allowed": _caption_clip_allow_download(),
        "tags_path": str(_caption_clip_tags_path()),
        "top_k": _caption_clip_top_k(max_words),
    }
    if source == "open_clip":
        return _caption_image_with_open_clip(path, max_words, selected_model, diagnostics)
    return _caption_image_with_transformers_clip(path, max_words, selected_model, diagnostics)


def _normalize_caption_provider(provider: str = "auto") -> str:
    provider = provider.strip().lower() or "auto"
    aliases = {
        "blip": "local_blip",
        "local": "local_blip",
        "clip": "clip_tagger",
        "clip_tagger": "clip_tagger",
        "clip-tagger": "clip_tagger",
        "vlm": "koboldcpp_vlm",
        "koboldcpp": "koboldcpp_vlm",
        "kobold": "koboldcpp_vlm",
        "florence": "florence2",
        "florence-2": "florence2",
        "florence2": "florence2",
        "filename": "filename_fallback",
        "fallback": "filename_fallback",
    }
    provider = aliases.get(provider, provider)
    if provider not in {"auto", "local_blip", "koboldcpp_vlm", "clip_tagger", "florence2", "filename_fallback"}:
        return "auto"
    return provider


def _caption_provider(default: str = "auto") -> str:
    return _normalize_caption_provider(os.getenv("STUDIO_CAPTION_PROVIDER", default))


def _normalize_local_endpoint(endpoint: str) -> str:
    parsed = urlparse((endpoint or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Endpoint must be an http(s) URL.")
    hostname = (parsed.hostname or "").lower()
    netloc = parsed.netloc
    if Path("/.dockerenv").exists() and hostname in {"127.0.0.1", "localhost"}:
        netloc = parsed.netloc.replace(parsed.hostname or hostname, "host.docker.internal", 1)
    return urlunparse((parsed.scheme, netloc, parsed.path.rstrip("/"), "", "", "")).rstrip("/")


def _chat_endpoint(endpoint: str) -> str:
    base_url = _normalize_local_endpoint(endpoint).rstrip("/")
    return base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"


def _extract_chat_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message") if isinstance(first, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [part.get("text") for part in content if isinstance(part, dict) and isinstance(part.get("text"), str)]
        return "\n".join(part.strip() for part in parts if part.strip())
    text = first.get("text") if isinstance(first, dict) else None
    return str(text).strip() if text else ""


def _clean_vlm_caption(text: str, max_words: int) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:text)?|```$", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"^(caption|tags|sdxl caption)\s*:\s*", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\b(subject|clothing|pose/action|pose|action|setting|lighting|framing|style)\s*:\s*", ", ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[.;]\s+", ", ", cleaned)
    cleaned = cleaned.strip("\"'` ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    parts: list[str] = []
    seen: set[str] = set()
    for raw_part in re.split(r",|\n", cleaned):
        part = raw_part.strip(" -_\t\r\n")
        part = re.sub(r"\s+", " ", part)
        if not part:
            continue
        words = []
        previous = ""
        for word in part.split():
            normalized_word = re.sub(r"[^a-z0-9]+", "", word.lower())
            if normalized_word and normalized_word == previous:
                continue
            words.append(word)
            previous = normalized_word
        part = " ".join(words).strip(" ,")
        normalized = re.sub(r"[^a-z0-9]+", " ", part.lower()).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        parts.append(part)
        if len(" ".join(parts).split()) >= max_words:
            break
    return _limit_caption_words(", ".join(parts) if parts else cleaned, max_words)


def _caption_vlm_settings() -> dict[str, Any]:
    settings = _settings_dict().get("llm", {})
    endpoint = os.getenv("STUDIO_CAPTION_VLM_ENDPOINT", "").strip() or str(settings.get("endpoint") or "").strip()
    model = os.getenv("STUDIO_CAPTION_VLM_MODEL", "").strip() or str(settings.get("model") or "koboldcpp").strip()
    api_key = os.getenv("STUDIO_CAPTION_VLM_API_KEY", "").strip() or str(settings.get("api_key") or "").strip()
    timeout_s = int(os.getenv("STUDIO_CAPTION_VLM_TIMEOUT_S", str(settings.get("timeout_s") or 120)) or "120")
    prompt = os.getenv("STUDIO_CAPTION_VLM_PROMPT", "").strip()
    return {
        "endpoint": endpoint,
        "model": model or "koboldcpp",
        "api_key": api_key,
        "timeout_s": timeout_s,
        "prompt": prompt,
    }


def _caption_image_with_vlm_result(path: Path, max_words: int) -> tuple[str | None, dict[str, Any]]:
    settings = _caption_vlm_settings()
    endpoint = str(settings.get("endpoint") or "").strip()
    model = str(settings.get("model") or "koboldcpp").strip()
    diagnostics: dict[str, Any] = {
        "source": "koboldcpp_vlm",
        "endpoint": endpoint,
        "model_id": model,
    }
    if not endpoint:
        return None, {
            **diagnostics,
            "source": "vlm_unconfigured",
            "fallback_reason": "No KoboldCPP/vLLM caption endpoint is configured.",
        }
    prompt = str(settings.get("prompt") or "").strip() or (
        "Create a concise SDXL LoRA training caption for this image. "
        f"Return 8 to 16 comma-separated visual tags, no labels and no explanation. Keep it under {max_words} words. "
        "Avoid repeated words or repeated tag phrases. Include subject, clothing, pose/action, setting, lighting, framing, and style when visible."
    )
    media_type = mimetypes.guess_type(path.name)[0] or "image/png"
    try:
        image_base64 = base64.b64encode(path.read_bytes()).decode("ascii")
        headers: dict[str, str] = {}
        if settings.get("api_key"):
            headers["Authorization"] = f"Bearer {settings['api_key']}"
        body = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{image_base64}"}},
                    ],
                }
            ],
            "temperature": 0.2,
            "max_tokens": max(64, min(512, max_words * 6)),
        }
        response = requests.post(_chat_endpoint(endpoint), json=body, headers=headers, timeout=int(settings.get("timeout_s") or 120))
        response.raise_for_status()
        raw = response.json()
        caption = _clean_vlm_caption(_extract_chat_text(raw if isinstance(raw, dict) else {}), max_words)
        if not caption:
            return None, {**diagnostics, "fallback_reason": "KoboldCPP/vLLM returned no readable caption."}
        return caption, diagnostics
    except Exception as exc:
        return None, {
            **diagnostics,
            "source": "vlm_error",
            "fallback_reason": "KoboldCPP/vLLM captioning failed; fallback was used.",
            "error": f"{type(exc).__name__}: {exc}",
        }


def _caption_florence_settings() -> dict[str, Any]:
    return {
        "url": os.getenv("STUDIO_FLORENCE_URL", "").strip().rstrip("/"),
        "model_id": os.getenv("STUDIO_FLORENCE_MODEL_ID", "microsoft/Florence-2-base").strip() or "microsoft/Florence-2-base",
        "device": os.getenv("STUDIO_FLORENCE_DEVICE", "auto").strip() or "auto",
        "allow_download": os.getenv("STUDIO_FLORENCE_ALLOW_DOWNLOAD", "").strip().lower() in {"1", "true", "yes", "on"},
        "timeout_s": int(os.getenv("STUDIO_FLORENCE_TIMEOUT_S", "120") or "120"),
    }


def _caption_florence_configured() -> bool:
    return bool(_caption_florence_settings()["url"])


def _caption_image_with_florence_result(path: Path, max_words: int) -> tuple[str | None, dict[str, Any]]:
    settings = _caption_florence_settings()
    url = str(settings["url"])
    diagnostics = {
        "source": "florence2",
        "endpoint": url,
        "model_id": settings["model_id"],
        "device": settings["device"],
        "download_allowed": settings["allow_download"],
    }
    if not url:
        return None, {
            **diagnostics,
            "source": "florence_unconfigured",
            "fallback_reason": "Florence-2 sidecar is not configured. Set STUDIO_FLORENCE_URL or choose Auto/filename fallback.",
        }
    try:
        health = requests.get(f"{url}/health", timeout=3)
        if health.status_code >= 400:
            return None, {
                **diagnostics,
                "source": "florence_unavailable",
                "fallback_reason": f"Florence-2 sidecar health check failed with HTTP {health.status_code}.",
            }
        health_payload = health.json()
        if isinstance(health_payload, dict) and health_payload.get("ready") is False:
            return None, {
                **diagnostics,
                "source": "florence_not_ready",
                "fallback_reason": str(health_payload.get("detail") or "Florence-2 sidecar is not ready."),
            }
        media_type = mimetypes.guess_type(path.name)[0] or "image/png"
        image_base64 = base64.b64encode(path.read_bytes()).decode("ascii")
        response = requests.post(
            f"{url}/caption",
            json={
                "image_base64": image_base64,
                "media_type": media_type,
                "max_words": max_words,
                "model_id": settings["model_id"],
                "task": "caption",
            },
            timeout=int(settings["timeout_s"]),
        )
        if response.status_code == 503:
            detail = response.json().get("detail", "Florence-2 sidecar is not ready.")
            return None, {**diagnostics, "source": "florence_not_ready", "fallback_reason": str(detail)}
        response.raise_for_status()
        raw = response.json()
        caption = _clean_vlm_caption(str(raw.get("caption") or raw.get("text") or ""), max_words)
        if not caption:
            return None, {**diagnostics, "source": "florence_empty", "fallback_reason": "Florence-2 returned no readable caption."}
        return caption, diagnostics
    except Exception as exc:
        return None, {
            **diagnostics,
            "source": "florence_error",
            "fallback_reason": "Florence-2 sidecar captioning failed; fallback was used.",
            "error": f"{type(exc).__name__}: {exc}",
        }


def _caption_image_with_local_model_result(path: Path, max_words: int, model_id: str | None = None) -> tuple[str | None, dict[str, Any]]:
    requested_model = _caption_model_id(model_id)
    model_ref = _caption_local_model_ref(requested_model)
    diagnostics: dict[str, Any] = {
        "source": "local_blip",
        "model_id": requested_model,
        "model_ref": model_ref,
        "download_allowed": _caption_download_allowed(),
        "local_model_enabled": not _captioning_disabled(),
    }
    if _captioning_disabled():
        return None, {
            **diagnostics,
            "source": "disabled",
            "fallback_reason": "Local captioning is disabled by STUDIO_DISABLE_LOCAL_CAPTIONING.",
        }
    if _CAPTIONING_MODEL_CACHE.get(model_ref) is False:
        return None, {
            **diagnostics,
            "source": "unavailable",
            "fallback_reason": "Local captioning model is unavailable after a previous load failure.",
        }
    try:
        from PIL import Image
        import torch
        from transformers import AutoProcessor, BlipConfig, BlipForConditionalGeneration

        if model_ref not in _CAPTIONING_MODEL_CACHE:
            allow_download = _caption_download_allowed()
            processor = AutoProcessor.from_pretrained(model_ref, local_files_only=not allow_download)
            load_kwargs: dict[str, Any] = {"local_files_only": not allow_download}
            if (Path(model_ref) / "model.safetensors").exists():
                load_kwargs["use_safetensors"] = True
            try:
                model = BlipForConditionalGeneration.from_pretrained(model_ref, **load_kwargs)
            except ValueError as exc:
                bin_path = Path(model_ref) / "pytorch_model.bin"
                if "torch.load" not in str(exc) or not bin_path.exists():
                    raise
                config = BlipConfig.from_pretrained(model_ref, local_files_only=not allow_download)
                model = BlipForConditionalGeneration(config)
                state_dict = torch.load(bin_path, map_location="cpu")
                model.load_state_dict(state_dict, strict=False)
            device = "cuda" if torch.cuda.is_available() else "cpu"
            model.to(device)
            model.eval()
            _CAPTIONING_MODEL_CACHE[model_ref] = (processor, model, device)
        processor, model, device = _CAPTIONING_MODEL_CACHE[model_ref]  # type: ignore[misc]
        with Image.open(path) as image:
            inputs = processor(images=image.convert("RGB"), return_tensors="pt").to(device)
        with torch.no_grad():
            tokens = model.generate(**inputs, max_new_tokens=max(8, max_words + 8))
        caption = processor.decode(tokens[0], skip_special_tokens=True).strip()
        if not caption:
            return None, {**diagnostics, "device": device, "fallback_reason": "Local caption model returned an empty caption."}
        return _limit_caption_words(caption, max_words), {**diagnostics, "device": device}
    except Exception as exc:
        _CAPTIONING_MODEL_CACHE[model_ref] = False
        return None, {
            **diagnostics,
            "source": "error",
            "fallback_reason": "Local caption model failed; filename fallback was used.",
            "error": f"{type(exc).__name__}: {exc}",
        }


def _caption_image_with_local_model(path: Path, max_words: int) -> str | None:
    caption, _ = _caption_image_with_local_model_result(path, max_words)
    return caption


def _caption_image_with_source(
    path: Path,
    max_words: int,
    provider: str = "auto",
    fallback_context: str = "",
    local_model_id: str | None = None,
    clip_model_id: str | None = None,
) -> tuple[str, dict[str, Any]]:
    requested_provider = _normalize_caption_provider(provider or _caption_provider())
    attempts: list[dict[str, Any]] = []

    def attempt_local() -> tuple[str | None, dict[str, Any]]:
        caption, info = _caption_image_with_local_model_result(path, max_words, model_id=local_model_id)
        attempts.append(info)
        return caption, info

    def attempt_vlm() -> tuple[str | None, dict[str, Any]]:
        caption, info = _caption_image_with_vlm_result(path, max_words)
        attempts.append(info)
        return caption, info

    def attempt_clip() -> tuple[str | None, dict[str, Any]]:
        caption, info = _caption_image_with_clip_result(path, max_words, model_id=clip_model_id)
        attempts.append(info)
        return caption, info

    def attempt_florence() -> tuple[str | None, dict[str, Any]]:
        caption, info = _caption_image_with_florence_result(path, max_words)
        attempts.append(info)
        return caption, info

    if requested_provider == "local_blip":
        caption, info = attempt_local()
        if caption:
            return caption, {**info, "requested_provider": requested_provider, "attempts": attempts}
    elif requested_provider == "koboldcpp_vlm":
        caption, info = attempt_vlm()
        if caption:
            return caption, {**info, "requested_provider": requested_provider, "attempts": attempts}
    elif requested_provider == "clip_tagger":
        caption, info = attempt_clip()
        if caption:
            return caption, {**info, "requested_provider": requested_provider, "attempts": attempts}
    elif requested_provider == "florence2":
        caption, info = attempt_florence()
        if caption:
            return caption, {**info, "requested_provider": requested_provider, "attempts": attempts}
        raise RuntimeError(info.get("fallback_reason") or "Florence-2 sidecar is unavailable.")
    elif requested_provider == "auto":
        auto_attempts = [attempt_local, attempt_vlm, attempt_clip]
        if _caption_florence_configured():
            auto_attempts.insert(0, attempt_florence)
        for attempt in auto_attempts:
            caption, info = attempt()
            if caption:
                return caption, {**info, "requested_provider": requested_provider, "attempts": attempts}

    fallback = _fallback_caption_from_filename(path, max_words, context=fallback_context)
    last_info = attempts[-1] if attempts else {"source": "filename_fallback"}
    return fallback, {
        **last_info,
        "source": "filename_fallback",
        "requested_provider": requested_provider,
        "attempts": attempts,
        "fallback_reason": last_info.get("fallback_reason") or "No image caption provider produced a caption.",
    }


def _caption_image(path: Path, max_words: int) -> str:
    caption, _ = _caption_image_with_source(path, max_words)
    return caption


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _image_model_root() -> Path:
    return DATA / "models" / "images"


def _case_matching_dir(parent: Path, name: str) -> Path:
    if not parent.exists():
        return parent / name
    for child in parent.iterdir():
        if child.is_dir() and child.name.lower() == name.lower():
            return child
    return parent / name


def _training_base_model_dir() -> Path:
    return _case_matching_dir(_image_model_root(), "base")


def _training_vae_model_dir() -> Path:
    return _case_matching_dir(_image_model_root(), "vae")


def _training_family_model_dir(family: str) -> Path:
    profile = MODEL_FAMILY_PROFILES.get(family, MODEL_FAMILY_PROFILES["sdxl"])
    return _case_matching_dir(_image_model_root(), str(profile["model_root"]))


def _training_model_read(path: Path, kind: Literal["base", "vae"], family: str = "sdxl") -> TrainingModelFileRead:
    stat = path.stat()
    return TrainingModelFileRead(
        name=path.name,
        path=str(path),
        size=stat.st_size,
        kind=kind,
        family=family,
        modified_at=datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
    )


def _training_model_files(root: Path, kind: Literal["base", "vae"], family: str = "sdxl") -> list[TrainingModelFileRead]:
    if not root.exists():
        return []
    return [
        _training_model_read(path, kind, family)
        for path in sorted(root.glob("*.safetensors"), key=lambda item: item.name.lower())
        if path.is_file()
    ]


def _all_training_base_models() -> list[TrainingModelFileRead]:
    models: list[TrainingModelFileRead] = []
    seen: set[str] = set()
    for family in ("sdxl", "sdxl_pony", "flux", "sd15"):
        for model in _training_model_files(_training_family_model_dir(family), "base", family):
            if model.path in seen:
                continue
            seen.add(model.path)
            models.append(model)
    for model in _training_model_files(_image_model_root(), "base", "local"):
        if model.path not in seen:
            seen.add(model.path)
            models.append(model)
    return models


def _find_model_by_name(file_name: str, roots: list[Path]) -> Path | None:
    cleaned = Path(file_name.replace("\\", "/")).name.lower()
    if not cleaned:
        return None
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.safetensors"):
            if path.name.lower() == cleaned:
                return path
    return None


def _resolve_training_file_path(value: str, role: Literal["base", "vae"], *, required: bool) -> str:
    raw = value.strip()
    if not raw:
        if required:
            raise RuntimeError("Select a Base SDXL checkpoint before queueing training.")
        return ""
    normalized = raw.replace("\\", "/")
    candidates: list[Path] = []
    marker_index = normalized.lower().rfind("/data/")
    if marker_index >= 0:
        candidates.append(DATA / normalized[marker_index + len("/data/") :])
    elif normalized.lower().startswith("data/"):
        candidates.append(DATA / normalized[len("data/") :])
    elif normalized.lower().startswith("/app/data/"):
        candidates.append(DATA / normalized[len("/app/data/") :])
    elif normalized.lower().startswith("/data/"):
        candidates.append(DATA / normalized[len("/data/") :])
    elif normalized.lower().startswith("models/"):
        candidates.append(DATA / normalized)
    else:
        path = Path(raw)
        candidates.append(path)
        if not path.is_absolute():
            candidates.append(DATA / normalized)
            candidates.append(_image_model_root() / normalized)

    roots = [
        _training_base_model_dir(),
        _training_vae_model_dir(),
        *[_training_family_model_dir(family) for family in MODEL_FAMILY_PROFILES],
        _image_model_root(),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    by_name = _find_model_by_name(raw, roots)
    if by_name is not None:
        return str(by_name)
    if required or role == "vae":
        raise RuntimeError(f"{role.upper()} model file was not found: {raw}. Select a .safetensors file from the Training model list.")
    return raw


@router.get("/model-files", response_model=TrainingModelFilesResponse)
def list_training_model_files() -> TrainingModelFilesResponse:
    script_path = _trainer_root() / "sdxl_train_network.py"
    return TrainingModelFilesResponse(
        families=list(MODEL_FAMILY_PROFILES.values()),
        base_models=_all_training_base_models(),
        vae_models=_training_model_files(_training_vae_model_dir(), "vae"),
        dry_run_forced=_truthy(os.getenv("STUDIO_TRAINING_DRY_RUN")),
        sd_scripts_root=str(_trainer_root()),
        sd_scripts_ready=script_path.exists(),
        accelerate_bin=os.getenv("STUDIO_ACCELERATE_BIN", "accelerate"),
    )


@router.get("/model-families")
def list_training_model_families() -> dict[str, Any]:
    return {"families": list(MODEL_FAMILY_PROFILES.values())}


def _caption_model_kind(model_dir: Path) -> str | None:
    config_path = model_dir / "config.json"
    if not config_path.exists():
        return None
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        config = {}
    model_type = str(config.get("model_type") or "").lower()
    architectures = " ".join(str(item) for item in config.get("architectures") or []).lower()
    name = model_dir.name.lower()
    if "blip" in model_type or "blip" in architectures or "blip" in name:
        return "local_blip"
    if "clip" in model_type or "clip" in architectures or "clip" in name:
        return "clip_tagger"
    return None


def _local_caption_models() -> list[dict[str, Any]]:
    models: list[dict[str, Any]] = []
    if CAPTION_MODEL_ROOT.exists():
        for model_dir in sorted((item for item in CAPTION_MODEL_ROOT.iterdir() if item.is_dir()), key=lambda item: item.name.lower()):
            kind = _caption_model_kind(model_dir)
            if not kind:
                continue
            models.append(
                {
                    "id": model_dir.name,
                    "label": model_dir.name,
                    "provider": kind,
                    "path": str(model_dir),
                    "local": True,
                    "source": "data/models/captioning",
                }
            )
    return models


@router.get("/caption-models")
def list_caption_models() -> list[dict[str, Any]]:
    local_models = _local_caption_models()
    existing_ids = {str(item["id"]) for item in local_models}
    models = list(local_models)
    for model_id, label in {
        "Salesforce/blip-image-captioning-base": "Salesforce BLIP base",
        "Salesforce/blip-image-captioning-large": "Salesforce BLIP large",
    }.items():
        if model_id not in existing_ids:
            models.append(
                {
                    "id": model_id,
                    "label": label,
                    "provider": "local_blip",
                    "path": model_id,
                    "local": False,
                    "source": "huggingface",
                }
            )
    for model_id, label in CAPTION_CLIP_MODELS.items():
        if model_id not in existing_ids:
            models.append(
                {
                    "id": model_id,
                    "label": label,
                    "provider": "clip_tagger",
                    "path": str(CAPTION_MODEL_ROOT / _safe_model_dir_name(model_id)),
                    "local": (CAPTION_MODEL_ROOT / _safe_model_dir_name(model_id)).exists(),
                    "source": _caption_clip_model_source(model_id),
                }
            )
    florence = _caption_florence_settings()
    models.append(
        {
            "id": florence["model_id"],
            "label": "Florence-2 sidecar",
            "provider": "florence2",
            "path": florence["url"] or "STUDIO_FLORENCE_URL not configured",
            "local": bool(florence["url"]),
            "source": "sidecar",
        }
    )
    return models


@router.get("/datasets", response_model=list[DatasetRead])
def list_datasets() -> list[DatasetRead]:
    datasets = []
    for metadata_path in sorted(DATASETS_ROOT.glob("*/metadata.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            datasets.append(_dataset_read(json.loads(metadata_path.read_text(encoding="utf-8"))))
        except Exception:
            continue
    return datasets


@router.post("/datasets", response_model=DatasetRead, status_code=201)
def create_dataset(payload: DatasetCreateRequest) -> DatasetRead:
    dataset_id = f"{slugify(payload.name, 'dataset')}-{uuid.uuid4().hex[:8]}"
    dataset_dir = DATASETS_ROOT / dataset_id
    image_dir = dataset_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    now = utc_now_iso()
    metadata = {
        "id": dataset_id,
        "name": payload.name.strip(),
        "path": str(dataset_dir),
        "settings": payload.model_dump(),
        "created_at": now,
        "updated_at": now,
    }
    _write_dataset(metadata)
    build_dataset_config(dataset_id)
    return _dataset_read(_load_dataset(dataset_id))


@router.post("/datasets/from-collection", response_model=CollectionDatasetImportResponse, status_code=201)
def import_collection_dataset(payload: CollectionDatasetImportRequest) -> CollectionDatasetImportResponse:
    timeout_s = _media_indexer_timeout_s()
    collection_items: list[dict[str, Any]] = []
    collection_name = payload.name or f"Collection {payload.collection_id}"
    total = None
    page = 1

    try:
        while len(collection_items) < payload.max_items:
            page_size = min(100, payload.max_items - len(collection_items))
            response = requests.get(
                _media_indexer_url(f"/collections/{payload.collection_id}"),
                params={"page": page, "page_size": page_size},
                timeout=timeout_s,
            )
            response.raise_for_status()
            detail = response.json()
            if page == 1:
                collection_name = payload.name or str(detail.get("name") or collection_name)
                total = int(detail.get("total") or 0)
            items = detail.get("items") if isinstance(detail, dict) else None
            if not isinstance(items, list) or not items:
                break
            collection_items.extend(item for item in items if isinstance(item, dict))
            if total is not None and len(collection_items) >= total:
                break
            page += 1
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Could not read media collection: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"Media collection returned invalid JSON: {exc}") from exc

    dataset = create_dataset(
        DatasetCreateRequest(
            name=payload.name or f"{collection_name} dataset",
            trigger_token=payload.trigger_token,
            class_tokens=payload.class_tokens,
            resolution=payload.resolution,
            batch_size=payload.batch_size,
            num_repeats=payload.num_repeats,
            caption_extension=payload.caption_extension,
            enable_bucket=payload.enable_bucket,
            bucket_no_upscale=payload.bucket_no_upscale,
        )
    )
    metadata = _load_dataset(dataset.id)
    settings = metadata.get("settings") or {}
    image_dir = _dataset_image_dir(metadata)
    imported = 0
    skipped = 0

    for item in collection_items[: payload.max_items]:
        if str(item.get("media_type") or "").lower() not in {"", "image"}:
            skipped += 1
            continue
        image_url = str(item.get("content_url") or item.get("preview_url") or "").strip()
        if not image_url:
            skipped += 1
            continue
        try:
            filename = safe_upload_name(_collection_image_name(item), allowed_extensions=IMAGE_EXTENSIONS)
            target_name = filename
            if (image_dir / target_name).exists():
                target_name = f"{uuid.uuid4().hex[:8]}_{filename}"
            image_response = requests.get(_media_indexer_url(image_url), timeout=timeout_s)
            image_response.raise_for_status()
            content = image_response.content
            if not content:
                skipped += 1
                continue
            if len(content) > max_image_upload_bytes():
                skipped += 1
                continue
            (image_dir / target_name).write_bytes(content)
            caption = _collection_caption(item, settings)
            if caption:
                _caption_path_for_image(image_dir / target_name, settings).write_text(caption.strip(), encoding="utf-8")
            imported += 1
        except (HTTPException, requests.RequestException, OSError):
            skipped += 1

    if imported == 0:
        raise HTTPException(status_code=400, detail="No images could be imported from this collection.")

    metadata["source_collection"] = {
        "id": payload.collection_id,
        "name": collection_name,
        "imported": imported,
        "skipped": skipped,
        "imported_at": utc_now_iso(),
    }
    _write_dataset(metadata)
    build_dataset_config(dataset.id)
    return CollectionDatasetImportResponse(
        dataset=_dataset_read(_load_dataset(dataset.id)),
        imported=imported,
        skipped=skipped,
        collection_id=payload.collection_id,
        collection_name=collection_name,
    )


@router.get("/datasets/{dataset_id}", response_model=DatasetRead)
def get_dataset(dataset_id: str) -> DatasetRead:
    return _dataset_read(_load_dataset(dataset_id))


@router.get("/datasets/{dataset_id}/items", response_model=list[DatasetItemRead])
def list_dataset_items(dataset_id: str) -> list[DatasetItemRead]:
    return _dataset_items(_load_dataset(dataset_id))


@router.get("/datasets/{dataset_id}/images/{filename}")
def get_dataset_image(dataset_id: str, filename: str) -> FileResponse:
    metadata = _load_dataset(dataset_id)
    safe_name = safe_upload_name(filename, allowed_extensions=IMAGE_EXTENSIONS)
    image_path = _dataset_image_dir(metadata) / safe_name
    if not image_path.exists() or not image_path.is_file():
        raise HTTPException(status_code=404, detail="Dataset image not found.")
    media_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    return FileResponse(image_path, media_type=media_type)


@router.get("/datasets/{dataset_id}/export.zip")
def export_dataset_zip(dataset_id: str) -> StreamingResponse:
    payload, filename = _dataset_zip_bytes(dataset_id)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(io.BytesIO(payload), media_type="application/zip", headers=headers)


@router.post("/datasets/{dataset_id}/upload")
def upload_dataset_images(dataset_id: str, files: list[UploadFile] = File(...)) -> dict[str, Any]:
    metadata = _load_dataset(dataset_id)
    settings = metadata.get("settings") or {}
    image_dir = _dataset_image_dir(metadata)
    uploaded = []
    for upload in files:
        safe_name = safe_upload_name(upload.filename, allowed_extensions=IMAGE_EXTENSIONS)
        target_name = safe_name
        if (image_dir / target_name).exists():
            target_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
        save_upload_with_limits(
            upload,
            image_dir / target_name,
            allowed_extensions=IMAGE_EXTENSIONS,
            max_bytes=max_image_upload_bytes(),
            validate_image_magic=True,
        )
        caption = " ".join(item for item in [settings.get("trigger_token", ""), settings.get("class_tokens", "")] if item).strip()
        if caption:
            _caption_path_for_image(image_dir / target_name, settings).write_text(caption, encoding="utf-8")
        uploaded.append(target_name)
    build_dataset_config(dataset_id)
    return {"uploaded": len(uploaded), "filenames": uploaded, "dataset": _dataset_read(_load_dataset(dataset_id))}


@router.post("/datasets/{dataset_id}/upload-zip", response_model=DatasetZipImportResponse)
def upload_dataset_zip(dataset_id: str, file: UploadFile = File(...)) -> DatasetZipImportResponse:
    metadata = _load_dataset(dataset_id)
    settings = metadata.get("settings") or {}
    image_dir = _dataset_image_dir(metadata)
    safe_upload_name(file.filename, allowed_extensions=ZIP_EXTENSIONS)
    payload = _read_upload_bytes_with_limit(file, _dataset_zip_max_bytes())
    imported = 0
    captions_written = 0
    skipped = 0

    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="Uploaded file is not a readable zip archive.") from exc

    with archive:
        text_entries: dict[str, str] = {}
        text_entries_by_stem: dict[str, str] = {}
        image_entries: list[tuple[str, zipfile.ZipInfo]] = []
        root_labels: set[str] = set()
        for entry in archive.infolist():
            if entry.is_dir():
                continue
            raw_name = entry.filename.replace("\\", "/")
            posix_name = PurePosixPath(raw_name)
            if len(posix_name.parts) > 1:
                root_labels.add(posix_name.parts[0])
            base_name = posix_name.name
            if not base_name or base_name.startswith("."):
                skipped += 1
                continue
            suffix = Path(base_name).suffix.lower()
            if suffix == ".txt":
                caption = archive.read(entry).decode("utf-8", errors="replace").strip()
                text_entries[str(posix_name.with_suffix("")).lower()] = caption
                text_entries_by_stem[Path(base_name).stem.lower()] = caption
            elif suffix in IMAGE_EXTENSIONS:
                image_entries.append((raw_name, entry))
            else:
                skipped += 1

        if not image_entries:
            raise HTTPException(status_code=400, detail="The zip archive did not contain supported image files.")

        for raw_name, entry in image_entries:
            posix_name = PurePosixPath(raw_name)
            base_name = posix_name.name
            safe_name = safe_upload_name(base_name, allowed_extensions=IMAGE_EXTENSIONS)
            image_payload = archive.read(entry)
            if len(image_payload) > max_image_upload_bytes():
                skipped += 1
                continue
            _validate_image_bytes(safe_name, image_payload)
            target_name = safe_name
            if (image_dir / target_name).exists():
                target_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
            (image_dir / target_name).write_bytes(image_payload)
            imported += 1
            caption = text_entries.get(str(posix_name.with_suffix("")).lower())
            if caption is None:
                caption = text_entries_by_stem.get(Path(base_name).stem.lower())
            if caption is not None:
                _caption_path_for_image(image_dir / target_name, settings).write_text(caption, encoding="utf-8")
                captions_written += 1

    archive_context = _caption_context_from_zip(str(file.filename or ""), root_labels)
    metadata.setdefault("source_archives", [])
    if isinstance(metadata["source_archives"], list):
        metadata["source_archives"].append(
            {
                "filename": str(file.filename or ""),
                "caption_context": archive_context,
                "imported": imported,
                "captions": captions_written,
                "imported_at": utc_now_iso(),
            }
        )
    if archive_context and not _useful_caption_context(str(metadata.get("caption_context") or "")):
        metadata["caption_context"] = archive_context
    _write_dataset(metadata)
    build_dataset_config(dataset_id)
    refreshed = _load_dataset(dataset_id)
    return DatasetZipImportResponse(
        dataset=_dataset_read(refreshed),
        items=_dataset_items(refreshed),
        imported=imported,
        captions=captions_written,
        skipped=skipped,
    )


@router.post("/datasets/{dataset_id}/captions", response_model=DatasetRead)
def update_caption(dataset_id: str, payload: CaptionUpdateRequest) -> DatasetRead:
    metadata = _load_dataset(dataset_id)
    settings = metadata.get("settings") or {}
    filename = safe_upload_name(payload.filename, allowed_extensions=IMAGE_EXTENSIONS)
    image_path = _dataset_image_dir(metadata) / filename
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Dataset image not found.")
    _caption_path_for_image(image_path, settings).write_text(payload.caption.strip(), encoding="utf-8")
    build_dataset_config(dataset_id)
    return _dataset_read(_load_dataset(dataset_id))


@router.post("/datasets/{dataset_id}/captions/apply-trigger", response_model=DatasetTriggerApplyResponse)
def apply_caption_trigger(dataset_id: str, payload: TriggerCaptionApplyRequest) -> DatasetTriggerApplyResponse:
    metadata = _load_dataset(dataset_id)
    settings = metadata.get("settings") or {}
    updated = 0
    unchanged = 0
    for item in _dataset_items(metadata):
        image_path = _dataset_image_dir(metadata) / item.filename
        caption_path = _caption_path_for_image(image_path, settings)
        if not caption_path.exists() and not payload.create_missing:
            unchanged += 1
            continue
        caption, changed = _prepend_trigger(_read_caption(caption_path), payload.trigger_word, payload.separator)
        if changed:
            caption_path.write_text(caption, encoding="utf-8")
            updated += 1
        else:
            unchanged += 1
    build_dataset_config(dataset_id)
    refreshed = _load_dataset(dataset_id)
    return DatasetTriggerApplyResponse(
        dataset=_dataset_read(refreshed),
        items=_dataset_items(refreshed),
        updated=updated,
        unchanged=unchanged,
    )


@router.post("/datasets/{dataset_id}/captions/scan", response_model=CaptionScanResponse, status_code=202)
async def create_caption_scan(dataset_id: str, payload: CaptionScanRequest, request: Request) -> CaptionScanResponse:
    _load_dataset(dataset_id)
    manager = getattr(request.app.state, "v2_jobs", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="V2 job manager is not available.")
    job_payload = payload.model_dump()
    job_payload["dataset_id"] = dataset_id
    job = await manager.create_job(CAPTION_SCAN_JOB_TYPE, job_payload)
    return CaptionScanResponse(job=JobRead.model_validate(job), events_url=f"/api/jobs/{job['id']}/events")


@router.post("/datasets/{dataset_id}/config", response_model=DatasetConfigResponse)
def create_dataset_config(dataset_id: str) -> DatasetConfigResponse:
    return build_dataset_config(dataset_id)


def _trainer_root() -> Path:
    return Path(os.getenv("STUDIO_SD_SCRIPTS_ROOT", "/app/trainers/sd-scripts")).resolve(strict=False)


def _auto_mixed_precision() -> str:
    try:
        import torch

        if torch.cuda.is_available() and torch.cuda.is_bf16_supported():
            return "bf16"
    except Exception:
        pass
    return "fp16"


def _resolve_base_model(payload: TrainingRunRequest) -> str:
    return _resolve_training_file_path(payload.base_model, "base", required=True)


def _extra_args(args: list[str], extra: dict[str, str | int | float | bool]) -> None:
    for key, value in sorted(extra.items()):
        flag = f"--{slugify(key).replace('-', '_')}"
        if isinstance(value, bool):
            if value:
                args.append(flag)
        else:
            args.extend([flag, str(value)])


def _extra_arg_name(key: str) -> str:
    return slugify(key).replace("-", "_")


def _extra_arg_flag_enabled(extra: dict[str, str | int | float | bool], name: str) -> bool:
    for key, value in extra.items():
        if _extra_arg_name(key) != name:
            continue
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)
    return False


def _filtered_extra_args(
    extra: dict[str, str | int | float | bool],
    managed_flags: set[str],
) -> dict[str, str | int | float | bool]:
    if not managed_flags:
        return extra
    return {key: value for key, value in extra.items() if _extra_arg_name(key) not in managed_flags}


def build_training_command(payload: TrainingRunRequest) -> TrainingCommandPreview:
    metadata = _load_dataset(payload.dataset_id)
    config = build_dataset_config(payload.dataset_id, overrides=payload.model_dump())
    run_output_dir = TRAINING_OUTPUT_ROOT / slugify(payload.output_name, "trained-model")
    run_output_dir.mkdir(parents=True, exist_ok=True)
    mixed_precision = _auto_mixed_precision() if payload.mixed_precision == "auto" else payload.mixed_precision
    sd_root = _trainer_root()
    accelerate_bin = os.getenv("STUDIO_ACCELERATE_BIN", "accelerate")
    scheduler = slugify(payload.lr_scheduler or "cosine", "cosine").replace("-", "_")
    optimizer_type = payload.optimizer_type.strip() or "Adafactor"
    managed_extra_flags: set[str] = set()
    effective_family = payload.model_family
    if payload.preset == "sd15_lora":
        effective_family = "sd15"
    elif payload.preset == "sdxl_pony_lora":
        effective_family = "sdxl_pony"
    elif payload.preset == "flux_lora":
        effective_family = "flux"

    if payload.preset in {"sd15_lora", "sdxl_lora", "sdxl_pony_lora"}:
        train_unet_only = payload.text_encoder_lr <= 0 or _extra_arg_flag_enabled(payload.extra_args, "network_train_unet_only")
        if _extra_arg_flag_enabled(payload.extra_args, "cache_text_encoder_outputs") and not train_unet_only:
            raise RuntimeError(
                "SDXL LoRA cannot cache text encoder outputs while training the text encoder. "
                "Set Text Encoder LR to 0 or enable network_train_unet_only."
            )
        script = sd_root / ("train_network.py" if effective_family == "sd15" else "sdxl_train_network.py")
        command = [
            accelerate_bin,
            "launch",
            "--num_cpu_threads_per_process",
            "1",
            str(script),
            "--pretrained_model_name_or_path",
            _resolve_base_model(payload),
            "--dataset_config",
            config.config_file,
            "--output_dir",
            str(run_output_dir),
            "--output_name",
            slugify(payload.output_name, f"mklan-{effective_family}-lora"),
            "--save_model_as",
            "safetensors",
            "--network_module",
            LORA_NETWORK_MODULES[payload.lora_type],
            "--network_dim",
            str(payload.network_dim),
            "--network_alpha",
            str(payload.network_alpha),
            "--learning_rate",
            str(payload.learning_rate),
            "--unet_lr",
            str(payload.unet_lr),
            "--lr_scheduler",
            scheduler,
            "--lr_scheduler_num_cycles",
            str(payload.lr_scheduler_num_cycles),
            "--optimizer_type",
            optimizer_type,
            "--max_train_steps",
            str(payload.max_train_steps),
            "--max_train_epochs",
            str(payload.epochs),
            "--mixed_precision",
            mixed_precision,
            "--gradient_checkpointing",
            "--cache_latents",
            "--min_snr_gamma",
            str(payload.min_snr_gamma),
            "--noise_offset",
            str(payload.noise_offset),
            "--save_every_n_epochs",
            str(payload.save_every_n_epochs),
        ]
        if effective_family != "flux":
            command.extend(["--clip_skip", str(payload.clip_skip)])
        if train_unet_only:
            command.extend(["--network_train_unet_only", "--cache_text_encoder_outputs"])
            managed_extra_flags.update({"network_train_unet_only", "cache_text_encoder_outputs"})
        else:
            command.extend(["--text_encoder_lr", str(payload.text_encoder_lr)])
        network_args = LORA_NETWORK_ARGS.get(payload.lora_type, [])
        if network_args:
            command.extend(["--network_args", *network_args])
        if payload.flip_aug:
            command.append("--flip_aug")
        if payload.vae.strip():
            command.extend(["--vae", _resolve_training_file_path(payload.vae, "vae", required=False)])
        if mixed_precision == "fp16":
            command.append("--no_half_vae")
    elif payload.preset == "sdxl_finetune":
        script = sd_root / "sdxl_train.py"
        command = [
            accelerate_bin,
            "launch",
            "--num_cpu_threads_per_process",
            "1",
            str(script),
            "--pretrained_model_name_or_path",
            _resolve_base_model(payload),
            "--dataset_config",
            config.config_file,
            "--output_dir",
            str(run_output_dir),
            "--output_name",
            slugify(payload.output_name, "mklan-sdxl-finetune"),
            "--save_model_as",
            "safetensors",
            "--learning_rate",
            str(payload.learning_rate),
            "--lr_scheduler",
            scheduler,
            "--lr_scheduler_num_cycles",
            str(payload.lr_scheduler_num_cycles),
            "--optimizer_type",
            optimizer_type,
            "--max_train_steps",
            str(payload.max_train_steps),
            "--max_train_epochs",
            str(payload.epochs),
            "--mixed_precision",
            mixed_precision,
            "--gradient_checkpointing",
            "--cache_latents",
            "--clip_skip",
            str(payload.clip_skip),
            "--min_snr_gamma",
            str(payload.min_snr_gamma),
            "--noise_offset",
            str(payload.noise_offset),
            "--save_every_n_epochs",
            str(payload.save_every_n_epochs),
        ]
        if payload.flip_aug:
            command.append("--flip_aug")
        if payload.vae.strip():
            command.extend(["--vae", _resolve_training_file_path(payload.vae, "vae", required=False)])
    elif payload.preset == "flux_lora":
        model_ref = payload.model_components.get("transformer") or payload.model_components.get("flux_model") or payload.base_model.strip()
        if not model_ref:
            raise RuntimeError("Flux LoRA requires a Flux base model path or model_components.flux_model.")
        simpletuner_root = Path(os.getenv("STUDIO_SIMPLETUNER_ROOT", "/app/trainers/SimpleTuner")).resolve(strict=False)
        script_text = payload.model_components.get("train_script") or os.getenv("STUDIO_FLUX_TRAIN_SCRIPT", "") or str(simpletuner_root / "train.py")
        script = Path(script_text).resolve(strict=False)
        command = [
            accelerate_bin,
            "launch",
            "--num_cpu_threads_per_process",
            "1",
            str(script),
            "--model_family",
            "flux",
            "--pretrained_model_name_or_path",
            model_ref,
            "--dataset_config",
            config.config_file,
            "--output_dir",
            str(run_output_dir),
            "--output_name",
            slugify(payload.output_name, "mklan-flux-lora"),
            "--max_train_steps",
            str(payload.max_train_steps),
            "--learning_rate",
            str(payload.learning_rate),
            "--optimizer_type",
            optimizer_type,
            "--lr_scheduler",
            scheduler,
            "--mixed_precision",
            mixed_precision,
            "--gradient_checkpointing",
            "--network_dim",
            str(payload.network_dim),
            "--network_alpha",
            str(payload.network_alpha),
        ]
    elif payload.preset == "anima_lora":
        required = ["dit", "text_encoder", "vae"]
        missing = [key for key in required if not payload.model_components.get(key)]
        if missing:
            raise RuntimeError(f"Anima LoRA requires model component paths: {', '.join(missing)}.")
        script = sd_root / "anima_train_network.py"
        command = [
            accelerate_bin,
            "launch",
            "--num_cpu_threads_per_process",
            "1",
            str(script),
            "--dit",
            payload.model_components["dit"],
            "--text_encoder",
            payload.model_components["text_encoder"],
            "--vae",
            payload.model_components["vae"],
            "--dataset_config",
            config.config_file,
            "--output_dir",
            str(run_output_dir),
            "--output_name",
            slugify(payload.output_name, "mklan-anima-lora"),
            "--network_module",
            "networks.lora",
            "--max_train_steps",
            str(payload.max_train_steps),
            "--mixed_precision",
            mixed_precision,
        ]
        if payload.model_components.get("llm_adapter"):
            command.extend(["--llm_adapter", payload.model_components["llm_adapter"]])
    else:
        script_text = payload.model_components.get("train_script") or os.getenv("STUDIO_Z_IMAGE_TRAIN_SCRIPT", "")
        if not script_text:
            raise RuntimeError("Z-Image training requires STUDIO_Z_IMAGE_TRAIN_SCRIPT or model_components.train_script.")
        script = Path(script_text)
        command = [
            accelerate_bin,
            "launch",
            "--num_cpu_threads_per_process",
            "1",
            str(script),
            "--dataset_config",
            config.config_file,
            "--output_dir",
            str(run_output_dir),
            "--output_name",
            slugify(payload.output_name, "mklan-z-image-lora"),
            "--max_train_steps",
            str(payload.max_train_steps),
            "--mixed_precision",
            mixed_precision,
        ]

    if payload.sample_prompt.strip():
        command.extend(["--sample_prompts", payload.sample_prompt.strip()])
    _extra_args(command, _filtered_extra_args(payload.extra_args, managed_extra_flags))

    return TrainingCommandPreview(
        preset=payload.preset,
        script=str(script),
        working_dir=str(script.parent),
        command=command,
        display_command=" ".join(shlex.quote(part) for part in command),
        dataset_config=config.config_file,
        output_dir=str(run_output_dir),
    )


@router.post("/runs/preview", response_model=TrainingCommandPreview)
def preview_training_command(payload: TrainingRunRequest) -> TrainingCommandPreview:
    return build_training_command(payload)


@router.post("/runs", response_model=TrainingRunResponse, status_code=202)
async def create_training_run(payload: TrainingRunRequest, request: Request) -> TrainingRunResponse:
    manager = getattr(request.app.state, "v2_jobs", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="V2 job manager is not available.")
    job_type = TRAINING_JOB_TYPES[payload.preset]
    command = build_training_command(payload)
    job = await manager.create_job(job_type, payload.model_dump())
    return TrainingRunResponse(job=JobRead.model_validate(job), events_url=f"/api/jobs/{job['id']}/events", command=command)


def _list_jobs(manager: JobManager, prefix: str) -> list[dict[str, Any]]:
    return manager.list_jobs(limit=80, prefix=prefix)


@router.get("/runs", response_model=list[JobRead])
def list_training_runs(request: Request) -> list[JobRead]:
    manager = getattr(request.app.state, "v2_jobs", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="V2 job manager is not available.")
    return [JobRead.model_validate(job) for job in _list_jobs(manager, "training.")]


@router.post("/runs/{job_id}/cancel", response_model=JobRead)
async def cancel_training_run(job_id: str, request: Request) -> JobRead:
    manager = getattr(request.app.state, "v2_jobs", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="V2 job manager is not available.")
    return JobRead.model_validate(await manager.cancel_job(job_id))


@router.get("/artifacts", response_model=list[ArtifactRead])
def list_artifacts() -> list[ArtifactRead]:
    artifacts = []
    for root, kind in ((TRAINING_OUTPUT_ROOT, "lora"), (DATA / "models" / "images", "checkpoint")):
        if not root.exists():
            continue
        for path in sorted(root.rglob("*"), key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True):
            if path.is_file() and path.suffix.lower() in {".safetensors", ".ckpt", ".pt"}:
                artifacts.append(
                    ArtifactRead(
                        name=path.name,
                        path=str(path),
                        size=path.stat().st_size,
                        modified_at=datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
                        kind=kind,
                    )
                )
    return artifacts


async def _terminate_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    try:
        if os.name != "nt":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        await asyncio.wait_for(process.wait(), timeout=10)
    except Exception:
        try:
            if os.name != "nt":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except Exception:
            pass


def _parse_training_progress(line: str, max_steps: int) -> tuple[float | None, dict[str, Any]]:
    payload: dict[str, Any] = {}
    fraction = None
    step_match = re.search(r"(\d+)\s*/\s*(\d+)", line)
    if step_match:
        current = int(step_match.group(1))
        total = max(int(step_match.group(2)), 1)
        fraction = current / total
        payload["step"] = current
        payload["total_steps"] = total
    elif max_steps:
        step_match = re.search(r"(?:steps?|step)\D+(\d+)", line, re.IGNORECASE)
        if step_match:
            current = int(step_match.group(1))
            fraction = min(current / max(max_steps, 1), 1)
            payload["step"] = current
            payload["total_steps"] = max_steps
    percent_match = re.search(r"(\d{1,3})%", line)
    if fraction is None and percent_match:
        fraction = min(int(percent_match.group(1)), 100) / 100
    loss_match = re.search(r"loss[:=]\s*([0-9.]+)", line, re.IGNORECASE)
    if loss_match:
        payload["loss"] = float(loss_match.group(1))
    return fraction, payload


async def run_caption_scan_job(job: dict[str, Any], manager: JobManager) -> dict[str, Any]:
    payload = CaptionScanRequest.model_validate(job["payload"])
    dataset_id = str(job["payload"].get("dataset_id") or "")
    metadata = _load_dataset(dataset_id)
    settings = metadata.get("settings") or {}
    image_dir = _dataset_image_dir(metadata)
    items = _dataset_items(metadata)
    total = max(len(items), 1)
    updated = 0
    skipped = 0
    failed = 0
    fallback_count = 0
    model_count = 0
    vlm_count = 0
    clip_count = 0
    florence_count = 0
    trigger_applied_count = 0
    errors: list[dict[str, str]] = []
    caption_sources: dict[str, int] = {}
    trigger_word = (payload.trigger_word or str(settings.get("trigger_token") or "")).strip()
    fallback_context = _caption_fallback_context(metadata)

    await manager.update_progress(
        job["id"],
        0.02,
        "Caption scan prepared.",
        payload={
            "dataset_id": dataset_id,
            "total": len(items),
            "provider": payload.provider,
            "caption_style": payload.caption_style,
            "local_model_id": payload.local_model_id,
            "clip_model_id": payload.clip_model_id,
        },
    )
    for index, item in enumerate(items, start=1):
        await manager.raise_if_canceled(job["id"])
        image_path = image_dir / item.filename
        caption_path = _caption_path_for_image(image_path, settings)
        caption_source = "skipped"
        if caption_path.exists() and caption_path.read_text(encoding="utf-8", errors="ignore").strip() and not payload.overwrite:
            skipped += 1
            caption_sources["skipped_existing"] = caption_sources.get("skipped_existing", 0) + 1
        else:
            try:
                caption, source_info = _caption_image_with_source(
                    image_path,
                    payload.max_words,
                    provider=payload.provider,
                    fallback_context=fallback_context,
                    local_model_id=payload.local_model_id,
                    clip_model_id=payload.clip_model_id,
                )
                caption = _apply_caption_style(caption, payload.caption_style, payload.max_words)
                caption_source = str(source_info.get("source") or "filename_fallback")
                caption_sources[caption_source] = caption_sources.get(caption_source, 0) + 1
                if caption_source == "filename_fallback":
                    fallback_count += 1
                    if source_info.get("error") and len(errors) < 10:
                        errors.append({"filename": item.filename, "error": str(source_info["error"])})
                else:
                    model_count += 1
                    if caption_source == "koboldcpp_vlm":
                        vlm_count += 1
                    if caption_source == "clip_tagger":
                        clip_count += 1
                    if caption_source == "florence2":
                        florence_count += 1
                if payload.prepend_trigger and trigger_word:
                    caption, trigger_changed = _prepend_trigger(caption, trigger_word, ", ")
                    if trigger_changed:
                        trigger_applied_count += 1
                caption_path.write_text(caption.strip(), encoding="utf-8")
                updated += 1
            except Exception as exc:
                failed += 1
                caption_source = "failed"
                if len(errors) < 10:
                    errors.append({"filename": item.filename, "error": f"{type(exc).__name__}: {exc}"})
        await manager.update_progress(
            job["id"],
            min(index / total, 0.95),
            f"Scanned captions: {index}/{len(items)}",
            payload={
                "dataset_id": dataset_id,
                "updated": updated,
                "skipped": skipped,
                "failed": failed,
                "fallback_count": fallback_count,
                "model_count": model_count,
                "vlm_count": vlm_count,
                "clip_count": clip_count,
                "florence_count": florence_count,
                "last_filename": item.filename,
                "last_source": caption_source,
                "caption_style": payload.caption_style,
            },
        )

    build_dataset_config(dataset_id)
    refreshed = _load_dataset(dataset_id)
    return {
        "dataset": _dataset_read(refreshed).model_dump(),
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
        "items": len(items),
        "max_words": payload.max_words,
        "trigger_applied": bool(payload.prepend_trigger and trigger_word),
        "trigger_applied_count": trigger_applied_count,
        "fallback_count": fallback_count,
        "model_count": model_count,
        "vlm_count": vlm_count,
        "clip_count": clip_count,
        "florence_count": florence_count,
        "provider": payload.provider,
        "caption_style": payload.caption_style,
        "local_model_id": payload.local_model_id,
        "clip_model_id": payload.clip_model_id,
        "caption_sources": caption_sources,
        "model_used": (
            _caption_model_id(payload.local_model_id)
            if caption_sources.get("local_blip")
            else (
                _caption_vlm_settings().get("model")
                if vlm_count
                else (
                    _caption_clip_model_id(payload.clip_model_id)
                    if clip_count
                    else (_caption_florence_settings().get("model_id") if florence_count else None)
                )
            )
        ),
        "download_allowed": _caption_download_allowed(),
        "clip_download_allowed": _caption_clip_allow_download(),
        "errors": errors,
    }


async def run_training_job(job: dict[str, Any], manager: JobManager) -> dict[str, Any]:
    payload = TrainingRunRequest.model_validate(job["payload"])
    command = build_training_command(payload)
    run_dir = RUNS_ROOT / job["id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "train.log"
    (run_dir / "command.json").write_text(command.model_dump_json(indent=2), encoding="utf-8")

    await manager.update_progress(job["id"], 0.04, "Training command prepared.", payload=command.model_dump())
    await manager.raise_if_canceled(job["id"])

    if payload.dry_run or os.getenv("STUDIO_TRAINING_DRY_RUN", "").lower() in {"1", "true", "yes", "on"}:
        log_path.write_text(f"DRY RUN\n{command.display_command}\n", encoding="utf-8")
        await asyncio.sleep(0.1)
        output_dir = Path(command.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        mock_artifact = output_dir / f"{slugify(payload.output_name, 'training-dry-run')}.safetensors"
        mock_artifact.write_bytes(b"dry-run training artifact")
        await manager.update_progress(job["id"], 0.92, "Dry-run artifact written.", payload={"artifact": str(mock_artifact)})
        return {"command": command.model_dump(), "log": str(log_path), "artifacts": [str(mock_artifact)], "dry_run": True}

    script_path = Path(command.script)
    if not script_path.exists():
        raise RuntimeError(
            f"Trainer script not found at {script_path}. Build the GPU backend with sd-scripts or set STUDIO_SD_SCRIPTS_ROOT."
        )

    process = await asyncio.create_subprocess_exec(
        *command.command,
        cwd=command.working_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=os.name != "nt",
    )
    artifacts: list[str] = []
    try:
        with log_path.open("a", encoding="utf-8", errors="ignore") as log_file:
            assert process.stdout is not None
            while True:
                line_bytes = await process.stdout.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace").rstrip()
                log_file.write(line + "\n")
                log_file.flush()
                fraction, event_payload = _parse_training_progress(line, payload.max_train_steps)
                if fraction is not None:
                    await manager.update_progress(job["id"], 0.08 + (fraction * 0.82), line[-240:], payload=event_payload)
                await manager.raise_if_canceled(job["id"])
        returncode = await process.wait()
        if returncode != 0:
            raise RuntimeError(f"Trainer exited with code {returncode}. See {log_path}.")
    except JobCanceled:
        await _terminate_process(process)
        raise
    except Exception:
        await _terminate_process(process)
        raise

    output_dir = Path(command.output_dir)
    for path in output_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".safetensors", ".ckpt", ".pt"}:
            artifacts.append(str(path))
    await manager.update_progress(job["id"], 0.96, "Training completed; artifacts indexed.", payload={"artifacts": artifacts})
    return {"command": command.model_dump(), "log": str(log_path), "artifacts": artifacts, "dry_run": False}
