from __future__ import annotations

import asyncio
from pathlib import Path

from .repository import MovieRepository
from .schemas import JobStatus, JobType
from .services.continuity_review import ContinuityReviewService
from .services.image_generation import ImageGenerationService
from .services.rendering import AssemblyService
from .services.video_generation import VideoGenerationService


class JobManager:
    def __init__(
        self,
        repository: MovieRepository,
        assembly_service: AssemblyService,
        continuity_review_service: ContinuityReviewService,
        image_generation_service: ImageGenerationService,
        video_generation_service: VideoGenerationService,
    ) -> None:
        self.repository = repository
        self.assembly_service = assembly_service
        self.continuity_review_service = continuity_review_service
        self.image_generation_service = image_generation_service
        self.video_generation_service = video_generation_service
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None

    async def start(self) -> None:
        self._worker_task = asyncio.create_task(self._worker(), name="movie-scripting-job-worker")
        for job_id in self.repository.requeue_pending_jobs():
            await self.enqueue(job_id)

    async def stop(self) -> None:
        await self._queue.put(None)
        if self._worker_task is not None:
            await self._worker_task

    async def enqueue(self, job_id: str) -> None:
        await self._queue.put(job_id)

    async def _worker(self) -> None:
        while True:
            job_id = await self._queue.get()
            if job_id is None:
                break
            await self._process_job(job_id)

    async def _process_job(self, job_id: str) -> None:
        job = self.repository.mark_job_running(job_id)
        if job is None:
            return

        try:
            if job["job_type"] == JobType.render.value:
                raise RuntimeError("Local video generation is no longer part of this product.")
            if job["job_type"] == JobType.export.value:
                await self._process_export_job(job)
                return
            if job["job_type"] == JobType.continuity_review.value:
                await self._process_continuity_review_job(job)
                return
            if job["job_type"] == JobType.image_generation.value:
                await self._process_image_generation_job(job)
                return
            if job["job_type"] == JobType.video_generation.value:
                await self._process_video_generation_job(job)
                return
            if job["job_type"] == JobType.character_image_generation.value:
                await self._process_character_image_generation_job(job)
                return
            raise RuntimeError(f"Unsupported job type: {job['job_type']}")
        except Exception as exc:
            if job["job_type"] == JobType.image_generation.value and job.get("scene_id"):
                self.repository.set_scene_image_generation_status(job["scene_id"], "failed")
            self.repository.update_job(
                job_id,
                status=JobStatus.failed,
                error_text=str(exc),
            )

    async def _process_export_job(self, job: dict) -> None:
        project_detail = self.repository.get_project_detail(job["project_id"])
        if project_detail is None:
            raise RuntimeError("Project not found for export job.")
        if project_detail["workflow_version"] < 2:
            raise RuntimeError("Upgrade this project to 2.0 before exporting a rough cut.")

        assembly_sequences = [
            sequence
            for scene in project_detail["scenes"]
            for sequence in scene["sequences"]
            if sequence["include_in_assembly"]
            and (sequence.get("approved_video_asset") is not None or sequence.get("uploaded_video_asset") is not None)
        ]
        if not assembly_sequences:
            raise RuntimeError("No approved or uploaded sequence videos are available to assemble.")

        missing_sequences = [
            sequence["absolute_order"]
            for scene in project_detail["scenes"]
            for sequence in scene["sequences"]
            if sequence["include_in_assembly"]
            and sequence.get("approved_video_asset") is None
            and sequence.get("uploaded_video_asset") is None
        ]
        if missing_sequences:
            missing = ", ".join(str(order) for order in missing_sequences)
            raise RuntimeError(f"Missing approved or uploaded sequence videos for included sequences: {missing}.")

        filename = job["payload"].get("filename") or self._default_export_name(project_detail["name"])
        project_root = self.repository.ensure_project_assets(project_detail["id"])
        output_path = project_root / "exports" / filename
        export_result = await asyncio.to_thread(
            self.assembly_service.export_project,
            project=project_detail,
            assembly_sequences=assembly_sequences,
            output_path=output_path,
            job_id=job["id"],
        )
        export_relative_path = f"exports/{Path(export_result['relative_path']).name}"
        export = self.repository.create_export_asset(
            project_id=project_detail["id"],
            job_id=job["id"],
            relative_path=export_relative_path,
            duration_s=export_result["duration_s"],
        )
        self.repository.update_job(
            job["id"],
            status=JobStatus.succeeded,
            progress=1.0,
            result={"export_id": export["id"], "relative_path": export["relative_path"]},
        )

    async def _process_continuity_review_job(self, job: dict) -> None:
        if not job.get("scene_id"):
            raise RuntimeError("Continuity review jobs must target a scene.")
        project_detail = self.repository.get_project_detail(job["project_id"])
        if project_detail is None:
            raise RuntimeError("Project not found for continuity review job.")
        scene = next((item for item in project_detail.get("scenes", []) if item["id"] == job["scene_id"]), None)
        if scene is None:
            raise RuntimeError("Scene not found for continuity review job.")

        self.repository.update_job(job["id"], progress=0.25)
        review = await asyncio.to_thread(
            self.continuity_review_service.review_scene,
            project_detail,
            scene,
            self.repository.get_resolved_model_settings(job["project_id"]),
        )
        self.repository.update_job(job["id"], progress=0.8)
        saved = self.repository.save_continuity_review(project_detail["id"], scene["id"], review)
        self.repository.update_job(
            job["id"],
            status=JobStatus.succeeded,
            progress=1.0,
            result={"scene_id": scene["id"], "review_id": saved["id"], "source": saved["source"]},
        )

    async def _process_image_generation_job(self, job: dict) -> None:
        scene_id = str(job["payload"].get("scene_id") or job.get("scene_id") or "")
        if not scene_id:
            raise RuntimeError("Image generation jobs must target a scene.")
        project_detail = self.repository.get_project_detail(job["project_id"])
        if project_detail is None:
            raise RuntimeError("Project not found for image generation job.")
        scene = next((item for item in project_detail.get("scenes", []) if item["id"] == scene_id), None)
        if scene is None:
            raise RuntimeError("Scene not found for image generation job.")
        request_payload = job["payload"].get("request", {})
        self.repository.set_scene_image_generation_status(scene_id, "running")
        variants = await asyncio.to_thread(
            self.image_generation_service.generate_scene_images,
            project=project_detail,
            scene=scene,
            media_settings=self.repository.get_media_generation_settings(),
            request=request_payload,
        )
        created_variant_ids: list[str] = []
        approved_scene = None
        for index, variant in enumerate(variants):
            created = self.repository.create_scene_image_variant(scene_id, **variant)
            created_variant_ids.append(created["id"])
            if index == 0 and request_payload.get("auto_approve", False):
                approved_scene = self.repository.approve_scene_image_variant(scene_id, created["id"])
        if approved_scene is None:
            self.repository.set_scene_image_generation_status(scene_id, "generated")
        self.repository.update_job(
            job["id"],
            status=JobStatus.succeeded,
            progress=1.0,
            result={
                "scene_id": scene_id,
                "variant_ids": created_variant_ids,
                "approved_asset_id": created_variant_ids[0] if created_variant_ids and request_payload.get("auto_approve", False) else None,
            },
        )

    async def _process_character_image_generation_job(self, job: dict) -> None:
        character_id = str(job["payload"].get("character_id") or "")
        shot_type = str(job["payload"].get("shot_type") or "portrait")
        if not character_id:
            raise RuntimeError("Character image generation jobs must target a character.")
        
        project_detail = self.repository.get_project_detail(job["project_id"])
        if project_detail is None:
            raise RuntimeError("Project not found for character image generation job.")
            
        character = self.repository.get_project_character(character_id)
        if character is None:
            raise RuntimeError("Character not found for character image generation job.")
            
        self.repository.update_job(job["id"], progress=0.1)
        
        # We need a prompt for the character portrait.
        # Use the name, role summary, and tags.
        base_prompt = f"{character['name']}, {character['role_summary']}, {character['prompt_tags']}"
        if shot_type == "portrait":
            prompt = f"portrait of {base_prompt}, closeup, face focused"
        elif shot_type == "cowboyshot":
            prompt = f"cowboy shot of {base_prompt}, medium shot, from waist up"
        else: # fullbody
            prompt = f"full body shot of {base_prompt}, standing, head to toe"
            
        # Use the image generation service
        image_path = await asyncio.to_thread(
            self.image_generation_service.generate_single_image,
            project=project_detail,
            prompt=prompt,
            media_settings=self.repository.get_media_generation_settings(),
        )
        
        # Save the path to the character model
        column_name = f"{shot_type}_image_url"
        self.repository.update_project_character(character_id, {column_name: image_path})
        
        self.repository.update_job(
            job["id"],
            status=JobStatus.succeeded,
            progress=1.0,
            result={
                "character_id": character_id,
                "shot_type": shot_type,
                "image_url": image_path
            },
        )

    async def _process_video_generation_job(self, job: dict) -> None:
        project_detail = self.repository.get_project_detail(job["project_id"])
        if project_detail is None:
            raise RuntimeError("Project not found for video generation job.")
        request_payload = job["payload"].get("request", {})
        mode = str(job["payload"].get("mode") or "single")
        scene_id = str(job["payload"].get("scene_id") or job.get("scene_id") or "")
        if not scene_id:
            raise RuntimeError("Video generation jobs must target a scene.")
        scene = next((item for item in project_detail.get("scenes", []) if item["id"] == scene_id), None)
        if scene is None:
            raise RuntimeError("Scene not found for video generation job.")
        sequences = sorted(scene.get("sequences", []), key=lambda item: item["order"])
        if mode == "single":
            target_sequence_id = str(job["payload"].get("sequence_id") or "")
            target_sequences = [sequence for sequence in sequences if sequence["id"] == target_sequence_id]
            if not target_sequences:
                raise RuntimeError("Target sequence not found for video generation job.")
        else:
            target_sequences = sequences
        if not target_sequences:
            raise RuntimeError("No sequences are available for video generation.")
        created_variant_ids: list[str] = []
        approved_variant_ids: list[str] = []
        for index, sequence in enumerate(target_sequences, start=1):
            if not sequence.get("wan_prompt_text", "").strip():
                raise RuntimeError(f"Sequence {sequence['order']:02d} is missing a Wan prompt.")
            input_asset = self._resolve_sequence_input_asset(scene, sequence["id"])
            if input_asset is None:
                raise RuntimeError(f"Sequence {sequence['order']:02d} is missing its required input image.")
            generated = await asyncio.to_thread(
                self.video_generation_service.generate_sequence_video,
                project=project_detail,
                scene=scene,
                sequence=sequence,
                input_asset=input_asset,
                media_settings=self.repository.get_media_generation_settings(),
                request=request_payload,
            )
            variant = self.repository.create_sequence_video_variant(sequence["id"], **generated)
            created_variant_ids.append(variant["id"])
            if request_payload.get("auto_approve", False):
                approved = self.repository.approve_sequence_video_variant(sequence["id"], variant["id"])
                if approved is not None:
                    approved_variant_ids.append(variant["id"])
            scene = self.repository.get_story_scene(scene_id) or scene
            sequences = sorted(scene.get("sequences", []), key=lambda item: item["order"])
            progress = 0.2 + (0.75 * index / max(len(target_sequences), 1))
            self.repository.update_job(job["id"], progress=min(progress, 0.95))
        self.repository.update_job(
            job["id"],
            status=JobStatus.succeeded,
            progress=1.0,
            result={
                "scene_id": scene_id,
                "sequence_ids": [sequence["id"] for sequence in target_sequences],
                "variant_ids": created_variant_ids,
                "approved_variant_ids": approved_variant_ids,
            },
        )

    def _resolve_sequence_input_asset(self, scene: dict, sequence_id: str) -> dict | None:
        sequences = sorted(scene.get("sequences", []), key=lambda item: item["order"])
        previous_last_frame = scene.get("first_image_asset")
        for sequence in sequences:
            if sequence["id"] == sequence_id:
                return previous_last_frame
            previous_last_frame = sequence.get("last_frame_asset")
        return None

    def _default_export_name(self, project_name: str) -> str:
        stem = "-".join(project_name.strip().lower().split()) or "movie"
        return f"{stem}-rough-cut.mp4"
