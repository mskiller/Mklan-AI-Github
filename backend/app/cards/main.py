from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
import re
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .config import get_settings
from .database import Database
from .model_settings import DEFAULT_INSTRUCTION, preview_sample_context, render_task_prompts
from .repository import MovieRepository
from .schemas import (
    AssistantConnectionTestRequest,
    AssistantConnectionTestResponse,
    AssistantSettingsRead,
    AssistantSettingsUpdateRequest,
    CharacterCreateRequest,
    CharacterImageGenerateRequest,
    CharacterRead,
    CharacterUpdateRequest,
    GeneratedImagePromptRead,
    GenerateAllRequest,
    GenerateCharactersRequest,
    GenerateLoreRequest,
    GenerateScenarioRequest,
    GenerateUserRequest,
    HardwareProfile,
    ImageCandidateRead,
    ImagePromptGenerateRequest,
    ImageModelInventoryRead,
    ImageModelUploadResponse,
    LoreEntryCreateRequest,
    LoreImageGenerateRequest,
    LoreEntryRead,
    LoreEntryUpdateRequest,
    MediaGenerationSettingsRead,
    MediaGenerationSettingsTestResponse,
    MediaGenerationSettingsUpdateRequest,
    ModelSettingsRead,
    ModelSettingsUpdateRequest,
    SillyTavernStatusRead,
    SillyTavernSyncResponse,
    GMCardProfileRead,
    GMCardProfileUpdateRequest,
    ProjectCreateRequest,
    ProjectListItem,
    ProjectModelSettingsOverrideRead,
    ProjectModelSettingsOverrideUpdateRequest,
    ProjectRead,
    ProjectScope,
    ProjectUpdateRequest,
    PromptPreviewRequest,
    PromptPreviewResponse,
    ScenarioImageGenerateRequest,
    UserProfileRead,
    UserImageGenerateRequest,
    UserProfileUpdateRequest,
)
from .services.card_exports import (
    build_bundle_export,
    build_character_card_payload,
    build_gm_card_payload,
    build_lorebook_export,
    build_persona_card_payload,
    build_persona_export,
    export_card_image,
)
from .services.card_generation import CardGenerationService
from .services.compatibility_inspector import CompatibilityInspector
from app.movie.services.hardware import detect_hardware_profile
from app.movie.services.image_generation import ImageGenerationService
from app.movie.services.model_runtime import LocalModelRuntime
from .services.sillytavern_bridge import SillyTavernBridge, SillyTavernBridgeError
from .services.shared_vault import SharedVaultService
from .services.wildcard_bridge import WildcardBridgeService


def _asset_url(project_id: str, relative_path: str) -> str:
    normalized_path = relative_path.replace("\\", "/")
    return f"/cards/assets/{project_id}/{normalized_path}"


def _slugify_filename(filename: str) -> str:
    stem = Path(filename or "export").stem or "export"
    suffix = Path(filename or "export").suffix.lower()
    safe_stem = re.sub(r"[^a-zA-Z0-9._-]+", "-", stem).strip("-") or "export"
    safe_suffix = re.sub(r"[^a-z0-9.]+", "", suffix)
    return f"{safe_stem}{safe_suffix}"


def _serialize_character(character: dict) -> dict:
    payload = dict(character)
    avatar_relative = payload.pop("avatar_relative_path", None)
    portrait_relative = payload.pop("portrait_relative_path", None)
    cowboy_relative = payload.pop("cowboy_shot_relative_path", None)
    fullbody_relative = payload.pop("fullbody_shot_relative_path", None)
    payload["portrait_url"] = _asset_url(payload["project_id"], portrait_relative) if portrait_relative else None
    payload["cowboy_shot_url"] = _asset_url(payload["project_id"], cowboy_relative) if cowboy_relative else None
    payload["fullbody_shot_url"] = _asset_url(payload["project_id"], fullbody_relative) if fullbody_relative else None
    chosen_avatar = avatar_relative or portrait_relative or cowboy_relative or fullbody_relative
    payload["avatar_url"] = _asset_url(payload["project_id"], chosen_avatar) if chosen_avatar else None
    return payload


def _serialize_lore_entry(entry: dict) -> dict:
    payload = dict(entry)
    project_id = str(payload.get("project_id", "") or "")
    image_relative = payload.pop("image_relative_path", None)
    payload["image_url"] = _asset_url(project_id, image_relative) if project_id and image_relative else None
    return payload


def _serialize_user_profile(profile: dict) -> dict:
    payload = dict(profile)
    project_id = str(payload.get("project_id", "") or "")
    avatar_relative = payload.pop("avatar_relative_path", None)
    portrait_relative = payload.pop("portrait_relative_path", None)
    cowboy_relative = payload.pop("cowboy_shot_relative_path", None)
    fullbody_relative = payload.pop("fullbody_shot_relative_path", None)
    chosen_avatar = avatar_relative or portrait_relative or cowboy_relative or fullbody_relative
    payload["avatar_url"] = _asset_url(project_id, chosen_avatar) if project_id and chosen_avatar else None
    payload["portrait_url"] = _asset_url(project_id, portrait_relative) if project_id and portrait_relative else None
    payload["cowboy_shot_url"] = _asset_url(project_id, cowboy_relative) if project_id and cowboy_relative else None
    payload["fullbody_shot_url"] = _asset_url(project_id, fullbody_relative) if project_id and fullbody_relative else None
    return payload


def _serialize_project(detail: dict) -> dict:
    scenario_relative = detail.get("scenario_image_relative_path")
    return {
        **detail,
        "scenario_world_image_url": _asset_url(detail["id"], scenario_relative) if scenario_relative else None,
        "characters": [_serialize_character(item) for item in detail.get("characters", [])],
        "lore_entries": [_serialize_lore_entry(item) for item in detail.get("lore_entries", [])],
        "user_profile": _serialize_user_profile(detail.get("user_profile", {})),
    }


def _normalize_shot_format(raw_format: str) -> str:
    normalized = str(raw_format or "").strip().lower()
    if normalized == "fullbody":
        return "fullbody_shot"
    if normalized == "reference":
        return "cowboy_shot"
    if normalized in {"portrait", "cowboy_shot", "fullbody_shot"}:
        return normalized
    return "portrait"


def _resolve_approved_relative_path(project: dict, owner_type: str, owner_id: str, image_slot: str) -> str | None:
    if owner_type == "scenario":
        return project.get("scenario_image_relative_path")
    if owner_type == "character":
        for character in project.get("characters", []):
            if character.get("id") != owner_id:
                continue
            return character.get("avatar_relative_path")
        return None
    if owner_type == "lore":
        for entry in project.get("lore_entries", []):
            if entry.get("id") != owner_id:
                continue
            return entry.get("image_relative_path")
        return None
    if owner_type == "user":
        profile = project.get("user_profile", {})
        return profile.get("avatar_relative_path")
    return None


def _serialize_image_candidate(project: dict, candidate: dict) -> dict:
    approved_relative_path = _resolve_approved_relative_path(
        project,
        owner_type=str(candidate.get("owner_type", "")),
        owner_id=str(candidate.get("owner_id", "")),
        image_slot=str(candidate.get("image_slot", "")),
    )
    relative_path = str(candidate.get("relative_path", ""))
    return {
        **candidate,
        "image_url": _asset_url(candidate["project_id"], relative_path),
        "approved": bool(approved_relative_path and approved_relative_path == relative_path),
    }


def _character_subject_text(character: dict) -> str:
    return ", ".join(
        item
        for item in (
            character.get("description", ""),
            character.get("personality", ""),
            character.get("scenario", ""),
            character.get("appearance_summary", ""),
        )
        if item
    )


def _lore_subject_text(entry: dict) -> str:
    return ", ".join(
        item
        for item in (
            entry.get("content", ""),
            entry.get("comment", ""),
            ", ".join(entry.get("keys", [])),
        )
        if item
    )


def _user_subject_text(profile: dict) -> str:
    return ", ".join(
        item
        for item in (
            profile.get("description", ""),
            profile.get("personality", ""),
            profile.get("scenario_role", ""),
            profile.get("appearance_summary", ""),
        )
        if item
    )


def _compose_booru_character_tag(name: str | None, copyright_name: str | None) -> str:
    clean_name = str(name or "").strip()
    clean_copyright = str(copyright_name or "").strip()
    if clean_name and clean_copyright:
        return f"{clean_name} ({clean_copyright})"
    return clean_name


def _compose_image_prompt(
    *,
    card_generation_service: CardGenerationService,
    project: dict,
    model_settings: dict,
    image_model_name: str,
    subject_type: str,
    shot_type: str,
    subject_name: str,
    subject_text: str,
    appearance_summary: str = "",
    booru_character_tag: str = "",
    instruction: str,
    prompt_override: str = "",
    negative_prompt_override: str = "",
    wildcard_tags: list[str] | None = None,
    style_anchor: str = "",
) -> dict[str, str]:
    generated = card_generation_service.generate_image_prompt(
        project=project,
        model_settings=model_settings,
        image_model_name=image_model_name,
        subject_type=subject_type,
        shot_type=shot_type,
        subject_name=subject_name,
        subject_text=subject_text,
        appearance_summary=appearance_summary,
        booru_character_tag=booru_character_tag,
        instruction=instruction,
    )
    prompt_text = str(prompt_override or "").strip() or generated["prompt"]
    prompt_additions = [item.strip() for item in (wildcard_tags or []) if str(item).strip()]
    if style_anchor.strip():
        prompt_additions.append(style_anchor.strip())
    if prompt_additions:
        prompt_text = ", ".join([prompt_text, *prompt_additions])
    negative_prompt = str(negative_prompt_override or "").strip() or generated["negative_prompt"]
    return {
        "prompt": prompt_text,
        "negative_prompt": negative_prompt,
        "style_profile": generated.get("style_profile", "generic_sdxl"),
    }


def _apply_candidate_approval(
    *,
    repository: MovieRepository,
    project_id: str,
    owner_type: str,
    owner_id: str,
    image_slot: str,
    relative_path: str,
) -> None:
    if owner_type == "scenario":
        repository.update_project(project_id, {"scenario_image_relative_path": relative_path})
        return
    if owner_type == "character":
        updates = {
            f"{image_slot}_relative_path": relative_path,
            "avatar_relative_path": relative_path,
        }
        repository.update_character(owner_id, updates)
        return
    if owner_type == "lore":
        repository.update_lore_entry(owner_id, {"image_relative_path": relative_path})
        return
    if owner_type == "user":
        updates = {
            f"{image_slot}_relative_path": relative_path,
            "avatar_relative_path": relative_path,
        }
        repository.update_user_profile(project_id, updates)
        return
    raise HTTPException(status_code=400, detail="Unsupported image owner type.")


def _build_prompt_preview_context(
    repository: MovieRepository,
    payload: PromptPreviewRequest,
) -> dict:
    context = preview_sample_context(payload.task.value)
    context["instruction"] = payload.instruction or DEFAULT_INSTRUCTION
    if payload.project_id:
        project = repository.get_project_detail(payload.project_id)
        if project:
            context["project"] = {
                "name": project["name"],
                "seed_sentence": project.get("seed_sentence", ""),
                "scenario_text": project.get("scenario_text", ""),
                "genre": project.get("genre", "roleplay"),
                "tone": project.get("tone", "immersive"),
                "mode": project.get("project_mode", "character"),
                "target_count": 3 if project.get("project_mode") == "game_master" else 1,
                "character_names": ", ".join(item["name"] for item in project.get("characters", []) if item.get("name")),
                "user_name": project.get("user_profile", {}).get("name", "User"),
            }
    return context


def _load_project_or_404(repository: MovieRepository, project_id: str) -> dict:
    detail = repository.get_project_detail(project_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return detail


def _ensure_project_editable(detail: dict) -> None:
    if detail.get("archived_at"):
        raise HTTPException(status_code=409, detail="Archived projects are read-only.")


def _resolve_user_avatar_url(project: dict) -> str | None:
    profile = project.get("user_profile", {}) or {}
    for key in (
        "avatar_relative_path",
        "portrait_relative_path",
        "cowboy_shot_relative_path",
        "fullbody_shot_relative_path",
    ):
        relative = profile.get(key)
        if relative:
            return _asset_url(project["id"], str(relative))
    return None


def create_app() -> FastAPI:
    settings = get_settings()
    database = Database(settings.database_path)
    repository = MovieRepository(database=database, settings=settings)
    model_runtime = LocalModelRuntime(settings)
    card_generation_service = CardGenerationService(model_runtime)
    image_generation_service = ImageGenerationService(settings)
    sillytavern_bridge = SillyTavernBridge(settings)
    compatibility_inspector = CompatibilityInspector(database)
    shared_vault_service = SharedVaultService(database)
    wildcard_bridge_service = WildcardBridgeService()
    hardware_profile = detect_hardware_profile(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        repository.initialize()
        app.state.settings = settings
        app.state.repository = repository
        app.state.model_runtime = model_runtime
        app.state.card_generation_service = card_generation_service
        app.state.image_generation_service = image_generation_service
        app.state.sillytavern_bridge = sillytavern_bridge
        app.state.compatibility_inspector = compatibility_inspector
        app.state.shared_vault_service = shared_vault_service
        app.state.wildcard_bridge_service = wildcard_bridge_service
        app.state.hardware_profile = hardware_profile
        yield

    app = FastAPI(
        title="SillyTavern Card Creator",
        version="1.0.0",
        lifespan=lifespan,
    )

    def ensure_cards_state() -> None:
        if hasattr(app.state, "repository"):
            return
        repository.initialize()
        app.state.settings = settings
        app.state.repository = repository
        app.state.model_runtime = model_runtime
        app.state.card_generation_service = card_generation_service
        app.state.image_generation_service = image_generation_service
        app.state.sillytavern_bridge = sillytavern_bridge
        app.state.compatibility_inspector = compatibility_inspector
        app.state.shared_vault_service = shared_vault_service
        app.state.wildcard_bridge_service = wildcard_bridge_service
        app.state.hardware_profile = hardware_profile

    @app.middleware("http")
    async def initialize_cards_state(request: Request, call_next):
        ensure_cards_state()
        return await call_next(request)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def healthcheck() -> dict:
        return {"ok": True}

    @app.get("/system/hardware", response_model=HardwareProfile)
    def get_hardware() -> HardwareProfile:
        return HardwareProfile.model_validate(app.state.hardware_profile)

    @app.get("/system/sillytavern", response_model=SillyTavernStatusRead)
    def get_sillytavern_status() -> SillyTavernStatusRead:
        return SillyTavernStatusRead.model_validate(app.state.sillytavern_bridge.status())

    @app.get("/system/scenario-assistant/settings", response_model=AssistantSettingsRead)
    def get_assistant_settings() -> AssistantSettingsRead:
        return AssistantSettingsRead.model_validate(app.state.repository.get_assistant_settings())

    @app.patch("/system/scenario-assistant/settings", response_model=AssistantSettingsRead)
    def update_assistant_settings(payload: AssistantSettingsUpdateRequest) -> AssistantSettingsRead:
        updated = app.state.repository.update_assistant_settings(payload.model_dump())
        return AssistantSettingsRead.model_validate(updated)

    @app.post("/system/scenario-assistant/test", response_model=AssistantConnectionTestResponse)
    def test_assistant_connection(payload: AssistantConnectionTestRequest) -> AssistantConnectionTestResponse:
        result = app.state.model_runtime.test_connection(
            {
                "provider": payload.provider,
                "base_url": payload.base_url,
                "api_key": payload.api_key,
                "model": payload.model,
                "timeout_s": payload.timeout_s,
            }
        )
        return AssistantConnectionTestResponse.model_validate(result)

    @app.get("/system/model-settings", response_model=ModelSettingsRead)
    def get_model_settings() -> ModelSettingsRead:
        return ModelSettingsRead.model_validate(app.state.repository.get_model_settings())

    @app.patch("/system/model-settings", response_model=ModelSettingsRead)
    def update_model_settings(payload: ModelSettingsUpdateRequest) -> ModelSettingsRead:
        updated = app.state.repository.update_model_settings(payload.model_dump())
        return ModelSettingsRead.model_validate(updated)

    @app.post("/system/model-settings/test-connection", response_model=AssistantConnectionTestResponse)
    def test_model_settings_connection(payload: ModelSettingsUpdateRequest) -> AssistantConnectionTestResponse:
        model = payload.runtime.default_model
        result = app.state.model_runtime.test_connection(
            {
                "provider": payload.runtime.provider,
                "base_url": payload.runtime.base_url,
                "api_key": payload.runtime.api_key,
                "model": model,
                "timeout_s": payload.runtime.timeout_s,
            }
        )
        return AssistantConnectionTestResponse.model_validate(result)

    @app.post("/system/model-settings/test-prompt", response_model=PromptPreviewResponse)
    def test_prompt_preview(payload: PromptPreviewRequest) -> PromptPreviewResponse:
        model_settings = app.state.repository.get_model_settings()
        context = _build_prompt_preview_context(app.state.repository, payload)
        output_text = None
        error_text = None
        rendered_variables: dict[str, str] = {}
        system_prompt = ""
        user_prompt = ""
        effective_parameters: dict[str, Any] = {}
        effective_model = model_settings["runtime"]["default_model"]
        try:
            rendered = render_task_prompts(model_settings, payload.task.value, context)
            rendered_variables = rendered["rendered_variables"]
            system_prompt = rendered["system_prompt"]
            user_prompt = rendered["user_prompt"]
            effective_parameters = rendered["task_config"]["parameters"]
            effective_model = rendered["task_config"]["runtime"]["model"]
            if payload.run_model:
                output_text = app.state.model_runtime.run_text(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    runtime_config=rendered["task_config"]["runtime"],
                    parameters=rendered["task_config"]["parameters"],
                )
        except KeyError as exc:
            error_text = f"Unknown template token: {exc.args[0]}"
        except Exception as exc:
            error_text = str(exc)
        return PromptPreviewResponse(
            task=payload.task,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            rendered_variables=rendered_variables,
            provider=model_settings["runtime"]["provider"],
            effective_model=effective_model,
            effective_parameters=effective_parameters,
            output_text=output_text,
            error_text=error_text,
        )

    @app.get("/system/media-generation-settings", response_model=MediaGenerationSettingsRead)
    def get_media_generation_settings() -> MediaGenerationSettingsRead:
        return MediaGenerationSettingsRead.model_validate(app.state.repository.get_media_generation_settings())

    @app.patch("/system/media-generation-settings", response_model=MediaGenerationSettingsRead)
    def update_media_generation_settings(payload: MediaGenerationSettingsUpdateRequest) -> MediaGenerationSettingsRead:
        updated = app.state.repository.update_media_generation_settings(payload.model_dump())
        return MediaGenerationSettingsRead.model_validate(updated)

    @app.post("/system/media-generation-settings/test", response_model=MediaGenerationSettingsTestResponse)
    def test_media_generation_settings(payload: MediaGenerationSettingsUpdateRequest | None = None) -> MediaGenerationSettingsTestResponse:
        media_settings = payload.model_dump() if payload else app.state.repository.get_media_generation_settings()
        image_result = app.state.image_generation_service.test_settings(media_settings, app.state.hardware_profile)
        return MediaGenerationSettingsTestResponse.model_validate({"image": image_result})

    @app.get("/system/media-generation/image-models", response_model=ImageModelInventoryRead)
    def list_image_models() -> ImageModelInventoryRead:
        inventory = app.state.image_generation_service.list_available_models(
            app.state.repository.get_media_generation_settings()
        )
        return ImageModelInventoryRead.model_validate(inventory)

    @app.post("/system/media-generation/image-models/upload", response_model=ImageModelUploadResponse)
    async def upload_image_model(
        file: UploadFile = File(...),
        destination_name: str = Form(default=""),
        set_default: bool = Form(default=True),
    ) -> ImageModelUploadResponse:
        payload = await file.read()
        if not payload:
            raise HTTPException(status_code=400, detail="Uploaded model file is empty.")
        current = app.state.repository.get_media_generation_settings()
        root_path, target_path = app.state.image_generation_service.reserve_uploaded_model_path(
            media_settings=current,
            filename=file.filename or "model.safetensors",
            destination_name=destination_name,
        )
        target_path.write_bytes(payload)
        uploaded = app.state.image_generation_service.describe_uploaded_model(root_path=root_path, model_path=target_path)
        next_settings = current
        if set_default:
            next_settings["image"]["default_model"] = uploaded["value"]
            next_settings["image"]["checkpoint_root"] = str(root_path)
        saved_settings = app.state.repository.update_media_generation_settings(next_settings)
        inventory = app.state.image_generation_service.list_available_models(saved_settings)
        return ImageModelUploadResponse.model_validate(
            {
                "uploaded_model": uploaded,
                "inventory": inventory,
                "settings": saved_settings,
            }
        )

    @app.get("/projects", response_model=list[ProjectListItem])
    def list_projects(scope: ProjectScope = ProjectScope.active) -> list[ProjectListItem]:
        return [ProjectListItem.model_validate(item) for item in app.state.repository.list_projects(scope.value)]

    @app.post("/projects", response_model=ProjectRead)
    def create_project(payload: ProjectCreateRequest) -> ProjectRead:
        project = app.state.repository.create_project(payload.model_dump(mode="json"))
        return ProjectRead.model_validate(_serialize_project(project))

    @app.patch("/projects/{project_id}", response_model=ProjectRead)
    def update_project(project_id: str, payload: ProjectUpdateRequest) -> ProjectRead:
        detail = _load_project_or_404(app.state.repository, project_id)
        _ensure_project_editable(detail)
        updated = app.state.repository.update_project(
            project_id,
            payload.model_dump(mode="json", exclude_none=True),
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="Project not found.")
        return ProjectRead.model_validate(_serialize_project(updated))

    @app.post("/projects/{project_id}/archive", response_model=ProjectRead)
    def archive_project(project_id: str) -> ProjectRead:
        updated = app.state.repository.archive_project(project_id)
        if updated is None:
            raise HTTPException(status_code=404, detail="Project not found.")
        return ProjectRead.model_validate(_serialize_project(updated))

    @app.post("/projects/{project_id}/restore", response_model=ProjectRead)
    def restore_project(project_id: str) -> ProjectRead:
        updated = app.state.repository.restore_project(project_id)
        if updated is None:
            raise HTTPException(status_code=404, detail="Project not found.")
        return ProjectRead.model_validate(_serialize_project(updated))

    @app.delete("/projects/{project_id}", status_code=204)
    def delete_project(project_id: str) -> Response:
        deleted = app.state.repository.delete_project(project_id)
        if deleted is None:
            raise HTTPException(status_code=404, detail="Project not found.")
        if deleted is False:
            raise HTTPException(status_code=409, detail="Archive the project before deleting it.")
        return Response(status_code=204)

    @app.get("/projects/{project_id}", response_model=ProjectRead)
    def get_project(project_id: str) -> ProjectRead:
        detail = _load_project_or_404(app.state.repository, project_id)
        return ProjectRead.model_validate(_serialize_project(detail))

    @app.post("/projects/{project_id}/sillytavern/sync", response_model=SillyTavernSyncResponse)
    def sync_project_to_sillytavern(project_id: str) -> SillyTavernSyncResponse:
        detail = _load_project_or_404(app.state.repository, project_id)
        report = app.state.compatibility_inspector.inspect(detail)
        if report["critical_count"]:
            raise HTTPException(status_code=409, detail={"message": "Compatibility report has critical issues.", "report": report})
        try:
            result = app.state.sillytavern_bridge.sync_project(
                repository=app.state.repository,
                project=detail,
            )
        except SillyTavernBridgeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return SillyTavernSyncResponse.model_validate(result)

    @app.get("/projects/{project_id}/gm-card", response_model=GMCardProfileRead)
    def get_gm_card(project_id: str) -> GMCardProfileRead:
        detail = _load_project_or_404(app.state.repository, project_id)
        return GMCardProfileRead.model_validate(detail.get("gm_card_profile", {}))

    @app.patch("/projects/{project_id}/gm-card", response_model=GMCardProfileRead)
    def update_gm_card(project_id: str, payload: GMCardProfileUpdateRequest) -> GMCardProfileRead:
        detail = _load_project_or_404(app.state.repository, project_id)
        _ensure_project_editable(detail)
        updated = app.state.repository.update_gm_card_profile(project_id, payload.model_dump(exclude_none=True))
        if updated is None:
            raise HTTPException(status_code=404, detail="Project not found.")
        return GMCardProfileRead.model_validate(updated)

    @app.get("/projects/{project_id}/model-settings", response_model=ProjectModelSettingsOverrideRead)
    def get_project_model_settings(project_id: str) -> ProjectModelSettingsOverrideRead:
        _load_project_or_404(app.state.repository, project_id)
        override = app.state.repository.get_project_model_settings_override(project_id)
        if override is None:
            raise HTTPException(status_code=404, detail="Project not found.")
        return ProjectModelSettingsOverrideRead.model_validate(override)

    @app.patch("/projects/{project_id}/model-settings", response_model=ProjectModelSettingsOverrideRead)
    def update_project_model_settings(
        project_id: str,
        payload: ProjectModelSettingsOverrideUpdateRequest,
    ) -> ProjectModelSettingsOverrideRead:
        _load_project_or_404(app.state.repository, project_id)
        override = app.state.repository.update_project_model_settings_override(project_id, payload.model_dump())
        if override is None:
            raise HTTPException(status_code=404, detail="Project not found.")
        return ProjectModelSettingsOverrideRead.model_validate(override)

    @app.get("/projects/{project_id}/characters", response_model=list[CharacterRead])
    def list_characters(project_id: str) -> list[CharacterRead]:
        detail = _load_project_or_404(app.state.repository, project_id)
        return [CharacterRead.model_validate(_serialize_character(item)) for item in detail.get("characters", [])]

    @app.post("/projects/{project_id}/characters", response_model=CharacterRead)
    def create_character(project_id: str, payload: CharacterCreateRequest) -> CharacterRead:
        detail = _load_project_or_404(app.state.repository, project_id)
        _ensure_project_editable(detail)
        character = app.state.repository.create_character(project_id, payload.model_dump())
        if character is None:
            raise HTTPException(status_code=404, detail="Project not found.")
        return CharacterRead.model_validate(_serialize_character(character))

    @app.patch("/projects/{project_id}/characters/{character_id}", response_model=CharacterRead)
    def update_character(project_id: str, character_id: str, payload: CharacterUpdateRequest) -> CharacterRead:
        detail = _load_project_or_404(app.state.repository, project_id)
        _ensure_project_editable(detail)
        existing = app.state.repository.get_character(character_id)
        if existing is None or existing["project_id"] != project_id:
            raise HTTPException(status_code=404, detail="Character not found.")
        character = app.state.repository.update_character(character_id, payload.model_dump(exclude_none=True))
        if character is None:
            raise HTTPException(status_code=404, detail="Character not found.")
        return CharacterRead.model_validate(_serialize_character(character))

    @app.delete("/projects/{project_id}/characters/{character_id}", status_code=204)
    def delete_character(project_id: str, character_id: str) -> Response:
        detail = _load_project_or_404(app.state.repository, project_id)
        _ensure_project_editable(detail)
        existing = app.state.repository.get_character(character_id)
        if existing is None or existing["project_id"] != project_id:
            raise HTTPException(status_code=404, detail="Character not found.")
        if not app.state.repository.delete_character(character_id):
            raise HTTPException(status_code=404, detail="Character not found.")
        return Response(status_code=204)

    @app.get("/projects/{project_id}/lore-entries", response_model=list[LoreEntryRead])
    def list_lore_entries(project_id: str) -> list[LoreEntryRead]:
        detail = _load_project_or_404(app.state.repository, project_id)
        return [LoreEntryRead.model_validate(_serialize_lore_entry(item)) for item in detail.get("lore_entries", [])]

    @app.post("/projects/{project_id}/lore-entries", response_model=LoreEntryRead)
    def create_lore_entry(project_id: str, payload: LoreEntryCreateRequest) -> LoreEntryRead:
        detail = _load_project_or_404(app.state.repository, project_id)
        _ensure_project_editable(detail)
        entry = app.state.repository.create_lore_entry(project_id, payload.model_dump())
        if entry is None:
            raise HTTPException(status_code=404, detail="Project not found.")
        return LoreEntryRead.model_validate(_serialize_lore_entry(entry))

    @app.patch("/projects/{project_id}/lore-entries/{lore_id}", response_model=LoreEntryRead)
    def update_lore_entry(project_id: str, lore_id: str, payload: LoreEntryUpdateRequest) -> LoreEntryRead:
        detail = _load_project_or_404(app.state.repository, project_id)
        _ensure_project_editable(detail)
        existing = app.state.repository.get_lore_entry(lore_id)
        if existing is None or existing["project_id"] != project_id:
            raise HTTPException(status_code=404, detail="Lore entry not found.")
        updated = app.state.repository.update_lore_entry(lore_id, payload.model_dump(exclude_none=True))
        if updated is None:
            raise HTTPException(status_code=404, detail="Lore entry not found.")
        return LoreEntryRead.model_validate(_serialize_lore_entry(updated))

    @app.delete("/projects/{project_id}/lore-entries/{lore_id}", status_code=204)
    def delete_lore_entry(project_id: str, lore_id: str) -> Response:
        detail = _load_project_or_404(app.state.repository, project_id)
        _ensure_project_editable(detail)
        existing = app.state.repository.get_lore_entry(lore_id)
        if existing is None or existing["project_id"] != project_id:
            raise HTTPException(status_code=404, detail="Lore entry not found.")
        if not app.state.repository.delete_lore_entry(lore_id):
            raise HTTPException(status_code=404, detail="Lore entry not found.")
        return Response(status_code=204)

    @app.get("/projects/{project_id}/user-profile", response_model=UserProfileRead)
    def get_user_profile(project_id: str) -> UserProfileRead:
        _load_project_or_404(app.state.repository, project_id)
        profile = app.state.repository.get_user_profile(project_id)
        return UserProfileRead.model_validate(_serialize_user_profile(profile))

    @app.patch("/projects/{project_id}/user-profile", response_model=UserProfileRead)
    def update_user_profile(project_id: str, payload: UserProfileUpdateRequest) -> UserProfileRead:
        detail = _load_project_or_404(app.state.repository, project_id)
        _ensure_project_editable(detail)
        profile = app.state.repository.update_user_profile(project_id, payload.model_dump(exclude_none=True))
        return UserProfileRead.model_validate(_serialize_user_profile(profile))

    @app.post("/projects/{project_id}/generate/scenario", response_model=ProjectRead)
    def generate_scenario(project_id: str, payload: GenerateScenarioRequest) -> ProjectRead:
        detail = _load_project_or_404(app.state.repository, project_id)
        _ensure_project_editable(detail)
        run = app.state.repository.create_generation_run(project_id, "scenario_generation")
        app.state.repository.update_generation_run(run["id"], status="running", progress=0.1)
        try:
            generated = app.state.card_generation_service.generate_scenario(
                detail,
                app.state.repository.get_resolved_model_settings(project_id),
                payload.instruction,
            )
            app.state.repository.update_project(
                project_id,
                {"scenario_text": generated["scenario_text"]},
            )
            app.state.repository.update_generation_run(run["id"], status="succeeded", progress=1.0, completed=True)
        except Exception as exc:
            app.state.repository.update_generation_run(
                run["id"], status="failed", progress=1.0, error_text=str(exc), completed=True
            )
            raise HTTPException(status_code=500, detail=str(exc))
        refreshed = _load_project_or_404(app.state.repository, project_id)
        return ProjectRead.model_validate(_serialize_project(refreshed))

    @app.post("/projects/{project_id}/generate/characters", response_model=ProjectRead)
    def generate_characters(project_id: str, payload: GenerateCharactersRequest) -> ProjectRead:
        detail = _load_project_or_404(app.state.repository, project_id)
        _ensure_project_editable(detail)
        if detail.get("project_mode") == "game_master":
            updated_detail = app.state.repository.update_project(
                project_id,
                {"sample_character_target_count": payload.target_count},
            )
            if updated_detail is not None:
                detail = updated_detail
        run = app.state.repository.create_generation_run(project_id, "character_card_generation")
        app.state.repository.update_generation_run(run["id"], status="running", progress=0.1)
        try:
            target_count = payload.target_count if detail.get("project_mode") == "game_master" else None
            items = app.state.card_generation_service.generate_characters(
                detail,
                app.state.repository.get_resolved_model_settings(project_id),
                payload.instruction,
                target_count,
            )
            if payload.overwrite_existing:
                app.state.repository.replace_characters(project_id, items)
            else:
                for item in items:
                    app.state.repository.create_character(project_id, item)
            app.state.repository.update_generation_run(run["id"], status="succeeded", progress=1.0, completed=True)
        except Exception as exc:
            app.state.repository.update_generation_run(
                run["id"], status="failed", progress=1.0, error_text=str(exc), completed=True
            )
            raise HTTPException(status_code=500, detail=str(exc))
        refreshed = _load_project_or_404(app.state.repository, project_id)
        return ProjectRead.model_validate(_serialize_project(refreshed))

    @app.post("/projects/{project_id}/generate/lore", response_model=ProjectRead)
    def generate_lore(project_id: str, payload: GenerateLoreRequest) -> ProjectRead:
        detail = _load_project_or_404(app.state.repository, project_id)
        _ensure_project_editable(detail)
        run = app.state.repository.create_generation_run(project_id, "lore_generation")
        app.state.repository.update_generation_run(run["id"], status="running", progress=0.1)
        try:
            items = app.state.card_generation_service.generate_lore(
                detail,
                [item["name"] for item in detail.get("characters", [])],
                app.state.repository.get_resolved_model_settings(project_id),
                payload.instruction,
            )
            if payload.overwrite_existing:
                app.state.repository.replace_lore_entries(project_id, items)
            else:
                for item in items:
                    app.state.repository.create_lore_entry(project_id, item)
            app.state.repository.update_generation_run(run["id"], status="succeeded", progress=1.0, completed=True)
        except Exception as exc:
            app.state.repository.update_generation_run(
                run["id"], status="failed", progress=1.0, error_text=str(exc), completed=True
            )
            raise HTTPException(status_code=500, detail=str(exc))
        refreshed = _load_project_or_404(app.state.repository, project_id)
        return ProjectRead.model_validate(_serialize_project(refreshed))

    @app.post("/projects/{project_id}/generate/user", response_model=ProjectRead)
    def generate_user_profile(project_id: str, payload: GenerateUserRequest) -> ProjectRead:
        detail = _load_project_or_404(app.state.repository, project_id)
        _ensure_project_editable(detail)
        run = app.state.repository.create_generation_run(project_id, "user_profile_generation")
        app.state.repository.update_generation_run(run["id"], status="running", progress=0.1)
        try:
            profile = app.state.card_generation_service.generate_user_profile(
                detail,
                [item["name"] for item in detail.get("characters", [])],
                app.state.repository.get_resolved_model_settings(project_id),
                payload.instruction,
            )
            app.state.repository.update_user_profile(project_id, profile)
            app.state.repository.update_generation_run(run["id"], status="succeeded", progress=1.0, completed=True)
        except Exception as exc:
            app.state.repository.update_generation_run(
                run["id"], status="failed", progress=1.0, error_text=str(exc), completed=True
            )
            raise HTTPException(status_code=500, detail=str(exc))
        refreshed = _load_project_or_404(app.state.repository, project_id)
        return ProjectRead.model_validate(_serialize_project(refreshed))

    @app.post("/projects/{project_id}/generate/gm-card", response_model=ProjectRead)
    def generate_gm_card(project_id: str, payload: GenerateScenarioRequest) -> ProjectRead:
        detail = _load_project_or_404(app.state.repository, project_id)
        _ensure_project_editable(detail)
        run = app.state.repository.create_generation_run(project_id, "game_master_card_generation")
        app.state.repository.update_generation_run(run["id"], status="running", progress=0.1)
        try:
            model_settings = app.state.repository.get_resolved_model_settings(project_id)
            profile = app.state.card_generation_service.generate_gm_card(
                detail,
                character_names=[item["name"] for item in detail.get("characters", []) if item.get("name")],
                user_name=detail.get("user_profile", {}).get("name", "User"),
                model_settings=model_settings,
                instruction=payload.instruction,
            )
            app.state.repository.update_gm_card_profile(project_id, profile)
            app.state.repository.update_generation_run(run["id"], status="succeeded", progress=1.0, completed=True)
        except Exception as exc:
            app.state.repository.update_generation_run(
                run["id"], status="failed", progress=1.0, error_text=str(exc), completed=True
            )
            raise HTTPException(status_code=500, detail=str(exc))
        refreshed = _load_project_or_404(app.state.repository, project_id)
        return ProjectRead.model_validate(_serialize_project(refreshed))

    @app.post("/projects/{project_id}/generate/all", response_model=ProjectRead)
    def generate_all(project_id: str, payload: GenerateAllRequest) -> ProjectRead:
        detail = _load_project_or_404(app.state.repository, project_id)
        _ensure_project_editable(detail)
        if detail.get("project_mode") == "game_master" and payload.target_count is not None:
            updated_detail = app.state.repository.update_project(
                project_id,
                {"sample_character_target_count": payload.target_count},
            )
            if updated_detail is not None:
                detail = updated_detail
        run = app.state.repository.create_generation_run(project_id, "scenario_generation")
        app.state.repository.update_generation_run(run["id"], status="running", progress=0.05)
        try:
            resolved_settings = app.state.repository.get_resolved_model_settings(project_id)
            scenario = app.state.card_generation_service.generate_scenario(detail, resolved_settings, payload.instruction)
            app.state.repository.update_project(project_id, {"scenario_text": scenario["scenario_text"]})
            app.state.repository.update_generation_run(run["id"], progress=0.3)

            detail = _load_project_or_404(app.state.repository, project_id)
            project_mode = str(detail.get("project_mode", "character") or "character")
            character_target_count = (
                payload.target_count
                if project_mode == "game_master" and payload.target_count is not None
                else int(detail.get("sample_character_target_count") or (5 if project_mode == "game_master" else 1))
            )
            if project_mode == "game_master":
                profile = app.state.card_generation_service.generate_user_profile(
                    detail,
                    [item["name"] for item in detail.get("characters", [])],
                    resolved_settings,
                    payload.instruction,
                )
                app.state.repository.update_user_profile(project_id, profile)
                app.state.repository.update_generation_run(run["id"], progress=0.5)

                detail = _load_project_or_404(app.state.repository, project_id)
                characters = app.state.card_generation_service.generate_characters(
                    detail,
                    resolved_settings,
                    payload.instruction,
                    character_target_count,
                )
                if payload.overwrite_characters:
                    app.state.repository.replace_characters(project_id, characters)
                else:
                    for item in characters:
                        app.state.repository.create_character(project_id, item)
                app.state.repository.update_generation_run(run["id"], progress=0.75)
            else:
                characters = app.state.card_generation_service.generate_characters(
                    detail,
                    resolved_settings,
                    payload.instruction,
                    character_target_count,
                )
                if payload.overwrite_characters:
                    app.state.repository.replace_characters(project_id, characters)
                else:
                    for item in characters:
                        app.state.repository.create_character(project_id, item)
                app.state.repository.update_generation_run(run["id"], progress=0.6)

                detail = _load_project_or_404(app.state.repository, project_id)
                profile = app.state.card_generation_service.generate_user_profile(
                    detail,
                    [item["name"] for item in detail.get("characters", [])],
                    resolved_settings,
                    payload.instruction,
                )
                app.state.repository.update_user_profile(project_id, profile)
                app.state.repository.update_generation_run(run["id"], progress=0.78)

            detail = _load_project_or_404(app.state.repository, project_id)
            lore = app.state.card_generation_service.generate_lore(
                detail,
                [item["name"] for item in detail.get("characters", [])],
                resolved_settings,
                payload.instruction,
            )
            if payload.overwrite_lore:
                app.state.repository.replace_lore_entries(project_id, lore)
            else:
                for item in lore:
                    app.state.repository.create_lore_entry(project_id, item)
            app.state.repository.update_generation_run(run["id"], progress=0.92)

            if project_mode == "game_master":
                detail = _load_project_or_404(app.state.repository, project_id)
                gm_profile = app.state.card_generation_service.generate_gm_card(
                    detail,
                    character_names=[item["name"] for item in detail.get("characters", []) if item.get("name")],
                    user_name=detail.get("user_profile", {}).get("name", "User"),
                    model_settings=resolved_settings,
                    instruction=payload.instruction,
                )
                app.state.repository.update_gm_card_profile(project_id, gm_profile)
                app.state.repository.update_generation_run(run["id"], progress=0.97)
            app.state.repository.update_generation_run(run["id"], status="succeeded", progress=1.0, completed=True)
        except Exception as exc:
            app.state.repository.update_generation_run(
                run["id"], status="failed", progress=1.0, error_text=str(exc), completed=True
            )
            raise HTTPException(status_code=500, detail=str(exc))
        refreshed = _load_project_or_404(app.state.repository, project_id)
        return ProjectRead.model_validate(_serialize_project(refreshed))

    @app.post("/projects/{project_id}/images/scenario/prompt", response_model=GeneratedImagePromptRead)
    def generate_scenario_world_prompt(project_id: str, payload: ImagePromptGenerateRequest) -> GeneratedImagePromptRead:
        detail = _load_project_or_404(app.state.repository, project_id)
        resolved_model_settings = app.state.repository.get_resolved_model_settings(project_id)
        media_settings = app.state.repository.get_media_generation_settings()
        prompt_payload = _compose_image_prompt(
            card_generation_service=app.state.card_generation_service,
            project=detail,
            model_settings=resolved_model_settings,
            image_model_name=media_settings["image"].get("default_model", ""),
            subject_type="scenario",
            shot_type="world",
            subject_name=detail.get("name", "world"),
            subject_text=detail.get("scenario_text", ""),
            instruction=payload.instruction,
            wildcard_tags=payload.wildcard_tags,
            style_anchor=payload.style_anchor,
        )
        return GeneratedImagePromptRead.model_validate({**prompt_payload, "image_slot": "world"})

    @app.post("/projects/{project_id}/characters/{character_id}/images/prompt", response_model=GeneratedImagePromptRead)
    def generate_character_image_prompt(
        project_id: str,
        character_id: str,
        payload: CharacterImageGenerateRequest,
    ) -> GeneratedImagePromptRead:
        detail = _load_project_or_404(app.state.repository, project_id)
        character = app.state.repository.get_character(character_id)
        if character is None or character["project_id"] != project_id:
            raise HTTPException(status_code=404, detail="Character not found.")
        shot_format = _normalize_shot_format(payload.format)
        resolved_model_settings = app.state.repository.get_resolved_model_settings(project_id)
        media_settings = app.state.repository.get_media_generation_settings()
        booru_tag = _compose_booru_character_tag(
            character.get("booru_character_name"),
            character.get("booru_copyright"),
        )
        prompt_payload = _compose_image_prompt(
            card_generation_service=app.state.card_generation_service,
            project=detail,
            model_settings=resolved_model_settings,
            image_model_name=media_settings["image"].get("default_model", ""),
            subject_type="character",
            shot_type=shot_format,
            subject_name=character.get("name", "character"),
            subject_text=_character_subject_text(character),
            appearance_summary=str(character.get("appearance_summary", "") or ""),
            booru_character_tag=booru_tag,
            instruction=payload.instruction,
            wildcard_tags=payload.wildcard_tags,
            style_anchor=payload.style_anchor,
        )
        return GeneratedImagePromptRead.model_validate({**prompt_payload, "image_slot": shot_format})

    @app.post("/projects/{project_id}/lore-entries/{lore_id}/image/prompt", response_model=GeneratedImagePromptRead)
    def generate_lore_image_prompt(project_id: str, lore_id: str, payload: ImagePromptGenerateRequest) -> GeneratedImagePromptRead:
        detail = _load_project_or_404(app.state.repository, project_id)
        entry = app.state.repository.get_lore_entry(lore_id)
        if entry is None or entry["project_id"] != project_id:
            raise HTTPException(status_code=404, detail="Lore entry not found.")
        resolved_model_settings = app.state.repository.get_resolved_model_settings(project_id)
        media_settings = app.state.repository.get_media_generation_settings()
        prompt_payload = _compose_image_prompt(
            card_generation_service=app.state.card_generation_service,
            project=detail,
            model_settings=resolved_model_settings,
            image_model_name=media_settings["image"].get("default_model", ""),
            subject_type="lore",
            shot_type="illustration",
            subject_name=entry.get("name", "lore"),
            subject_text=_lore_subject_text(entry),
            instruction=payload.instruction,
            wildcard_tags=payload.wildcard_tags,
            style_anchor=payload.style_anchor,
        )
        return GeneratedImagePromptRead.model_validate({**prompt_payload, "image_slot": "lore"})

    @app.post("/projects/{project_id}/user-profile/images/prompt", response_model=GeneratedImagePromptRead)
    def generate_user_profile_image_prompt(project_id: str, payload: UserImageGenerateRequest) -> GeneratedImagePromptRead:
        detail = _load_project_or_404(app.state.repository, project_id)
        profile = app.state.repository.get_user_profile(project_id)
        shot_format = _normalize_shot_format(payload.format)
        resolved_model_settings = app.state.repository.get_resolved_model_settings(project_id)
        media_settings = app.state.repository.get_media_generation_settings()
        booru_tag = _compose_booru_character_tag(
            profile.get("booru_character_name"),
            profile.get("booru_copyright"),
        )
        prompt_payload = _compose_image_prompt(
            card_generation_service=app.state.card_generation_service,
            project=detail,
            model_settings=resolved_model_settings,
            image_model_name=media_settings["image"].get("default_model", ""),
            subject_type="user",
            shot_type=shot_format,
            subject_name=profile.get("name", "user"),
            subject_text=_user_subject_text(profile),
            appearance_summary=str(profile.get("appearance_summary", "") or ""),
            booru_character_tag=booru_tag,
            instruction=payload.instruction,
            wildcard_tags=payload.wildcard_tags,
            style_anchor=payload.style_anchor,
        )
        return GeneratedImagePromptRead.model_validate({**prompt_payload, "image_slot": shot_format})

    @app.post("/projects/{project_id}/images/scenario/generate", response_model=ProjectRead)
    def generate_scenario_world_image(project_id: str, payload: ScenarioImageGenerateRequest) -> ProjectRead:
        detail = _load_project_or_404(app.state.repository, project_id)
        _ensure_project_editable(detail)
        resolved_model_settings = app.state.repository.get_resolved_model_settings(project_id)
        media_settings = app.state.repository.get_media_generation_settings()
        prompt_payload = _compose_image_prompt(
            card_generation_service=app.state.card_generation_service,
            project=detail,
            model_settings=resolved_model_settings,
            image_model_name=media_settings["image"].get("default_model", ""),
            subject_type="scenario",
            shot_type="world",
            subject_name=detail.get("name", "world"),
            subject_text=detail.get("scenario_text", ""),
            instruction=payload.instruction,
            prompt_override=payload.prompt,
            negative_prompt_override=payload.negative_prompt,
            wildcard_tags=payload.wildcard_tags,
            style_anchor=payload.style_anchor,
        )
        relative_path = app.state.image_generation_service.generate_single_image(
            project=detail,
            prompt=prompt_payload["prompt"],
            media_settings=media_settings,
            output_group="scenario",
            output_stem=f"{detail.get('name', 'project')}-world",
            variant="world",
            negative_prompt=prompt_payload["negative_prompt"],
        )
        app.state.repository.add_image_candidate(
            project_id=project_id,
            owner_type="scenario",
            owner_id=project_id,
            image_slot="world",
            relative_path=relative_path,
            prompt_text=prompt_payload["prompt"],
            negative_prompt=prompt_payload["negative_prompt"],
        )
        if not detail.get("scenario_image_relative_path"):
            app.state.repository.update_project(project_id, {"scenario_image_relative_path": relative_path})
        refreshed = _load_project_or_404(app.state.repository, project_id)
        return ProjectRead.model_validate(_serialize_project(refreshed))

    @app.post("/projects/{project_id}/characters/{character_id}/images/generate", response_model=CharacterRead)
    def generate_character_image(
        project_id: str,
        character_id: str,
        payload: CharacterImageGenerateRequest,
    ) -> CharacterRead:
        detail = _load_project_or_404(app.state.repository, project_id)
        _ensure_project_editable(detail)
        character = app.state.repository.get_character(character_id)
        if character is None or character["project_id"] != project_id:
            raise HTTPException(status_code=404, detail="Character not found.")

        shot_format = _normalize_shot_format(payload.format)
        resolved_model_settings = app.state.repository.get_resolved_model_settings(project_id)
        media_settings = app.state.repository.get_media_generation_settings()
        booru_tag = _compose_booru_character_tag(
            character.get("booru_character_name"),
            character.get("booru_copyright"),
        )
        prompt_payload = _compose_image_prompt(
            card_generation_service=app.state.card_generation_service,
            project=detail,
            model_settings=resolved_model_settings,
            image_model_name=media_settings["image"].get("default_model", ""),
            subject_type="character",
            shot_type=shot_format,
            subject_name=character.get("name", "character"),
            subject_text=_character_subject_text(character),
            appearance_summary=str(character.get("appearance_summary", "") or ""),
            booru_character_tag=booru_tag,
            instruction=payload.instruction,
            prompt_override=payload.prompt,
            negative_prompt_override=payload.negative_prompt,
            wildcard_tags=payload.wildcard_tags,
            style_anchor=payload.style_anchor,
        )
        relative_path = app.state.image_generation_service.generate_single_image(
            project=detail,
            prompt=prompt_payload["prompt"],
            media_settings=media_settings,
            output_group="character",
            output_stem=character.get("name", "character"),
            variant=shot_format,
            negative_prompt=prompt_payload["negative_prompt"],
        )
        app.state.repository.add_image_candidate(
            project_id=project_id,
            owner_type="character",
            owner_id=character_id,
            image_slot=shot_format,
            relative_path=relative_path,
            prompt_text=prompt_payload["prompt"],
            negative_prompt=prompt_payload["negative_prompt"],
        )
        updates = {f"{shot_format}_relative_path": relative_path}
        if not character.get("avatar_relative_path"):
            updates["avatar_relative_path"] = relative_path
        updated = app.state.repository.update_character(character_id, updates)
        if updated is None:
            raise HTTPException(status_code=404, detail="Character not found.")
        return CharacterRead.model_validate(_serialize_character(updated))

    @app.post("/projects/{project_id}/lore-entries/{lore_id}/image/generate", response_model=LoreEntryRead)
    def generate_lore_image(project_id: str, lore_id: str, payload: LoreImageGenerateRequest) -> LoreEntryRead:
        detail = _load_project_or_404(app.state.repository, project_id)
        _ensure_project_editable(detail)
        entry = app.state.repository.get_lore_entry(lore_id)
        if entry is None or entry["project_id"] != project_id:
            raise HTTPException(status_code=404, detail="Lore entry not found.")

        resolved_model_settings = app.state.repository.get_resolved_model_settings(project_id)
        media_settings = app.state.repository.get_media_generation_settings()
        prompt_payload = _compose_image_prompt(
            card_generation_service=app.state.card_generation_service,
            project=detail,
            model_settings=resolved_model_settings,
            image_model_name=media_settings["image"].get("default_model", ""),
            subject_type="lore",
            shot_type="illustration",
            subject_name=entry.get("name", "lore"),
            subject_text=_lore_subject_text(entry),
            instruction=payload.instruction,
            prompt_override=payload.prompt,
            negative_prompt_override=payload.negative_prompt,
            wildcard_tags=payload.wildcard_tags,
            style_anchor=payload.style_anchor,
        )
        relative_path = app.state.image_generation_service.generate_single_image(
            project=detail,
            prompt=prompt_payload["prompt"],
            media_settings=media_settings,
            output_group="lore",
            output_stem=entry.get("name", "lore"),
            variant="lore",
            negative_prompt=prompt_payload["negative_prompt"],
        )
        app.state.repository.add_image_candidate(
            project_id=project_id,
            owner_type="lore",
            owner_id=lore_id,
            image_slot="lore",
            relative_path=relative_path,
            prompt_text=prompt_payload["prompt"],
            negative_prompt=prompt_payload["negative_prompt"],
        )
        if not entry.get("image_relative_path"):
            app.state.repository.update_lore_entry(lore_id, {"image_relative_path": relative_path})
        refreshed_entry = app.state.repository.get_lore_entry(lore_id)
        if refreshed_entry is None:
            raise HTTPException(status_code=404, detail="Lore entry not found.")
        return LoreEntryRead.model_validate(_serialize_lore_entry(refreshed_entry))

    @app.post("/projects/{project_id}/user-profile/images/generate", response_model=UserProfileRead)
    def generate_user_profile_image(project_id: str, payload: UserImageGenerateRequest) -> UserProfileRead:
        detail = _load_project_or_404(app.state.repository, project_id)
        _ensure_project_editable(detail)
        profile = app.state.repository.get_user_profile(project_id)
        shot_format = _normalize_shot_format(payload.format)
        resolved_model_settings = app.state.repository.get_resolved_model_settings(project_id)
        media_settings = app.state.repository.get_media_generation_settings()
        booru_tag = _compose_booru_character_tag(
            profile.get("booru_character_name"),
            profile.get("booru_copyright"),
        )
        prompt_payload = _compose_image_prompt(
            card_generation_service=app.state.card_generation_service,
            project=detail,
            model_settings=resolved_model_settings,
            image_model_name=media_settings["image"].get("default_model", ""),
            subject_type="user",
            shot_type=shot_format,
            subject_name=profile.get("name", "user"),
            subject_text=_user_subject_text(profile),
            appearance_summary=str(profile.get("appearance_summary", "") or ""),
            booru_character_tag=booru_tag,
            instruction=payload.instruction,
            prompt_override=payload.prompt,
            negative_prompt_override=payload.negative_prompt,
            wildcard_tags=payload.wildcard_tags,
            style_anchor=payload.style_anchor,
        )
        relative_path = app.state.image_generation_service.generate_single_image(
            project=detail,
            prompt=prompt_payload["prompt"],
            media_settings=media_settings,
            output_group="user",
            output_stem=profile.get("name", "user"),
            variant=shot_format,
            negative_prompt=prompt_payload["negative_prompt"],
        )
        app.state.repository.add_image_candidate(
            project_id=project_id,
            owner_type="user",
            owner_id=project_id,
            image_slot=shot_format,
            relative_path=relative_path,
            prompt_text=prompt_payload["prompt"],
            negative_prompt=prompt_payload["negative_prompt"],
        )
        updates = {f"{shot_format}_relative_path": relative_path}
        if not profile.get("avatar_relative_path"):
            updates["avatar_relative_path"] = relative_path
        updated = app.state.repository.update_user_profile(project_id, updates)
        return UserProfileRead.model_validate(_serialize_user_profile(updated))

    @app.get("/projects/{project_id}/image-candidates", response_model=list[ImageCandidateRead])
    def list_project_image_candidates(
        project_id: str,
        owner_type: str | None = Query(default=None),
        owner_id: str | None = Query(default=None),
        image_slot: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=250),
    ) -> list[ImageCandidateRead]:
        detail = _load_project_or_404(app.state.repository, project_id)
        normalized_owner_type = owner_type.strip().lower() if owner_type else None
        if normalized_owner_type and normalized_owner_type not in {"scenario", "character", "lore", "user"}:
            raise HTTPException(status_code=400, detail="Invalid owner_type. Use scenario, character, lore, or user.")
        candidates = app.state.repository.list_image_candidates(
            project_id=project_id,
            owner_type=normalized_owner_type,
            owner_id=owner_id,
            image_slot=image_slot,
            limit=limit,
        )
        return [ImageCandidateRead.model_validate(_serialize_image_candidate(detail, item)) for item in candidates]

    @app.post("/projects/{project_id}/image-candidates/{candidate_id}/approve", response_model=ImageCandidateRead)
    def approve_image_candidate(project_id: str, candidate_id: str) -> ImageCandidateRead:
        detail = _load_project_or_404(app.state.repository, project_id)
        _ensure_project_editable(detail)
        candidate = app.state.repository.get_image_candidate(candidate_id)
        if candidate is None or candidate["project_id"] != project_id:
            raise HTTPException(status_code=404, detail="Image candidate not found.")
        _apply_candidate_approval(
            repository=app.state.repository,
            project_id=project_id,
            owner_type=str(candidate["owner_type"]),
            owner_id=str(candidate["owner_id"]),
            image_slot=str(candidate["image_slot"]),
            relative_path=str(candidate["relative_path"]),
        )
        refreshed_project = _load_project_or_404(app.state.repository, project_id)
        refreshed_candidate = app.state.repository.get_image_candidate(candidate_id)
        if refreshed_candidate is None:
            raise HTTPException(status_code=404, detail="Image candidate not found.")
        return ImageCandidateRead.model_validate(_serialize_image_candidate(refreshed_project, refreshed_candidate))

    @app.get("/projects/{project_id}/characters/{character_id}/export.json")
    def export_character_json(project_id: str, character_id: str) -> JSONResponse:
        project = _load_project_or_404(app.state.repository, project_id)
        character = app.state.repository.get_character(character_id)
        if character is None or character["project_id"] != project_id:
            raise HTTPException(status_code=404, detail="Character not found.")
        payload = build_character_card_payload(project, character)
        response = JSONResponse(content=payload)
        response.headers["Content-Disposition"] = (
            f'attachment; filename="{_slugify_filename(character["name"])}-card.json"'
        )
        return response

    @app.get("/projects/{project_id}/characters/{character_id}/export.image")
    def export_character_image(
        project_id: str,
        character_id: str,
        image_format: str = Query(default="png", pattern="^(png|webp)$"),
    ) -> FileResponse:
        project = _load_project_or_404(app.state.repository, project_id)
        character = app.state.repository.get_character(character_id)
        if character is None or character["project_id"] != project_id:
            raise HTTPException(status_code=404, detail="Character not found.")
        payload = build_character_card_payload(project, character)
        output_path = export_card_image(
            repository=app.state.repository,
            project=project,
            payload=payload,
            export_dir_name="character-exports",
            image_basename=_slugify_filename(character["name"]),
            image_format=image_format,
            source_relative_paths=[
                character.get("avatar_relative_path"),
                character.get("portrait_relative_path"),
                character.get("cowboy_shot_relative_path"),
                character.get("fullbody_shot_relative_path"),
            ],
            placeholder_title=character["name"],
        )
        return FileResponse(
            output_path,
            filename=output_path.name,
            media_type="image/png" if image_format == "png" else "image/webp",
        )

    @app.get("/projects/{project_id}/gm-card/export.json")
    def export_gm_card_json(project_id: str) -> JSONResponse:
        project = _load_project_or_404(app.state.repository, project_id)
        payload = build_gm_card_payload(project)
        response = JSONResponse(content=payload)
        gm_name = str(project.get("gm_card_profile", {}).get("name") or project["name"])
        response.headers["Content-Disposition"] = (
            f'attachment; filename="{_slugify_filename(gm_name)}-gm-card.json"'
        )
        return response

    @app.get("/projects/{project_id}/gm-card/export.image")
    def export_gm_card_image(
        project_id: str,
        image_format: str = Query(default="png", pattern="^(png|webp)$"),
    ) -> FileResponse:
        project = _load_project_or_404(app.state.repository, project_id)
        gm_name = str(project.get("gm_card_profile", {}).get("name") or project["name"])
        payload = build_gm_card_payload(project)
        output_path = export_card_image(
            repository=app.state.repository,
            project=project,
            payload=payload,
            export_dir_name="gm-exports",
            image_basename=_slugify_filename(f"{gm_name}-gm-card"),
            image_format=image_format,
            source_relative_paths=[project.get("scenario_image_relative_path")],
            placeholder_title=gm_name,
        )
        return FileResponse(
            output_path,
            filename=output_path.name,
            media_type="image/png" if image_format == "png" else "image/webp",
        )

    @app.get("/projects/{project_id}/lorebook.json")
    def export_lorebook(project_id: str) -> JSONResponse:
        project = _load_project_or_404(app.state.repository, project_id)
        payload = build_lorebook_export(project)
        response = JSONResponse(content=payload)
        response.headers["Content-Disposition"] = (
            f'attachment; filename="{_slugify_filename(project["name"])}-lorebook.json"'
        )
        return response

    @app.get("/projects/{project_id}/user-export.json")
    def export_user(project_id: str) -> JSONResponse:
        project = _load_project_or_404(app.state.repository, project_id)
        payload = build_persona_export(project, avatar_url=_resolve_user_avatar_url(project))
        response = JSONResponse(content=payload)
        response.headers["Content-Disposition"] = (
            f'attachment; filename="{_slugify_filename(project["name"])}-persona.json"'
        )
        return response

    @app.get("/projects/{project_id}/persona-card/export.json")
    def export_persona_card_json(project_id: str) -> JSONResponse:
        project = _load_project_or_404(app.state.repository, project_id)
        profile = project.get("user_profile", {}) or {}
        persona_name = str(profile.get("name") or "User")
        payload = build_persona_card_payload(project)
        response = JSONResponse(content=payload)
        response.headers["Content-Disposition"] = (
            f'attachment; filename="{_slugify_filename(persona_name)}-persona-card.json"'
        )
        return response

    @app.get("/projects/{project_id}/persona-card/export.image")
    def export_persona_card_image(
        project_id: str,
        image_format: str = Query(default="png", pattern="^(png|webp)$"),
    ) -> FileResponse:
        project = _load_project_or_404(app.state.repository, project_id)
        profile = project.get("user_profile", {}) or {}
        persona_name = str(profile.get("name") or "User")
        payload = build_persona_card_payload(project)
        output_path = export_card_image(
            repository=app.state.repository,
            project=project,
            payload=payload,
            export_dir_name="persona-exports",
            image_basename=_slugify_filename(f"{persona_name}-persona-card"),
            image_format=image_format,
            source_relative_paths=[
                profile.get("avatar_relative_path"),
                profile.get("portrait_relative_path"),
                profile.get("cowboy_shot_relative_path"),
                profile.get("fullbody_shot_relative_path"),
            ],
            placeholder_title=persona_name,
        )
        return FileResponse(
            output_path,
            filename=output_path.name,
            media_type="image/png" if image_format == "png" else "image/webp",
        )

    @app.get("/projects/{project_id}/export-bundle.json")
    def export_bundle(project_id: str) -> JSONResponse:
        project = _load_project_or_404(app.state.repository, project_id)
        payload = build_bundle_export(project, avatar_url=_resolve_user_avatar_url(project))
        response = JSONResponse(content=payload)
        response.headers["Content-Disposition"] = (
            f'attachment; filename="{_slugify_filename(project["name"])}-bundle.json"'
        )
        return response

    @app.get("/projects/{project_id}/compatibility")
    def inspect_project_compatibility(project_id: str) -> dict:
        project = _load_project_or_404(app.state.repository, project_id)
        return app.state.compatibility_inspector.inspect(project)

    @app.get("/vault/characters")
    def list_vault_characters() -> dict:
        return {"characters": app.state.shared_vault_service.list_characters()}

    @app.post("/vault/characters")
    async def add_vault_character(request: Request) -> dict:
        payload = await request.json()
        return app.state.shared_vault_service.upsert_character(payload)

    @app.get("/vault/lore")
    def list_vault_lore() -> dict:
        return {"lore": app.state.shared_vault_service.list_lore()}

    @app.post("/vault/lore")
    async def add_vault_lore(request: Request) -> dict:
        payload = await request.json()
        return app.state.shared_vault_service.upsert_lore(payload)

    @app.post("/vault/characters/{vault_id}/reuse-in-movie/{movie_project_id}")
    def reuse_vault_character_in_movie(vault_id: str, movie_project_id: str) -> dict:
        try:
            vault_character = app.state.shared_vault_service.get_character(vault_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Vault character not found.") from exc

        from app.movie.config import get_settings as get_movie_settings
        from app.movie.database import Database as MovieDatabase
        from app.movie.repository import MovieRepository as StudioMovieRepository

        movie_settings = get_movie_settings()
        movie_repository = StudioMovieRepository(MovieDatabase(movie_settings.database_path), movie_settings)
        movie_repository.initialize()
        project = movie_repository.get_project_detail(movie_project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Movie project not found.")
        created = movie_repository.create_project_character(
            movie_project_id,
            {
                "name": vault_character["name"],
                "role_summary": vault_character.get("role_summary") or vault_character.get("description", ""),
                "prompt_tags": ", ".join(vault_character.get("prompt_tags", [])),
                "portrait_image_url": vault_character.get("avatar_path"),
            },
        )
        return {"movie_project_id": movie_project_id, "movie_character": created, "vault_character": vault_character}

    @app.get("/wildcard-bridge/suggestions")
    def wildcard_bridge_suggestions(q: str = "", limit: int = Query(default=30, ge=1, le=100)) -> dict:
        return app.state.wildcard_bridge_service.suggestions(q, limit)

    @app.post("/projects/{project_id}/assets/upload")
    async def upload_project_asset(
        project_id: str,
        asset_path: str = Form(...),
        file: UploadFile = File(...)
    ) -> dict:
        detail = _load_project_or_404(app.state.repository, project_id)
        _ensure_project_editable(detail)

        project_root = app.state.repository.ensure_project_assets(project_id)
        target_path = (project_root / asset_path).resolve()
        
        # Directory traversal protection
        if not str(target_path).startswith(str(project_root.resolve())):
            raise HTTPException(status_code=400, detail="Invalid asset path.")

        target_path.parent.mkdir(parents=True, exist_ok=True)
        content = await file.read()
        target_path.write_bytes(content)

        return {"relative_path": asset_path}

    @app.get("/assets/{project_id}/{asset_path:path}")
    @app.head("/assets/{project_id}/{asset_path:path}")
    def get_asset(project_id: str, asset_path: str) -> FileResponse:
        project_root = app.state.repository.ensure_project_assets(project_id)
        candidate = (project_root / asset_path).resolve()
        if not str(candidate).startswith(str(project_root.resolve())) or not candidate.exists():
            raise HTTPException(status_code=404, detail="Asset not found.")
        return FileResponse(candidate)

    return app


app = create_app()
