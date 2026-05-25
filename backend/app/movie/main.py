from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import re
import shutil
from typing import Any, Literal
import uuid

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

from .config import get_settings
from .router import router
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
    _bs = '\\'
    return f"/assets/{project_id}/{relative_path.replace(_bs, '/')}"


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


def create_app() -> FastAPI:
    settings = get_settings()
    database = Database(settings.database_path)
    repository = MovieRepository(database=database, settings=settings)
    model_runtime = LocalModelRuntime(settings)
    generation_service = NarrativeStudio(settings, model_runtime)
    continuity_review_service = ContinuityReviewService(settings, model_runtime)
    scenario_assistant = ScenarioAssistant(settings, model_runtime)
    hardware_profile = detect_hardware_profile(settings)
    assembly_service = AssemblyService(settings=settings)
    image_generation_service = ImageGenerationService(settings)
    video_generation_service = VideoGenerationService(settings)
    media_model_download_service = MediaModelDownloadService(settings)
    job_manager = JobManager(
        repository=repository,
        assembly_service=assembly_service,
        continuity_review_service=continuity_review_service,
        image_generation_service=image_generation_service,
        video_generation_service=video_generation_service,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        repository.initialize()
        app.state.settings = settings
        app.state.repository = repository
        app.state.generation_service = generation_service
        app.state.scenario_assistant = scenario_assistant
        app.state.continuity_review_service = continuity_review_service
        app.state.image_generation_service = image_generation_service
        app.state.video_generation_service = video_generation_service
        app.state.media_model_download_service = media_model_download_service
        app.state.media_downloads = {}
        app.state.media_download_tasks = {}
        app.state.hardware_profile = hardware_profile
        app.state.job_manager = job_manager
        await job_manager.start()
        try:
            yield
        finally:
            await job_manager.stop()

    app = FastAPI(
        title="Movie Scripting Tool",
        version="0.4.1",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(DurationConflictError)
    async def handle_duration_conflict(request: Request, exc: DurationConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})
    app.include_router(router)
