from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from ..config import Settings
from ..model_settings import render_task_prompts
from .model_runtime import LocalModelRuntime


VALID_FINDING_CATEGORIES = {
    "identity",
    "wardrobe",
    "location",
    "lighting",
    "props",
    "camera",
    "action",
    "missing_media",
}
VALID_SEVERITIES = {"info", "warning", "issue"}


class ContinuityReviewService:
    def __init__(self, settings: Settings, runtime: LocalModelRuntime) -> None:
        self.settings = settings
        self.runtime = runtime

    def review_scene(self, project: dict, scene: dict, model_settings: dict) -> dict:
        with tempfile.TemporaryDirectory(prefix="movie-scripting-continuity-") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            review_assets = self._collect_review_assets(project, scene, temp_dir)
            if (review_assets["reference_image"] or review_assets["sequence_frames"]) and self.runtime.supports_vision(
                model_settings["runtime"]
            ):
                review = self._review_with_local_vision(project, scene, review_assets, model_settings)
                if review is not None:
                    return review
            return self._review_with_rules(project, scene)

    def _review_with_local_vision(
        self,
        project: dict,
        scene: dict,
        review_assets: dict,
        model_settings: dict,
    ) -> dict | None:
        reference_image = review_assets["reference_image"]
        sequence_frames = review_assets["sequence_frames"]
        holistic_images = []
        if reference_image is not None:
            holistic_images.append(reference_image)
        holistic_images.extend(
            sequence_frames[sequence["id"]]
            for sequence in scene.get("sequences", [])
            if sequence["id"] in sequence_frames
        )

        if 0 < len(holistic_images) <= 4:
            holistic_review = self._run_local_vision_pass(
                project=project,
                scene=scene,
                model_settings=model_settings,
                image_paths=holistic_images,
                focus_sequence=None,
            )
            if holistic_review is not None:
                return holistic_review

        return self._review_with_local_vision_by_sequence(
            project=project,
            scene=scene,
            review_assets=review_assets,
            model_settings=model_settings,
        )

    def _run_local_vision_pass(
        self,
        *,
        project: dict,
        scene: dict,
        model_settings: dict,
        image_paths: list[Path],
        focus_sequence: dict | None,
    ) -> dict | None:
        context = {
            "project": {
                "name": project["name"],
                "genre": project["genre"],
                "tone": project["tone"],
            },
            "style_anchor_text": project.get("style_anchor_text", ""),
            "scene": {
                "id": scene["id"],
                "order": scene["order"],
                "title": scene["title"],
                "target_duration_s": scene["target_duration_s"],
                "narrative_text": scene["narrative_text"],
                "first_image_prompt_text": scene.get("first_image_prompt_text", ""),
                "reference_image_available": "true" if scene.get("first_image_asset") else "false",
            },
            "review_context": self._build_review_context(scene, focus_sequence_id=focus_sequence["id"] if focus_sequence else None),
        }
        rendered = render_task_prompts(model_settings, "continuity_review", context)
        try:
            parsed = self.runtime.run_vision_json(
                system_prompt=rendered["system_prompt"],
                user_prompt=rendered["user_prompt"],
                image_paths=image_paths,
                runtime_config=rendered["task_config"]["runtime"],
                parameters=rendered["task_config"]["parameters"],
            )
        except Exception:
            return None
        if not isinstance(parsed, dict):
            return None
        return self._normalize_review_payload(scene, parsed, source="local_vision")

    def _review_with_local_vision_by_sequence(
        self,
        *,
        project: dict,
        scene: dict,
        review_assets: dict,
        model_settings: dict,
    ) -> dict | None:
        reference_image: Path | None = review_assets["reference_image"]
        sequence_frames: dict[str, Path] = review_assets["sequence_frames"]
        sequence_lookup = {sequence["id"]: sequence for sequence in scene.get("sequences", [])}
        ordered_sequences = [sequence_lookup[sequence["id"]] for sequence in scene.get("sequences", [])]

        aggregated_findings: list[dict] = []
        aggregated_suggestions: dict[str, dict] = {}
        seen_findings: set[tuple] = set()
        successful_reviews = 0

        for index, sequence in enumerate(ordered_sequences):
            image_paths: list[Path] = []
            if reference_image is not None:
                image_paths.append(reference_image)

            neighbor_ids = []
            if index > 0:
                neighbor_ids.append(ordered_sequences[index - 1]["id"])
            neighbor_ids.append(sequence["id"])
            if index + 1 < len(ordered_sequences):
                neighbor_ids.append(ordered_sequences[index + 1]["id"])

            seen_paths: set[str] = {str(path) for path in image_paths}
            for sequence_id in neighbor_ids:
                path = sequence_frames.get(sequence_id)
                if path is None:
                    continue
                key = str(path)
                if key in seen_paths:
                    continue
                seen_paths.add(key)
                image_paths.append(path)

            if not image_paths:
                continue

            review = self._run_local_vision_pass(
                project=project,
                scene=scene,
                model_settings=model_settings,
                image_paths=image_paths,
                focus_sequence=sequence,
            )
            if review is None:
                return None

            successful_reviews += 1
            for finding in review.get("findings", []):
                key = (
                    finding.get("category"),
                    finding.get("severity"),
                    finding.get("summary_text"),
                    finding.get("detail_text"),
                    finding.get("sequence_id"),
                )
                if key in seen_findings:
                    continue
                seen_findings.add(key)
                aggregated_findings.append(finding)

            for suggestion in review.get("sequence_suggestions", []):
                sequence_id = suggestion.get("sequence_id")
                if not sequence_id:
                    continue
                current = aggregated_suggestions.get(sequence_id)
                if current is None or len(suggestion.get("suggested_prompt_fix", "")) > len(
                    current.get("suggested_prompt_fix", "")
                ):
                    aggregated_suggestions[sequence_id] = suggestion

        if successful_reviews == 0:
            return None

        return {
            "source": "local_vision",
            "summary_text": (
                f"Local vision continuity review completed for Scene {scene['order']:02d} "
                f"across {successful_reviews} sequence check(s)."
            ),
            "findings": aggregated_findings,
            "sequence_suggestions": [
                aggregated_suggestions[sequence["id"]]
                for sequence in ordered_sequences
                if sequence["id"] in aggregated_suggestions
            ],
        }

    def _review_with_rules(self, project: dict, scene: dict) -> dict:
        findings: list[dict] = []
        sequence_suggestions: list[dict] = []

        if scene.get("first_image_asset") is None:
            findings.append(
                {
                    "category": "missing_media",
                    "severity": "warning",
                    "summary_text": "No scene reference image is uploaded.",
                    "detail_text": "Continuity can still be reviewed across uploaded sequences, but identity and wardrobe checks have lower confidence without a scene reference image.",
                    "sequence_id": None,
                    "confidence": 0.55,
                }
            )

        previous_sequence: dict | None = None
        for sequence in scene.get("sequences", []):
            if (sequence.get("approved_video_asset") or sequence.get("uploaded_video_asset")) is None:
                findings.append(
                    {
                        "category": "missing_media",
                        "severity": "issue",
                        "summary_text": f"Sequence {sequence['order']:02d} is missing an approved video.",
                        "detail_text": "Approve or upload the sequence clip to review visual continuity against adjacent shots.",
                        "sequence_id": sequence["id"],
                        "confidence": 1.0,
                    }
                )

            if not sequence.get("camera_direction", "").strip():
                findings.append(
                    {
                        "category": "camera",
                        "severity": "warning",
                        "summary_text": f"Sequence {sequence['order']:02d} has no explicit camera direction.",
                        "detail_text": "Specify framing, movement, and lens intent so the clip preserves shot continuity with neighboring sequences.",
                        "sequence_id": sequence["id"],
                        "confidence": 0.92,
                    }
                )

            if not sequence.get("action_direction", "").strip():
                findings.append(
                    {
                        "category": "action",
                        "severity": "warning",
                        "summary_text": f"Sequence {sequence['order']:02d} has no explicit action timeline.",
                        "detail_text": "Describe what changes over the 5 to 10 second shot so Wan has a concrete motion path to follow.",
                        "sequence_id": sequence["id"],
                        "confidence": 0.92,
                    }
                )

            if previous_sequence is not None:
                previous_camera = previous_sequence.get("camera_direction", "").lower()
                current_camera = sequence.get("camera_direction", "").lower()
                if previous_camera and current_camera:
                    drastic_scale_change = (
                        ("wide" in previous_camera and "close" in current_camera)
                        or ("close" in previous_camera and "wide" in current_camera)
                    )
                    if drastic_scale_change:
                        findings.append(
                            {
                                "category": "camera",
                                "severity": "info",
                                "summary_text": f"Sequence {previous_sequence['order']:02d} to {sequence['order']:02d} makes a strong framing jump.",
                                "detail_text": "That jump may be intentional, but it is worth checking whether the edit wants a smoother bridge or a more explicit story motivation.",
                                "sequence_id": sequence["id"],
                                "confidence": 0.58,
                            }
                        )
            previous_sequence = sequence

            suggested_parts = []
            if scene.get("first_image_prompt_text", "").strip():
                suggested_parts.append("Keep identity, wardrobe, and lighting consistent with the scene still reference.")
            if sequence.get("camera_direction", "").strip():
                suggested_parts.append(f"Camera: {sequence['camera_direction'].strip()}.")
            else:
                suggested_parts.append("Set a clear lens and camera move that matches neighboring shots.")
            if sequence.get("action_direction", "").strip():
                suggested_parts.append(f"Action timeline: {sequence['action_direction'].strip()}.")
            else:
                suggested_parts.append("Describe a short, readable action timeline across the clip.")
            suggested_parts.append("Keep motion controlled, readable, and consistent with the previous and next sequence.")
            sequence_suggestions.append(
                {
                    "sequence_id": sequence["id"],
                    "suggested_prompt_fix": " ".join(suggested_parts).strip(),
                    "rationale": "Rules-only review strengthened continuity anchors, camera intent, and motion boundaries.",
                }
            )

        summary_text = (
            f"Rules-only continuity review completed for Scene {scene['order']:02d}. "
            f"Found {len(findings)} issue(s) or advisory note(s) across {len(scene.get('sequences', []))} sequences."
        )
        return self._normalize_review_payload(
            scene,
            {
                "summary_text": summary_text,
                "findings": findings,
                "sequence_suggestions": sequence_suggestions,
            },
            source="rules_only",
        )

    def _normalize_review_payload(self, scene: dict, payload: dict, *, source: str) -> dict:
        sequence_ids = {sequence["id"] for sequence in scene.get("sequences", [])}
        findings: list[dict] = []
        for item in payload.get("findings", []):
            if not isinstance(item, dict):
                continue
            category = str(item.get("category", "camera")).strip().lower()
            severity = str(item.get("severity", "warning")).strip().lower()
            sequence_id = item.get("sequence_id")
            findings.append(
                {
                    "category": category if category in VALID_FINDING_CATEGORIES else "camera",
                    "severity": severity if severity in VALID_SEVERITIES else "warning",
                    "summary_text": str(item.get("summary_text", "")).strip(),
                    "detail_text": str(item.get("detail_text", "")).strip(),
                    "sequence_id": sequence_id if sequence_id in sequence_ids else None,
                    "confidence": max(0.0, min(1.0, float(item.get("confidence", 0.65) or 0.65))),
                }
            )

        suggestions: list[dict] = []
        for item in payload.get("sequence_suggestions", []):
            if not isinstance(item, dict):
                continue
            sequence_id = str(item.get("sequence_id", "")).strip()
            if sequence_id not in sequence_ids:
                continue
            suggestions.append(
                {
                    "sequence_id": sequence_id,
                    "suggested_prompt_fix": str(item.get("suggested_prompt_fix", "")).strip(),
                    "rationale": str(item.get("rationale", "")).strip(),
                }
            )

        return {
            "source": source,
            "summary_text": str(payload.get("summary_text", "")).strip()
            or f"Continuity review completed for Scene {scene['order']:02d}.",
            "findings": findings,
            "sequence_suggestions": suggestions,
        }

    def _build_review_context(self, scene: dict, *, focus_sequence_id: str | None = None) -> str:
        lines = [
            f"Scene {scene['order']:02d}: {scene['title']}",
            f"Scene narrative: {scene['narrative_text']}",
            f"First image prompt: {scene.get('first_image_prompt_text', '')}",
        ]
        sequences = scene.get("sequences", [])
        if focus_sequence_id:
            focus_index = next((index for index, sequence in enumerate(sequences) if sequence["id"] == focus_sequence_id), None)
            if focus_index is not None:
                lines.append(f"Focus the review on sequence id={focus_sequence_id} and compare it to adjacent shots.")
                start = max(0, focus_index - 1)
                end = min(len(sequences), focus_index + 2)
                sequences = sequences[start:end]

        for sequence in sequences:
            lines.append(
                (
                    f"Sequence {sequence['order']:02d} | id={sequence['id']} | approved={'yes' if (sequence.get('approved_video_asset') or sequence.get('uploaded_video_asset')) else 'no'} | "
                    f"camera={sequence.get('camera_direction', '')} | action={sequence.get('action_direction', '')} | "
                    f"prompt={sequence.get('wan_prompt_text', '')}"
                )
            )
        return "\n".join(lines)

    def _collect_review_assets(self, project: dict, scene: dict, temp_dir: Path) -> dict:
        reference_image: Path | None = None
        sequence_frames: dict[str, Path] = {}
        project_root = self.settings.projects_root / project["id"]
        reference_asset = scene.get("first_image_asset")
        if reference_asset is not None:
            reference_path = project_root / reference_asset["relative_path"]
            if reference_path.exists():
                copied_reference = temp_dir / f"scene-reference{reference_path.suffix or '.jpg'}"
                shutil.copy2(reference_path, copied_reference)
                reference_image = copied_reference

        for sequence in scene.get("sequences", []):
            approved_asset = sequence.get("approved_video_asset") or sequence.get("uploaded_video_asset")
            if approved_asset is None:
                continue
            video_path = project_root / approved_asset["relative_path"]
            if not video_path.exists():
                continue
            frame_path = temp_dir / f"sequence-{sequence['order']:02d}.jpg"
            if self._extract_representative_frame(video_path, frame_path):
                sequence_frames[sequence["id"]] = frame_path
        return {
            "reference_image": reference_image,
            "sequence_frames": sequence_frames,
        }

    def _extract_representative_frame(self, video_path: Path, frame_path: Path) -> bool:
        frame_path.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [
                self.settings.ffmpeg_binary,
                "-y",
                "-i",
                str(video_path),
                "-vf",
                "thumbnail,scale=768:-1",
                "-frames:v",
                "1",
                str(frame_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0 and frame_path.exists()
