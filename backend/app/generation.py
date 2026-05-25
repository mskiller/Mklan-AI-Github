from __future__ import annotations

import asyncio
import base64
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import random
import re
from typing import Any, Literal
from urllib.parse import urlparse, urlunparse
import uuid

import requests
import yaml
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.comfyui_client import ComfyUIClient, build_workflow_from_generation
from app.config import WILDCARD_SOURCE_ROOT
from app.studio_features import DATA, GENERATED, load_settings
from app.v2.assets import GeneratedAssetIngestRequest
from app.v2.jobs import JobManager, JobRead


router = APIRouter(prefix="/generation", tags=["generation"])

WILDCARD_REF_RE = re.compile(r"__([A-Za-z0-9][A-Za-z0-9_./\\-]*?)__")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"] = "user"
    content: str


class GenerationChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list)
    prompt: str = ""
    image_base64: str | None = None
    temperature: float = Field(default=0.4, ge=0, le=2)
    max_tokens: int = Field(default=512, ge=1, le=8192)
    model: str | None = None


class GenerationChatResponse(BaseModel):
    ok: bool
    content: str
    model: str
    endpoint: str
    raw: dict[str, Any] = Field(default_factory=dict)


class LoraSelection(BaseModel):
    name: str
    weight: float = Field(default=1.0, ge=-4.0, le=4.0)


class ImageGenerationRequest(BaseModel):
    prompt: str = Field(min_length=1)
    negative_prompt: str = ""
    provider: Literal["auto", "integrated", "comfyui"] = "auto"
    model: str | None = None
    loras: list[LoraSelection] = Field(default_factory=list)
    width: int = Field(default=1024, ge=128, le=4096)
    height: int = Field(default=1024, ge=128, le=4096)
    steps: int = Field(default=30, ge=1, le=200)
    cfg_scale: float = Field(default=7.0, ge=0.0, le=40.0)
    sampler_name: str = "Euler a"
    scheduler: str = "Automatic"
    seed: int | None = None
    batch_count: int = Field(default=1, ge=1, le=8)
    expand_wildcards: bool = True
    wildcard_seed: int | None = None
    workflow_json: str | dict[str, Any] | None = None
    source_module: str = "generation"


class ImageGenerationResponse(BaseModel):
    job: dict[str, Any]
    events_url: str


class WildcardPreviewRequest(BaseModel):
    prompt: str
    seed: int | None = None


class WildcardPreviewResponse(BaseModel):
    original_prompt: str
    expanded_prompt: str
    seed: int
    refs: list[dict[str, str]]
    missing: list[str]


class JobClearResponse(BaseModel):
    deleted: int
    status: Literal["failed", "succeeded"]


def register_generation_jobs(manager: JobManager) -> None:
    manager.register_handler("generation.image", run_image_generation_job)


def _normalize_openai_base_url(endpoint: str) -> str:
    parsed = urlparse((endpoint or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="LLM endpoint must be an http(s) URL.")
    hostname = (parsed.hostname or "").lower()
    netloc = parsed.netloc
    if Path("/.dockerenv").exists() and hostname in {"127.0.0.1", "localhost"}:
        netloc = parsed.netloc.replace(parsed.hostname or hostname, "host.docker.internal", 1)
    return urlunparse((parsed.scheme, netloc, parsed.path.rstrip("/"), "", "", "")).rstrip("/")


def _chat_endpoint(endpoint: str) -> str:
    base_url = str(endpoint or "").strip().rstrip("/")
    parsed = urlparse(base_url)
    if Path("/.dockerenv").exists() and parsed.hostname in {"127.0.0.1", "localhost"}:
        netloc = "host.docker.internal"
        if parsed.port:
            netloc = f"{netloc}:{parsed.port}"
        base_url = urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)).rstrip("/")
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


def _image_data_url(image_base64: str) -> str:
    cleaned = image_base64.strip()
    if cleaned.startswith("data:image/"):
        return cleaned
    return f"data:image/png;base64,{cleaned}"


@router.post("/chat", response_model=GenerationChatResponse)
def chat(payload: GenerationChatRequest) -> GenerationChatResponse:
    settings = load_settings()
    llm = settings.get("llm", {})
    endpoint = _normalize_openai_base_url(str(llm.get("endpoint") or ""))
    model = payload.model or str(llm.get("model") or "koboldcpp")
    messages = [message.model_dump() for message in payload.messages]
    if payload.prompt.strip():
        messages.append({"role": "user", "content": payload.prompt.strip()})
    if not messages:
        raise HTTPException(status_code=400, detail="Provide a prompt or messages.")
    if payload.image_base64:
        last = messages[-1]
        text = last.get("content") if isinstance(last.get("content"), str) else ""
        last["content"] = [
            {"type": "text", "text": text or "Analyze this image."},
            {"type": "image_url", "image_url": {"url": _image_data_url(payload.image_base64)}},
        ]

    headers: dict[str, str] = {}
    if llm.get("api_key"):
        headers["Authorization"] = f"Bearer {llm['api_key']}"
    body = {
        "model": model,
        "messages": messages,
        "temperature": payload.temperature,
        "max_tokens": payload.max_tokens,
    }
    try:
        response = requests.post(_chat_endpoint(endpoint), json=body, headers=headers, timeout=int(llm.get("timeout_s") or 120))
        response.raise_for_status()
        raw = response.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM chat request failed: {exc}") from exc

    content = _extract_chat_text(raw if isinstance(raw, dict) else {})
    if not content:
        raise HTTPException(status_code=502, detail="LLM did not return readable text.")
    return GenerationChatResponse(ok=True, content=content, model=model, endpoint=endpoint, raw=raw)


def _wildcard_root() -> Path:
    root = Path(os.getenv("WILDCARD_SOURCE_ROOT", str(WILDCARD_SOURCE_ROOT))).resolve(strict=False)
    return root


def _candidate_wildcard_paths(name: str) -> list[Path]:
    safe_name = name.strip().replace("\\", "/").strip("/")
    if not safe_name or ".." in safe_name.split("/"):
        return []
    root = _wildcard_root()
    raw = root / safe_name
    suffix = raw.suffix.lower()
    paths = [raw] if suffix in {".txt", ".yaml", ".yml"} else []
    for ext in (".txt", ".yaml", ".yml"):
        paths.append(root / f"{safe_name}{ext}")
    return paths


def _flatten_yaml(value: Any) -> list[str]:
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned and not cleaned.startswith("#") else []
    if isinstance(value, list):
        output: list[str] = []
        for item in value:
            output.extend(_flatten_yaml(item))
        return output
    if isinstance(value, dict):
        output = []
        for item in value.values():
            output.extend(_flatten_yaml(item))
        return output
    return []


def _wildcard_options(name: str) -> tuple[list[str], str | None]:
    root = _wildcard_root()
    for path in _candidate_wildcard_paths(name):
        resolved = path.resolve(strict=False)
        if root != resolved and root not in resolved.parents:
            continue
        if not resolved.exists() or not resolved.is_file():
            continue
        try:
            if resolved.suffix.lower() == ".txt":
                options = [
                    line.strip().lstrip("-").strip().strip("'\"")
                    for line in resolved.read_text(encoding="utf-8", errors="ignore").splitlines()
                    if line.strip() and not line.lstrip().startswith("#")
                ]
            else:
                options = _flatten_yaml(yaml.safe_load(resolved.read_text(encoding="utf-8", errors="ignore")))
        except Exception:
            options = []
        options = [option for option in options if option]
        if options:
            return options, str(resolved.relative_to(root))
    return [], None


def expand_wildcards(prompt: str, *, seed: int | None = None, max_depth: int = 8) -> WildcardPreviewResponse:
    resolved_seed = int(seed if seed is not None else random.randint(1, 2**31 - 1))
    rng = random.Random(resolved_seed)
    refs: list[dict[str, str]] = []
    missing: list[str] = []
    expanded = prompt

    for _ in range(max_depth):
        changed = False

        def replace(match: re.Match[str]) -> str:
            nonlocal changed
            name = match.group(1).strip()
            options, source = _wildcard_options(name)
            if not options:
                if name not in missing:
                    missing.append(name)
                return match.group(0)
            choice = rng.choice(options)
            refs.append({"name": name, "source": source or "", "value": choice})
            changed = True
            return choice

        expanded = WILDCARD_REF_RE.sub(replace, expanded)
        if not changed or not WILDCARD_REF_RE.search(expanded):
            break

    return WildcardPreviewResponse(
        original_prompt=prompt,
        expanded_prompt=expanded,
        seed=resolved_seed,
        refs=refs,
        missing=missing,
    )


@router.post("/wildcards/preview", response_model=WildcardPreviewResponse)
def preview_wildcards(payload: WildcardPreviewRequest) -> WildcardPreviewResponse:
    return expand_wildcards(payload.prompt, seed=payload.seed)


@router.get("/images")
def list_generated_images() -> dict[str, Any]:
    files = []
    for path in sorted(GENERATED.glob("*"), key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True):
        if path.suffix.lower() not in IMAGE_EXTENSIONS or not path.is_file():
            continue
        metadata = {}
        metadata_path = path.with_suffix(".json")
        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except Exception:
                metadata = {}
        files.append(
            {
                "name": path.name,
                "url": f"/generated/{path.name}",
                "size": path.stat().st_size,
                "created_at": path.stat().st_mtime,
                "metadata": metadata,
            }
        )
    return {"images": files}


@router.get("/models")
def list_generation_models() -> dict[str, Any]:
    from app.studio_features import list_models

    lora_root = DATA / "models" / "loras"
    loras = []
    if lora_root.exists():
        for path in sorted(lora_root.rglob("*")):
            if path.is_file() and path.suffix.lower() in {".safetensors", ".ckpt", ".pt"}:
                loras.append({"name": path.name, "path": str(path.relative_to(lora_root)), "size": path.stat().st_size})
    return {**list_models(), "loras": loras}


@router.post("/images", response_model=ImageGenerationResponse, status_code=202)
async def create_image_generation(payload: ImageGenerationRequest, request: Request) -> ImageGenerationResponse:
    manager = getattr(request.app.state, "v2_jobs", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="V2 job manager is not available.")
    job = await manager.create_job("generation.image", payload.model_dump())
    return ImageGenerationResponse(job=job, events_url=f"/api/jobs/{job['id']}/events")


@router.get("/jobs", response_model=list[JobRead])
def list_generation_jobs(request: Request) -> list[JobRead]:
    manager = getattr(request.app.state, "v2_jobs", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="V2 job manager is not available.")
    with manager._connect() as conn:
        rows = conn.execute("SELECT * FROM jobs WHERE job_type LIKE 'generation.%' ORDER BY created_at DESC LIMIT 80").fetchall()
    return [JobRead.model_validate(manager._job_from_row(row)) for row in rows]


def clear_generation_jobs(manager: JobManager, status: Literal["failed", "succeeded"]) -> int:
    with manager._connect() as conn:
        rows = conn.execute(
            "SELECT id FROM jobs WHERE job_type LIKE 'generation.%' AND status = ?",
            (status,),
        ).fetchall()
        job_ids = [str(row["id"]) for row in rows]
        if not job_ids:
            return 0
        placeholders = ",".join("?" for _ in job_ids)
        conn.execute(f"DELETE FROM job_events WHERE job_id IN ({placeholders})", job_ids)
        conn.execute(f"DELETE FROM jobs WHERE id IN ({placeholders})", job_ids)
        conn.commit()
        return len(job_ids)


@router.delete("/jobs", response_model=JobClearResponse)
def delete_generation_jobs(status: Literal["failed", "succeeded"], request: Request) -> JobClearResponse:
    manager = getattr(request.app.state, "v2_jobs", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="V2 job manager is not available.")
    return JobClearResponse(deleted=clear_generation_jobs(manager, status), status=status)


async def run_image_generation_job(job: dict[str, Any], manager: JobManager) -> dict[str, Any]:
    request_payload = ImageGenerationRequest.model_validate(job["payload"])
    settings = load_settings()
    image_settings = settings.get("image", {})
    provider = request_payload.provider
    if provider == "auto":
        provider = "comfyui" if str(image_settings.get("provider") or "").lower() == "comfyui" else "integrated"

    wildcard_seed = request_payload.wildcard_seed if request_payload.wildcard_seed is not None else request_payload.seed
    wildcard_preview = expand_wildcards(request_payload.prompt, seed=wildcard_seed) if request_payload.expand_wildcards else WildcardPreviewResponse(
        original_prompt=request_payload.prompt,
        expanded_prompt=request_payload.prompt,
        seed=int(wildcard_seed if wildcard_seed is not None else random.randint(1, 2**31 - 1)),
        refs=[],
        missing=[],
    )
    await manager.update_progress(job["id"], 0.06, "Prompt prepared.", payload=wildcard_preview.model_dump())
    await manager.raise_if_canceled(job["id"])

    results: list[dict[str, Any]] = []
    for index in range(request_payload.batch_count):
        await manager.update_progress(job["id"], 0.08 + (index / request_payload.batch_count) * 0.84, f"Rendering image {index + 1}/{request_payload.batch_count}.")
        await manager.raise_if_canceled(job["id"])
        if provider == "comfyui":
            result = await _render_comfyui_image(request_payload, wildcard_preview, image_settings, job["id"], manager, index)
        else:
            result = await asyncio.to_thread(_render_integrated_image, request_payload, wildcard_preview, image_settings, job["id"], index, manager)
        results.append(result)
        await manager.update_progress(job["id"], 0.16 + ((index + 1) / request_payload.batch_count) * 0.78, f"Saved image {index + 1}/{request_payload.batch_count}.", payload=result)

    return {"images": results, "provider": provider, "wildcards": wildcard_preview.model_dump()}


def _save_generated_image(image_bytes: bytes, metadata: dict[str, Any], manager: JobManager | None = None) -> dict[str, Any]:
    GENERATED.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.png"
    path = GENERATED / filename
    path.write_bytes(image_bytes)
    path.with_suffix(".json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    asset = None
    registry = getattr(manager, "asset_registry", None) if manager is not None else None
    if registry is not None:
        asset = registry.ingest_generated(
            GeneratedAssetIngestRequest(
                file=filename,
                source_module=str(metadata.get("source_module") or "generation"),
                source_id=str(metadata.get("job_id") or metadata.get("seed") or path.stem),
                metadata=metadata,
                provenance={"job_id": metadata.get("job_id"), "registered_by": "generation.image"},
            )
        )
    return {"file": f"/generated/{filename}", "metadata": metadata, "asset": asset}


async def _render_comfyui_image(
    payload: ImageGenerationRequest,
    wildcard_preview: WildcardPreviewResponse,
    image_settings: dict[str, Any],
    job_id: str,
    manager: JobManager,
    batch_index: int,
) -> dict[str, Any]:
    endpoint = str(image_settings.get("endpoint") or "").strip()
    if not endpoint:
        raise RuntimeError("ComfyUI endpoint is not configured.")
    model_name = payload.model or str(image_settings.get("model") or "").strip()
    client = ComfyUIClient(endpoint, timeout_s=int(image_settings.get("timeout_s") or 300))
    if not model_name:
        checkpoints = await asyncio.to_thread(client.list_checkpoints)
        model_name = checkpoints[0] if checkpoints else ""
    seed = payload.seed + batch_index if payload.seed is not None else None
    workflow, resolved_seed = build_workflow_from_generation(
        workflow_json=payload.workflow_json if payload.workflow_json is not None else image_settings.get("workflow_json") or "",
        prompt=wildcard_preview.expanded_prompt,
        negative_prompt=payload.negative_prompt,
        model=model_name,
        width=payload.width,
        height=payload.height,
        steps=payload.steps,
        cfg_scale=payload.cfg_scale,
        sampler_name=payload.sampler_name,
        scheduler=payload.scheduler,
        seed=seed,
    )
    await manager.update_progress(job_id, 0.2, "ComfyUI workflow queued.")
    loop = asyncio.get_running_loop()

    def publish_comfyui_event(event: dict[str, Any]) -> None:
        event = {**event, "batch_index": batch_index}
        fraction = event.get("fraction")
        progress = 0.22
        message = "ComfyUI is rendering."
        if isinstance(fraction, (int, float)):
            progress = 0.22 + max(0.0, min(1.0, float(fraction))) * 0.56
            value = event.get("value")
            maximum = event.get("max")
            message = f"ComfyUI sampling {value}/{maximum}." if value is not None and maximum is not None else "ComfyUI sampling."
        elif event.get("type") == "comfyui.websocket_connected":
            message = "ComfyUI websocket connected."
        elif event.get("type") == "comfyui.websocket_unavailable":
            message = "ComfyUI websocket unavailable; polling history."
        elif event.get("type") == "comfyui.websocket_fallback":
            message = "ComfyUI websocket fell back to history polling."
        elif event.get("node"):
            message = f"ComfyUI node {event.get('node')} is running."
        asyncio.run_coroutine_threadsafe(manager.update_progress(job_id, progress, message, payload=event), loop)

    render_result = await asyncio.to_thread(client.render, workflow, progress_callback=publish_comfyui_event)
    metadata = {
        **payload.model_dump(),
        "provider": "comfyui",
        "model": model_name,
        "seed": resolved_seed,
        "batch_index": batch_index,
        "original_prompt": wildcard_preview.original_prompt,
        "prompt": wildcard_preview.expanded_prompt,
        "wildcards": wildcard_preview.model_dump(),
        "comfyui_prompt_id": render_result.prompt_id,
        "comfyui_output": render_result.output,
        "job_id": job_id,
        "created_at": utc_now_iso(),
    }
    return _save_generated_image(render_result.image_bytes, metadata, manager)


def _find_model_file(model_name: str | None) -> Path | None:
    model_root = DATA / "models"
    candidates: list[Path] = []
    for ext in ("*.safetensors", "*.ckpt", "*.pt", "*.bin"):
        candidates.extend(model_root.rglob(ext))
    if model_name:
        for path in candidates:
            if path.name == model_name or path.stem == model_name or str(path.relative_to(model_root)).replace("\\", "/") == model_name:
                return path
    return candidates[0] if candidates else None


def _find_lora_file(name: str) -> Path | None:
    lora_root = DATA / "models" / "loras"
    if not lora_root.exists():
        return None
    for path in lora_root.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".safetensors", ".ckpt", ".pt"} and (path.name == name or path.stem == name):
            return path
    return None


def _render_integrated_image(
    payload: ImageGenerationRequest,
    wildcard_preview: WildcardPreviewResponse,
    image_settings: dict[str, Any],
    job_id: str,
    batch_index: int,
    manager: JobManager,
) -> dict[str, Any]:
    model_file = _find_model_file(payload.model or str(image_settings.get("model") or ""))
    if model_file is None:
        raise RuntimeError("Integrated generation needs a local SDXL checkpoint in data/models.")
    try:
        import io

        import torch
        from diffusers import DPMSolverMultistepScheduler, DPMSolverSinglestepScheduler, EulerAncestralDiscreteScheduler, LCMScheduler, StableDiffusionXLPipeline
    except Exception as exc:
        raise RuntimeError(f"Integrated generation dependencies are not installed: {exc}") from exc

    dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    device = "cuda" if torch.cuda.is_available() else "cpu"
    pipe = StableDiffusionXLPipeline.from_single_file(
        str(model_file),
        torch_dtype=dtype,
        use_safetensors=model_file.suffix.lower() == ".safetensors",
    ).to(device)

    sampler = payload.sampler_name.lower()
    if "lcm" in sampler:
        pipe.scheduler = LCMScheduler.from_config(pipe.scheduler.config)
    elif "dpm++ sde" in sampler or "dpmpp_sde" in sampler:
        pipe.scheduler = DPMSolverSinglestepScheduler.from_config(pipe.scheduler.config, use_karras_sigmas="karras" in payload.scheduler.lower())
    elif "dpm++ 2s" in sampler or "dpmpp_2s" in sampler:
        pipe.scheduler = DPMSolverSinglestepScheduler.from_config(pipe.scheduler.config)
    elif "dpm++ 2m" in sampler or "dpmpp_2m" in sampler:
        pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config, use_karras_sigmas="karras" in payload.scheduler.lower())
    else:
        pipe.scheduler = EulerAncestralDiscreteScheduler.from_config(pipe.scheduler.config)
    pipe.enable_attention_slicing()

    loaded_loras = []
    for lora in payload.loras:
        lora_file = _find_lora_file(lora.name)
        if lora_file is None:
            raise RuntimeError(f"LoRA not found: {lora.name}")
        adapter_name = f"lora_{len(loaded_loras)}"
        pipe.load_lora_weights(str(lora_file.parent), weight_name=lora_file.name, adapter_name=adapter_name)
        loaded_loras.append((adapter_name, lora.weight, lora_file.name))
    if loaded_loras and hasattr(pipe, "set_adapters"):
        pipe.set_adapters([item[0] for item in loaded_loras], adapter_weights=[item[1] for item in loaded_loras])

    seed = payload.seed + batch_index if payload.seed is not None else random.randint(1, 2**31 - 1)
    generator = torch.Generator(device=device).manual_seed(seed)
    result = pipe(
        prompt=wildcard_preview.expanded_prompt,
        negative_prompt=payload.negative_prompt or None,
        width=payload.width,
        height=payload.height,
        num_inference_steps=payload.steps,
        guidance_scale=payload.cfg_scale,
        generator=generator,
    )
    buffer = io.BytesIO()
    result.images[0].save(buffer, format="PNG")
    metadata = {
        **payload.model_dump(),
        "provider": "integrated",
        "model": model_file.name,
        "seed": seed,
        "batch_index": batch_index,
        "original_prompt": wildcard_preview.original_prompt,
        "prompt": wildcard_preview.expanded_prompt,
        "wildcards": wildcard_preview.model_dump(),
        "loaded_loras": [{"adapter": item[0], "weight": item[1], "file": item[2]} for item in loaded_loras],
        "job_id": job_id,
        "created_at": utc_now_iso(),
    }
    return _save_generated_image(buffer.getvalue(), metadata, manager)
