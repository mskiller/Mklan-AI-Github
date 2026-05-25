from __future__ import annotations

from typing import Any

from ..config import Settings
from ..model_settings import DEFAULT_INSTRUCTION, render_task_prompts, resolve_task_config
from .model_runtime import LocalModelRuntime


class ScenarioAssistant:
    def __init__(self, settings: Settings, runtime: LocalModelRuntime) -> None:
        self.settings = settings
        self.runtime = runtime

    def assist(
        self,
        *,
        project: dict,
        focus: str,
        instruction: str,
        rewrite_scenario: bool,
        max_suggestions: int,
        model_settings: dict,
    ) -> dict:
        task_config = resolve_task_config(model_settings, "scenario_assistant")
        local_result = self._assist_with_local_model(
            project=project,
            focus=focus,
            instruction=instruction,
            rewrite_scenario=rewrite_scenario,
            max_suggestions=max_suggestions,
            model_settings=model_settings,
        )
        if local_result is not None:
            return {
                **local_result,
                "source": "local_model",
                "provider": task_config["runtime"]["provider"],
                "model": task_config["runtime"]["model"],
                "focus": focus,
                "instruction": instruction,
            }

        if task_config["parameters"]["fallback_to_heuristics"]:
            fallback = self._fallback_assist(
                project=project,
                focus=focus,
                instruction=instruction,
                rewrite_scenario=rewrite_scenario,
                max_suggestions=max_suggestions,
            )
            return {
                **fallback,
                "source": "fallback",
                "provider": task_config["runtime"]["provider"],
                "model": task_config["runtime"]["model"],
                "focus": focus,
                "instruction": instruction,
            }

        raise RuntimeError("The configured local model did not return valid JSON for the scenario assistant task.")

    def test_connection(self, runtime_config: dict | None = None) -> dict:
        if runtime_config is None:
            raise ValueError("Runtime configuration is required for connection tests.")
        return self.runtime.test_connection(
            {
                "provider": runtime_config["provider"],
                "base_url": runtime_config["base_url"],
                "api_key": runtime_config.get("api_key", ""),
                "model": runtime_config["model"],
                "timeout_s": runtime_config["timeout_s"],
            }
        )

    def _assist_with_local_model(
        self,
        *,
        project: dict,
        focus: str,
        instruction: str,
        rewrite_scenario: bool,
        max_suggestions: int,
        model_settings: dict,
    ) -> dict | None:
        context = {
            "project": {
                "name": project["name"],
                "genre": project["genre"],
                "tone": project["tone"],
                "target_duration_s": project["target_duration_s"],
                "scenario_text": project.get("scenario_text", "").strip(),
            },
            "focus": focus,
            "instruction": instruction or DEFAULT_INSTRUCTION,
            "rewrite_scenario": "yes" if rewrite_scenario else "no",
            "max_suggestions": max_suggestions,
        }
        rendered = render_task_prompts(model_settings, "scenario_assistant", context)
        try:
            payload = self.runtime.run_json(
                system_prompt=rendered["system_prompt"],
                user_prompt=rendered["user_prompt"],
                runtime_config=rendered["task_config"]["runtime"],
                parameters=rendered["task_config"]["parameters"],
            )
        except Exception:
            return None
        return self._parse_assistant_payload(payload)

    def _parse_assistant_payload(self, data: object | None) -> dict | None:
        if not isinstance(data, dict):
            return None
        return {
            "summary": str(data.get("summary", "")).strip(),
            "revised_scenario_text": str(data.get("revised_scenario_text", "")).strip(),
            "suggestions": self._clean_string_list(data.get("suggestions")),
            "beat_notes": self._clean_string_list(data.get("beat_notes")),
            "title_options": self._clean_string_list(data.get("title_options")),
        }

    def _fallback_assist(
        self,
        *,
        project: dict,
        focus: str,
        instruction: str,
        rewrite_scenario: bool,
        max_suggestions: int,
    ) -> dict:
        scenario_text = project.get("scenario_text", "").strip()
        sentences = [
            sentence.strip()
            for sentence in scenario_text.replace("\n", " ").split(".")
            if sentence.strip()
        ]
        opening = sentences[0] if sentences else "Introduce the protagonist in a strong visual situation"
        middle = sentences[1] if len(sentences) > 1 else "Escalate the conflict with a concrete obstacle"
        ending = sentences[-1] if sentences else "Land the final choice on a clean emotional image"

        focus_templates = {
            "structure": [
                "Clarify the inciting incident earlier so the movie starts moving within the first 20-30 seconds.",
                "Give the middle section one visible complication that forces a harder choice.",
                "Make the ending image echo the opening image so the short feels complete.",
                "Trim abstract exposition and convert it into visible behavior or props.",
            ],
            "stakes": [
                "Name what the protagonist stands to lose if they fail in this specific night or sequence.",
                "Add one irreversible consequence to the midpoint so the ending carries pressure.",
                "Let the antagonist force a decision instead of staying passive in the background.",
                "Tie the final choice to something personal, not just plot information.",
            ],
            "character": [
                "Give the protagonist one contradiction or wound that shapes how they act in each beat.",
                "Make the emotional turn visible through a choice, gesture, or repeated object.",
                "Strengthen the relationship pressure around the protagonist so the short has human texture.",
                "End on a changed behavior, not only a solved clue.",
            ],
            "pacing": [
                "Compress the setup so the first scene reaches motion quickly.",
                "Alternate quiet observation with decisive action to keep the rhythm alive.",
                "Use one strong midpoint reversal instead of multiple smaller detours.",
                "Keep each later beat sharper and shorter than the opening setup beats.",
            ],
            "dialogue": [
                "Prefer image-driven beats and only keep dialogue that changes power or information.",
                "Cut explanatory lines that repeat what the audience can already see.",
                "Give each speaker a different rhythm so the voices do not flatten together.",
                "Let silence carry one important emotional beat before the ending.",
            ],
            "rewrite": [
                "Open on the strongest visual hook rather than background explanation.",
                "Push the central conflict into a cleaner cause-and-effect chain.",
                "Sharpen the midpoint so the ending grows naturally from it.",
                "Make the final image emotionally specific and easy to shoot.",
            ],
        }
        suggestions = focus_templates.get(focus, focus_templates["rewrite"])[:max_suggestions]
        if instruction:
            suggestions[0] = f"{instruction.strip().rstrip('.')}. Keep it grounded in visible, filmable action."

        beat_notes = [
            f"Opening beat: {opening}.",
            "Beat 2: Show the goal or desire in physical action rather than explanation.",
            f"Middle beat: {middle}.",
            "Beat 4: Force a choice that closes off the easy option.",
            f"Final beat: {ending}.",
        ]

        revised_scenario_text = scenario_text
        if rewrite_scenario:
            revised_scenario_text = self._rewrite_scenario_text(
                project=project,
                opening=opening,
                middle=middle,
                ending=ending,
            )

        return {
            "summary": (
                f"This pass strengthens the {focus} of the short while keeping it contained enough for a "
                f"{project['target_duration_s']}-second film."
            ),
            "revised_scenario_text": revised_scenario_text,
            "suggestions": suggestions,
            "beat_notes": beat_notes,
            "title_options": self._title_options(project),
        }

    def _rewrite_scenario_text(self, *, project: dict, opening: str, middle: str, ending: str) -> str:
        return (
            f"In a {project['tone']} {project['genre']} short, {opening.lower()}. "
            f"As the story tightens, {middle.lower()}. "
            f"The film builds toward a final decision where {ending.lower()}, leaving the audience with a precise emotional afterimage."
        )

    def _title_options(self, project: dict) -> list[str]:
        name = project["name"].strip() or "Short Film"
        genre_word = project["genre"].split()[0].title() if project["genre"].strip() else "Film"
        return [
            name,
            f"{name}: First Cut",
            f"The {genre_word} Hour",
        ]

    def _clean_string_list(self, raw_value: Any) -> list[str]:
        if not isinstance(raw_value, list):
            return []
        cleaned = [str(item).strip() for item in raw_value if str(item).strip()]
        return cleaned
