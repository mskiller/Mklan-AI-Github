from __future__ import annotations

import copy
import re
from typing import Any

from .config import Settings


TASK_IDS = (
    "scenario_generation",
    "character_card_generation",
    "lore_generation",
    "user_profile_generation",
    "game_master_card_generation",
    "image_prompt_generation",
)

TASK_LABELS = {
    "scenario_generation": "Scenario Generation",
    "character_card_generation": "Character Card Generation",
    "lore_generation": "Lore Generation",
    "user_profile_generation": "User Profile Generation",
    "game_master_card_generation": "Game Master Card Generation",
    "image_prompt_generation": "Image Prompt Generation",
}

TASK_VARIABLES = {
    "scenario_generation": [
        "project.name",
        "project.seed_sentence",
        "project.scenario_text",
        "project.genre",
        "project.tone",
        "project.mode",
        "project.game_master_pattern",
        "project.user_role_hint",
        "project.sample_character_role_hint",
        "project.scenario_focus",
        "instruction",
    ],
    "character_card_generation": [
        "project.name",
        "project.seed_sentence",
        "project.scenario_text",
        "project.genre",
        "project.tone",
        "project.mode",
        "project.target_count",
        "project.game_master_pattern",
        "project.user_name",
        "project.user_role_summary",
        "project.user_role_hint",
        "project.sample_character_role_hint",
        "instruction",
    ],
    "lore_generation": [
        "project.name",
        "project.seed_sentence",
        "project.scenario_text",
        "project.genre",
        "project.tone",
        "project.mode",
        "project.character_names",
        "project.user_role_summary",
        "project.scenario_focus",
        "instruction",
    ],
    "user_profile_generation": [
        "project.name",
        "project.seed_sentence",
        "project.scenario_text",
        "project.genre",
        "project.tone",
        "project.mode",
        "project.game_master_pattern",
        "project.character_names",
        "project.user_name",
        "project.user_role_summary",
        "project.user_role_hint",
        "project.scenario_focus",
        "instruction",
    ],
    "game_master_card_generation": [
        "project.name",
        "project.seed_sentence",
        "project.scenario_text",
        "project.genre",
        "project.tone",
        "project.character_names",
        "project.user_name",
        "project.user_role_summary",
        "project.user_role_hint",
        "project.scenario_focus",
        "instruction",
    ],
    "image_prompt_generation": [
        "project.name",
        "project.genre",
        "project.tone",
        "project.scenario_text",
        "subject.type",
        "subject.shot_type",
        "subject.name",
        "subject.description",
        "subject.appearance_summary",
        "subject.booru_character_tag",
        "style_profile",
        "style_guide",
        "instruction",
    ],
}

DEFAULT_INSTRUCTION = "Keep outputs coherent, roleplay-ready, and concise where possible."
TOKEN_PATTERN = re.compile(r"{{\s*([a-zA-Z0-9_.]+)\s*}}")


def _default_task_profiles() -> dict[str, dict]:
    return {
        "scenario_generation": {
            "model_override": None,
            "temperature_override": None,
            "top_p_override": None,
            "max_output_tokens_override": None,
            "system_template": """
You write compact, high-signal SillyTavern scenario setup text.
Return strict JSON only and never include markdown fences.
""".strip(),
            "user_template": """
Task: Produce the scenario foundation for a SillyTavern project.

Output JSON schema:
{
  "scenario_text": "string",
  "title_suggestion": "string"
}

Constraints:
- JSON only.
- No markdown, no commentary, no XML.
- Keep the scenario specific, playable, and oriented around recurring roleplay turns.
- In character mode, write context that supports one or more focused character cards.
- In game_master mode, write the user-facing play loop that the GM will run.
- In game_master mode, the user is the active role in the scenario, never a passive spectator.
- In game_master mode, use {{user}} for the player's role and reserve {{char}} for the GM/narrator card.

Project:
- Name: {{project.name}}
- Mode: {{project.mode}}
- Genre: {{project.genre}}
- Tone: {{project.tone}}
- Seed sentence: {{project.seed_sentence}}
- Existing scenario: {{project.scenario_text}}
- GM pattern: {{project.game_master_pattern}}
- User role hint: {{project.user_role_hint}}
- Sample character role hint: {{project.sample_character_role_hint}}
- Scenario focus: {{project.scenario_focus}}
- Extra instruction: {{instruction}}
""".strip(),
        },
        "character_card_generation": {
            "model_override": None,
            "temperature_override": None,
            "top_p_override": None,
            "max_output_tokens_override": None,
            "system_template": """
You create SillyTavern-compatible character card data.
Return strict JSON only and never include markdown fences.
""".strip(),
            "user_template": """
Task: Produce SillyTavern character card objects.

Return JSON only as:
{
  "characters": [
    {
      "name": "string",
      "description": "string",
      "personality": "string",
      "scenario": "string",
      "first_message": "string",
      "example_dialogue": "string",
      "tags": ["string"],
      "creator_notes": "string",
      "system_prompt": "string",
      "post_history_instructions": "string",
      "alternate_greetings": ["string"],
      "creator": "string",
      "character_version": "string",
      "character_note": "string",
      "character_note_depth": 4,
      "character_note_role": "system",
      "talkativeness": 0.5,
      "appearance_summary": "string",
      "booru_character_name": "string",
      "booru_copyright": "string"
    }
  ]
}

Field responsibilities:
- description: stable identity, background, competencies, motivations.
- personality: concise behavioral summary.
- scenario: how this character fits the current project.
- first_message: greeting/opening line.
- example_dialogue: short style sample, suitable for ST.
- character_note: a compact depth prompt / author note for this character when useful.
- talkativeness: 0.0 to 1.0.

Rules:
- JSON only.
- No markdown, no commentary.
- In character mode, create the featured characters for the project.
- In game_master mode, never create the user persona.
- In game_master mode, never create the GM narrator as a character.
- In game_master mode, create exactly {{project.target_count}} supporting sample characters or encounter examples.
- In game_master mode, each sample character must serve the user's role loop instead of replacing it.
- In tavern game_master projects, sample characters are customers, visitors, staff, heroes, rumor-bringers, or other NPCs; they are not the tavern owner.
- Favor variety across the returned sample set.

Project:
- Name: {{project.name}}
- Mode: {{project.mode}}
- Requested character count: {{project.target_count}}
- Seed sentence: {{project.seed_sentence}}
- Genre: {{project.genre}}
- Tone: {{project.tone}}
- Scenario text: {{project.scenario_text}}
- GM pattern: {{project.game_master_pattern}}
- User name: {{project.user_name}}
- User role summary: {{project.user_role_summary}}
- User role hint: {{project.user_role_hint}}
- Sample character role hint: {{project.sample_character_role_hint}}
- Extra instruction: {{instruction}}
""".strip(),
        },
        "lore_generation": {
            "model_override": None,
            "temperature_override": None,
            "top_p_override": None,
            "max_output_tokens_override": None,
            "system_template": """
You create SillyTavern lorebook entries with valid world-info structure.
Return strict JSON only and never include markdown fences.
""".strip(),
            "user_template": """
Task: Produce SillyTavern lorebook entries.

Return JSON only as:
{
  "lore_entries": [
    {
      "name": "string",
      "keys": ["string"],
      "secondary_keys": ["string"],
      "content": "string",
      "comment": "string",
      "enabled": true,
      "insertion_order": 100,
      "position": "before_char",
      "constant": false,
      "selective_logic": 0,
      "probability": 100,
      "case_sensitive": false,
      "priority": 0,
      "scan_depth": null,
      "match_whole_words": null,
      "group": "",
      "group_weight": 100,
      "prevent_recursion": true,
      "delay_until_recursion": false,
      "character_filter_json": "",
      "automation_id": "",
      "role": "system",
      "extensions_json": "{}"
    }
  ]
}

Rules:
- JSON only.
- No markdown, no commentary.
- Use only these positions: before_char, after_char, before_examples, after_examples.
- Write trigger-ready entries with strong keys and compact, useful content.
- Prefer sensible defaults for advanced settings unless the scenario strongly suggests otherwise.
- character_filter_json and extensions_json must be JSON strings, not nested objects.

Project:
- Name: {{project.name}}
- Mode: {{project.mode}}
- Seed sentence: {{project.seed_sentence}}
- Characters: {{project.character_names}}
- User role summary: {{project.user_role_summary}}
- Scenario: {{project.scenario_text}}
- Scenario focus: {{project.scenario_focus}}
- Extra instruction: {{instruction}}
""".strip(),
        },
        "user_profile_generation": {
            "model_override": None,
            "temperature_override": None,
            "top_p_override": None,
            "max_output_tokens_override": None,
            "system_template": """
You create SillyTavern user persona data.
Return strict JSON only and never include markdown fences.
""".strip(),
            "user_template": """
Task: Produce a SillyTavern persona for the user.

Return JSON only as:
{
  "name": "string",
  "description": "string",
  "title": "string",
  "personality": "string",
  "scenario_role": "string",
  "first_message": "string",
  "tags": ["string"],
  "persona_note": "string",
  "persona_note_depth": 4,
  "persona_note_role": "system",
  "appearance_summary": "string",
  "booru_character_name": "string",
  "booru_copyright": "string"
}

Rules:
- JSON only.
- No markdown, no commentary.
- In character mode, create a persona that can interact naturally with the featured character set.
- In game_master mode, create the player's active in-world role.
- In game_master mode, the user must have agency, responsibility, or a clear reason to act.
- In tavern game_master projects, the user persona is the tavern owner/barkeep; never assign that role to the GM card.
- persona_note should be a short author-note style reminder that reinforces the user's role.

Project:
- Name: {{project.name}}
- Mode: {{project.mode}}
- Seed sentence: {{project.seed_sentence}}
- GM pattern: {{project.game_master_pattern}}
- Characters: {{project.character_names}}
- Existing user name: {{project.user_name}}
- Existing user role summary: {{project.user_role_summary}}
- User role hint: {{project.user_role_hint}}
- Scenario: {{project.scenario_text}}
- Scenario focus: {{project.scenario_focus}}
- Extra instruction: {{instruction}}
""".strip(),
        },
        "game_master_card_generation": {
            "model_override": None,
            "temperature_override": None,
            "top_p_override": None,
            "max_output_tokens_override": None,
            "system_template": """
You create GM-first SillyTavern scenario cards for instruct-tuned local models.
Return strict JSON only and never include markdown fences.
""".strip(),
            "user_template": """
Task: Produce the primary GM / narrator card for this project.

Return JSON only as:
{
  "name": "string",
  "description": "string",
  "personality": "string",
  "scenario": "string",
  "first_message": "string",
  "example_dialogue": "string",
  "tags": ["string"],
  "creator_notes": "string",
  "system_prompt": "string",
  "post_history_instructions": "string",
  "alternate_greetings": ["string"],
  "creator": "string",
  "character_version": "string",
  "character_note": "string",
  "character_note_depth": 4,
  "character_note_role": "system",
  "talkativeness": 0.35
}

Field responsibilities:
- description: world rules, GM contract, scenario operating logic.
- personality: narrator voice, pacing, and tone.
- scenario: current premise and the user's active role in it.
- first_message: opening scene that hands initiative to the user.
- system_prompt: compact GM behavior rules.
- post_history_instructions: hard constraints, especially never speaking or choosing for the user.
- character_note: short depth prompt / scenario memo.

Rules:
- JSON only.
- No markdown, no commentary.
- This card is the GM, not a participant character.
- In every field, define {{char}} as the GM/narrator and define {{user}} as the active player role.
- Never write the GM card as {{user}}, the player persona, the tavern owner, the explorer, or any other player role.
- Keep the user as the active protagonist role inside the scenario.
- Sample characters are supporting NPC references only.
- The GM must never decide the user's actions, dialogue, thoughts, or feelings.
- Use strong scene framing and forward momentum.
- For tavern projects, {{user}} owns the tavern; {{char}} generates customers and plays them as NPCs as they come and go.

Project:
- Name: {{project.name}}
- Seed sentence: {{project.seed_sentence}}
- Genre: {{project.genre}}
- Tone: {{project.tone}}
- Scenario text: {{project.scenario_text}}
- Scenario focus: {{project.scenario_focus}}
- Sample character names: {{project.character_names}}
- User persona name: {{project.user_name}}
- User role summary: {{project.user_role_summary}}
- User role hint: {{project.user_role_hint}}
- Extra instruction: {{instruction}}
""".strip(),
        },
        "image_prompt_generation": {
            "model_override": None,
            "temperature_override": None,
            "top_p_override": None,
            "max_output_tokens_override": None,
            "system_template": """
You produce Stable Diffusion prompt payloads.
Return JSON only with keys: prompt, negative_prompt.
""".strip(),
            "user_template": """
Create one production-ready prompt pair for the requested image target.
Output JSON only:
{
  "prompt": "comma-separated tags",
  "negative_prompt": "comma-separated tags"
}

Prompt rules:
- Tags first, prose never.
- Prioritize physical attributes for portrait/cowboy/fullbody character renders.
- Include framing and camera intent for the requested shot type.
- Preserve identity consistency by applying booru_character_tag when provided.
- Prefer Danbooru-style tag phrases for noobai/illustrious profiles.
- Do not include control words like "prompt", "json", or markdown.

Project: {{project.name}}
Genre: {{project.genre}}
Tone: {{project.tone}}
Scenario: {{project.scenario_text}}
Style profile: {{style_profile}}
Style guide: {{style_guide}}
Subject type: {{subject.type}}
Shot type: {{subject.shot_type}}
Subject name: {{subject.name}}
Subject description: {{subject.description}}
Subject appearance summary: {{subject.appearance_summary}}
Identity tag (booru): {{subject.booru_character_tag}}
Instruction: {{instruction}}
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
    defaults_override["json_retries"] = _clean_optional_int(defaults_override.get("json_retries"))
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
    # SillyTavern macros are valid prompt text, not model-settings tokens.
    flattened.setdefault("char", "{{char}}")
    flattened.setdefault("user", "{{user}}")
    flattened.setdefault("original", "{{original}}")
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
    context = {
        "project": {
            "name": "Sample RP World",
            "seed_sentence": "A renegade archivist enters a haunted data-vault to recover forbidden memories.",
            "scenario_text": "In a city where memory is currency, the user joins a renegade archivist to recover a stolen truth.",
            "genre": "cyber-fantasy",
            "tone": "noir and intimate",
            "mode": "character",
            "game_master_pattern": "generic_gm",
            "target_count": 3,
            "character_names": "Nyx, Curator Vale",
            "user_name": "User",
            "user_role_summary": "User is an adaptive outsider searching for the truth.",
            "user_role_hint": "The user is the active protagonist who drives the next decision.",
            "sample_character_role_hint": "Sample characters are supporting NPCs and encounter examples around the user.",
            "scenario_focus": "The scenario loop follows the user's choices through a dangerous world.",
        },
        "subject": {
            "type": "character",
            "shot_type": "portrait",
            "name": "Nyx",
            "description": "cipher archivist, poised expression, tailored coat, silver hair",
            "appearance_summary": "silver bob haircut, pale skin, amber eyes, slim build",
            "booru_character_tag": "nyx archivist (original)",
        },
        "style_profile": "noobai",
        "style_guide": "Use Danbooru-style tags with quality tags first, then identity and physical attributes.",
        "instruction": DEFAULT_INSTRUCTION,
    }
    if task_id in TASK_IDS:
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
