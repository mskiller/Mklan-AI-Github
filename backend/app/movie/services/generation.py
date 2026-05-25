from __future__ import annotations

from itertools import cycle
import math
import re

from ..config import Settings
from ..model_settings import render_task_prompts, resolve_task_config
from .model_runtime import LocalModelRuntime


class NarrativeStudio:
    def __init__(self, settings: Settings, runtime: LocalModelRuntime) -> None:
        self.settings = settings
        self.runtime = runtime

    def generate_beat_board(self, project: dict, model_settings: dict) -> list[dict]:
        beats = self._generate_beat_board_with_local_model(project, model_settings)
        if beats:
            return beats
        if resolve_task_config(model_settings, "beat_board_generation")["parameters"]["fallback_to_heuristics"]:
            return self._generate_beat_board_heuristic(project)
        raise RuntimeError("The configured local model did not return valid JSON for beat board generation.")

    def generate_characters(self, project: dict, model_settings: dict) -> list[dict]:
        characters = self._generate_characters_with_local_model(project, model_settings)
        if characters:
            return characters
        if resolve_task_config(model_settings, "character_extraction")["parameters"]["fallback_to_heuristics"]:
            return self._generate_characters_heuristic(project)
        raise RuntimeError("The configured local model did not return valid JSON for character extraction.")

    def generate_scenes(
        self,
        project: dict,
        model_settings: dict,
        *,
        source_text: str | None = None,
    ) -> list[dict]:
        project_input = {
            **project,
            "scenario_text": (source_text if source_text is not None else project.get("scenario_text", "")).strip(),
        }
        scenes = self._generate_scenes_with_local_model(project_input, model_settings)
        if scenes:
            return scenes
        if resolve_task_config(model_settings, "scene_generation")["parameters"]["fallback_to_heuristics"]:
            return self._generate_scenes_heuristic(project_input)
        raise RuntimeError("The configured local model did not return valid JSON for scene generation.")

    def generate_style_anchor(self, project: dict, scenes: list[dict]) -> str:
        genre = project["genre"]
        tone = project["tone"]
        return (
            f"Consistency guide for a {genre} movie with a {tone} tone. "
            "Preserve protagonist identity, wardrobe continuity, location logic, lighting mood, "
            "prop consistency, and grounded cinematic realism across all scenes and sequences."
        )

    def generate_scene_image_prompts(
        self,
        project: dict,
        scenes: list[dict],
        style_anchor_text: str,
        model_settings: dict,
    ) -> list[dict]:
        prompts = self._generate_scene_image_prompts_with_local_model(project, scenes, style_anchor_text, model_settings)
        prompt_by_scene_id = {
            str(item["scene_id"]): item
            for item in prompts
            if str(item.get("scene_id", "")).strip() and str(item.get("first_image_prompt_text", "")).strip()
        }
        if len(prompt_by_scene_id) == len(scenes):
            return [prompt_by_scene_id[scene["id"]] for scene in scenes]
        if resolve_task_config(model_settings, "scene_image_prompt_generation")["parameters"]["fallback_to_heuristics"]:
            for scene in scenes:
                if scene["id"] not in prompt_by_scene_id:
                    prompt_by_scene_id[scene["id"]] = self._build_scene_image_prompt_heuristic(
                        scene,
                        style_anchor_text,
                    )
        if prompt_by_scene_id:
            return [prompt_by_scene_id[scene["id"]] for scene in scenes if scene["id"] in prompt_by_scene_id]
        raise RuntimeError("The configured local model did not return valid JSON for scene image prompts.")

    def generate_sequences(self, project: dict, scene: dict, model_settings: dict) -> list[dict]:
        sequences = self._generate_sequences_with_local_model(project, scene, model_settings)
        if sequences:
            return sequences
        if resolve_task_config(model_settings, "sequence_generation")["parameters"]["fallback_to_heuristics"]:
            return self._generate_sequences_heuristic(project, scene)
        raise RuntimeError("The configured local model did not return valid JSON for sequence generation.")

    def generate_wan_prompts(
        self,
        project: dict,
        scenes: list[dict],
        style_anchor_text: str,
        model_settings: dict,
    ) -> list[dict]:
        prompts = self._generate_wan_prompts_with_local_model(project, scenes, style_anchor_text, model_settings)
        bundle_by_sequence_id = {
            str(item["sequence_id"]): item
            for item in prompts
            if str(item.get("sequence_id", "")).strip() and str(item.get("wan_prompt_text", "")).strip()
        }
        if resolve_task_config(model_settings, "wan_prompt_generation")["parameters"]["fallback_to_heuristics"]:
            for scene in scenes:
                for sequence in scene.get("sequences", []):
                    if sequence["id"] not in bundle_by_sequence_id:
                        bundle_by_sequence_id[sequence["id"]] = self._build_wan_prompt_heuristic(
                            scene,
                            sequence,
                            style_anchor_text,
                        )
        if bundle_by_sequence_id:
            ordered_bundles: list[dict] = []
            for scene in scenes:
                for sequence in scene.get("sequences", []):
                    bundle = bundle_by_sequence_id.get(sequence["id"])
                    if bundle is not None:
                        ordered_bundles.append(bundle)
            return ordered_bundles
        raise RuntimeError("The configured local model did not return valid JSON for Wan prompt generation.")

    def scenario_text_from_beats(self, project: dict, beats: list[dict]) -> str:
        if not beats:
            return project.get("scenario_text", "")
        acts: list[str] = []
        for act_index in range(1, 4):
            act_beats = [beat for beat in beats if int(beat["act_index"]) == act_index]
            if not act_beats:
                continue
            lines = [f"Act {act_index}:"]
            for beat in act_beats:
                title = beat["title"].strip()
                summary = beat.get("summary_text", "").strip()
                purpose = beat.get("purpose_text", "").strip()
                line = f"{title}: {summary}" if summary else title
                if purpose:
                    line = f"{line} Purpose: {purpose}"
                lines.append(line)
            acts.append("\n".join(lines))
        return "\n\n".join(acts).strip()

    def _format_project_characters(self, project: dict) -> str:
        characters = project.get("characters", [])
        if not characters:
            return "No characters defined."
        lines = []
        for char in characters:
            lines.append(f"- {char['name']} ({char.get('role_summary', '')}): {char.get('prompt_tags', '')}")
        return "\n".join(lines)

    def _generate_scenes_with_local_model(self, project: dict, model_settings: dict) -> list[dict]:
        context = {
            "project": {
                "name": project["name"],
                "genre": project["genre"],
                "tone": project["tone"],
                "target_duration_s": project["target_duration_s"],
                "scenario_text": project.get("scenario_text", "").strip(),
            }
        }
        rendered = render_task_prompts(model_settings, "scene_generation", context)
        try:
            parsed = self.runtime.run_json(
                system_prompt=rendered["system_prompt"],
                user_prompt=rendered["user_prompt"],
                runtime_config=rendered["task_config"]["runtime"],
                parameters=rendered["task_config"]["parameters"],
            )
        except Exception:
            return []
        parsed = self._extract_list_payload(parsed, "scenes", "items", "result")
        if not isinstance(parsed, list):
            return []
        output = []
        for index, item in enumerate(parsed, start=1):
            if not isinstance(item, dict):
                return []
            try:
                output.append(
                    {
                        "title": str(item["title"]).strip() or f"Scene {index:02d}",
                        "narrative_text": str(item["narrative_text"]).strip(),
                        "target_duration_s": max(30, min(90, int(item["target_duration_s"]))),
                    }
                )
            except Exception:
                return []
        return output

    def _generate_beat_board_with_local_model(self, project: dict, model_settings: dict) -> list[dict]:
        context = {
            "project": {
                "name": project["name"],
                "genre": project["genre"],
                "tone": project["tone"],
                "target_duration_s": project["target_duration_s"],
                "scenario_text": project.get("scenario_text", "").strip(),
            }
        }
        rendered = render_task_prompts(model_settings, "beat_board_generation", context)
        try:
            parsed = self.runtime.run_json(
                system_prompt=rendered["system_prompt"],
                user_prompt=rendered["user_prompt"],
                runtime_config=rendered["task_config"]["runtime"],
                parameters=rendered["task_config"]["parameters"],
            )
        except Exception:
            return []
        parsed = self._extract_list_payload(parsed, "beats", "items", "result")
        if not isinstance(parsed, list):
            return []
        output = []
        for index, item in enumerate(parsed, start=1):
            if not isinstance(item, dict):
                return []
            try:
                output.append(
                    {
                        "act_index": max(1, min(3, int(item["act_index"]))),
                        "order_index": max(1, int(item.get("order_index", index))),
                        "title": str(item["title"]).strip() or f"Beat {index:02d}",
                        "summary_text": str(item.get("summary_text", "")).strip(),
                        "purpose_text": str(item.get("purpose_text", "")).strip(),
                        "source": str(item.get("source", "generated")).strip() or "generated",
                    }
                )
            except Exception:
                return []
        return self._normalize_generated_beats(output)

    def _generate_scene_image_prompts_with_local_model(
        self,
        project: dict,
        scenes: list[dict],
        style_anchor_text: str,
        model_settings: dict,
    ) -> list[dict]:
        output = []
        for scene in scenes:
            context = {
                "project": {
                    "name": project["name"],
                    "genre": project["genre"],
                    "tone": project["tone"],
                    "target_duration_s": project["target_duration_s"],
                    "characters": self._format_project_characters(project),
                },
                "style_anchor_text": style_anchor_text,
                "scene": {
                    "id": scene["id"],
                    "order": scene["order"],
                    "title": scene["title"],
                    "target_duration_s": scene["target_duration_s"],
                    "narrative_text": scene["narrative_text"],
                },
            }
            rendered = render_task_prompts(model_settings, "scene_image_prompt_generation", context)
            try:
                parsed = self.runtime.run_json(
                    system_prompt=rendered["system_prompt"],
                    user_prompt=rendered["user_prompt"],
                    runtime_config=rendered["task_config"]["runtime"],
                    parameters=rendered["task_config"]["parameters"],
                )
            except Exception:
                continue
            parsed = self._extract_dict_payload(parsed, "prompt", "result")
            if not isinstance(parsed, dict):
                continue
            prompt_text = self._first_present_string(
                parsed,
                "first_image_prompt_text",
                "first_image_prompt",
                "image_prompt",
                "prompt_text",
                "prompt",
            )
            if not prompt_text:
                continue
            output.append(
                {
                    "scene_id": scene["id"],
                    "first_image_prompt_text": prompt_text,
                }
            )
        return output

    def _generate_sequences_with_local_model(self, project: dict, scene: dict, model_settings: dict) -> list[dict]:
        context = {
            "project": {
                "name": project["name"],
                "genre": project["genre"],
                "tone": project["tone"],
                "target_duration_s": project["target_duration_s"],
            },
            "scene": {
                "id": scene["id"],
                "order": scene["order"],
                "title": scene["title"],
                "target_duration_s": scene["target_duration_s"],
                "narrative_text": scene["narrative_text"],
            },
        }
        rendered = render_task_prompts(model_settings, "sequence_generation", context)
        try:
            parsed = self.runtime.run_json(
                system_prompt=rendered["system_prompt"],
                user_prompt=rendered["user_prompt"],
                runtime_config=rendered["task_config"]["runtime"],
                parameters=rendered["task_config"]["parameters"],
            )
        except Exception:
            return []
        parsed = self._extract_list_payload(parsed, "sequences", "items", "result")
        if not isinstance(parsed, list):
            return []
        output = []
        for index, item in enumerate(parsed, start=1):
            if not isinstance(item, dict):
                return []
            try:
                output.append(
                    {
                        "title": str(item["title"]).strip() or f"Sequence {index:02d}",
                        "narrative_text": str(item["narrative_text"]).strip(),
                        "target_duration_s": max(5, min(10, int(item["target_duration_s"]))),
                        "camera_direction": str(item.get("camera_direction", "")).strip(),
                        "action_direction": str(item.get("action_direction", "")).strip(),
                    }
                )
            except Exception:
                return []
        return output

    def _generate_wan_prompts_with_local_model(
        self,
        project: dict,
        scenes: list[dict],
        style_anchor_text: str,
        model_settings: dict,
    ) -> list[dict]:
        bundles = []
        for scene in scenes:
            for sequence in scene.get("sequences", []):
                context = {
                    "project": {
                        "name": project["name"],
                        "genre": project["genre"],
                        "tone": project["tone"],
                        "target_duration_s": project["target_duration_s"],
                        "characters": self._format_project_characters(project),
                    },
                    "style_anchor_text": style_anchor_text,
                    "scene": {
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
                    },
                    "sequence": {
                        "id": sequence["id"],
                        "order": sequence["order"],
                        "absolute_order": sequence["absolute_order"],
                        "title": sequence["title"],
                        "target_duration_s": sequence["target_duration_s"],
                        "narrative_text": sequence["narrative_text"],
                        "camera_direction": sequence["camera_direction"],
                        "action_direction": sequence["action_direction"],
                    },
                }
                rendered = render_task_prompts(model_settings, "wan_prompt_generation", context)
                try:
                    parsed = self.runtime.run_json(
                        system_prompt=rendered["system_prompt"],
                        user_prompt=rendered["user_prompt"],
                        runtime_config=rendered["task_config"]["runtime"],
                        parameters=rendered["task_config"]["parameters"],
                    )
                except Exception:
                    continue
                parsed = self._extract_dict_payload(parsed, "prompt", "result")
                if not isinstance(parsed, dict):
                    continue
                wan_prompt_text = self._first_present_string(
                    parsed,
                    "wan_prompt_text",
                    "wan_prompt",
                    "prompt_text",
                    "prompt",
                )
                if not wan_prompt_text:
                    continue
                camera_direction = self._first_present_string(
                    parsed,
                    "camera_direction",
                    "camera",
                    "camera_move",
                ) or str(sequence.get("camera_direction", "")).strip()
                action_direction = self._first_present_string(
                    parsed,
                    "action_direction",
                    "action",
                    "motion_direction",
                ) or str(sequence.get("action_direction", "")).strip()
                bundles.append(
                    {
                        "sequence_id": sequence["id"],
                        "camera_direction": camera_direction,
                        "action_direction": action_direction,
                        "wan_prompt_text": wan_prompt_text,
                    }
                )
        return bundles

    def _build_scene_image_prompt_heuristic(self, scene: dict, style_anchor_text: str) -> dict:
        return {
            "scene_id": scene["id"],
            "first_image_prompt_text": (
                f"{style_anchor_text} Create the first still image for scene {scene['order']:02d}, "
                f"\"{scene['title']}\". Story beat: {scene['narrative_text']}. "
                "Frame the central character, location, props, and lighting clearly so the later Wan 2.2 "
                "sequence prompts can preserve continuity within this scene."
            ),
        }

    def _build_wan_prompt_heuristic(self, scene: dict, sequence: dict, style_anchor_text: str) -> dict:
        scene_reference = scene["first_image_prompt_text"].strip()
        if scene.get("first_image_asset") is not None:
            scene_reference = (
                "Use the scene reference image as the primary visual anchor and preserve its identity, "
                f"wardrobe, props, lighting, and layout. Original still prompt: {scene['first_image_prompt_text']}"
            )
        if not scene_reference:
            scene_reference = (
                f"Maintain visual continuity for scene {scene['order']:02d}, {scene['title']}, "
                f"grounded in this scene beat: {scene['narrative_text']}"
            )
        camera_direction = sequence["camera_direction"].strip() or "slow forward dolly with stable cinematic framing"
        action_direction = sequence["action_direction"].strip() or (
            "the character studies the space, notices a change, and reacts with purpose"
        )
        return {
            "sequence_id": sequence["id"],
            "camera_direction": camera_direction,
            "action_direction": action_direction,
            "wan_prompt_text": (
                f"{scene_reference}. Keep cast count and identity consistent across the clip. "
                f"Framing and camera: {camera_direction}. "
                f"Action timeline over {sequence['target_duration_s']} seconds: {action_direction}. "
                f"Sequence beat: {sequence['narrative_text']}. "
                "Motion stays believable, readable, and controlled, with coherent screen direction and stable subject scale. "
                f"Style tail: {style_anchor_text}"
            ),
        }

    def _extract_list_payload(self, parsed: object | None, *keys: str) -> list | None:
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            for key in keys:
                value = parsed.get(key)
                if isinstance(value, list):
                    return value
        return None

    def _extract_dict_payload(self, parsed: object | None, *keys: str) -> dict | None:
        if isinstance(parsed, dict):
            for key in keys:
                value = parsed.get(key)
                if isinstance(value, dict):
                    return value
            return parsed
        return None

    def _first_present_string(self, payload: dict, *keys: str) -> str:
        for key in keys:
            value = payload.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return ""

    def _generate_scenes_heuristic(self, project: dict) -> list[dict]:
        scenario_text = project["scenario_text"].strip()
        if not scenario_text:
            scenario_text = (
                "A filmmaker chases a half-remembered clue through an old district, reconstructs a missing conversation, "
                "and risks everything to finish the story before dawn."
            )
        sentences = self._split_sentences(scenario_text)
        desired_scene_count = max(3, min(4, round(project["target_duration_s"] / 75)))
        chunks = self._chunk_sentences(sentences, desired_scene_count)
        durations = self._distribute_duration(project["target_duration_s"], len(chunks), 30, 90)
        scenes = []
        for index, chunk in enumerate(chunks, start=1):
            title = self._title_from_text(chunk[0])
            narrative = " ".join(chunk)
            scenes.append(
                {
                    "title": f"{index:02d}. {title}",
                    "narrative_text": narrative,
                    "target_duration_s": durations[index - 1],
                }
            )
        return scenes

    def _generate_characters_with_local_model(self, project: dict, model_settings: dict) -> list[dict]:
        context = {
            "project": {
                "name": project["name"],
                "genre": project["genre"],
                "tone": project["tone"],
                "scenario_text": project.get("scenario_text", "").strip(),
            }
        }
        rendered = render_task_prompts(model_settings, "character_extraction", context)
        try:
            parsed = self.runtime.run_json(
                system_prompt=rendered["system_prompt"],
                user_prompt=rendered["user_prompt"],
                runtime_config=rendered["task_config"]["runtime"],
                parameters=rendered["task_config"]["parameters"],
            )
        except Exception:
            return []
        parsed = self._extract_list_payload(parsed, "characters", "items", "result")
        if not isinstance(parsed, list):
            return []
        output = []
        for index, item in enumerate(parsed, start=1):
            if not isinstance(item, dict):
                return []
            try:
                output.append(
                    {
                        "name": str(item.get("name", "")).strip() or f"Character {index:02d}",
                        "role_summary": str(item.get("role_summary", "")).strip(),
                        "prompt_tags": str(item.get("prompt_tags", "")).strip(),
                        "order_index": index,
                    }
                )
            except Exception:
                return []
        return output

    def _generate_characters_heuristic(self, project: dict) -> list[dict]:
        return []

    def _generate_beat_board_heuristic(self, project: dict) -> list[dict]:
        scenario_text = project.get("scenario_text", "").strip()
        if not scenario_text:
            scenario_text = (
                "A courier crosses the city before dawn, uncovers a buried confession, and must decide whether to "
                "deliver it to the only witness still awake."
            )
        sentences = self._split_sentences(scenario_text)
        beat_count = max(8, min(10, len(sentences) + 2))
        chunks = self._chunk_sentences(sentences, beat_count)
        beats: list[dict] = []
        for index, chunk in enumerate(chunks, start=1):
            if index <= math.ceil(len(chunks) * 0.3):
                act_index = 1
                purpose = "Set the world, introduce the protagonist, and define the destabilizing event."
            elif index <= math.ceil(len(chunks) * 0.7):
                act_index = 2
                purpose = "Escalate obstacles, deepen the conflict, and tighten the emotional stakes."
            else:
                act_index = 3
                purpose = "Deliver the climax, consequence, and final emotional turn."
            beats.append(
                {
                    "act_index": act_index,
                    "order_index": 0,
                    "title": self._title_from_text(chunk[0]),
                    "summary_text": " ".join(chunk),
                    "purpose_text": purpose,
                    "source": "generated",
                }
            )
        return self._normalize_generated_beats(beats)

    def _generate_sequences_heuristic(self, project: dict, scene: dict) -> list[dict]:
        sentences = self._split_sentences(scene["narrative_text"])
        desired_sequence_count = max(1, round(scene["target_duration_s"] / 7.5))
        chunks = self._chunk_sentences(sentences, desired_sequence_count)
        durations = self._distribute_duration(scene["target_duration_s"], len(chunks), 5, 10)
        camera_cycle = cycle(
            [
                "slow forward dolly that narrows attention on the key subject",
                "steady lateral tracking move that reveals spatial relationships",
                "locked medium-wide frame that lets the blocking play out",
                "intimate close framing with subtle handheld drift",
                "measured reveal move that discovers a new visual clue",
            ]
        )
        action_cycle = cycle(
            [
                "the character studies the environment and notices a shift",
                "the character crosses the frame with a clear objective",
                "the character commits to a gesture that changes the beat",
                "the character pauses, reads the stakes, then moves decisively",
                "the character interacts with a prop or clue that advances the scene",
            ]
        )
        sequences = []
        for index, chunk in enumerate(chunks, start=1):
            title = self._title_from_text(chunk[0])
            sequences.append(
                {
                    "title": f"{scene['order']:02d}.{index:02d} {title}",
                    "narrative_text": " ".join(chunk),
                    "target_duration_s": durations[index - 1],
                    "camera_direction": next(camera_cycle),
                    "action_direction": next(action_cycle),
                }
            )
        return sequences

    def _split_sentences(self, text: str) -> list[str]:
        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", text.replace("\n", " ").strip())
            if sentence.strip()
        ]
        return sentences or ["A cinematic beat advances the story."]

    def _chunk_sentences(self, sentences: list[str], desired_count: int) -> list[list[str]]:
        if desired_count <= 1:
            return [sentences]
        chunk_size = max(1, math.ceil(len(sentences) / desired_count))
        chunks: list[list[str]] = []
        for start in range(0, len(sentences), chunk_size):
            chunks.append(sentences[start : start + chunk_size])
        while len(chunks) < desired_count:
            chunks.append([chunks[-1][-1]])
        return chunks[:desired_count]

    def _distribute_duration(self, target_duration_s: int, item_count: int, minimum: int, maximum: int) -> list[int]:
        if item_count <= 0:
            return []
        base = max(minimum, min(maximum, round(target_duration_s / item_count)))
        durations = [base for _ in range(item_count)]
        total = sum(durations)
        index = 0
        while total < target_duration_s:
            if durations[index] < maximum:
                durations[index] += 1
                total += 1
            index = (index + 1) % item_count
            if index == 0 and all(duration >= maximum for duration in durations):
                break
        while total > target_duration_s:
            if durations[index] > minimum:
                durations[index] -= 1
                total -= 1
            index = (index + 1) % item_count
            if index == 0 and all(duration <= minimum for duration in durations):
                break
        return durations

    def _title_from_text(self, text: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9\s]", "", text)
        words = cleaned.split()
        return " ".join(words[:5]).title() or "Story Beat"

    def _normalize_generated_beats(self, beats: list[dict]) -> list[dict]:
        normalized: list[dict] = []
        grouped: dict[int, list[dict]] = {1: [], 2: [], 3: []}
        for beat in beats:
            grouped[max(1, min(3, int(beat["act_index"])))].append(beat)
        for act_index in range(1, 4):
            for order_index, beat in enumerate(grouped[act_index], start=1):
                normalized.append(
                    {
                        "act_index": act_index,
                        "order_index": order_index,
                        "title": beat["title"],
                        "summary_text": beat.get("summary_text", ""),
                        "purpose_text": beat.get("purpose_text", ""),
                        "source": beat.get("source", "generated"),
                    }
                )
        return normalized
