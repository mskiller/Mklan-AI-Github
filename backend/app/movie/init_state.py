"""Populate app.state with Movie module services.

Called during the unified app lifespan startup so that movie route handlers
(which use `request.app.state.*`) have all dependencies available.
"""
from __future__ import annotations

from fastapi import FastAPI

from .config import get_settings
from .database import Database
from .services.continuity_review import ContinuityReviewService
from .services.generation import NarrativeStudio
from .services.hardware import detect_hardware_profile
from .services.image_generation import ImageGenerationService
from .services.model_runtime import LocalModelRuntime
from .services.model_downloads import MediaModelDownloadService
from .services.rendering import AssemblyService
from .services.scenario_assistant import ScenarioAssistant
from .services.video_generation import VideoGenerationService
from .job_manager import JobManager
from .repository import MovieRepository, DurationConflictError


def init_movie_app_state(app: FastAPI, database: Database | None = None) -> None:
    """Initialise all Movie services and attach them to app.state."""
    settings = get_settings()

    if database is None:
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

    # Register exception handler on the target app
    @app.exception_handler(DurationConflictError)
    async def handle_duration_conflict(request, exc: DurationConflictError):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=409, content={"detail": str(exc)})