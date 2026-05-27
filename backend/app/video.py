from __future__ import annotations

import base64
from datetime import UTC, datetime
import json
import os
from pathlib import Path, PurePosixPath
import random
import re
import subprocess
from typing import Any, Literal
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.movie.config import get_settings as get_movie_settings
from app.movie.services.video_generation import VideoGenerationService
from app.v2.assets import AssetRegistry, GeneratedAssetIngestRequest
from app.v2.jobs import JobManager, JobRead
from app.v2.workspaces import active_workspace_id


VIDEO_JOB_TYPE = "video.generate"
VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".mkv"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}

router = APIRouter(prefix="/video", tags=["video"])


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def slugify(value: str, fallback: str = "video") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("-._").lower()
    return cleaned[:90] or fallback


class VideoSettingsRead(BaseModel):
    enabled: bool = True
    provider: Literal["mock", "lightx2v", "wan_gguf", "comfyui_template"] = "mock"
    model_root: str
    model_class: str = "wan2.2_i2v"
    encoder_root: str = ""
    vae_root: str = ""
    gguf_model_path: str = ""
    lora_path: str = ""
    lora_scale: float = Field(default=1.0, ge=0.0, le=4.0)
    quantization_preset: str = "auto"
    attention_mode: str = "sdpa"
    infer_steps: int = Field(default=4, ge=1, le=200)
    native_height: int = Field(default=480, ge=128, le=2160)
    native_width: int = Field(default=832, ge=128, le=4096)
    native_frame_count: int = Field(default=49, ge=1, le=4096)
    guidance_scale: float = Field(default=1.0, ge=0.0, le=40.0)
    sample_shift: float = Field(default=5.0, ge=0.0, le=20.0)
    cpu_offload: bool = True
    text_encoder_offload: bool = True
    image_encoder_offload: bool = True
    vae_offload: bool = True
    retime_mode: Literal["none", "fit_duration", "frame_interpolate_fit"] = "none"
    target_output_fps: int = Field(default=24, ge=1, le=120)
    seed_mode: Literal["random", "fixed"] = "random"
    seed: int | None = None
    output_root: str


class VideoSettingsResponse(BaseModel):
    settings: VideoSettingsRead
    status: dict[str, Any]


class VideoSettingsUpdate(BaseModel):
    enabled: bool | None = None
    provider: Literal["mock", "lightx2v", "wan_gguf", "comfyui_template"] | None = None
    model_root: str | None = None
    model_class: str | None = None
    encoder_root: str | None = None
    vae_root: str | None = None
    gguf_model_path: str | None = None
    lora_path: str | None = None
    lora_scale: float | None = Field(default=None, ge=0.0, le=4.0)
    quantization_preset: str | None = None
    attention_mode: str | None = None
    infer_steps: int | None = Field(default=None, ge=1, le=200)
    native_height: int | None = Field(default=None, ge=128, le=2160)
    native_width: int | None = Field(default=None, ge=128, le=4096)
    native_frame_count: int | None = Field(default=None, ge=1, le=4096)
    guidance_scale: float | None = Field(default=None, ge=0.0, le=40.0)
    sample_shift: float | None = Field(default=None, ge=0.0, le=20.0)
    cpu_offload: bool | None = None
    text_encoder_offload: bool | None = None
    image_encoder_offload: bool | None = None
    vae_offload: bool | None = None
    retime_mode: Literal["none", "fit_duration", "frame_interpolate_fit"] | None = None
    target_output_fps: int | None = Field(default=None, ge=1, le=120)
    seed_mode: Literal["random", "fixed"] | None = None
    seed: int | None = None


class VideoModelInventoryResponse(BaseModel):
    root_path: str
    providers: list[str]
    transformer_gguf: list[dict[str, Any]]
    model_dirs: list[dict[str, Any]]
    encoders: list[dict[str, Any]]
    vaes: list[dict[str, Any]]
    loras: list[dict[str, Any]]
    other: list[dict[str, Any]]
    auto_config: dict[str, str]


class VideoGenerateRequest(BaseModel):
    mode: Literal["text_to_video", "image_to_video"] = "text_to_video"
    prompt: str = Field(min_length=1, max_length=6000)
    negative_prompt: str = Field(default="", max_length=4000)
    provider: Literal["mock", "lightx2v", "wan_gguf", "comfyui_template"] | None = None
    model_name: str | None = Field(default=None, max_length=240)
    seed: int | None = None
    duration_s: float = Field(default=2.0, ge=0.5, le=120.0)
    fps: int | None = Field(default=None, ge=1, le=120)
    width: int | None = Field(default=None, ge=128, le=4096)
    height: int | None = Field(default=None, ge=128, le=2160)
    reference_image_url: str | None = Field(default=None, max_length=1000)
    reference_image_base64: str | None = None
    workflow_preset_id: str | None = Field(default=None, max_length=120)
    movie_project_id: str | None = Field(default=None, max_length=160)
    scene_id: str | None = Field(default=None, max_length=160)
    sequence_id: str | None = Field(default=None, max_length=160)
    workspace_id: str | None = Field(default=None, max_length=120)


class VideoGenerateResponse(BaseModel):
    job: JobRead
    events_url: str


def register_video_jobs(manager: JobManager) -> None:
    manager.register_handler(VIDEO_JOB_TYPE, run_video_generation_job)


def _settings_path(data_root: Path) -> Path:
    return data_root / "studio_video_settings.json"


def _default_video_settings(data_root: Path) -> dict[str, Any]:
    model_root = Path(os.getenv("STUDIO_VIDEO_MODEL_ROOT", str(data_root / "models" / "video")))
    output_root = Path(os.getenv("STUDIO_VIDEO_OUTPUT_ROOT", str(data_root / "generated" / "video")))
    return {
        "enabled": True,
        "provider": os.getenv("STUDIO_VIDEO_PROVIDER", "mock"),
        "model_root": str(model_root),
        "model_class": os.getenv("STUDIO_VIDEO_MODEL_CLASS", "wan2.2_i2v"),
        "encoder_root": "",
        "vae_root": "",
        "gguf_model_path": "",
        "lora_path": "",
        "lora_scale": 1.0,
        "quantization_preset": "auto",
        "attention_mode": "sdpa",
        "infer_steps": 4,
        "native_height": 480,
        "native_width": 832,
        "native_frame_count": 49,
        "guidance_scale": 1.0,
        "sample_shift": 5.0,
        "cpu_offload": True,
        "text_encoder_offload": True,
        "image_encoder_offload": True,
        "vae_offload": True,
        "retime_mode": "none",
        "target_output_fps": 24,
        "seed_mode": "random",
        "seed": None,
        "output_root": str(output_root),
    }


def _load_video_settings(data_root: Path) -> VideoSettingsRead:
    settings = _default_video_settings(data_root)
    path = _settings_path(data_root)
    if path.exists():
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                settings.update(saved)
        except Exception:
            pass
    settings["model_root"] = settings.get("model_root") or str(data_root / "models" / "video")
    settings["output_root"] = settings.get("output_root") or str(data_root / "generated" / "video")
    return VideoSettingsRead.model_validate(settings)


def _save_video_settings(data_root: Path, settings: VideoSettingsRead) -> None:
    path = _settings_path(data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(settings.model_dump_json(indent=2), encoding="utf-8")


def _data_root(request: Request) -> Path:
    data_root = getattr(request.app.state, "data_root", None)
    if data_root:
        return Path(data_root)
    configured = os.getenv("STUDIO_DATA_ROOT")
    return Path(configured) if configured else Path(__file__).resolve().parents[2] / "data"


def _video_service() -> VideoGenerationService:
    return VideoGenerationService(get_movie_settings())


def _media_settings(settings: VideoSettingsRead) -> dict[str, Any]:
    payload = settings.model_dump()
    payload.pop("output_root", None)
    return {"video": payload}


def _hardware_profile(request: Request | None = None) -> dict[str, Any]:
    if request is not None:
        profile = getattr(request.app.state, "hardware_profile", None)
        if isinstance(profile, dict):
            return profile
    return {"cuda_available": False, "vram_gb": 0}


def _provider_status(settings: VideoSettingsRead, request: Request | None = None) -> dict[str, Any]:
    if settings.provider == "comfyui_template":
        return {
            "ok": True,
            "ready": True,
            "status": "template_route",
            "message": "ComfyUI template routing is available through workflow templates; direct video render requires a template-aware provider.",
            "provider": settings.provider,
            "resolved_paths": {"model_root": settings.model_root},
            "warnings": [],
        }
    try:
        return _video_service().test_settings(_media_settings(settings), _hardware_profile(request))
    except Exception as exc:
        return {
            "ok": False,
            "ready": False,
            "status": "error",
            "message": str(exc),
            "provider": settings.provider,
            "resolved_paths": {},
            "warnings": [],
        }


def _resolve_seed(settings: VideoSettingsRead, payload: VideoGenerateRequest) -> int:
    if payload.seed is not None:
        return int(payload.seed)
    if settings.seed_mode == "fixed" and settings.seed is not None:
        return int(settings.seed)
    return random.randint(0, 2**31 - 1)


def _resolve_generated_path(data_root: Path, value: str) -> Path:
    raw = value.strip().replace("\\", "/")
    if raw.startswith("/generated/"):
        raw = raw.split("/generated/", 1)[1]
    elif raw.startswith("generated/"):
        raw = raw.split("generated/", 1)[1]
    relative = PurePosixPath(raw)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise HTTPException(status_code=400, detail="Reference image URL is not a generated asset path.")
    path = (data_root / "generated" / Path(*relative.parts)).resolve(strict=False)
    root = (data_root / "generated").resolve(strict=False)
    if root != path and root not in path.parents:
        raise HTTPException(status_code=400, detail="Reference image escapes the generated directory.")
    if not path.exists() or path.suffix.lower() not in IMAGE_SUFFIXES:
        raise HTTPException(status_code=404, detail="Reference image was not found.")
    return path


def _write_reference_frame(data_root: Path, payload: VideoGenerateRequest, width: int, height: int, job_id: str) -> Path:
    frame_dir = data_root / "generated" / "video" / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    frame_path = frame_dir / f"{job_id}.png"
    if payload.reference_image_base64:
        try:
            image_bytes = base64.b64decode(payload.reference_image_base64.split(",", 1)[-1], validate=False)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Reference image base64 is not readable.") from exc
        frame_path.write_bytes(image_bytes)
        return frame_path
    if payload.reference_image_url:
        source = _resolve_generated_path(data_root, payload.reference_image_url)
        frame_path.write_bytes(source.read_bytes())
        return frame_path

    try:
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (width, height), color=(18, 22, 30))
        draw = ImageDraw.Draw(image)
        lines = ["Mklan Studio V2", "mock video frame", payload.prompt[:120]]
        y = max(24, height // 5)
        for line in lines:
            draw.text((32, y), line, fill=(236, 238, 246))
            y += 28
        image.save(frame_path)
    except Exception:
        frame_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    return frame_path


def _generate_mock_video(input_path: Path, output_path: Path, settings: VideoSettingsRead, duration_s: float, fps: int) -> None:
    ffmpeg = os.getenv("MOVIE_TOOL_FFMPEG_BINARY", "ffmpeg")
    width = settings.native_width
    height = settings.native_height
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-loop",
            "1",
            "-i",
            str(input_path),
            "-t",
            f"{duration_s:.2f}",
            "-vf",
            f"fps={fps},scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0 and output_path.exists():
        return
    output_path.write_bytes(
        b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
        + f"\nMock video fallback for {input_path.name}\n".encode("utf-8")
    )


def _run_real_provider(input_path: Path, output_path: Path, prompt: str, settings: VideoSettingsRead, seed: int, provider: str) -> None:
    service = _video_service()
    config = settings.model_dump()
    config.pop("output_root", None)
    model_name = config.get("model_class") or "wan2.2_i2v"
    if provider == "lightx2v":
        service._generate_lightx2v_video(input_path, output_path, prompt, config, model_name, seed)  # noqa: SLF001
        return
    if provider == "wan_gguf":
        warnings: list[str] = []
        config = service._auto_fill_gguf_config(config, _media_settings(settings), warnings)  # noqa: SLF001
        service._generate_wan_gguf_video(input_path, output_path, prompt, config, model_name, seed)  # noqa: SLF001
        return
    raise RuntimeError("ComfyUI template video rendering needs a concrete video workflow template before it can run.")


async def run_video_generation_job(job: dict[str, Any], manager: JobManager) -> dict[str, Any]:
    payload = VideoGenerateRequest.model_validate(job["payload"])
    settings = _load_video_settings(manager.data_root)
    if payload.provider:
        settings = settings.model_copy(update={"provider": payload.provider})
    provider = settings.provider
    if not settings.enabled:
        raise RuntimeError("Native video generation is disabled in Video settings.")

    output_root = Path(settings.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    seed = _resolve_seed(settings, payload)
    width = payload.width or settings.native_width
    height = payload.height or settings.native_height
    fps = payload.fps or settings.target_output_fps
    await manager.update_progress(job["id"], 0.08, "Video job prepared.", payload={"provider": provider, "seed": seed})
    await manager.raise_if_canceled(job["id"])

    input_path = _write_reference_frame(manager.data_root, payload, width, height, job["id"])
    output_name = f"{slugify(payload.prompt)}-{job['id'][:8]}.mp4"
    output_path = output_root / output_name
    if provider == "mock":
        _generate_mock_video(input_path, output_path, settings, payload.duration_s, fps)
    else:
        _run_real_provider(input_path, output_path, payload.prompt, settings, seed, provider)
    await manager.update_progress(job["id"], 0.82, "Video file generated.", payload={"file": str(output_path)})
    await manager.raise_if_canceled(job["id"])

    generated_root = manager.data_root / "generated"
    relative_path = output_path.resolve(strict=False).relative_to(generated_root.resolve(strict=False)).as_posix()
    metadata = {
        "prompt": payload.prompt,
        "negative_prompt": payload.negative_prompt,
        "mode": payload.mode,
        "provider": provider,
        "seed": seed,
        "duration_s": payload.duration_s,
        "fps": fps,
        "width": width,
        "height": height,
        "movie_project_id": payload.movie_project_id,
        "scene_id": payload.scene_id,
        "sequence_id": payload.sequence_id,
        "workflow_preset_id": payload.workflow_preset_id,
        "workspace_id": job.get("workspace_id") or payload.workspace_id or active_workspace_id(manager.data_root),
        "created_at": utc_now_iso(),
    }
    sidecar_path = output_path.with_suffix(".json")
    sidecar_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    registry: AssetRegistry | None = getattr(manager, "asset_registry", None)
    if registry is None:
        registry = AssetRegistry(manager.data_root)
        registry.initialize()
    asset = registry.ingest_generated(
        GeneratedAssetIngestRequest(
            file=relative_path,
            kind="video",
            source_module="video",
            source_id=job["id"],
            metadata=metadata,
            provenance={"job_id": job["id"], "provider": provider},
            workspace_id=str(metadata["workspace_id"]),
        )
    )
    await manager.update_progress(job["id"], 0.96, "Video registered in the asset registry.", payload={"asset_id": asset["id"]})
    return {
        "video": {
            "name": output_path.name,
            "url": f"/generated/{relative_path}",
            "path": str(output_path),
            "sidecar": str(sidecar_path),
            "size": output_path.stat().st_size,
            "metadata": metadata,
        },
        "asset": asset,
    }


@router.get("/models", response_model=VideoModelInventoryResponse)
def list_video_models(request: Request) -> VideoModelInventoryResponse:
    data_root = _data_root(request)
    settings = _load_video_settings(data_root)
    Path(settings.model_root).mkdir(parents=True, exist_ok=True)
    inventory = _video_service().list_available_video_models(_media_settings(settings))
    return VideoModelInventoryResponse(providers=["mock", "lightx2v", "wan_gguf", "comfyui_template"], **inventory)


@router.get("/settings", response_model=VideoSettingsResponse)
def get_video_settings(request: Request) -> VideoSettingsResponse:
    settings = _load_video_settings(_data_root(request))
    Path(settings.model_root).mkdir(parents=True, exist_ok=True)
    Path(settings.output_root).mkdir(parents=True, exist_ok=True)
    return VideoSettingsResponse(settings=settings, status=_provider_status(settings, request))


@router.post("/settings", response_model=VideoSettingsResponse)
def update_video_settings(payload: VideoSettingsUpdate, request: Request) -> VideoSettingsResponse:
    data_root = _data_root(request)
    current = _load_video_settings(data_root)
    patch = {key: value for key, value in payload.model_dump(exclude_unset=True).items() if value is not None}
    settings = current.model_copy(update=patch)
    _save_video_settings(data_root, settings)
    return VideoSettingsResponse(settings=settings, status=_provider_status(settings, request))


@router.get("/clips")
def list_video_clips(request: Request, limit: int = 80) -> dict[str, Any]:
    registry = getattr(request.app.state, "v2_assets", None)
    data_root = _data_root(request)
    if registry is None:
        registry = AssetRegistry(data_root)
        registry.initialize()
    assets = [asset for asset in registry.list_assets(limit=limit) if str(asset.get("kind") or "").lower() == "video"]
    seen = {asset["url"] for asset in assets}
    scanned = [
        asset
        for asset in registry.search_local("", limit=limit)
        if str(asset.get("kind") or "").lower() == "video" and asset.get("url") not in seen
    ]
    return {"clips": assets + scanned, "workspace_id": active_workspace_id(data_root)}


@router.get("/jobs", response_model=list[JobRead])
def list_video_jobs(request: Request, limit: int = 80) -> list[JobRead]:
    manager = getattr(request.app.state, "v2_jobs", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="V2 job manager is not available.")
    return [JobRead.model_validate(job) for job in manager.list_jobs(limit=limit, prefix="video.")]


@router.get("/jobs/{job_id}", response_model=JobRead)
def get_video_job(job_id: str, request: Request) -> JobRead:
    manager = getattr(request.app.state, "v2_jobs", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="V2 job manager is not available.")
    job = manager.get_job(job_id)
    if not str(job.get("job_type") or "").startswith("video."):
        raise HTTPException(status_code=404, detail="Video job not found.")
    return JobRead.model_validate(job)


@router.post("/generate", response_model=VideoGenerateResponse, status_code=202)
async def generate_video(payload: VideoGenerateRequest, request: Request) -> VideoGenerateResponse:
    manager = getattr(request.app.state, "v2_jobs", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="V2 job manager is not available.")
    workspace_id = payload.workspace_id or active_workspace_id(_data_root(request))
    job_payload = payload.model_dump()
    job_payload["workspace_id"] = workspace_id
    job = await manager.create_job(VIDEO_JOB_TYPE, job_payload, workspace_id=workspace_id)
    return VideoGenerateResponse(job=JobRead.model_validate(job), events_url=f"/api/jobs/{job['id']}/events")
