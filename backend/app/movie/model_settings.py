from __future__ import annotations

import copy
import re
from typing import Any

from .config import Settings


TASK_IDS = (
    "scenario_assistant",
    "beat_board_generation",
    "character_extraction",
    "scene_generation",
    "scene_image_prompt_generation",
    "sequence_generation",
    "wan_prompt_generation",
    "continuity_review",
)

TASK_LABELS = {
    "scenario_assistant": "Scenario Assistant",
    "beat_board_generation": "Beat Board Generation",
    "character_extraction": "Character Extraction",
    "scene_generation": "Scene Generation",
    "scene_image_prompt_generation": "Scene Image Prompt Generation",
    "sequence_generation": "Sequence Generation",
    "wan_prompt_generation": "Wan Prompt Generation",
    "continuity_review": "Continuity Review",
}

TASK_VARIABLES = {
    "scenario_assistant": [
        "project.name",
        "project.genre",
        "project.tone",
        "project.target_duration_s",
        "project.scenario_text",
        "focus",
        "instruction",
        "rewrite_scenario",
        "max_suggestions",
    ],
    "scene_generation": [
        "project.name",
        "project.genre",
        "project.tone",
        "project.target_duration_s",
        "project.scenario_text",
    ],
    "beat_board_generation": [
        "project.name",
        "project.genre",
        "project.tone",
        "project.target_duration_s",
        "project.scenario_text",
    ],
    "character_extraction": [
        "project.name",
        "project.genre",
        "project.tone",
        "project.scenario_text",
    ],
    "scene_image_prompt_generation": [
        "project.name",
        "project.genre",
        "project.tone",
        "project.target_duration_s",
        "project.characters",
        "style_anchor_text",
        "scene.id",
        "scene.order",
        "scene.title",
        "scene.target_duration_s",
        "scene.narrative_text",
    ],
    "sequence_generation": [
        "project.name",
        "project.genre",
        "project.tone",
        "project.target_duration_s",
        "scene.id",
        "scene.order",
        "scene.title",
        "scene.target_duration_s",
        "scene.narrative_text",
    ],
    "wan_prompt_generation": [
        "project.name",
        "project.genre",
        "project.tone",
        "project.target_duration_s",
        "project.characters",
        "style_anchor_text",
        "scene.id",
        "scene.order",
        "scene.title",
        "scene.target_duration_s",
        "scene.narrative_text",
        "scene.first_image_prompt_text",
        "scene.reference_image_available",
        "sequence.id",
        "sequence.order",
        "sequence.absolute_order",
        "sequence.title",
        "sequence.target_duration_s",
        "sequence.narrative_text",
        "sequence.camera_direction",
        "sequence.action_direction",
    ],
    "continuity_review": [
        "project.name",
        "project.genre",
        "project.tone",
        "style_anchor_text",
        "scene.id",
        "scene.order",
        "scene.title",
        "scene.target_duration_s",
        "scene.narrative_text",
        "scene.first_image_prompt_text",
        "scene.reference_image_available",
        "review_context",
    ],
}

DEFAULT_INSTRUCTION = "Improve the story while keeping it filmable and emotionally clear."
TOKEN_PATTERN = re.compile(r"{{\s*([a-zA-Z0-9_.]+)\s*}}")


def _default_task_profiles() -> dict[str, dict]:
    return {
        "scenario_assistant": {
            "model_override": None,
            "temperature_override": None,
            "top_p_override": None,
            "max_output_tokens_override": None,
            "system_template": "",
            "user_template": """
You are a local screenplay development assistant. Respond with JSON only.

Help develop this movie scenario for a 3 to 5 minute short film.
Return valid JSON only with keys:
- summary
- revised_scenario_text
- suggestions
- beat_notes
- title_options

Rules:
- Keep suggestions concrete and production-oriented.
- Tailor advice to the requested focus.
- Provide {{max_suggestions}} suggestions.
- Provide 4 to 6 beat_notes.
- Provide 3 title_options.
- If rewrite_scenario is false, revised_scenario_text must repeat the original scenario_text exactly.
- If rewrite_scenario is true, deliver a cleaner, stronger scenario while preserving the core premise.

Project name: {{project.name}}
Genre: {{project.genre}}
Tone: {{project.tone}}
Target duration seconds: {{project.target_duration_s}}
Focus: {{focus}}
Instruction: {{instruction}}
Rewrite scenario: {{rewrite_scenario}}

Scenario:
{{project.scenario_text}}
""".strip(),
        },
        "beat_board_generation": {
            "model_override": None,
            "temperature_override": None,
            "top_p_override": None,
            "max_output_tokens_override": None,
            "system_template": "",
            "user_template": """
You are helping prepare a short film before scene generation.
Create a 3-act beat board for this 3 to 5 minute movie.
Return only valid JSON as an array.
Return 8 to 10 beats total.
Each item must include:
- act_index
- order_index
- title
- summary_text
- purpose_text
- source

Rules:
- act_index must be 1, 2, or 3.
- order_index starts at 1 within each act.
- source must be "generated".
- Keep beats practical for scene generation and short-film pacing.
- Use concise, filmable language.

Project:
- Name: {{project.name}}
- Genre: {{project.genre}}
- Tone: {{project.tone}}
- Target duration seconds: {{project.target_duration_s}}

Scenario:
{{project.scenario_text}}
""".strip(),
        },
        "character_extraction": {
            "model_override": None,
            "temperature_override": None,
            "top_p_override": None,
            "max_output_tokens_override": None,
            "system_template": "",
            "user_template": """
Extract the main characters from the movie scenario.
Return only valid JSON as an array of objects.
Each object must include:
- name: The character's name.
- role_summary: A brief description of their role in the story.
- prompt_tags: A comma-separated list of visual tags describing their appearance. Follow the NoobAI-XL format: use Danbooru-style tags (e.g. "1girl, solo, blue hair, trench coat"), replace underscores with spaces, and escape parentheses with backslashes (e.g. "ganyu \\(genshin impact\\)"). Focus on identity-locking features: hair color, hair style, eye color, signature clothing, physical build, and approximate age. Do NOT include quality tags or natural language sentences.

Project name: {{project.name}}
Genre: {{project.genre}}
Tone: {{project.tone}}

Scenario:
{{project.scenario_text}}
""".strip(),
        },
        "scene_generation": {
            "model_override": None,
            "temperature_override": None,
            "top_p_override": None,
            "max_output_tokens_override": None,
            "system_template": "",
            "user_template": """
You are helping prepare a 3 to 5 minute short movie.
Split the scenario into 3 to 4 major scenes.
Return only valid JSON as an array.
Each item must include title, narrative_text, target_duration_s.
Every target_duration_s must be an integer between 30 and 90.
The total duration should stay close to {{project.target_duration_s}} seconds.
Scenario:
{{project.scenario_text}}
""".strip(),
        },
        "scene_image_prompt_generation": {
            "model_override": None,
            "temperature_override": None,
            "top_p_override": None,
            "max_output_tokens_override": None,
            "system_template": "",
            "user_template": """
Create the first-image prompt for this movie scene.
Return only valid JSON as an object.
The object must include scene_id and first_image_prompt_text.

The first_image_prompt_text MUST strictly follow the NoobAI tag-based prompting format:
- Use a comma-separated list of tags (e.g., "1girl, solo, blue hair"). Do NOT use natural language sentences.
- DO NOT use underscores in tags (e.g., use "blue hair" instead of "blue_hair"). Replace all underscores with spaces.
- Place quality and aesthetic tags at the very beginning of the prompt. ALWAYS start the prompt with exactly this prefix:
  "very awa, masterpiece, best quality, year 2024, newest, highres, absurdres, "
- Follow the prefix with a logical order of tags: subject (e.g., 1girl, 1boy, character name), series, artist style, general descriptive tags, and finally background/setting tags.
- Escape any parentheses used in specific tags (e.g., "ganyu \\(genshin impact\\)").

Project Characters:
{{project.characters}}

These prompts are for still images that define scene-level continuity before sequence generation.
Style anchor:
{{style_anchor_text}}
Scene:
{
  "scene_id": "{{scene.id}}",
  "order": {{scene.order}},
  "title": "{{scene.title}}",
  "target_duration_s": {{scene.target_duration_s}},
  "narrative_text": "{{scene.narrative_text}}"
}
""".strip(),
        },
        "sequence_generation": {
            "model_override": None,
            "temperature_override": None,
            "top_p_override": None,
            "max_output_tokens_override": None,
            "system_template": "",
            "user_template": """
Split this movie scene into 5 to 10 second sequences.
Return only valid JSON as an array.
Each item must include title, narrative_text, target_duration_s, camera_direction, action_direction.
Every target_duration_s must be an integer between 5 and 10.
The total duration should stay close to {{scene.target_duration_s}} seconds.
Scene:
{
  "title": "{{scene.title}}",
  "target_duration_s": {{scene.target_duration_s}},
  "narrative_text": "{{scene.narrative_text}}"
}
""".strip(),
        },
        "wan_prompt_generation": {
            "model_override": None,
            "temperature_override": 0.25,
            "top_p_override": 0.85,
            "max_output_tokens_override": 700,
            "system_template": "",
            "user_template": """
Create a Wan 2.2 prompt for this sequence.
Return only valid JSON as an object with keys:
- sequence_id
- camera_direction
- action_direction
- wan_prompt_text

The wan_prompt_text must be one plain image-to-video prompt string, not labeled sections.
Use short sentences and keep it concise, around 60 to 110 words.
For image-to-video, prioritize motion description and camera movement while preserving scene continuity.
Do not mention filenames, uploads, JSON, headings, bullet labels, or negative-prompt framing.
Use this order inside the final prompt:
1. scene reference continuity anchor
2. exact cast/count and identity lock when relevant
3. essential setting, time, or lighting anchors only when needed
4. framing, camera, and lens language
5. a short action timeline across the clip
6. positive motion boundaries
7. style tail

If camera_direction or action_direction are weak, improve them before returning.

Project Characters:
{{project.characters}}

Style anchor:
{{style_anchor_text}}
Scene:
{
  "scene_id": "{{scene.id}}",
  "order": {{scene.order}},
  "title": "{{scene.title}}",
  "first_image_prompt_text": "{{scene.first_image_prompt_text}}",
  "reference_image_available": "{{scene.reference_image_available}}",
  "narrative_text": "{{scene.narrative_text}}"
}
Sequence:
{
  "sequence_id": "{{sequence.id}}",
  "title": "{{sequence.title}}",
  "target_duration_s": {{sequence.target_duration_s}},
  "narrative_text": "{{sequence.narrative_text}}",
  "camera_direction": "{{sequence.camera_direction}}",
  "action_direction": "{{sequence.action_direction}}"
}
""".strip(),
        },
        "continuity_review": {
            "model_override": None,
            "temperature_override": 0.2,
            "top_p_override": 0.85,
            "max_output_tokens_override": 900,
            "system_template": "",
            "user_template": """
You are reviewing continuity for a short-film scene.
Return only valid JSON as an object with keys:
- summary_text
- findings
- sequence_suggestions

Each item in findings must include:
- category
- severity
- summary_text
- detail_text
- sequence_id
- confidence

Each item in sequence_suggestions must include:
- sequence_id
- suggested_prompt_fix
- rationale

Valid categories: identity, wardrobe, location, lighting, props, camera, action, missing_media
Valid severities: info, warning, issue
Keep suggestions advisory. Do not overwrite prompts automatically.

Project:
- Name: {{project.name}}
- Genre: {{project.genre}}
- Tone: {{project.tone}}

Style anchor:
{{style_anchor_text}}

Scene:
- ID: {{scene.id}}
- Order: {{scene.order}}
- Title: {{scene.title}}
- Duration seconds: {{scene.target_duration_s}}
- Narrative: {{scene.narrative_text}}
- First image prompt: {{scene.first_image_prompt_text}}
- Reference image available: {{scene.reference_image_available}}

Review context:
{{review_context}}
""".strip(),
        },
    }


def default_generation_defaults() -> dict:
    return {
        "temperature": 0.4,
        "top_p": 0.9,
        "top_k": 40,
        "min_p": 0.05,
        "repeat_penalty": 1.05,
        "max_output_tokens": 1600,
        "seed": None,
        "stop_sequences": [],
        "json_retries": 2,
        "strip_markdown_fences": True,
        "fallback_to_heuristics": True,
    }


def default_project_model_settings_override() -> dict:
    return {
        "enabled": False,
        "default_model_override": None,
        "generation_defaults_override": {
            "temperature": None,
            "top_p": None,
            "top_k": None,
            "min_p": None,
            "repeat_penalty": None,
            "max_output_tokens": None,
            "seed": None,
            "stop_sequences": None,
            "json_retries": None,
            "strip_markdown_fences": None,
            "fallback_to_heuristics": None,
        },
        "task_profiles": {
            task_id: {
                "model_override": None,
                "temperature_override": None,
                "top_p_override": None,
                "max_output_tokens_override": None,
                "system_template": None,
                "user_template": None,
            }
            for task_id in TASK_IDS
        },
    }


def build_default_model_settings(settings: Settings, legacy_runtime: dict | None = None) -> dict:
    runtime = {
        "provider": settings.scenario_assistant_provider,
        "base_url": settings.scenario_assistant_base_url,
        "api_key": settings.scenario_assistant_api_key or "",
        "default_model": settings.scenario_assistant_model,
        "timeout_s": settings.scenario_assistant_timeout_s,
    }
    if legacy_runtime:
        runtime.update(
            {
                "provider": legacy_runtime.get("provider", runtime["provider"]),
                "base_url": legacy_runtime.get("base_url", runtime["base_url"]),
                "api_key": legacy_runtime.get("api_key", runtime["api_key"]),
                "default_model": legacy_runtime.get("model", runtime["default_model"]),
                "timeout_s": int(legacy_runtime.get("timeout_s", runtime["timeout_s"])),
            }
        )
    return {
        "runtime": runtime,
        "generation_defaults": default_generation_defaults(),
        "task_profiles": _default_task_profiles(),
    }


def build_task_catalog() -> list[dict]:
    return [
        {
            "id": task_id,
            "label": TASK_LABELS[task_id],
            "variables": TASK_VARIABLES[task_id],
        }
        for task_id in TASK_IDS
    ]


def _deep_merge(base: dict, overrides: dict | None) -> dict:
    result = copy.deepcopy(base)
    if not overrides:
        return result
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def normalize_model_settings(raw_value: dict | None, settings: Settings, legacy_runtime: dict | None = None) -> dict:
    merged = _deep_merge(build_default_model_settings(settings, legacy_runtime), raw_value or {})
    runtime = merged["runtime"]
    runtime["provider"] = str(runtime.get("provider", "ollama")).strip().lower() or "ollama"
    if runtime["provider"] in {"openai", "openai-compatible"}:
        runtime["provider"] = "openai_compatible"
    runtime["base_url"] = str(runtime.get("base_url", "")).strip()
    runtime["api_key"] = str(runtime.get("api_key", "") or "")
    runtime["default_model"] = str(runtime.get("default_model", "")).strip()
    runtime["timeout_s"] = int(runtime.get("timeout_s", settings.scenario_assistant_timeout_s))

    defaults = merged["generation_defaults"]
    defaults["temperature"] = float(defaults.get("temperature", 0.4))
    defaults["top_p"] = float(defaults.get("top_p", 0.9))
    defaults["top_k"] = int(defaults.get("top_k", 40))
    defaults["min_p"] = float(defaults.get("min_p", 0.05))
    defaults["repeat_penalty"] = float(defaults.get("repeat_penalty", 1.05))
    defaults["max_output_tokens"] = int(defaults.get("max_output_tokens", 1600))
    defaults["seed"] = None if defaults.get("seed") in {None, ""} else int(defaults["seed"])
    defaults["stop_sequences"] = [str(item) for item in defaults.get("stop_sequences", []) if str(item)]
    defaults["json_retries"] = int(defaults.get("json_retries", 2))
    defaults["strip_markdown_fences"] = bool(defaults.get("strip_markdown_fences", True))
    defaults["fallback_to_heuristics"] = bool(defaults.get("fallback_to_heuristics", True))

    normalized_profiles = _default_task_profiles()
    for task_id in TASK_IDS:
        source = merged.get("task_profiles", {}).get(task_id, {})
        target = normalized_profiles[task_id]
        target["model_override"] = _clean_optional_string(source.get("model_override"))
        target["temperature_override"] = _clean_optional_float(source.get("temperature_override"))
        target["top_p_override"] = _clean_optional_float(source.get("top_p_override"))
        target["max_output_tokens_override"] = _clean_optional_int(source.get("max_output_tokens_override"))
        target["system_template"] = str(source.get("system_template", target["system_template"]))
        target["user_template"] = str(source.get("user_template", target["user_template"]))
    merged["task_profiles"] = normalized_profiles
    return merged


def normalize_project_model_settings_override(raw_value: dict | None) -> dict:
    merged = _deep_merge(default_project_model_settings_override(), raw_value or {})
    merged["enabled"] = bool(merged.get("enabled", False))
    merged["default_model_override"] = _clean_optional_string(merged.get("default_model_override"))

    defaults_override = merged["generation_defaults_override"]
    defaults_override["temperature"] = _clean_optional_float(defaults_override.get("temperature"))
    defaults_override["top_p"] = _clean_optional_float(defaults_override.get("top_p"))
    defaults_override["top_k"] = _clean_optional_int(defaults_override.get("top_k"))
    defaults_override["min_p"] = _clean_optional_float(defaults_override.get("min_p"))
    defaults_override["repeat_penalty"] = _clean_optional_float(defaults_override.get("repeat_penalty"))
    defaults_override["max_output_tokens"] = _clean_optional_int(defaults_override.get("max_output_tokens"))
    defaults_override["seed"] = _clean_optional_int(defaults_override.get("seed"))
    stop_sequences = defaults_override.get("stop_sequences")
    if isinstance(stop_sequences, list):
        defaults_override["stop_sequences"] = [str(item) for item in stop_sequences if str(item)]
    else:
        defaults_override["stop_sequences"] = None
    for key in ("json_retries",):
        defaults_override[key] = _clean_optional_int(defaults_override.get(key))
    for key in ("strip_markdown_fences", "fallback_to_heuristics"):
        value = defaults_override.get(key)
        defaults_override[key] = None if value is None else bool(value)

    normalized_profiles = default_project_model_settings_override()["task_profiles"]
    for task_id in TASK_IDS:
        source = merged.get("task_profiles", {}).get(task_id, {})
        target = normalized_profiles[task_id]
        target["model_override"] = _clean_optional_string(source.get("model_override"))
        target["temperature_override"] = _clean_optional_float(source.get("temperature_override"))
        target["top_p_override"] = _clean_optional_float(source.get("top_p_override"))
        target["max_output_tokens_override"] = _clean_optional_int(source.get("max_output_tokens_override"))
        target["system_template"] = source.get("system_template") if source.get("system_template") is not None else None
        target["user_template"] = source.get("user_template") if source.get("user_template") is not None else None
    merged["task_profiles"] = normalized_profiles
    return merged


def resolve_model_settings(global_settings: dict, project_override: dict | None = None) -> dict:
    resolved = copy.deepcopy(global_settings)
    override = normalize_project_model_settings_override(project_override)
    if not override["enabled"]:
        return resolved

    if override["default_model_override"]:
        resolved["runtime"]["default_model"] = override["default_model_override"]

    for key, value in override["generation_defaults_override"].items():
        if value is not None:
            resolved["generation_defaults"][key] = value

    for task_id in TASK_IDS:
        task_override = override["task_profiles"][task_id]
        task_profile = resolved["task_profiles"][task_id]
        for key, value in task_override.items():
            if value is not None:
                task_profile[key] = value
    return resolved


def resolve_task_config(model_settings: dict, task_id: str) -> dict:
    runtime = copy.deepcopy(model_settings["runtime"])
    defaults = copy.deepcopy(model_settings["generation_defaults"])
    profile = copy.deepcopy(model_settings["task_profiles"][task_id])
    model_name = profile["model_override"] or runtime["default_model"]
    parameters = {
        "model": model_name,
        "temperature": profile["temperature_override"]
        if profile["temperature_override"] is not None
        else defaults["temperature"],
        "top_p": profile["top_p_override"] if profile["top_p_override"] is not None else defaults["top_p"],
        "top_k": defaults["top_k"],
        "min_p": defaults["min_p"],
        "repeat_penalty": defaults["repeat_penalty"],
        "max_output_tokens": profile["max_output_tokens_override"]
        if profile["max_output_tokens_override"] is not None
        else defaults["max_output_tokens"],
        "seed": defaults["seed"],
        "stop_sequences": defaults["stop_sequences"],
        "json_retries": defaults["json_retries"],
        "strip_markdown_fences": defaults["strip_markdown_fences"],
        "fallback_to_heuristics": defaults["fallback_to_heuristics"],
    }
    runtime["model"] = parameters["model"]
    return {
        "runtime": runtime,
        "profile": profile,
        "parameters": parameters,
    }


def flatten_template_context(context: dict[str, Any]) -> dict[str, str]:
    flattened: dict[str, str] = {}

    def visit(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                next_prefix = f"{prefix}.{key}" if prefix else str(key)
                visit(next_prefix, nested)
            return
        if value is None:
            flattened[prefix] = ""
            return
        if isinstance(value, bool):
            flattened[prefix] = "true" if value else "false"
            return
        if isinstance(value, list):
            flattened[prefix] = ", ".join(str(item) for item in value)
            return
        flattened[prefix] = str(value)

    visit("", context)
    return flattened


def render_template(template: str, context: dict[str, Any]) -> tuple[str, dict[str, str]]:
    flattened = flatten_template_context(context)
    used: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        token = match.group(1)
        if token not in flattened:
            raise KeyError(token)
        used[token] = flattened[token]
        return flattened[token]

    return TOKEN_PATTERN.sub(replace, template), used


def render_task_prompts(model_settings: dict, task_id: str, context: dict[str, Any]) -> dict:
    task_config = resolve_task_config(model_settings, task_id)
    system_prompt, system_used = render_template(task_config["profile"]["system_template"], context)
    user_prompt, user_used = render_template(task_config["profile"]["user_template"], context)
    return {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "rendered_variables": {**system_used, **user_used},
        "task_config": task_config,
    }


def preview_sample_context(task_id: str) -> dict[str, Any]:
    project = {
        "name": "Sample Movie",
        "genre": "cinematic drama",
        "tone": "grounded and atmospheric",
        "target_duration_s": 240,
        "scenario_text": (
            "A courier crosses the city before dawn, uncovers a buried confession, and must decide whether to deliver "
            "it to the only witness still awake."
        ),
    }
    scene = {
        "id": "scene-sample-01",
        "order": 1,
        "title": "01. Tram Depot",
        "target_duration_s": 60,
        "narrative_text": "The courier enters the tram depot, realizes the witness is already there, and commits to the handoff.",
        "first_image_prompt_text": "very awa, masterpiece, best quality, year 2024, newest, highres, absurdres, 1girl, 1boy, courier, witness, rain-slick tram depot at dawn, cold industrial lighting, distance, cinematic lighting",
        "first_image_asset": {
            "original_filename": "scene-reference.jpg",
        },
        "reference_image_available": "true",
    }
    sequence = {
        "id": "sequence-sample-01",
        "order": 1,
        "absolute_order": 1,
        "title": "01.01 Entering The Depot",
        "target_duration_s": 8,
        "narrative_text": "The courier crosses the threshold, clocks the witness, and tightens their grip on the envelope.",
        "camera_direction": "slow dolly inward from the depot entrance toward the waiting witness",
        "action_direction": "the courier hesitates, then walks deeper into the depot with rising resolve",
    }
    context = {
        "project": project,
        "scene": scene,
        "sequence": sequence,
        "style_anchor_text": (
            "Consistency guide for a grounded cinematic drama. Preserve identity, wardrobe, props, location logic, and lighting continuity."
        ),
        "review_context": (
            "Reference image: available. Sequence 01 uploaded. Sequence 02 missing upload. Adjacent framing drifts from medium tracking shot "
            "to extreme handheld close-up without a motivating beat."
        ),
        "focus": "rewrite",
        "instruction": DEFAULT_INSTRUCTION,
        "rewrite_scenario": "yes",
        "max_suggestions": 4,
    }
    if task_id == "scenario_assistant":
        return context
    if task_id == "scene_generation":
        return context
    if task_id == "scene_image_prompt_generation":
        return context
    if task_id == "sequence_generation":
        return context
    return context


def _clean_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _clean_optional_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    return float(value)


def _clean_optional_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    return int(value)
