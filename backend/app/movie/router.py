from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import re
import shutil
from typing import Any, Literal
import uuid

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile, APIRouter
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

from .config import get_settings
from .database import Database, utc_now_iso
from .job_manager import JobManager
from .model_settings import DEFAULT_INSTRUCTION, preview_sample_context, render_task_prompts
from .repository import DurationConflictError, MovieRepository
from .schemas import (
    AssistantConnectionTestRequest,
    AssistantConnectionTestResponse,
    AssistantSettingsRead,
    AssistantSettingsUpdateRequest,
    BeatBoardGenerateRequest,
    BeatBoardRead,
    BeatBoardReorderRequest,
    ComfySceneExtractRead,
    CharacterCreateRequest,
    CharacterGenerateRequest,
    CharacterImageGenerateRequest,
    CharacterRead,
    CharacterUpdateRequest,
    ContinuityReviewRead,
    CreateBeatRequest,
    ExportRequest,
    GenerateSceneImagePromptsRequest,
    GenerateScenesRequest,
    GenerateSequencesRequest,
    GenerateWanPromptsRequest,
    HardwareProfile,
    ImageModelInventoryRead,
    ImageModelUploadResponse,
    VideoModelInventoryRead,
    JobRead,
    JobType,
    MediaModelDownloadRequest,
    MediaModelDownloadStatusRead,
    MediaGenerationSettingsRead,
    MediaGenerationSettingsTestResponse,
    MediaGenerationSettingsUpdateRequest,
    ModelSettingsRead,
    ModelSettingsUpdateRequest,
    ProjectModelSettingsOverrideRead,
    ProjectModelSettingsOverrideUpdateRequest,
    ProjectCreateRequest,
    ProjectListItem,
    ProjectRead,
    ProjectUpdateRequest,
    PromptPreviewRequest,
    PromptPreviewResponse,
    PromptPackageRead,
    ScenarioAssistantRequest,
    ScenarioAssistantResponse,
    SceneImageGenerateRequest,
    SceneVideoChainGenerateRequest,
    SequenceBatchUpdateRequest,
    SequenceVideoGenerateRequest,
    UpdateAssemblyRequest,
    UpdateBeatRequest,
    UpdateSceneRequest,
    UpdateSequenceRequest,
    UpdateSequenceWanPromptRequest,
)
from .services.continuity_review import ContinuityReviewService
from .services.generation import NarrativeStudio
from .services.hardware import detect_hardware_profile
from .services.image_generation import ImageGenerationService
from .services.model_runtime import LocalModelRuntime
from .services.model_downloads import MediaModelDownloadService
from .services.prompt_package import build_prompt_package, determine_prompt_package_status, render_prompt_package_markdown
from .services.rendering import AssemblyService
from .services.scenario_assistant import ScenarioAssistant
from .services.video_generation import VideoGenerationService

COMFY_SCENE_EXTRACT_FORMAT = "movie_scripting_scene_extract.v1"


def _asset_url(project_id: str, relative_path: str) -> str:
    return f"/assets/{project_id}/{relative_path.replace(chr(92), '/')}"


def _slugify_filename(filename: str) -> str:
    stem = Path(filename or "upload").stem or "upload"
    suffix = Path(filename or "upload").suffix.lower()
    safe_stem = re.sub(r"[^a-zA-Z0-9._-]+", "-", stem).strip("-") or "upload"
    safe_suffix = re.sub(r"[^a-z0-9.]+", "", suffix)
    return f"{safe_stem}{safe_suffix}"


def _attach_asset_url(project_id: str, asset: dict | None) -> dict | None:
    if asset is None:
        return None
    return {
        **asset,
        "asset_url": _asset_url(project_id, asset["relative_path"]),
    }


def _attach_variant_asset_urls(project_id: str, variants: list[dict] | None) -> list[dict]:
    next_variants: list[dict] = []
    for variant in variants or []:
        next_variants.append(
            {
                **variant,
                "asset": _attach_asset_url(project_id, variant.get("asset")),
                "input_frame_asset": _attach_asset_url(project_id, variant.get("input_frame_asset")),
                "last_frame_asset": _attach_asset_url(project_id, variant.get("last_frame_asset")),
            }
        )
    return next_variants


def _serialize_sequence(sequence: dict) -> dict:
    return {
        **sequence,
        "uploaded_video_asset": _attach_asset_url(sequence["project_id"], sequence.get("uploaded_video_asset")),
        "approved_video_asset": _attach_asset_url(sequence["project_id"], sequence.get("approved_video_asset")),
        "input_frame_asset": _attach_asset_url(sequence["project_id"], sequence.get("input_frame_asset")),
        "last_frame_asset": _attach_asset_url(sequence["project_id"], sequence.get("last_frame_asset")),
        "generated_video_variants": _attach_variant_asset_urls(
            sequence["project_id"], sequence.get("generated_video_variants")
        ),
    }


def _serialize_scene(scene: dict) -> dict:
    return {
        **scene,
        "first_image_asset": _attach_asset_url(scene["project_id"], scene.get("first_image_asset")),
        "generated_image_variants": _attach_variant_asset_urls(
            scene["project_id"], scene.get("generated_image_variants")
        ),
        "sequences": [_serialize_sequence(sequence) for sequence in scene.get("sequences", [])],
    }


def _serialize_character(character: dict) -> dict:
    project_id = character["project_id"]
    return {
        **character,
        "portrait_image_url": _asset_url(project_id, character["portrait_image_url"]) if character["portrait_image_url"] else None,
        "cowboyshot_image_url": _asset_url(project_id, character["cowboyshot_image_url"]) if character["cowboyshot_image_url"] else None,
        "fullbody_image_url": _asset_url(project_id, character["fullbody_image_url"]) if character["fullbody_image_url"] else None,
    }


def _serialize_project(detail: dict, hardware_profile: dict) -> dict:
    scenes = [_serialize_scene(scene) for scene in detail["scenes"]]
    exports = [
        {
            **export,
            "asset_url": _asset_url(detail["id"], export["relative_path"]),
        }
        for export in detail["exports"]
    ]
    style_anchor = None
    if detail["style_anchor_text"]:
        style_anchor = {
            "id": f"style-{detail['id']}",
            "project_id": detail["id"],
            "content": detail["style_anchor_text"],
            "updated_at": detail["updated_at"],
        }
    return {
        **detail,
        "style_anchor": style_anchor,
        "scenes": scenes,
        "exports": exports,
        "characters": [_serialize_character(char) for char in detail.get("characters", [])],
        "prompt_package_status": determine_prompt_package_status({**detail, "scenes": scenes}),
        "hardware_profile": hardware_profile,
        "beat_board": detail.get("beat_board"),
        "scenes": scenes,
        "exports": exports,
    }


def _serialize_job(job: dict) -> dict:
    return job


def _serialize_media_download(status: dict) -> dict:
    return status


def _load_project_or_404(repository: MovieRepository, project_id: str) -> dict:
    detail = repository.get_project_detail(project_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return detail


def _load_story_scene_or_404(repository: MovieRepository, scene_id: str) -> dict:
    scene = repository.get_story_scene(scene_id)
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found.")
    return scene


def _load_sequence_or_404(repository: MovieRepository, sequence_id: str) -> dict:
    sequence = repository.get_sequence(sequence_id)
    if sequence is None:
        raise HTTPException(status_code=404, detail="Sequence not found.")
    return sequence


def _legacy_video_generation_error() -> HTTPException:
    return HTTPException(
        status_code=410,
        detail="Legacy render-first endpoints were retired. Use the Images tab, the Video tab, uploads, and assembly export instead.",
    )


def _legacy_opening_image_error() -> HTTPException:
    return HTTPException(
        status_code=410,
        detail="Movie-level opening images were retired in 2.0. Use scene-level first-image prompts and scene-level first-image uploads instead.",
    )


def _ensure_v2_project(detail: dict) -> None:
    if detail["workflow_version"] < 2:
        raise HTTPException(
            status_code=409,
            detail="This is a legacy v1 project. Upgrade it to 2.0 before using the scene and sequence workflow.",
        )


def _ensure_project_editable(detail: dict) -> None:
    if detail.get("archived_at"):
        raise HTTPException(
            status_code=409,
            detail="Archived projects are read-only. Restore the project before editing, generating, uploading, or exporting.",
        )


def _resolve_comfy_extract_window(scene: dict, start_order: int) -> list[dict]:
    if start_order < 1:
        raise HTTPException(status_code=400, detail="start_order must be 1 or greater.")

    sequences = sorted(
        scene.get("sequences", []),
        key=lambda item: (item["order"], item.get("absolute_order", 0), item["created_at"]),
    )
    required_orders = [start_order, start_order + 1, start_order + 2]
    selected = [sequence for sequence in sequences if sequence["order"] in required_orders]

    if len(selected) != 3 or [sequence["order"] for sequence in selected] != required_orders:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Scene {scene['order']:02d} does not have 3 consecutive sequences starting at order "
                f"{start_order}."
            ),
        )
    return selected


def _resolve_sequence_input_asset(scene: dict, sequence_id: str) -> dict | None:
    ordered_sequences = sorted(
        scene.get("sequences", []),
        key=lambda item: (item.get("order", 0), item.get("absolute_order", 0), item.get("created_at", "")),
    )
    previous_last_frame = scene.get("first_image_asset")
    for sequence in ordered_sequences:
        if sequence["id"] == sequence_id:
            return previous_last_frame
        previous_last_frame = sequence.get("last_frame_asset")
    return None


def _put_media_download_status(app: FastAPI, download_id: str, status: dict) -> None:
    app.state.media_downloads[download_id] = status


def _update_media_download_status(app: FastAPI, download_id: str, **changes: Any) -> dict:
    current = dict(app.state.media_downloads.get(download_id) or {})
    current.update(changes)
    current["updated_at"] = utc_now_iso()
    app.state.media_downloads[download_id] = current
    return current


def _build_comfy_scene_extract(project: dict, scene: dict, sequences: list[dict]) -> dict:
    start_order = sequences[0]["order"]
    end_order = sequences[-1]["order"]
    payload = {
        "format": COMFY_SCENE_EXTRACT_FORMAT,
        "project": {
            "id": project["id"],
            "name": project["name"],
        },
        "scene": {
            "id": scene["id"],
            "order": scene["order"],
            "title": scene["title"],
            "target_duration_s": scene["target_duration_s"],
        },
        "block": {
            "start_order": start_order,
            "end_order": end_order,
        },
        "prompts": {
            "first_image_prompt": scene["first_image_prompt_text"],
            "sequence_1_wan_prompt": sequences[0]["wan_prompt_text"],
            "sequence_2_wan_prompt": sequences[1]["wan_prompt_text"],
            "sequence_3_wan_prompt": sequences[2]["wan_prompt_text"],
        },
        "sequences": [
            {
                "id": sequence["id"],
                "order": sequence["order"],
                "title": sequence["title"],
                "wan_prompt_text": sequence["wan_prompt_text"],
            }
            for sequence in sequences
        ],
    }
    return ComfySceneExtractRead.model_validate(payload).model_dump(mode="json")


def _build_prompt_preview_context(
    repository: MovieRepository,
    payload: PromptPreviewRequest,
) -> dict:
    context = preview_sample_context(payload.task.value)
    if payload.project_id:
        project = _load_project_or_404(repository, payload.project_id)
        context["project"] = {
            "name": project["name"],
            "genre": project["genre"],
            "tone": project["tone"],
            "target_duration_s": project["target_duration_s"],
            "scenario_text": project.get("scenario_text", "").strip(),
        }
        context["style_anchor_text"] = project.get("style_anchor_text", "") or context["style_anchor_text"]
        scene = None
        if payload.scene_id:
            scene = next((item for item in project.get("scenes", []) if item["id"] == payload.scene_id), None)
        elif project.get("scenes"):
            scene = project["scenes"][0]
        if scene:
            context["scene"] = {
                "id": scene["id"],
                "order": scene["order"],
                "title": scene["title"],
                "target_duration_s": scene["target_duration_s"],
                "narrative_text": scene["narrative_text"],
                "first_image_prompt_text": scene.get("first_image_prompt_text", ""),
                "first_image_asset": {
                    "original_filename": scene.get("first_image_asset", {}).get("original_filename", "")
                    if scene.get("first_image_asset")
                    else ""
                },
                "reference_image_available": "true" if scene.get("first_image_asset") else "false",
            }
            sequence = None
            if payload.sequence_id:
                sequence = next((item for item in scene.get("sequences", []) if item["id"] == payload.sequence_id), None)
            elif scene.get("sequences"):
                sequence = scene["sequences"][0]
            if sequence:
                context["sequence"] = {
                    "id": sequence["id"],
                    "order": sequence["order"],
                    "absolute_order": sequence["absolute_order"],
                    "title": sequence["title"],
                    "target_duration_s": sequence["target_duration_s"],
                    "narrative_text": sequence["narrative_text"],
                    "camera_direction": sequence["camera_direction"],
                    "action_direction": sequence["action_direction"],
                }
        if payload.task.value == "continuity_review":
            context["review_context"] = (
                "Scene reference image: "
                f"{'available' if scene and scene.get('first_image_asset') else 'missing'}. "
                "Use uploaded sequence frames to compare identity, wardrobe, location, lighting, props, camera, and action continuity."
            )
    context["focus"] = payload.focus
    context["instruction"] = payload.instruction or DEFAULT_INSTRUCTION
    context["rewrite_scenario"] = "yes" if payload.rewrite_scenario else "no"
    context["max_suggestions"] = payload.max_suggestions
    return context



router = APIRouter(prefix="", tags=["movie"])
@router.get("/health")
def healthcheck(request: Request) -> dict:
    return {"ok": True}

@router.get("/system/hardware", response_model=HardwareProfile)
def get_hardware(request: Request) -> HardwareProfile:
    return HardwareProfile.model_validate(request.app.state.hardware_profile)

@router.get("/system/scenario-assistant/settings", response_model=AssistantSettingsRead)
def get_assistant_settings(request: Request) -> AssistantSettingsRead:
    settings_payload = request.app.state.repository.get_assistant_settings()
    return AssistantSettingsRead.model_validate(settings_payload)

@router.patch("/system/scenario-assistant/settings", response_model=AssistantSettingsRead)
def update_assistant_settings(request: Request, payload: AssistantSettingsUpdateRequest) -> AssistantSettingsRead:
    settings_payload = request.app.state.repository.update_assistant_settings(payload.model_dump())
    return AssistantSettingsRead.model_validate(settings_payload)

@router.post("/system/scenario-assistant/test", response_model=AssistantConnectionTestResponse)
def test_assistant_connection(request: Request, payload: AssistantConnectionTestRequest) -> AssistantConnectionTestResponse:
    result = request.app.state.scenario_assistant.test_connection(payload.model_dump())
    return AssistantConnectionTestResponse.model_validate(result)

@router.get("/system/model-settings", response_model=ModelSettingsRead)
def get_model_settings(request: Request) -> ModelSettingsRead:
    payload = request.app.state.repository.get_model_settings()
    return ModelSettingsRead.model_validate(payload)

@router.patch("/system/model-settings", response_model=ModelSettingsRead)
def update_model_settings(request: Request, payload: ModelSettingsUpdateRequest) -> ModelSettingsRead:
    updated = request.app.state.repository.update_model_settings(payload.model_dump())
    return ModelSettingsRead.model_validate(updated)

@router.post("/system/model-settings/test-connection", response_model=AssistantConnectionTestResponse)
def test_model_settings_connection(request: Request, payload: ModelSettingsUpdateRequest) -> AssistantConnectionTestResponse:
    runtime = payload.model_dump()["runtime"]
    result = request.app.state.scenario_assistant.test_connection(
        {
            "provider": runtime["provider"],
            "base_url": runtime["base_url"],
            "api_key": runtime["api_key"],
            "model": runtime["default_model"],
            "timeout_s": runtime["timeout_s"],
        }
    )
    return AssistantConnectionTestResponse.model_validate(result)

@router.post("/system/model-settings/test-prompt", response_model=PromptPreviewResponse)
def test_prompt_preview(request: Request, payload: PromptPreviewRequest) -> PromptPreviewResponse:
    if payload.project_id:
        global_settings = request.app.state.repository.get_resolved_model_settings(payload.project_id)
    else:
        global_settings = request.app.state.repository.get_resolved_model_settings()
    context = _build_prompt_preview_context(request.app.state.repository, payload)
    try:
        rendered = render_task_prompts(global_settings, payload.task.value, context)
    except KeyError as exc:
        return PromptPreviewResponse.model_validate(
            {
                "task": payload.task.value,
                "system_prompt": "",
                "user_prompt": "",
                "rendered_variables": {},
                "provider": global_settings["runtime"]["provider"],
                "effective_model": global_settings["runtime"]["default_model"],
                "effective_parameters": {},
                "error_text": f"Unknown template token: {exc.args[0]}",
            }
        )
    output_text = None
    error_text = None
    if payload.run_model:
        try:
            output_text = request.app.state.scenario_assistant.runtime.run_text(
                system_prompt=rendered["system_prompt"],
                user_prompt=rendered["user_prompt"],
                runtime_config=rendered["task_config"]["runtime"],
                parameters=rendered["task_config"]["parameters"],
            )
        except Exception as exc:
            error_text = str(exc)
    return PromptPreviewResponse.model_validate(
        {
            "task": payload.task.value,
            "system_prompt": rendered["system_prompt"],
            "user_prompt": rendered["user_prompt"],
            "rendered_variables": rendered["rendered_variables"],
            "provider": rendered["task_config"]["runtime"]["provider"],
            "effective_model": rendered["task_config"]["runtime"]["model"],
            "effective_parameters": rendered["task_config"]["parameters"],
            "output_text": output_text,
            "error_text": error_text,
        }
    )

@router.get("/system/media-generation-settings", response_model=MediaGenerationSettingsRead)
def get_media_generation_settings(request: Request) -> MediaGenerationSettingsRead:
    payload = request.app.state.repository.get_media_generation_settings()
    return MediaGenerationSettingsRead.model_validate(payload)

@router.patch("/system/media-generation-settings", response_model=MediaGenerationSettingsRead)
def update_media_generation_settings(
    request: Request,
    payload: MediaGenerationSettingsUpdateRequest,
) -> MediaGenerationSettingsRead:
    updated = request.app.state.repository.update_media_generation_settings(payload.model_dump())
    return MediaGenerationSettingsRead.model_validate(updated)

@router.post("/system/media-generation-settings/test", response_model=MediaGenerationSettingsTestResponse)
def test_media_generation_settings(
    request: Request,
    payload: MediaGenerationSettingsUpdateRequest | None = None,
) -> MediaGenerationSettingsTestResponse:
    effective_settings = payload.model_dump() if payload is not None else request.app.state.repository.get_media_generation_settings()
    image_result = request.app.state.image_generation_service.test_settings(
        effective_settings,
        request.app.state.hardware_profile,
    )
    video_result = request.app.state.video_generation_service.test_settings(
        effective_settings,
        request.app.state.hardware_profile,
    )
    return MediaGenerationSettingsTestResponse.model_validate(
        {
            "image": image_result,
            "video": video_result,
        }
    )

@router.get("/system/media-generation/image-models", response_model=ImageModelInventoryRead)
def list_image_models(request: Request) -> ImageModelInventoryRead:
    inventory = request.app.state.image_generation_service.list_available_models(
        request.app.state.repository.get_media_generation_settings()
    )
    return ImageModelInventoryRead.model_validate(inventory)

@router.get("/system/media-generation/video-models", response_model=VideoModelInventoryRead)
def list_video_models(request: Request) -> VideoModelInventoryRead:
    """Scan the video-models folder and return a grouped inventory.

    Groups files by detected component type (transformer GGUF, model dir,
    encoder, VAE, LoRA) and includes an auto_config dict with the
    best-guess path for each component.
    """
    inventory = request.app.state.video_generation_service.list_available_video_models(
        request.app.state.repository.get_media_generation_settings()
    )
    return VideoModelInventoryRead.model_validate(inventory)

@router.post("/system/media-generation/image-models/upload", response_model=ImageModelUploadResponse)
async def upload_image_model(
    request: Request,
    file: UploadFile = File(...),
    destination_name: str = Form(""),
    set_default: bool = Form(True),
) -> ImageModelUploadResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Choose a checkpoint file before uploading.")
    media_settings = request.app.state.repository.get_media_generation_settings()
    inventory_root, target_path = request.app.state.image_generation_service.reserve_uploaded_model_path(
        media_settings=media_settings,
        filename=file.filename,
        destination_name=destination_name,
    )
    try:
        with target_path.open("wb") as output_stream:
            while True:
                chunk = await file.read(8 * 1024 * 1024)
                if not chunk:
                    break
                output_stream.write(chunk)
    except Exception:
        if target_path.exists():
            target_path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    uploaded_model = request.app.state.image_generation_service.describe_uploaded_model(
        root_path=inventory_root,
        model_path=target_path,
    )
    if set_default:
        inventory_root = request.app.state.image_generation_service.list_available_models(media_settings)["root_path"]
        media_settings["image"]["provider"] = "diffusers"
        media_settings["image"]["checkpoint_root"] = inventory_root
        media_settings["image"]["default_model"] = uploaded_model["value"]
        media_settings = request.app.state.repository.update_media_generation_settings(media_settings)
    inventory = request.app.state.image_generation_service.list_available_models(media_settings)
    return ImageModelUploadResponse.model_validate(
        {
            "uploaded_model": uploaded_model,
            "inventory": inventory,
            "settings": media_settings,
        }
    )

async def _run_media_model_download(app: FastAPI, download_id: str, payload: dict[str, Any]) -> None:
    _update_media_download_status(
        app,
        download_id,
        status="running",
        progress=0.05,
        message="Connecting to Hugging Face and preparing the download.",
        error_text=None,
    )
    try:
        effective_settings = app.state.repository.get_media_generation_settings()
        result = await asyncio.to_thread(
            app.state.media_model_download_service.download,
            request=payload,
            media_settings=effective_settings,
        )
        applied_to_settings = False
        if payload.get("apply_to_settings", True):
            updated_settings = app.state.repository.get_media_generation_settings()
            if payload["target"] == "image":
                updated_settings["image"]["provider"] = "diffusers"
                updated_settings["image"]["checkpoint_root"] = result["settings_path"]
                updated_settings["image"]["default_model"] = result.get("default_model", "")
            else:
                # After a video model download, re-scan the video-models folder
                # and auto-apply detected component paths to settings.
                scan = app.state.video_generation_service.list_available_video_models(
                    updated_settings
                )
                auto = scan["auto_config"]
                # Choose provider: wan_gguf when a .gguf transformer was found,
                # otherwise fall back to lightx2v (full-precision safetensors).
                if auto.get("gguf_model_path"):
                    updated_settings["video"]["provider"] = "wan_gguf"
                    updated_settings["video"]["gguf_model_path"] = auto["gguf_model_path"]
                else:
                    updated_settings["video"]["provider"] = "lightx2v"
                # Fill model_root, encoder, VAE, LoRA when auto-detected.
                for field in ("model_root", "encoder_root", "vae_root", "lora_path"):
                    if auto.get(field) and not updated_settings["video"].get(field):
                        updated_settings["video"][field] = auto[field]
                # Always fall back model_root to the downloaded destination.
                if not auto.get("model_root"):
                    updated_settings["video"]["model_root"] = result["settings_path"]
            app.state.repository.update_media_generation_settings(updated_settings)
            applied_to_settings = True

        _update_media_download_status(
            app,
            download_id,
            status="succeeded",
            progress=1.0,
            destination_path=result["destination_path"],
            downloaded_path=result["downloaded_path"],
            applied_to_settings=applied_to_settings,
            message="Model download finished successfully.",
            error_text=None,
        )
    except Exception as exc:
        _update_media_download_status(
            app,
            download_id,
            status="failed",
            progress=1.0,
            message="Model download failed.",
            error_text=str(exc),
        )
    finally:
        app.state.media_download_tasks.pop(download_id, None)

@router.post("/system/media-generation/downloads", response_model=MediaModelDownloadStatusRead)
async def start_media_model_download(request: Request, payload: MediaModelDownloadRequest) -> MediaModelDownloadStatusRead:
    download_id = str(uuid.uuid4())
    now = utc_now_iso()
    status_payload = {
        "id": download_id,
        "target": payload.target,
        "status": "queued",
        "progress": 0.0,
        "repo_id": payload.repo_id,
        "revision": payload.revision,
        "destination_path": "",
        "downloaded_path": None,
        "applied_to_settings": False,
        "message": "Model download queued.",
        "error_text": None,
        "created_at": now,
        "updated_at": now,
    }
    _put_media_download_status(request.app, download_id, status_payload)
    request.app.state.media_download_tasks[download_id] = asyncio.create_task(
        _run_media_model_download(request.app, download_id, payload.model_dump()),
        name=f"media-model-download-{download_id[:8]}",
    )
    return MediaModelDownloadStatusRead.model_validate(_serialize_media_download(status_payload))

@router.get("/system/media-generation/downloads/{download_id}", response_model=MediaModelDownloadStatusRead)
def get_media_model_download(request: Request, download_id: str) -> MediaModelDownloadStatusRead:
    status = request.app.state.media_downloads.get(download_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Media model download not found.")
    return MediaModelDownloadStatusRead.model_validate(_serialize_media_download(status))

@router.get("/projects", response_model=list[ProjectListItem])
def list_projects(request: Request, scope: Literal["active", "archived", "all"] = "active") -> list[ProjectListItem]:
    return [ProjectListItem.model_validate(item) for item in request.app.state.repository.list_projects(scope)]

@router.post("/projects", response_model=ProjectRead)
def create_project(request: Request, payload: ProjectCreateRequest) -> ProjectRead:
    detail = request.app.state.repository.create_project(payload.model_dump())
    return ProjectRead.model_validate(_serialize_project(detail, request.app.state.hardware_profile))

@router.patch("/projects/{project_id}", response_model=ProjectRead)
def update_project(request: Request, project_id: str, payload: ProjectUpdateRequest) -> ProjectRead:
    existing = _load_project_or_404(request.app.state.repository, project_id)
    _ensure_project_editable(existing)
    detail = request.app.state.repository.update_project(project_id, payload.model_dump(exclude_none=True))
    if detail is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return ProjectRead.model_validate(_serialize_project(detail, request.app.state.hardware_profile))

@router.post("/projects/{project_id}/archive", response_model=ProjectRead)
def archive_project(request: Request, project_id: str) -> ProjectRead:
    detail = request.app.state.repository.archive_project(project_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return ProjectRead.model_validate(_serialize_project(detail, request.app.state.hardware_profile))

@router.post("/projects/{project_id}/restore", response_model=ProjectRead)
def restore_project(request: Request, project_id: str) -> ProjectRead:
    detail = request.app.state.repository.restore_project(project_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return ProjectRead.model_validate(_serialize_project(detail, request.app.state.hardware_profile))

@router.delete("/projects/{project_id}", status_code=204)
def delete_project(request: Request, project_id: str) -> Response:
    deleted = request.app.state.repository.delete_project(project_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    if deleted is False:
        raise HTTPException(status_code=409, detail="Archive the project before permanently deleting it.")
    return Response(status_code=204)

@router.get("/projects/{project_id}", response_model=ProjectRead)
def get_project(request: Request, project_id: str) -> ProjectRead:
    detail = _load_project_or_404(request.app.state.repository, project_id)
    return ProjectRead.model_validate(_serialize_project(detail, request.app.state.hardware_profile))

@router.get("/projects/{project_id}/model-settings", response_model=ProjectModelSettingsOverrideRead)
def get_project_model_settings(request: Request, project_id: str) -> ProjectModelSettingsOverrideRead:
    override = request.app.state.repository.get_project_model_settings_override(project_id)
    if override is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return ProjectModelSettingsOverrideRead.model_validate(override)

@router.patch("/projects/{project_id}/model-settings", response_model=ProjectModelSettingsOverrideRead)
def update_project_model_settings(
    request: Request,
    project_id: str,
    payload: ProjectModelSettingsOverrideUpdateRequest,
) -> ProjectModelSettingsOverrideRead:
    existing = _load_project_or_404(request.app.state.repository, project_id)
    _ensure_project_editable(existing)
    override = request.app.state.repository.update_project_model_settings_override(project_id, payload.model_dump())
    if override is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return ProjectModelSettingsOverrideRead.model_validate(override)

@router.get("/projects/{project_id}/characters", response_model=list[CharacterRead])
def list_project_characters(request: Request, project_id: str) -> list[CharacterRead]:
    _load_project_or_404(request.app.state.repository, project_id)
    chars = request.app.state.repository.list_project_characters(project_id)
    return [CharacterRead.model_validate(_serialize_character(char)) for char in chars]

@router.post("/projects/{project_id}/characters", response_model=CharacterRead)
def create_project_character(request: Request, project_id: str, payload: CharacterCreateRequest) -> CharacterRead:
    detail = _load_project_or_404(request.app.state.repository, project_id)
    _ensure_project_editable(detail)
    char = request.app.state.repository.create_project_character(project_id, payload.model_dump())
    if char is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return CharacterRead.model_validate(_serialize_character(char))

@router.patch("/projects/{project_id}/characters/{character_id}", response_model=CharacterRead)
def update_project_character(request: Request, project_id: str, character_id: str, payload: CharacterUpdateRequest) -> CharacterRead:
    detail = _load_project_or_404(request.app.state.repository, project_id)
    _ensure_project_editable(detail)
    char = request.app.state.repository.update_project_character(character_id, payload.model_dump(exclude_none=True))
    if char is None:
        raise HTTPException(status_code=404, detail="Character not found.")
    return CharacterRead.model_validate(_serialize_character(char))

@router.post("/projects/{project_id}/characters/{character_id}/send-to-cards")
def send_movie_character_to_cards(request: Request, project_id: str, character_id: str) -> dict:
    _load_project_or_404(request.app.state.repository, project_id)
    char = request.app.state.repository.get_project_character(character_id)
    if char is None or char.get("project_id") != project_id:
        raise HTTPException(status_code=404, detail="Character not found.")

    from app.cards.config import get_settings as get_cards_settings
    from app.cards.database import Database as CardsDatabase
    from app.cards.services.shared_vault import SharedVaultService

    cards_settings = get_cards_settings()
    cards_database = CardsDatabase(cards_settings.database_path)
    cards_database.initialize()
    vault = SharedVaultService(cards_database)
    vault_character = vault.upsert_character(
        {
            "source_module": "movie",
            "source_id": character_id,
            "name": char.get("name", "Character"),
            "description": char.get("role_summary", ""),
            "personality": "",
            "role_summary": char.get("role_summary", ""),
            "prompt_tags": [
                item.strip()
                for item in str(char.get("prompt_tags") or "").split(",")
                if item.strip()
            ],
            "avatar_path": char.get("portrait_image_url"),
            "source_metadata": {"movie_project_id": project_id},
        }
    )
    return {"vault_character": vault_character}

@router.delete("/projects/{project_id}/characters/{character_id}", status_code=204)
def delete_project_character(request: Request, project_id: str, character_id: str) -> Response:
    detail = _load_project_or_404(request.app.state.repository, project_id)
    _ensure_project_editable(detail)
    deleted = request.app.state.repository.delete_project_character(character_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Character not found.")
    return Response(status_code=204)

@router.post("/projects/{project_id}/characters/generate", response_model=list[CharacterRead])
def generate_project_characters(request: Request, project_id: str, payload: CharacterGenerateRequest) -> list[CharacterRead]:
    detail = _load_project_or_404(request.app.state.repository, project_id)
    _ensure_project_editable(detail)
    if not payload.overwrite_existing and detail.get("characters"):
        return [CharacterRead.model_validate(char) for char in detail["characters"]]
    characters = request.app.state.generation_service.generate_characters(
        detail,
        request.app.state.repository.get_resolved_model_settings(project_id),
    )
    saved = request.app.state.repository.replace_project_characters(project_id, characters)
    return [CharacterRead.model_validate(_serialize_character(char)) for char in saved]

@router.post("/projects/{project_id}/characters/{character_id}/images/generate", response_model=JobRead)
async def generate_character_image(request: Request, project_id: str, character_id: str, payload: CharacterImageGenerateRequest) -> JobRead:
    detail = _load_project_or_404(request.app.state.repository, project_id)
    _ensure_project_editable(detail)
    char = request.app.state.repository.get_project_character(character_id)
    if char is None:
        raise HTTPException(status_code=404, detail="Character not found.")
        
    job = request.app.state.repository.create_job(
        project_id=project_id,
        job_type=JobType.character_image_generation,
        payload={
            "character_id": character_id,
            "shot_type": payload.shot_type
        }
    )
    asyncio.create_task(request.app.state.job_manager.enqueue(job["id"]))
    return JobRead.model_validate(_serialize_job(job))

@router.get("/projects/{project_id}/beat-board", response_model=BeatBoardRead)
def get_beat_board(request: Request, project_id: str) -> BeatBoardRead:
    beat_board = request.app.state.repository.get_beat_board(project_id)
    if beat_board is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return BeatBoardRead.model_validate(beat_board)

@router.post("/projects/{project_id}/beat-board/generate", response_model=BeatBoardRead)
def generate_beat_board(request: Request, project_id: str, payload: BeatBoardGenerateRequest) -> BeatBoardRead:
    detail = _load_project_or_404(request.app.state.repository, project_id)
    _ensure_v2_project(detail)
    _ensure_project_editable(detail)
    if not payload.overwrite_existing and detail.get("beat_board", {}).get("beats"):
        return BeatBoardRead.model_validate(detail["beat_board"])
    beats = request.app.state.generation_service.generate_beat_board(
        detail,
        request.app.state.repository.get_resolved_model_settings(project_id),
    )
    saved = request.app.state.repository.replace_story_beats(project_id, beats, status="generated")
    return BeatBoardRead.model_validate(
        {
            "project_id": project_id,
            "status": "generated" if saved else "empty",
            "beats": saved,
            "updated_at": _load_project_or_404(request.app.state.repository, project_id)["updated_at"],
        }
    )

@router.post("/projects/{project_id}/beat-board/reorder", response_model=BeatBoardRead)
def reorder_beat_board(request: Request, project_id: str, payload: BeatBoardReorderRequest) -> BeatBoardRead:
    detail = _load_project_or_404(request.app.state.repository, project_id)
    _ensure_v2_project(detail)
    _ensure_project_editable(detail)
    beats = request.app.state.repository.reorder_story_beats(project_id, [item.model_dump() for item in payload.beats])
    refreshed = _load_project_or_404(request.app.state.repository, project_id)
    return BeatBoardRead.model_validate(
        {
            "project_id": project_id,
            "status": refreshed.get("beat_board_status", "empty"),
            "beats": beats,
            "updated_at": refreshed["updated_at"],
        }
    )

@router.post("/projects/{project_id}/beat-board/apply-to-scenario", response_model=ProjectRead)
def apply_beat_board_to_scenario(request: Request, project_id: str) -> ProjectRead:
    detail = _load_project_or_404(request.app.state.repository, project_id)
    _ensure_v2_project(detail)
    _ensure_project_editable(detail)
    if not detail.get("beat_board", {}).get("beats"):
        raise HTTPException(status_code=400, detail="Generate or add beats before applying the beat board to the scenario.")
    updated = request.app.state.repository.apply_beat_board_to_scenario(project_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    refreshed = _load_project_or_404(request.app.state.repository, project_id)
    return ProjectRead.model_validate(_serialize_project(refreshed, request.app.state.hardware_profile))

@router.post("/projects/{project_id}/beats", response_model=dict)
def create_beat(request: Request, project_id: str, payload: CreateBeatRequest) -> dict:
    detail = _load_project_or_404(request.app.state.repository, project_id)
    _ensure_v2_project(detail)
    _ensure_project_editable(detail)
    beat = request.app.state.repository.create_story_beat(project_id, payload.model_dump())
    if beat is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return beat

@router.patch("/beats/{beat_id}", response_model=dict)
def update_beat(request: Request, beat_id: str, payload: UpdateBeatRequest) -> dict:
    beat = request.app.state.repository.get_story_beat(beat_id)
    if beat is None:
        raise HTTPException(status_code=404, detail="Beat not found.")
    project = _load_project_or_404(request.app.state.repository, beat["project_id"])
    _ensure_project_editable(project)
    updated = request.app.state.repository.update_story_beat(beat_id, payload.model_dump(exclude_none=True))
    if updated is None:
        raise HTTPException(status_code=404, detail="Beat not found.")
    return updated

@router.delete("/beats/{beat_id}", status_code=204)
def delete_beat(request: Request, beat_id: str) -> Response:
    beat = request.app.state.repository.get_story_beat(beat_id)
    if beat is None:
        raise HTTPException(status_code=404, detail="Beat not found.")
    project = _load_project_or_404(request.app.state.repository, beat["project_id"])
    _ensure_project_editable(project)
    deleted = request.app.state.repository.delete_story_beat(beat_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Beat not found.")
    return Response(status_code=204)

@router.post("/projects/{project_id}/scenes/generate", response_model=ProjectRead)
def generate_scenes(request: Request, project_id: str, payload: GenerateScenesRequest) -> ProjectRead:
    detail = _load_project_or_404(request.app.state.repository, project_id)
    _ensure_v2_project(detail)
    _ensure_project_editable(detail)
    source_text = detail.get("scenario_text", "")
    if payload.source == "beat_board":
        beats = detail.get("beat_board", {}).get("beats", [])
        if not beats:
            raise HTTPException(status_code=400, detail="Generate or add beat-board beats before generating scenes from the beat board.")
        source_text = request.app.state.generation_service.scenario_text_from_beats(detail, beats)
    scenes = request.app.state.generation_service.generate_scenes(
        detail,
        request.app.state.repository.get_resolved_model_settings(project_id),
        source_text=source_text,
    )
    if payload.replace_existing:
        request.app.state.repository.replace_story_scenes(project_id, scenes)
    detail = _load_project_or_404(request.app.state.repository, project_id)
    return ProjectRead.model_validate(_serialize_project(detail, request.app.state.hardware_profile))

@router.post("/projects/{project_id}/scene-image-prompts/generate", response_model=ProjectRead)
def generate_scene_image_prompts(
    request: Request,
    project_id: str,
    payload: GenerateSceneImagePromptsRequest,
) -> ProjectRead:
    detail = _load_project_or_404(request.app.state.repository, project_id)
    _ensure_v2_project(detail)
    _ensure_project_editable(detail)
    if not detail["scenes"]:
        raise HTTPException(status_code=400, detail="Generate scenes before creating scene image prompts.")

    style_anchor_text = detail["style_anchor_text"] or request.app.state.generation_service.generate_style_anchor(
        detail,
        detail["scenes"],
    )
    if not detail["style_anchor_text"]:
        request.app.state.repository.set_project_style_anchor(project_id, style_anchor_text)

    selected_scene_ids = set(payload.scene_ids or [scene["id"] for scene in detail["scenes"]])
    selected_scenes = [scene for scene in detail["scenes"] if scene["id"] in selected_scene_ids]
    prompts = request.app.state.generation_service.generate_scene_image_prompts(
        detail,
        selected_scenes,
        style_anchor_text,
        request.app.state.repository.get_resolved_model_settings(project_id),
    )
    by_scene_id = {item["scene_id"]: item for item in prompts}
    for scene in selected_scenes:
        bundle = by_scene_id.get(scene["id"])
        if bundle is None:
            continue
        if payload.overwrite_existing or not scene["first_image_prompt_text"].strip():
            request.app.state.repository.update_story_scene(
                scene["id"],
                {"first_image_prompt_text": bundle["first_image_prompt_text"]},
            )

    refreshed = _load_project_or_404(request.app.state.repository, project_id)
    return ProjectRead.model_validate(_serialize_project(refreshed, request.app.state.hardware_profile))

@router.post("/scenes/{scene_id}/first-image", response_model=dict)
def upload_scene_first_image(request: Request, scene_id: str, file: UploadFile = File(...)) -> dict:
    scene = _load_story_scene_or_404(request.app.state.repository, scene_id)
    project = _load_project_or_404(request.app.state.repository, scene["project_id"])
    _ensure_v2_project(project)
    _ensure_project_editable(project)
    project_root = request.app.state.repository.ensure_project_assets(scene["project_id"])
    safe_name = _slugify_filename(file.filename or f"scene-{scene['order']:02d}-first-image")
    relative_path = f"scene-images/uploads/scene-{scene['order']:02d}-{safe_name}"
    target_path = project_root / relative_path
    with target_path.open("wb") as target:
        shutil.copyfileobj(file.file, target)
    size_bytes = target_path.stat().st_size
    updated = request.app.state.repository.set_story_scene_first_image_asset(
        scene_id,
        relative_path=relative_path,
        original_filename=file.filename or safe_name,
        mime_type=file.content_type,
        size_bytes=size_bytes,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Scene not found after upload.")
    return _serialize_scene(updated)

@router.post("/scenes/{scene_id}/images/generate", response_model=JobRead)
async def generate_scene_images(request: Request, scene_id: str, payload: SceneImageGenerateRequest) -> JobRead:
    scene = _load_story_scene_or_404(request.app.state.repository, scene_id)
    project = _load_project_or_404(request.app.state.repository, scene["project_id"])
    _ensure_v2_project(project)
    _ensure_project_editable(project)
    if not scene["first_image_prompt_text"].strip():
        raise HTTPException(
            status_code=400,
            detail="Generate or enter a first-image prompt before starting image generation.",
        )
    request.app.state.repository.set_scene_image_generation_status(scene_id, "queued")
    job = request.app.state.repository.create_job(
        project_id=project["id"],
        job_type=JobType.image_generation,
        payload={"scene_id": scene_id, "request": payload.model_dump()},
        scene_id=scene_id,
    )
    await request.app.state.job_manager.enqueue(job["id"])
    return JobRead.model_validate(_serialize_job(job))

@router.post("/scenes/{scene_id}/images/{asset_id}/approve", response_model=dict)
def approve_scene_image(request: Request, scene_id: str, asset_id: str) -> dict:
    scene = _load_story_scene_or_404(request.app.state.repository, scene_id)
    project = _load_project_or_404(request.app.state.repository, scene["project_id"])
    _ensure_v2_project(project)
    _ensure_project_editable(project)
    updated = request.app.state.repository.approve_scene_image_variant(scene_id, asset_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Generated scene image not found.")
    return _serialize_scene(updated)

@router.post("/projects/{project_id}/sequences/generate", response_model=ProjectRead)
def generate_sequences(request: Request, project_id: str, payload: GenerateSequencesRequest) -> ProjectRead:
    detail = _load_project_or_404(request.app.state.repository, project_id)
    _ensure_v2_project(detail)
    _ensure_project_editable(detail)
    if not detail["scenes"]:
        raise HTTPException(status_code=400, detail="Generate scenes before creating sequences.")

    selected_scene_ids = set(payload.scene_ids or [scene["id"] for scene in detail["scenes"]])
    for scene in detail["scenes"]:
        if scene["id"] not in selected_scene_ids:
            continue
        if not payload.overwrite_existing and scene["sequences"]:
            continue
        sequences = request.app.state.generation_service.generate_sequences(
            detail,
            scene,
            request.app.state.repository.get_resolved_model_settings(project_id),
        )
        request.app.state.repository.replace_sequences_for_scene(scene["id"], sequences)

    refreshed = _load_project_or_404(request.app.state.repository, project_id)
    return ProjectRead.model_validate(_serialize_project(refreshed, request.app.state.hardware_profile))

@router.post("/projects/{project_id}/wan-prompts/generate", response_model=ProjectRead)
def generate_wan_prompts(request: Request, project_id: str, payload: GenerateWanPromptsRequest) -> ProjectRead:
    detail = _load_project_or_404(request.app.state.repository, project_id)
    _ensure_v2_project(detail)
    _ensure_project_editable(detail)
    if not detail["scenes"]:
        raise HTTPException(status_code=400, detail="Generate scenes before creating Wan prompts.")
    if payload.scene_ids and payload.sequence_ids:
        raise HTTPException(
            status_code=400,
            detail="Provide either scene_ids or sequence_ids when generating Wan prompts, not both.",
        )

    style_anchor_text = detail["style_anchor_text"] or request.app.state.generation_service.generate_style_anchor(
        detail,
        detail["scenes"],
    )
    if not detail["style_anchor_text"]:
        request.app.state.repository.set_project_style_anchor(project_id, style_anchor_text)

    if payload.sequence_ids:
        selected_sequence_ids = set(payload.sequence_ids)
        selected_scenes = []
        for scene in detail["scenes"]:
            selected_sequences = [
                sequence for sequence in scene["sequences"] if sequence["id"] in selected_sequence_ids
            ]
            if selected_sequences:
                selected_scenes.append({**scene, "sequences": selected_sequences})
    else:
        selected_scene_ids = set(payload.scene_ids or [scene["id"] for scene in detail["scenes"]])
        selected_scenes = [scene for scene in detail["scenes"] if scene["id"] in selected_scene_ids]
    if not selected_scenes:
        detail_text = (
            "Select at least one valid sequence before creating Wan prompts."
            if payload.sequence_ids
            else "Select at least one valid scene before creating Wan prompts."
        )
        raise HTTPException(status_code=400, detail=detail_text)
    missing_sequence_scenes = [scene for scene in selected_scenes if not scene["sequences"]]
    if missing_sequence_scenes:
        scene_labels = ", ".join(
            f"Scene {scene['order']:02d}" for scene in missing_sequence_scenes
        )
        raise HTTPException(
            status_code=400,
            detail=f"Generate sequences before creating Wan prompts for {scene_labels}.",
        )
    prompt_bundles = request.app.state.generation_service.generate_wan_prompts(
        detail,
        selected_scenes,
        style_anchor_text,
        request.app.state.repository.get_resolved_model_settings(project_id),
    )
    by_sequence_id = {item["sequence_id"]: item for item in prompt_bundles}
    for scene in selected_scenes:
        for sequence in scene["sequences"]:
            bundle = by_sequence_id.get(sequence["id"])
            if bundle is None:
                continue
            updates: dict[str, Any] = {}
            if payload.overwrite_existing or not sequence["camera_direction"].strip():
                updates["camera_direction"] = bundle["camera_direction"]
            if payload.overwrite_existing or not sequence["action_direction"].strip():
                updates["action_direction"] = bundle["action_direction"]
            if payload.overwrite_existing or not sequence["wan_prompt_text"].strip():
                updates["wan_prompt_text"] = bundle["wan_prompt_text"]
            if updates:
                request.app.state.repository.update_sequence(sequence["id"], updates)

    refreshed = _load_project_or_404(request.app.state.repository, project_id)
    return ProjectRead.model_validate(_serialize_project(refreshed, request.app.state.hardware_profile))

@router.patch("/scenes/{scene_id}", response_model=dict)
def update_scene(request: Request, scene_id: str, payload: UpdateSceneRequest) -> dict:
    existing = _load_story_scene_or_404(request.app.state.repository, scene_id)
    project = _load_project_or_404(request.app.state.repository, existing["project_id"])
    _ensure_project_editable(project)
    scene = request.app.state.repository.update_story_scene(scene_id, payload.model_dump(exclude_none=True))
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found.")
    return _serialize_scene(scene)

@router.patch("/sequences/{sequence_id}", response_model=dict)
def update_sequence(request: Request, sequence_id: str, payload: UpdateSequenceRequest) -> dict:
    existing = _load_sequence_or_404(request.app.state.repository, sequence_id)
    project = _load_project_or_404(request.app.state.repository, existing["project_id"])
    _ensure_project_editable(project)
    sequence = request.app.state.repository.update_sequence(sequence_id, payload.model_dump(exclude_none=True))
    if sequence is None:
        raise HTTPException(status_code=404, detail="Sequence not found.")
    return _serialize_sequence(sequence)

@router.patch("/scenes/{scene_id}/sequences/batch", response_model=list[dict])
def batch_update_sequences(request: Request, scene_id: str, payload: SequenceBatchUpdateRequest) -> list[dict]:
    scene = _load_story_scene_or_404(request.app.state.repository, scene_id)
    project = _load_project_or_404(request.app.state.repository, scene["project_id"])
    _ensure_project_editable(project)

    def apply_text_mode(current_value: str, incoming_value: str, mode: str) -> str:
        if mode == "append":
            return f"{current_value.rstrip()} {incoming_value.strip()}".strip()
        if mode == "fill_empty":
            return current_value if current_value.strip() else incoming_value.strip()
        return incoming_value.strip()

    updated_sequences: list[dict] = []
    for sequence in scene["sequences"]:
        if sequence["id"] not in set(payload.sequence_ids):
            continue
        next_updates: dict[str, Any] = {}
        if payload.camera_direction is not None and payload.camera_direction_mode is not None:
            next_updates["camera_direction"] = apply_text_mode(
                sequence.get("camera_direction", ""),
                payload.camera_direction,
                payload.camera_direction_mode.value,
            )
        if payload.action_direction is not None and payload.action_direction_mode is not None:
            next_updates["action_direction"] = apply_text_mode(
                sequence.get("action_direction", ""),
                payload.action_direction,
                payload.action_direction_mode.value,
            )
        if payload.include_in_assembly is not None:
            next_updates["include_in_assembly"] = payload.include_in_assembly
        if next_updates:
            updated = request.app.state.repository.update_sequence(sequence["id"], next_updates)
            if updated is not None:
                updated_sequences.append(updated)
    if not updated_sequences:
        return []
    return [_serialize_sequence(sequence) for sequence in updated_sequences]

@router.patch("/sequences/{sequence_id}/wan-prompt", response_model=dict)
def update_sequence_wan_prompt(request: Request, sequence_id: str, payload: UpdateSequenceWanPromptRequest) -> dict:
    existing = _load_sequence_or_404(request.app.state.repository, sequence_id)
    project = _load_project_or_404(request.app.state.repository, existing["project_id"])
    _ensure_project_editable(project)
    sequence = request.app.state.repository.update_sequence_wan_prompt(sequence_id, payload.wan_prompt_text)
    if sequence is None:
        raise HTTPException(status_code=404, detail="Sequence not found.")
    return _serialize_sequence(sequence)

@router.post("/sequences/{sequence_id}/video", response_model=dict)
def upload_sequence_video(request: Request, sequence_id: str, file: UploadFile = File(...)) -> dict:
    sequence = _load_sequence_or_404(request.app.state.repository, sequence_id)
    project = _load_project_or_404(request.app.state.repository, sequence["project_id"])
    _ensure_v2_project(project)
    _ensure_project_editable(project)
    scene = _load_story_scene_or_404(request.app.state.repository, sequence["scene_id"])
    project_root = request.app.state.repository.ensure_project_assets(sequence["project_id"])
    safe_name = _slugify_filename(file.filename or f"sequence-{sequence['absolute_order']:03d}.mp4")
    relative_path = f"sequence-videos/uploads/sequence-{sequence['absolute_order']:03d}-{safe_name}"
    target_path = project_root / relative_path
    with target_path.open("wb") as target:
        shutil.copyfileobj(file.file, target)
    input_asset = _resolve_sequence_input_asset(scene, sequence_id)
    stamp = Path(target_path).stem
    last_frame_path = project_root / "sequence-frames" / f"{stamp}-last.png"
    request.app.state.video_generation_service.extract_last_frame(target_path, last_frame_path)
    size_bytes = target_path.stat().st_size
    updated = request.app.state.repository.set_uploaded_sequence_video_asset(
        sequence_id,
        relative_path=relative_path,
        original_filename=file.filename or safe_name,
        mime_type=file.content_type,
        size_bytes=size_bytes,
        input_frame=input_asset,
        last_frame={
            "relative_path": str(last_frame_path.relative_to(project_root)).replace("\\", "/"),
            "original_filename": last_frame_path.name,
            "mime_type": "image/png",
            "size_bytes": last_frame_path.stat().st_size,
            "created_at": utc_now_iso(),
        },
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Sequence not found after upload.")
    return _serialize_sequence(updated)

@router.post("/sequences/{sequence_id}/video/generate", response_model=JobRead)
async def generate_sequence_video(request: Request, sequence_id: str, payload: SequenceVideoGenerateRequest) -> JobRead:
    sequence = _load_sequence_or_404(request.app.state.repository, sequence_id)
    project = _load_project_or_404(request.app.state.repository, sequence["project_id"])
    _ensure_v2_project(project)
    _ensure_project_editable(project)
    if not sequence["wan_prompt_text"].strip():
        raise HTTPException(status_code=400, detail="Generate or enter a Wan prompt before starting video generation.")
    scene = _load_story_scene_or_404(request.app.state.repository, sequence["scene_id"])
    if _resolve_sequence_input_asset(scene, sequence_id) is None:
        raise HTTPException(
            status_code=400,
            detail="This sequence is missing its required input image. Approve a scene image or regenerate the upstream sequence first.",
        )
    job = request.app.state.repository.create_job(
        project_id=project["id"],
        job_type=JobType.video_generation,
        payload={
            "mode": "single",
            "scene_id": scene["id"],
            "sequence_id": sequence_id,
            "request": payload.model_dump(),
        },
        scene_id=scene["id"],
    )
    await request.app.state.job_manager.enqueue(job["id"])
    return JobRead.model_validate(_serialize_job(job))

@router.post("/scenes/{scene_id}/video/generate-chain", response_model=JobRead)
async def generate_scene_video_chain(request: Request, scene_id: str, payload: SceneVideoChainGenerateRequest) -> JobRead:
    scene = _load_story_scene_or_404(request.app.state.repository, scene_id)
    project = _load_project_or_404(request.app.state.repository, scene["project_id"])
    _ensure_v2_project(project)
    _ensure_project_editable(project)
    if not scene.get("sequences"):
        raise HTTPException(status_code=400, detail="Generate sequences before starting a scene video chain.")
    if not scene.get("first_image_asset"):
        raise HTTPException(
            status_code=400,
            detail="Approve or upload a scene reference image before generating the scene video chain.",
        )
    missing_orders = [sequence["order"] for sequence in scene["sequences"] if not sequence["wan_prompt_text"].strip()]
    if missing_orders:
        joined = ", ".join(str(order) for order in missing_orders)
        raise HTTPException(
            status_code=400,
            detail=f"Generate or enter Wan prompts for every sequence before running the scene chain. Missing order(s): {joined}.",
        )
    job = request.app.state.repository.create_job(
        project_id=project["id"],
        job_type=JobType.video_generation,
        payload={
            "mode": "chain",
            "scene_id": scene_id,
            "request": payload.model_dump(),
        },
        scene_id=scene_id,
    )
    await request.app.state.job_manager.enqueue(job["id"])
    return JobRead.model_validate(_serialize_job(job))

@router.post("/sequences/{sequence_id}/videos/{asset_id}/approve", response_model=dict)
def approve_sequence_video(request: Request, sequence_id: str, asset_id: str) -> dict:
    sequence = _load_sequence_or_404(request.app.state.repository, sequence_id)
    project = _load_project_or_404(request.app.state.repository, sequence["project_id"])
    _ensure_v2_project(project)
    _ensure_project_editable(project)
    updated = request.app.state.repository.approve_sequence_video_variant(sequence_id, asset_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Generated sequence video not found.")
    return _serialize_sequence(updated)

@router.patch("/sequences/{sequence_id}/assembly", response_model=dict)
def update_sequence_assembly(request: Request, sequence_id: str, payload: UpdateAssemblyRequest) -> dict:
    existing = _load_sequence_or_404(request.app.state.repository, sequence_id)
    project = _load_project_or_404(request.app.state.repository, existing["project_id"])
    _ensure_project_editable(project)
    sequence = request.app.state.repository.update_sequence(sequence_id, payload.model_dump(exclude_none=True))
    if sequence is None:
        raise HTTPException(status_code=404, detail="Sequence not found.")
    return _serialize_sequence(sequence)

@router.post("/scenes/{scene_id}/continuity-review", response_model=JobRead)
async def start_continuity_review(request: Request, scene_id: str) -> JobRead:
    scene = _load_story_scene_or_404(request.app.state.repository, scene_id)
    project = _load_project_or_404(request.app.state.repository, scene["project_id"])
    _ensure_project_editable(project)
    job = request.app.state.repository.create_job(
        project_id=project["id"],
        job_type=JobType.continuity_review,
        payload={"scene_id": scene_id},
        scene_id=scene_id,
    )
    await request.app.state.job_manager.enqueue(job["id"])
    return JobRead.model_validate(_serialize_job(job))

@router.get("/scenes/{scene_id}/continuity-review", response_model=ContinuityReviewRead)
def get_continuity_review(request: Request, scene_id: str) -> ContinuityReviewRead:
    _load_story_scene_or_404(request.app.state.repository, scene_id)
    review = request.app.state.repository.get_continuity_review(scene_id)
    if review is None:
        raise HTTPException(status_code=404, detail="No continuity review exists for this scene yet.")
    return ContinuityReviewRead.model_validate(review)

@router.post("/projects/{project_id}/upgrade-to-v2", response_model=ProjectRead)
def upgrade_project_to_v2(request: Request, project_id: str) -> ProjectRead:
    detail = _load_project_or_404(request.app.state.repository, project_id)
    _ensure_project_editable(detail)
    if detail["workflow_version"] >= 2:
        return ProjectRead.model_validate(_serialize_project(detail, request.app.state.hardware_profile))
    upgraded = request.app.state.repository.duplicate_project_to_v2(project_id)
    if upgraded is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    if upgraded["scenes"]:
        style_anchor_text = upgraded["style_anchor_text"] or request.app.state.generation_service.generate_style_anchor(
            upgraded,
            upgraded["scenes"],
        )
        if not upgraded["style_anchor_text"]:
            request.app.state.repository.set_project_style_anchor(upgraded["id"], style_anchor_text)
        prompts = request.app.state.generation_service.generate_scene_image_prompts(
            upgraded,
            upgraded["scenes"],
            style_anchor_text,
            request.app.state.repository.get_resolved_model_settings(upgraded["id"]),
        )
        by_scene_id = {item["scene_id"]: item for item in prompts}
        for scene in upgraded["scenes"]:
            bundle = by_scene_id.get(scene["id"])
            if bundle is not None:
                request.app.state.repository.update_story_scene(
                    scene["id"],
                    {"first_image_prompt_text": bundle["first_image_prompt_text"]},
                )
        upgraded = _load_project_or_404(request.app.state.repository, upgraded["id"])
    return ProjectRead.model_validate(_serialize_project(upgraded, request.app.state.hardware_profile))

@router.post("/projects/{project_id}/scenario-assistant", response_model=ScenarioAssistantResponse)
def run_scenario_assistant(request: Request, project_id: str, payload: ScenarioAssistantRequest) -> ScenarioAssistantResponse:
    detail = _load_project_or_404(request.app.state.repository, project_id)
    _ensure_project_editable(detail)
    result = request.app.state.scenario_assistant.assist(
        project=detail,
        focus=payload.focus.strip().lower(),
        instruction=payload.instruction.strip(),
        rewrite_scenario=payload.rewrite_scenario,
        max_suggestions=payload.max_suggestions,
        model_settings=request.app.state.repository.get_resolved_model_settings(project_id),
    )
    return ScenarioAssistantResponse.model_validate(result)

@router.get("/projects/{project_id}/prompt-package", response_model=PromptPackageRead)
def get_prompt_package(request: Request, project_id: str) -> PromptPackageRead:
    detail = _load_project_or_404(request.app.state.repository, project_id)
    serialized = _serialize_project(detail, request.app.state.hardware_profile)
    package = build_prompt_package(serialized)
    return PromptPackageRead.model_validate(package)

@router.get("/projects/{project_id}/prompt-package.json")
def download_prompt_package_json(request: Request, project_id: str) -> JSONResponse:
    detail = _load_project_or_404(request.app.state.repository, project_id)
    serialized = _serialize_project(detail, request.app.state.hardware_profile)
    package = build_prompt_package(serialized)
    response = JSONResponse(content=package)
    response.headers["Content-Disposition"] = (
        f'attachment; filename="{_slugify_filename(serialized["name"])}-prompt-package.json"'
    )
    return response

@router.get("/projects/{project_id}/prompt-package.md")
def download_prompt_package_markdown(request: Request, project_id: str) -> PlainTextResponse:
    detail = _load_project_or_404(request.app.state.repository, project_id)
    serialized = _serialize_project(detail, request.app.state.hardware_profile)
    package = build_prompt_package(serialized)
    response = PlainTextResponse(render_prompt_package_markdown(package), media_type="text/markdown")
    response.headers["Content-Disposition"] = (
        f'attachment; filename="{_slugify_filename(serialized["name"])}-prompt-package.md"'
    )
    return response

@router.get("/scenes/{scene_id}/comfy-extract.json")
def download_comfy_scene_extract(request: Request, scene_id: str, start_order: int = 1) -> JSONResponse:
    scene = _load_story_scene_or_404(request.app.state.repository, scene_id)
    project = request.app.state.repository.get_project_record(scene["project_id"])
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    _ensure_v2_project(project)

    if not scene["first_image_prompt_text"].strip():
        raise HTTPException(
            status_code=400,
            detail="Generate or enter a first-image prompt before exporting a Comfy extract.",
        )

    selected_sequences = _resolve_comfy_extract_window(scene, start_order)
    missing_orders = [sequence["order"] for sequence in selected_sequences if not sequence["wan_prompt_text"].strip()]
    if missing_orders:
        joined_orders = ", ".join(str(order) for order in missing_orders)
        raise HTTPException(
            status_code=400,
            detail=(
                "Generate or enter Wan prompts for every sequence in the selected block before exporting. "
                f"Missing order(s): {joined_orders}."
            ),
        )

    payload = _build_comfy_scene_extract(project, scene, selected_sequences)
    response = JSONResponse(content=payload)
    response.headers["Content-Disposition"] = (
        "attachment; filename="
        f'"{_slugify_filename(project["name"])}-scene-{scene["order"]:02d}-seq-{start_order}-{start_order + 2}-comfy.json"'
    )
    return response

@router.post("/projects/{project_id}/assembly/export", response_model=JobRead)
async def export_project(request: Request, project_id: str, payload: ExportRequest) -> JobRead:
    detail = _load_project_or_404(request.app.state.repository, project_id)
    _ensure_v2_project(detail)
    _ensure_project_editable(detail)
    job = request.app.state.repository.create_job(
        project_id=project_id,
        job_type=JobType.export,
        payload=payload.model_dump(exclude_none=True),
    )
    await request.app.state.job_manager.enqueue(job["id"])
    return JobRead.model_validate(_serialize_job(job))

@router.get("/jobs/{job_id}", response_model=JobRead)
def get_job(request: Request, job_id: str) -> JobRead:
    job = request.app.state.repository.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return JobRead.model_validate(_serialize_job(job))

@router.post("/projects/{project_id}/opening-image-prompt/generate")
def legacy_generate_opening_image_prompt(request: Request, project_id: str) -> None:
    raise _legacy_opening_image_error()

@router.post("/projects/{project_id}/opening-image")
def legacy_upload_opening_image(request: Request, project_id: str) -> None:
    raise _legacy_opening_image_error()

@router.patch("/scenes/{scene_id}/prompt")
def legacy_update_prompt(request: Request, scene_id: str) -> None:
    raise _legacy_video_generation_error()

@router.post("/projects/{project_id}/renders")
def legacy_render_project(request: Request, project_id: str) -> None:
    raise _legacy_video_generation_error()

@router.post("/renders/{job_id}/cancel")
def legacy_cancel_render(request: Request, job_id: str) -> None:
    raise _legacy_video_generation_error()

@router.post("/projects/{project_id}/exports")
def legacy_export_project(request: Request, project_id: str) -> None:
    raise _legacy_video_generation_error()

@router.post("/scenes/{scene_id}/sequence-upload")
def legacy_upload_scene_sequence(request: Request, scene_id: str) -> None:
    raise _legacy_video_generation_error()

@router.patch("/scenes/{scene_id}/assembly")
def legacy_update_scene_assembly(request: Request, scene_id: str) -> None:
    raise _legacy_video_generation_error()

@router.patch("/scenes/{scene_id}/wan-prompt")
def legacy_update_scene_wan_prompt(request: Request, scene_id: str) -> None:
    raise _legacy_video_generation_error()

@router.get("/assets/{project_id}/{asset_path:path}")
def get_asset(request: Request, project_id: str, asset_path: str) -> FileResponse:
    project_root = request.app.state.repository.ensure_project_assets(project_id)
    candidate = (project_root / asset_path).resolve()
    if not str(candidate).startswith(str(project_root.resolve())) or not candidate.exists():
        raise HTTPException(status_code=404, detail="Asset not found.")
    return FileResponse(candidate)
