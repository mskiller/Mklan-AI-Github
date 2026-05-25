from __future__ import annotations

import asyncio
import base64
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.comfyui_client import ComfyUIClient, DEFAULT_COMFYUI_WORKFLOW, build_workflow_from_generation, parse_workflow_template
from app.v2.assets import GeneratedAssetIngestRequest
from app.v2.jobs import JobManager


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


WORKFLOW_PRESETS: list[dict[str, Any]] = [
    {
        "id": "wildcard_sandbox_txt2img",
        "label": "Wildcard Sandbox txt2img",
        "task": "wildcards",
        "description": "General prompt sandbox using the built-in ComfyUI txt2img graph.",
        "placeholders": ["%prompt%", "%negative_prompt%", "%model%", "%width%", "%height%", "%steps%", "%scale%", "%sampler%", "%scheduler%", "%seed%"],
        "workflow_json": DEFAULT_COMFYUI_WORKFLOW,
    },
    {
        "id": "movie_scene_first_frame",
        "label": "Movie Scene First Frame",
        "task": "movie",
        "description": "Scene/sequence first-frame generation with deterministic seed metadata.",
        "placeholders": ["%prompt%", "%negative_prompt%", "%model%", "%width%", "%height%", "%steps%", "%scale%", "%seed%"],
        "workflow_json": DEFAULT_COMFYUI_WORKFLOW,
    },
    {
        "id": "cards_character_portrait",
        "label": "Cards Character Portrait",
        "task": "cards",
        "description": "Portrait/cowboy/fullbody card image generation routed through ComfyUI.",
        "placeholders": ["%prompt%", "%negative_prompt%", "%model%", "%width%", "%height%", "%steps%", "%scale%", "%seed%"],
        "workflow_json": DEFAULT_COMFYUI_WORKFLOW,
    },
]


class WorkflowValidationRequest(BaseModel):
    workflow_json: str | dict[str, Any] | None = None
    endpoint: str | None = None


class WorkflowRenderRequest(BaseModel):
    prompt: str = Field(min_length=1)
    negative_prompt: str = ""
    width: int = Field(default=1024, ge=128, le=4096)
    height: int = Field(default=1024, ge=128, le=4096)
    steps: int = Field(default=30, ge=1, le=200)
    cfg_scale: float = Field(default=7.0, ge=0.0, le=40.0)
    sampler_name: str = "Euler a"
    scheduler: str = "Automatic"
    seed: int | None = None
    model: str | None = None
    endpoint: str | None = None
    timeout_s: int | None = Field(default=None, ge=1, le=3600)
    workflow_json: str | dict[str, Any] | None = None
    source_module: str = "workflow_hub"
    source_id: str | None = None


class WorkflowRenderResponse(BaseModel):
    job: dict[str, Any]
    events_url: str


router = APIRouter(prefix="/workflows", tags=["v2-workflows"])


def register_workflow_jobs(manager: JobManager) -> None:
    manager.register_handler("workflow.render", render_workflow_job)


def _collect_placeholders(value: Any, found: set[str]) -> None:
    if isinstance(value, str):
        for part in value.split("%"):
            if part and part.replace("_", "").isalnum():
                token = f"%{part}%"
                if token in value:
                    found.add(token)
    elif isinstance(value, list):
        for item in value:
            _collect_placeholders(item, found)
    elif isinstance(value, dict):
        for item in value.values():
            _collect_placeholders(item, found)


def _workflow_summary(workflow: dict[str, Any]) -> dict[str, Any]:
    placeholders: set[str] = set()
    _collect_placeholders(workflow, placeholders)
    class_counts: dict[str, int] = {}
    for node in workflow.values():
        if isinstance(node, dict):
            class_type = str(node.get("class_type") or "unknown")
            class_counts[class_type] = class_counts.get(class_type, 0) + 1
    return {
        "node_count": len(workflow),
        "class_counts": class_counts,
        "placeholders": sorted(placeholders),
    }


def _load_studio_image_settings() -> dict[str, Any]:
    from app.studio_features import load_settings

    return load_settings().get("image", {})


def _generated_root() -> Path:
    from app.studio_features import GENERATED

    GENERATED.mkdir(parents=True, exist_ok=True)
    return GENERATED


async def render_workflow_job(job: dict[str, Any], manager: JobManager) -> dict[str, Any]:
    payload = dict(job["payload"])
    request_payload = WorkflowRenderRequest.model_validate(payload)
    image_settings = _load_studio_image_settings()
    endpoint = (request_payload.endpoint or image_settings.get("endpoint") or "").strip()
    if not endpoint:
        raise RuntimeError("ComfyUI endpoint is not configured.")

    timeout_s = request_payload.timeout_s or int(image_settings.get("timeout_s") or 300)
    model_name = request_payload.model or str(image_settings.get("model") or "").strip()
    client = ComfyUIClient(endpoint, timeout_s=timeout_s)
    await manager.update_progress(job["id"], 0.08, "Connected to ComfyUI settings.")
    await manager.raise_if_canceled(job["id"])

    if not model_name:
        checkpoints = await asyncio.to_thread(client.list_checkpoints)
        model_name = checkpoints[0] if checkpoints else ""
    workflow, seed = build_workflow_from_generation(
        workflow_json=request_payload.workflow_json if request_payload.workflow_json is not None else image_settings.get("workflow_json") or "",
        prompt=request_payload.prompt,
        negative_prompt=request_payload.negative_prompt,
        model=model_name,
        width=request_payload.width,
        height=request_payload.height,
        steps=request_payload.steps,
        cfg_scale=request_payload.cfg_scale,
        sampler_name=request_payload.sampler_name,
        scheduler=request_payload.scheduler,
        seed=request_payload.seed,
    )
    await manager.update_progress(job["id"], 0.18, "Workflow rendered from preset/template.", payload=_workflow_summary(workflow))
    await manager.raise_if_canceled(job["id"])

    image_b64, prompt_id, output = await asyncio.to_thread(client.render_base64, workflow)
    await manager.update_progress(job["id"], 0.82, "ComfyUI render completed.", payload={"prompt_id": prompt_id})
    await manager.raise_if_canceled(job["id"])

    image_bytes = base64.b64decode(image_b64)
    filename = f"{uuid.uuid4().hex}.png"
    image_path = _generated_root() / filename
    image_path.write_bytes(image_bytes)
    metadata = {
        **request_payload.model_dump(),
        "provider": "comfyui",
        "model": model_name,
        "seed": seed,
        "workflow": "workflow_hub",
        "comfyui_prompt_id": prompt_id,
        "comfyui_output": output,
        "created_at": utc_now_iso(),
    }
    image_path.with_suffix(".json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    asset = None
    registry = getattr(manager, "asset_registry", None)
    if registry is not None:
        asset = registry.ingest_generated(
            GeneratedAssetIngestRequest(
                file=filename,
                source_module=request_payload.source_module,
                source_id=request_payload.source_id or job["id"],
                metadata=metadata,
                provenance={"job_id": job["id"], "comfyui_prompt_id": prompt_id},
            )
        )
    await manager.update_progress(job["id"], 0.94, "Generated asset saved and registered.")
    return {
        "file": f"/generated/{filename}",
        "metadata": metadata,
        "asset": asset,
    }


@router.get("/presets")
def list_workflow_presets() -> dict[str, Any]:
    return {"presets": WORKFLOW_PRESETS}


@router.post("/validate")
def validate_workflow(payload: WorkflowValidationRequest) -> dict[str, Any]:
    try:
        workflow = parse_workflow_template(payload.workflow_json)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    response = {"ok": True, "workflow": _workflow_summary(workflow), "comfyui": None}
    if payload.endpoint:
        try:
            client = ComfyUIClient(payload.endpoint, timeout_s=30)
            object_info = client.object_info()
            response["comfyui"] = {
                "ok": True,
                "endpoint": client.endpoint,
                "available_node_classes": len(object_info),
                "missing_node_classes": sorted(
                    class_type
                    for class_type in response["workflow"]["class_counts"]
                    if class_type not in object_info
                ),
                "checkpoints": client.list_checkpoints(),
                "loras": client.list_models("loras"),
                "vae": client.list_models("vae"),
            }
        except Exception as exc:
            response["comfyui"] = {"ok": False, "error": str(exc)}
    return response


@router.post("/render", response_model=WorkflowRenderResponse, status_code=202)
async def render_workflow(payload: WorkflowRenderRequest, request: Request) -> WorkflowRenderResponse:
    manager = getattr(request.app.state, "v2_jobs", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="V2 job manager is not available.")
    job = await manager.create_job("workflow.render", payload.model_dump())
    audit = getattr(request.app.state, "v2_audit", None)
    if audit is not None:
        audit.record("workflows.render", target=job["id"], payload={"source_module": payload.source_module})
    return WorkflowRenderResponse(job=job, events_url=f"/api/jobs/{job['id']}/events")

