from __future__ import annotations

import json
import re
from typing import Any

from ..model_settings import DEFAULT_INSTRUCTION, render_task_prompts, resolve_task_config
from app.movie.services.model_runtime import LocalModelRuntime


class CardGenerationService:
    def __init__(self, runtime: LocalModelRuntime) -> None:
        self.runtime = runtime

    def _build_project_prompt_context(
        self,
        project: dict,
        *,
        target_count: int | None = None,
        character_names: list[str] | None = None,
    ) -> dict[str, Any]:
        project_mode = str(project.get("project_mode", "character") or "character")
        pattern = self._infer_game_master_pattern(project)
        user_profile = self._effective_user_profile(project, project_mode=project_mode)
        user_name = str(user_profile.get("name", "") or "User").strip() or "User"
        user_role_summary = self._user_role_summary(user_profile)
        guidance = self._game_master_guidance(project, pattern=pattern, project_mode=project_mode)
        return {
            "name": project["name"],
            "seed_sentence": project.get("seed_sentence", ""),
            "scenario_text": project.get("scenario_text", ""),
            "genre": project.get("genre", "roleplay"),
            "tone": project.get("tone", "immersive"),
            "mode": project_mode,
            "game_master_pattern": pattern,
            "target_count": self._resolve_sample_character_target_count(project, target_count),
            "character_names": ", ".join(character_names or []),
            "user_name": user_name,
            "user_role_summary": user_role_summary,
            "user_role_hint": guidance["user_role_hint"],
            "sample_character_role_hint": guidance["sample_character_role_hint"],
            "scenario_focus": guidance["scenario_focus"],
        }

    def _effective_user_profile(self, project: dict, *, project_mode: str | None = None) -> dict[str, Any]:
        resolved_mode = str(project_mode or project.get("project_mode", "character") or "character")
        effective = dict(project.get("user_profile", {}) or {})
        if resolved_mode != "game_master":
            return effective
        fallback = self._fallback_user_profile(project)
        for key, value in fallback.items():
            existing = effective.get(key)
            if isinstance(value, list):
                if not existing:
                    effective[key] = list(value)
                continue
            if not str(existing or "").strip():
                effective[key] = value
        return effective

    def _resolve_sample_character_target_count(self, project: dict, requested_count: int | None = None) -> int:
        project_mode = str(project.get("project_mode", "character") or "character")
        default_count = int(project.get("sample_character_target_count") or (5 if project_mode == "game_master" else 1))
        chosen = requested_count if requested_count is not None else default_count
        if project_mode != "game_master":
            return max(1, int(chosen or 1))
        return max(1, min(10, int(chosen or default_count or 5)))

    def generate_scenario(self, project: dict, model_settings: dict, instruction: str = "") -> dict:
        context = {
            "project": self._build_project_prompt_context(project),
            "instruction": instruction.strip() or DEFAULT_INSTRUCTION,
        }
        rendered = render_task_prompts(model_settings, "scenario_generation", context)
        parsed = self.runtime.run_json(
            system_prompt=rendered["system_prompt"],
            user_prompt=rendered["user_prompt"],
            runtime_config=rendered["task_config"]["runtime"],
            parameters=rendered["task_config"]["parameters"],
        )
        if isinstance(parsed, dict):
            scenario_text = str(parsed.get("scenario_text", "")).strip()
            if scenario_text:
                return {
                    "scenario_text": scenario_text,
                    "title_suggestion": str(parsed.get("title_suggestion", "")).strip(),
                }
        if resolve_task_config(model_settings, "scenario_generation")["parameters"]["fallback_to_heuristics"]:
            return self._fallback_scenario(project)
        raise RuntimeError("Scenario generation failed: model did not return valid JSON.")

    def generate_characters(
        self,
        project: dict,
        model_settings: dict,
        instruction: str = "",
        target_count: int | None = None,
    ) -> list[dict]:
        project_mode = str(project.get("project_mode", "character") or "character")
        requested_count = self._resolve_sample_character_target_count(project, target_count)
        context = {
            "project": self._build_project_prompt_context(project, target_count=requested_count),
            "instruction": instruction.strip() or DEFAULT_INSTRUCTION,
        }
        rendered = render_task_prompts(model_settings, "character_card_generation", context)
        parsed = self.runtime.run_json(
            system_prompt=rendered["system_prompt"],
            user_prompt=rendered["user_prompt"],
            runtime_config=rendered["task_config"]["runtime"],
            parameters=rendered["task_config"]["parameters"],
        )
        items = self._as_list(parsed, "characters", "items")
        output = []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            output.append(
                {
                    "name": name,
                    "description": str(item.get("description", "")).strip(),
                    "personality": str(item.get("personality", "")).strip(),
                    "scenario": str(item.get("scenario", "")).strip(),
                    "first_message": str(item.get("first_message", "")).strip(),
                    "example_dialogue": str(item.get("example_dialogue", "")).strip(),
                    "tags": self._clean_list(item.get("tags")),
                    "creator_notes": str(item.get("creator_notes", "")).strip(),
                    "system_prompt": str(item.get("system_prompt", "")).strip(),
                    "post_history_instructions": str(item.get("post_history_instructions", "")).strip(),
                    "alternate_greetings": self._clean_list(item.get("alternate_greetings")),
                    "creator": str(item.get("creator", "")).strip(),
                    "character_version": str(item.get("character_version", "")).strip(),
                    "character_note": str(item.get("character_note", "")).strip(),
                    "character_note_depth": self._clean_int(item.get("character_note_depth"), 4),
                    "character_note_role": self._clean_role(item.get("character_note_role"), "system"),
                    "talkativeness": self._clean_float(item.get("talkativeness")),
                    "appearance_summary": str(item.get("appearance_summary", "")).strip(),
                    "booru_character_name": str(item.get("booru_character_name", "")).strip(),
                    "booru_copyright": str(item.get("booru_copyright", "")).strip(),
                }
            )
        if project_mode == "game_master":
            output = self._filter_game_master_samples(project, output)
        if output:
            if len(output) >= requested_count:
                return output[:requested_count]
            if resolve_task_config(model_settings, "character_card_generation")["parameters"]["fallback_to_heuristics"]:
                fallback = self._fallback_characters(project, target_count=requested_count)
                names = {item["name"] for item in output}
                for item in fallback:
                    if len(output) >= requested_count:
                        break
                    if item["name"] in names:
                        continue
                    output.append(item)
                    names.add(item["name"])
            return output[:requested_count]
        if resolve_task_config(model_settings, "character_card_generation")["parameters"]["fallback_to_heuristics"]:
            return self._fallback_characters(project, target_count=requested_count)
        raise RuntimeError("Character generation failed: model did not return valid JSON.")

    def generate_lore(
        self,
        project: dict,
        character_names: list[str],
        model_settings: dict,
        instruction: str = "",
    ) -> list[dict]:
        context = {
            "project": self._build_project_prompt_context(project, character_names=character_names),
            "instruction": instruction.strip() or DEFAULT_INSTRUCTION,
        }
        rendered = render_task_prompts(model_settings, "lore_generation", context)
        parsed = self.runtime.run_json(
            system_prompt=rendered["system_prompt"],
            user_prompt=rendered["user_prompt"],
            runtime_config=rendered["task_config"]["runtime"],
            parameters=rendered["task_config"]["parameters"],
        )
        items = self._as_list(parsed, "lore_entries", "items", "entries")
        output = []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            content = str(item.get("content", "")).strip()
            if not name or not content:
                continue
            position = self._clean_lore_position(item.get("position"), "after_char")
            output.append(
                {
                    "name": name,
                    "keys": self._clean_list(item.get("keys")),
                    "secondary_keys": self._clean_list(item.get("secondary_keys")),
                    "content": content,
                    "comment": str(item.get("comment", "")).strip(),
                    "enabled": bool(item.get("enabled", True)),
                    "insertion_order": self._clean_int(item.get("insertion_order"), 100),
                    "position": position,
                    "constant": bool(item.get("constant", False)),
                    "selective_logic": self._clean_int(item.get("selective_logic"), 0),
                    "probability": self._clean_int(item.get("probability"), 100),
                    "case_sensitive": bool(item.get("case_sensitive", False)),
                    "priority": self._clean_int(item.get("priority"), 0),
                    "scan_depth": self._clean_optional_int(item.get("scan_depth")),
                    "match_whole_words": self._clean_optional_bool(item.get("match_whole_words")),
                    "group": str(item.get("group", "")).strip(),
                    "group_weight": self._clean_int(item.get("group_weight"), 100),
                    "prevent_recursion": bool(item.get("prevent_recursion", True)),
                    "delay_until_recursion": bool(item.get("delay_until_recursion", False)),
                    "character_filter_json": self._clean_json_string(item.get("character_filter_json"), ""),
                    "automation_id": str(item.get("automation_id", "")).strip(),
                    "role": self._clean_role(item.get("role"), "system"),
                    "extensions_json": self._clean_json_string(item.get("extensions_json"), "{}"),
                }
            )
        if output:
            return output
        if resolve_task_config(model_settings, "lore_generation")["parameters"]["fallback_to_heuristics"]:
            return self._fallback_lore(project, character_names)
        raise RuntimeError("Lore generation failed: model did not return valid JSON.")

    def generate_user_profile(
        self,
        project: dict,
        character_names: list[str],
        model_settings: dict,
        instruction: str = "",
    ) -> dict:
        context = {
            "project": self._build_project_prompt_context(project, character_names=character_names),
            "instruction": instruction.strip() or DEFAULT_INSTRUCTION,
        }
        rendered = render_task_prompts(model_settings, "user_profile_generation", context)
        parsed = self.runtime.run_json(
            system_prompt=rendered["system_prompt"],
            user_prompt=rendered["user_prompt"],
            runtime_config=rendered["task_config"]["runtime"],
            parameters=rendered["task_config"]["parameters"],
        )
        if isinstance(parsed, dict):
            name = str(parsed.get("name", "")).strip() or "User"
            profile = {
                "name": name,
                "description": str(parsed.get("description", "")).strip(),
                "title": str(parsed.get("title", "")).strip(),
                "personality": str(parsed.get("personality", "")).strip(),
                "scenario_role": str(parsed.get("scenario_role", "")).strip(),
                "first_message": str(parsed.get("first_message", "")).strip(),
                "tags": self._clean_list(parsed.get("tags")),
                "persona_note": str(parsed.get("persona_note", "")).strip(),
                "persona_note_depth": self._clean_int(parsed.get("persona_note_depth"), 4),
                "persona_note_role": self._clean_role(parsed.get("persona_note_role"), "system"),
                "appearance_summary": str(parsed.get("appearance_summary", "")).strip(),
                "booru_character_name": str(parsed.get("booru_character_name", "")).strip(),
                "booru_copyright": str(parsed.get("booru_copyright", "")).strip(),
            }
            return self._normalize_user_profile(project, profile)
        if resolve_task_config(model_settings, "user_profile_generation")["parameters"]["fallback_to_heuristics"]:
            return self._fallback_user_profile(project)
        raise RuntimeError("User profile generation failed: model did not return valid JSON.")

    def generate_gm_card(
        self,
        project: dict,
        *,
        character_names: list[str],
        user_name: str,
        model_settings: dict,
        instruction: str = "",
    ) -> dict:
        context = {
            "project": {
                **self._build_project_prompt_context(project, character_names=character_names),
                "user_name": user_name or "User",
            },
            "instruction": instruction.strip() or DEFAULT_INSTRUCTION,
        }
        rendered = render_task_prompts(model_settings, "game_master_card_generation", context)
        parsed = self.runtime.run_json(
            system_prompt=rendered["system_prompt"],
            user_prompt=rendered["user_prompt"],
            runtime_config=rendered["task_config"]["runtime"],
            parameters=rendered["task_config"]["parameters"],
        )
        if isinstance(parsed, dict):
            profile = {
                "name": str(parsed.get("name", "")).strip() or f"{project['name']} GM",
                "description": str(parsed.get("description", "")).strip(),
                "personality": str(parsed.get("personality", "")).strip(),
                "scenario": str(parsed.get("scenario", "")).strip() or project.get("scenario_text", ""),
                "first_message": str(parsed.get("first_message", "")).strip(),
                "example_dialogue": str(parsed.get("example_dialogue", "")).strip(),
                "tags": self._clean_list(parsed.get("tags")),
                "creator_notes": str(parsed.get("creator_notes", "")).strip(),
                "system_prompt": str(parsed.get("system_prompt", "")).strip(),
                "post_history_instructions": str(parsed.get("post_history_instructions", "")).strip(),
                "alternate_greetings": self._clean_list(parsed.get("alternate_greetings")),
                "creator": str(parsed.get("creator", "")).strip(),
                "character_version": str(parsed.get("character_version", "")).strip(),
                "character_note": str(parsed.get("character_note", "")).strip(),
                "character_note_depth": self._clean_int(parsed.get("character_note_depth"), 4),
                "character_note_role": self._clean_role(parsed.get("character_note_role"), "system"),
                "talkativeness": self._clean_float(parsed.get("talkativeness")),
            }
            if str(project.get("project_mode", "character") or "character") == "game_master":
                return self._normalize_gm_card_profile(
                    project,
                    profile,
                    character_names=character_names,
                    user_name=user_name,
                )
            return profile
        if resolve_task_config(model_settings, "game_master_card_generation")["parameters"]["fallback_to_heuristics"]:
            return self._fallback_gm_card(project, character_names=character_names, user_name=user_name)
        raise RuntimeError("GM card generation failed: model did not return valid JSON.")

    def _fallback_scenario(self, project: dict) -> dict:
        seed = project.get("seed_sentence", "").strip()
        if not seed:
            seed = "The user enters a strange world where trust is expensive and secrets are alive."
        project_mode = str(project.get("project_mode", "character") or "character")
        if project_mode == "game_master":
            pattern = self._infer_game_master_pattern(project)
            if pattern == "tavern_story_listener":
                return {
                    "scenario_text": (
                        "The user is the owner and barkeep of a tavern where battered heroes, mercenaries, and strange travelers "
                        "return from danger to eat, drink, and tell their stories. Each guest brings rumors, trophies, wounds, lies, "
                        "debts, or fresh hooks for the next adventure. The roleplay loop centers on listening to their tales, deciding "
                        "who to trust, managing the tavern atmosphere, and choosing which story threads deserve deeper involvement."
                    ),
                    "title_suggestion": project["name"],
                }
            if pattern == "labyrinth_explorer":
                return {
                    "scenario_text": (
                        "The user enters a shifting labyrinth with a personal reason to keep moving deeper. Each chamber forces choices "
                        "about routes, risks, bargains, clues, and survival. The roleplay loop centers on exploring the maze, handling "
                        "creatures and rivals, uncovering why the labyrinth matters to the user, and deciding what price they will pay to reach the core."
                    ),
                    "title_suggestion": project["name"],
                }
        return {
            "scenario_text": (
                f"{seed} The user is drawn into escalating choices, relationships, and hidden motives that "
                "shape the world over multiple roleplay turns."
            ),
            "title_suggestion": project["name"],
        }

    def _fallback_characters(self, project: dict, *, target_count: int = 1) -> list[dict]:
        scenario = project.get("scenario_text", "")
        project_mode = str(project.get("project_mode", "character") or "character")
        pattern = self._infer_game_master_pattern(project)
        total = max(1, int(target_count))
        output: list[dict] = []
        if project_mode == "game_master" and pattern == "tavern_story_listener":
            templates = [
                {
                    "name": "Sir Branic Ashcloak",
                    "description": "A scarred knight who returns to the tavern with muddy armor and a story he hesitates to tell.",
                    "personality": "Courteous, tired, proud, and haunted by what he saw on the road.",
                    "first_message": "Ale first. Then I'll tell you why half my company never came home.",
                    "example_dialogue": "{{char}}: The road south is wrong now. {{user}}: Wrong how? {{char}}: The dead are asking for directions.",
                    "tags": ["hero", "customer", "rumor-bringer"],
                },
                {
                    "name": "Mira Thistledown",
                    "description": "A clever ranger who trades gossip, monster signs, and half-truths for strong drink.",
                    "personality": "Quick-witted, restless, teasing, and always watching the room.",
                    "first_message": "You keep the best fire in town. Shame about the cursed map in my pocket.",
                    "example_dialogue": "{{char}}: I tracked something wearing a man's shadow. {{user}}: And? {{char}}: It tracked me back.",
                    "tags": ["ranger", "customer", "quest-hook"],
                },
                {
                    "name": "Brother Halren",
                    "description": "A battlefield priest carrying relics, quiet guilt, and unsettling news from the frontier.",
                    "personality": "Gentle, severe, sincere, and burdened by duty.",
                    "first_message": "I need a room, a meal, and perhaps absolution, in that order.",
                    "example_dialogue": "{{char}}: Three champions swore the same impossible thing. {{user}}: Which was? {{char}}: That the mountain answered them back.",
                    "tags": ["priest", "customer", "mystery"],
                },
            ]
        elif project_mode == "game_master" and pattern == "labyrinth_explorer":
            templates = [
                {
                    "name": "Mossjaw Stalker",
                    "description": "A lean labyrinth predator that waits in side passages and tests the weak.",
                    "personality": "Patient, territorial, and unnervingly intelligent for a beast.",
                    "first_message": "The creature watches from the dark, measuring whether you belong here.",
                    "example_dialogue": "{{char}}: *a low scraping growl echoes from the stone*",
                    "tags": ["creature", "labyrinth", "encounter"],
                },
                {
                    "name": "Teren of the Fifth Torch",
                    "description": "A rival delver who claims to know a safe route but always asks for something first.",
                    "personality": "Charming, opportunistic, brave, and fundamentally untrustworthy.",
                    "first_message": "You're headed deeper too? Then maybe we can lie to each other profitably.",
                    "example_dialogue": "{{char}}: Left path if you want answers, right path if you want to survive. {{user}}: Which did you take? {{char}}: That's the problem.",
                    "tags": ["rival", "labyrinth", "traveler"],
                },
                {
                    "name": "The Spiral Warden",
                    "description": "A sentinel bound to the heart of the maze, speaking in rules and riddles.",
                    "personality": "Ancient, formal, cryptic, and pitilessly fair.",
                    "first_message": "State your reason for descent. The labyrinth listens more closely than I do.",
                    "example_dialogue": "{{char}}: Every door here opens onto a choice you already made. {{user}}: Then why am I still lost? {{char}}: Because you have not chosen honestly.",
                    "tags": ["guardian", "labyrinth", "boss"],
                },
            ]
        else:
            anchor = self._title_from_text(scenario) or "The Guide"
            templates = [
                {
                    "name": anchor,
                    "description": "A central figure tied to the conflict and the world secrets.",
                    "personality": "Focused, protective, and morally conflicted.",
                    "first_message": "I was hoping you would show up before things got worse.",
                    "example_dialogue": "{{char}}: Keep your voice down. {{user}}: Why? {{char}}: Because walls listen here.",
                    "tags": ["original character", "story-driven", "roleplay"],
                }
            ]
        for index in range(total):
            template = templates[index % len(templates)]
            output.append(
                {
                    "name": template["name"] if index < len(templates) else f"{template['name']} {index + 1}",
                    "description": template["description"],
                    "personality": template["personality"],
                    "scenario": scenario,
                    "first_message": template["first_message"],
                    "example_dialogue": template["example_dialogue"],
                    "tags": template["tags"],
                    "creator_notes": "Generated fallback character.",
                    "system_prompt": "",
                    "post_history_instructions": "",
                    "alternate_greetings": [template["first_message"]],
                    "creator": "",
                    "character_version": "",
                    "character_note": "",
                    "character_note_depth": 4,
                    "character_note_role": "system",
                    "talkativeness": None,
                    "appearance_summary": "",
                    "booru_character_name": "",
                    "booru_copyright": "",
                }
            )
        return output

    def _fallback_lore(self, project: dict, character_names: list[str]) -> list[dict]:
        scenario = project.get("scenario_text", "").strip()
        keys = [name for name in character_names if name][:2]
        return [
            {
                "name": "World Rules",
                "keys": ["world", "rules"] + keys,
                "secondary_keys": ["law", "customs"],
                "content": (
                    "Information is traded like currency. Broken promises become social debt. "
                    "Public memory can be edited, but private memory leaves traces."
                ),
                "comment": "Core setting constraints.",
                "enabled": True,
                "insertion_order": 100,
                "position": "after_char",
                "constant": False,
                "selective_logic": 0,
                "probability": 100,
                "case_sensitive": False,
                "priority": 0,
                "scan_depth": None,
                "match_whole_words": None,
                "group": "",
                "group_weight": 100,
                "prevent_recursion": True,
                "delay_until_recursion": False,
                "character_filter_json": "",
                "automation_id": "",
                "role": "system",
                "extensions_json": "{}",
            },
            {
                "name": "Current Situation",
                "keys": ["current", "situation", "mission"],
                "secondary_keys": ["goal"],
                "content": scenario or "The user is pulled into a high-stakes conflict with hidden factions.",
                "comment": "Main arc anchor.",
                "enabled": True,
                "insertion_order": 110,
                "position": "after_char",
                "constant": False,
                "selective_logic": 0,
                "probability": 100,
                "case_sensitive": False,
                "priority": 0,
                "scan_depth": None,
                "match_whole_words": None,
                "group": "",
                "group_weight": 100,
                "prevent_recursion": True,
                "delay_until_recursion": False,
                "character_filter_json": "",
                "automation_id": "",
                "role": "system",
                "extensions_json": "{}",
            },
        ]

    def _fallback_user_profile(self, project: dict) -> dict:
        project_mode = str(project.get("project_mode", "character") or "character")
        pattern = self._infer_game_master_pattern(project)
        if project_mode == "game_master" and pattern == "tavern_story_listener":
            return {
                "name": "User",
                "description": "Tavern owner and barkeep of a well-placed tavern where heroes, mercenaries, and wanderers return with dangerous stories.",
                "title": "Tavern Owner",
                "personality": "Grounded, observant, welcoming, and sharper than most guests first assume.",
                "scenario_role": "Tavern owner who listens to travelers' tales, judges what matters, and decides which threads to pull.",
                "first_message": "Set your pack down, warm yourself by the fire, and start from the part no one else believed.",
                "tags": ["player", "persona", "tavern owner", "story listener"],
                "persona_note": "The user is the tavern owner and decision-maker. Keep them central to rumors, requests, and consequences.",
                "persona_note_depth": 4,
                "persona_note_role": "system",
                "appearance_summary": "",
                "booru_character_name": "",
                "booru_copyright": "",
            }
        if project_mode == "game_master" and pattern == "labyrinth_explorer":
            return {
                "name": "User",
                "description": "A determined explorer entering the labyrinth for a deeply personal reason that keeps them moving forward.",
                "title": "Labyrinth Delver",
                "personality": "Curious, resilient, wary, and willing to press on when others turn back.",
                "scenario_role": "Labyrinth delver seeking answers, someone, or something only the deeper chambers can reveal.",
                "first_message": "If the maze wants my fear, it'll have to settle for my footsteps.",
                "tags": ["player", "persona", "explorer", "labyrinth"],
                "persona_note": "The user is the active explorer. Present routes, pressure, and consequences without speaking for them.",
                "persona_note_depth": 4,
                "persona_note_role": "system",
                "appearance_summary": "",
                "booru_character_name": "",
                "booru_copyright": "",
            }
        return {
            "name": "User",
            "description": "A capable outsider with flexible morals and a curiosity that attracts trouble.",
            "title": "Catalyst",
            "personality": "Adaptive, observant, and emotionally grounded.",
            "scenario_role": "Catalyst who decides which truths are worth the cost.",
            "first_message": "I need the truth, not the safe version. Start from the beginning.",
            "tags": ["player", "persona", "story-driven"],
            "persona_note": "Keep the user as the active protagonist and preserve room for their choices.",
            "persona_note_depth": 4,
            "persona_note_role": "system",
            "appearance_summary": "",
            "booru_character_name": "",
            "booru_copyright": "",
        }

    def _fallback_gm_card(self, project: dict, *, character_names: list[str], user_name: str) -> dict:
        scenario_text = project.get("scenario_text", "").strip() or self._fallback_scenario(project)["scenario_text"]
        sample_names = ", ".join(character_names[:5]) if character_names else "sample NPCs"
        pattern = self._infer_game_master_pattern(project)
        guidance = self._game_master_guidance(
            project,
            pattern=pattern,
            project_mode=str(project.get("project_mode", "character") or "character"),
        )
        first_message = (
            f"Welcome, {user_name or 'traveler'}. The world is already in motion. "
            "Tell me your first action and I will resolve the consequences."
        )
        example_dialogue = (
            "{{char}}: The scene changes with your decision.\n"
            "{{user}}: Then I choose the riskier path.\n"
            "{{char}}: The world answers immediately."
        )
        alternate_greetings = [
            "The situation is already moving. What do you do first?",
            "A choice is waiting on the edge of the next scene. How do you proceed?",
        ]
        if pattern == "tavern_story_listener":
            first_message = (
                f"The fire is warm, the tables are filling, and the first battered hero of the night is asking for a private word, {user_name or 'innkeeper'}. "
                "Do you wave them over, keep serving, or listen from a distance?"
            )
            example_dialogue = (
                "{{char}}: Rain follows the customers in as three road-worn heroes crowd your bar.\n"
                "{{user}}: I pour the first round and ask which story drew blood tonight.\n"
                "{{char}}: The eldest hero slides a dented relic across the wood and says the mountain kept one of their names."
            )
            alternate_greetings = [
                "The tavern doors open on a fresh rumor and wet boots. Who gets your attention first?",
                "A regular, a wounded stranger, and a suspicious noble all want your ear at once. How do you handle the room?",
            ]
        elif pattern == "labyrinth_explorer":
            first_message = (
                f"The labyrinth seals another passage behind you, {user_name or 'explorer'}, and three possible routes remain ahead. "
                "One smells of incense, one of blood, and one of fresh rain. Which do you choose?"
            )
            example_dialogue = (
                "{{char}}: Your torchlight catches claw marks spiraling toward a half-open gate.\n"
                "{{user}}: I study the tracks before I commit to the gate.\n"
                "{{char}}: The marks are recent, and something on the other side is waiting for hesitation."
            )
            alternate_greetings = [
                "A new chamber opens with a threat, a clue, and a lie. Which one do you test first?",
                "You hear movement deeper in the maze and a voice behind you. Where do you turn?",
            ]
        return {
            "name": f"{project.get('name', 'Project')} GM",
            "description": self._gm_description_contract(project, pattern=pattern, user_name=user_name),
            "personality": "Impartial narrator, dramatic pacing, reactive world simulation, and distinct NPC voices.",
            "scenario": self._gm_scenario_contract(project, scenario_text=scenario_text, pattern=pattern, user_name=user_name),
            "first_message": first_message,
            "example_dialogue": example_dialogue,
            "tags": ["game_master", "scenario", "world_simulation", "narrator"],
            "creator_notes": f"Sample characters referenced: {sample_names}. User-role focus: {guidance['user_role_hint']}",
            "system_prompt": self._gm_system_prompt_contract(project, pattern=pattern),
            "post_history_instructions": self._gm_post_history_contract(project, pattern=pattern),
            "alternate_greetings": alternate_greetings,
            "creator": "",
            "character_version": "2.0",
            "character_note": self._gm_character_note_contract(project, pattern=pattern),
            "character_note_depth": 4,
            "character_note_role": "system",
            "talkativeness": 0.35,
        }

    def _normalize_gm_card_profile(
        self,
        project: dict,
        profile: dict,
        *,
        character_names: list[str],
        user_name: str,
    ) -> dict:
        pattern = self._infer_game_master_pattern(project)
        fallback = self._fallback_gm_card(project, character_names=character_names, user_name=user_name)
        normalized = dict(profile)
        suspect = self._gm_profile_confuses_user_role(project, normalized)

        name = str(normalized.get("name", "") or "").strip()
        if not name or self._gm_name_confuses_user_role(name, pattern):
            normalized["name"] = fallback["name"]

        generated_description = "" if suspect else str(normalized.get("description", "") or "").strip()
        normalized["description"] = self._join_unique_sections(
            self._gm_description_contract(project, pattern=pattern, user_name=user_name),
            generated_description,
        )
        normalized["personality"] = self._join_unique_sections(
            str(normalized.get("personality", "") or "").strip(),
            "Uses clear scene framing, fair consequence tracking, and distinct voices for temporary NPCs.",
        )
        scenario_source = str(project.get("scenario_text", "") or "").strip() if suspect else str(normalized.get("scenario", "") or "").strip()
        normalized["scenario"] = self._gm_scenario_contract(
            project,
            scenario_text=scenario_source or str(project.get("scenario_text", "") or "").strip(),
            pattern=pattern,
            user_name=user_name,
        )

        first_message = str(normalized.get("first_message", "") or "").strip()
        if not first_message or self._gm_first_message_confuses_user_role(first_message, pattern):
            normalized["first_message"] = fallback["first_message"]

        example_dialogue = str(normalized.get("example_dialogue", "") or "").strip()
        if not self._gm_example_dialogue_is_safe(example_dialogue, pattern):
            normalized["example_dialogue"] = fallback["example_dialogue"]

        tags = self._clean_list(normalized.get("tags"))
        required_tags = ["game_master", "scenario", "narrator"]
        if pattern == "tavern_story_listener":
            required_tags.extend(["tavern", "npc-customers"])
        normalized["tags"] = self._merge_tags(tags, required_tags)

        normalized["system_prompt"] = self._join_unique_sections(
            self._gm_system_prompt_contract(project, pattern=pattern),
            "" if suspect else str(normalized.get("system_prompt", "") or "").strip(),
        )
        normalized["post_history_instructions"] = self._join_unique_sections(
            "" if suspect else str(normalized.get("post_history_instructions", "") or "").strip(),
            self._gm_post_history_contract(project, pattern=pattern),
        )
        normalized["character_note"] = self._join_unique_sections(
            self._gm_character_note_contract(project, pattern=pattern),
            "" if suspect else str(normalized.get("character_note", "") or "").strip(),
        )

        if not str(normalized.get("creator_notes", "") or "").strip():
            normalized["creator_notes"] = fallback["creator_notes"]
        if not self._clean_list(normalized.get("alternate_greetings")):
            normalized["alternate_greetings"] = fallback["alternate_greetings"]
        if not str(normalized.get("character_version", "") or "").strip():
            normalized["character_version"] = "2.0"
        if normalized.get("talkativeness") in {None, ""}:
            normalized["talkativeness"] = fallback["talkativeness"]
        normalized["character_note_depth"] = self._clean_int(normalized.get("character_note_depth"), 4)
        normalized["character_note_role"] = self._clean_role(normalized.get("character_note_role"), "system")
        return normalized

    def _gm_description_contract(self, project: dict, *, pattern: str, user_name: str) -> str:
        if pattern == "tavern_story_listener":
            return (
                "{{char}} is the Game Master and narrator for a fantasy tavern scenario. "
                "{{char}} is not the tavern owner and never replaces {{user}}. "
                f"{{{{user}}}}/{user_name or 'User'} is the tavern owner and decision-maker. "
                "{{char}} creates visiting customers, travelers, heroes, staff, rumors, requests, and consequences, then plays those NPCs as they arrive, interact, and leave."
            )
        if pattern == "labyrinth_explorer":
            return (
                "{{char}} is the Game Master and narrator for a labyrinth exploration scenario. "
                "{{char}} is not {{user}} and never replaces {{user}}. "
                f"{{{{user}}}}/{user_name or 'User'} is the delver whose choices drive routes, risks, and discoveries. "
                "{{char}} runs chambers, hazards, creatures, rivals, clues, and consequences."
            )
        return (
            "{{char}} is the Game Master and narrator for this scenario. "
            "{{char}} is not {{user}} and never replaces {{user}}. "
            f"{{{{user}}}}/{user_name or 'User'} is the active player character whose choices drive the story. "
            "{{char}} runs the world, NPCs, pacing, and consequences."
        )

    def _gm_scenario_contract(self, project: dict, *, scenario_text: str, pattern: str, user_name: str) -> str:
        scenario = scenario_text.strip() or self._fallback_scenario(project)["scenario_text"]
        if pattern == "tavern_story_listener":
            lead = (
                f"{{{{user}}}}/{user_name or 'User'} owns and runs the tavern. "
                "{{char}} narrates the tavern, introduces customers and other NPCs, speaks for those NPCs, tracks the room, and resolves consequences. "
                "{{char}} never writes {{user}}'s actions, dialogue, thoughts, or feelings."
            )
        elif pattern == "labyrinth_explorer":
            lead = (
                f"{{{{user}}}}/{user_name or 'User'} explores the labyrinth. "
                "{{char}} narrates chambers, threats, NPCs, clues, and consequences while leaving every player choice to {{user}}."
            )
        else:
            lead = (
                f"{{{{user}}}}/{user_name or 'User'} is the active protagonist. "
                "{{char}} runs the scenario as narrator and NPC handler while leaving every player choice to {{user}}."
            )
        return self._join_unique_sections(lead, scenario)

    def _gm_system_prompt_contract(self, project: dict, *, pattern: str) -> str:
        if pattern == "tavern_story_listener":
            return (
                "You are {{char}}, the Game Master for a tavern-owner roleplay. "
                "Write as narrator and as NPC customers only. Generate distinct patrons, heroes, workers, troublemakers, and rumor-bringers, then play them while they come and go. "
                "Never write as {{user}}, never decide {{user}}'s actions, and never make {{user}} speak."
            )
        return (
            "You are {{char}}, the Game Master for this roleplay. "
            "Write as narrator and NPCs only. Track continuity, stakes, world state, and consequences. "
            "Never write as {{user}}, never decide {{user}}'s actions, and never make {{user}} speak."
        )

    def _gm_post_history_contract(self, project: dict, *, pattern: str) -> str:
        if pattern == "tavern_story_listener":
            return (
                "Final reply rules: {{user}} owns the tavern; {{char}} runs the world and NPC customers. "
                "Respond to {{user}}'s latest action, advance the tavern scene through NPC behavior, and end with a clear opening for {{user}} to choose. "
                "Do not narrate {{user}}'s chosen action, dialogue, thoughts, or emotions."
            )
        return (
            "Final reply rules: respond to {{user}}'s latest action, advance the scene through narration and NPC behavior, and leave the next decision to {{user}}. "
            "Do not narrate {{user}}'s chosen action, dialogue, thoughts, or emotions."
        )

    def _gm_character_note_contract(self, project: dict, *, pattern: str) -> str:
        if pattern == "tavern_story_listener":
            return (
                "Stay in GM mode. {{user}} is the tavern owner. Introduce and play NPC customers; track arrivals, departures, rumors, requests, debts, and consequences. Never act as {{user}}."
            )
        return "Stay in GM mode. Present consequences clearly, play NPCs distinctly, and never act as {{user}}."

    def _gm_profile_confuses_user_role(self, project: dict, profile: dict) -> bool:
        pattern = self._infer_game_master_pattern(project)
        combined = " ".join(
            str(profile.get(key, "") or "")
            for key in ("name", "description", "personality", "scenario", "first_message", "example_dialogue", "system_prompt", "post_history_instructions", "character_note")
        ).lower()
        if any(phrase in combined for phrase in ("act as the user", "play as the user", "write as the user", "speak as the user")):
            return True
        if pattern == "tavern_story_listener":
            bad_phrases = (
                "{{char}} is the tavern owner",
                "{{char}} owns the tavern",
                "{{char}} runs the tavern",
                "you are the tavern owner",
                "you are the innkeeper",
                "you are the barkeep",
                "you own the tavern",
                "you run the tavern",
                "act as the tavern owner",
                "play as the tavern owner",
                "act as the innkeeper",
                "play as the innkeeper",
                "act as the barkeep",
                "play as the barkeep",
            )
            return any(phrase in combined for phrase in bad_phrases)
        return False

    def _gm_name_confuses_user_role(self, name: str, pattern: str) -> bool:
        normalized = name.lower()
        if normalized in {"user", "{{user}}", "player", "protagonist"}:
            return True
        if pattern == "tavern_story_listener":
            return any(token in normalized for token in ("tavern owner", "innkeeper", "barkeep", "bartender", "publican"))
        return False

    def _gm_first_message_confuses_user_role(self, text: str, pattern: str) -> bool:
        normalized = text.lower()
        if any(phrase in normalized for phrase in ("i am {{user}}", "i'm {{user}}", "i act as {{user}}")):
            return True
        if pattern == "tavern_story_listener":
            return any(
                phrase in normalized
                for phrase in (
                    "i own this tavern",
                    "i run this tavern",
                    "my tavern is open",
                    "welcome to my tavern",
                    "as the tavern owner, i",
                    "as the innkeeper, i",
                )
            )
        return False

    def _gm_example_dialogue_is_safe(self, text: str, pattern: str) -> bool:
        if not text.strip():
            return False
        normalized = text.lower()
        if "{{char}}" not in text or "{{user}}" not in text:
            return False
        if pattern == "tavern_story_listener":
            return not any(
                phrase in normalized
                for phrase in (
                    "{{char}}: i pour",
                    "{{char}}: i serve",
                    "{{char}}: i own",
                    "{{char}}: my tavern",
                    "{{char}}: welcome to my tavern",
                )
            )
        return True

    def _join_unique_sections(self, *sections: str) -> str:
        output: list[str] = []
        seen: set[str] = set()
        for section in sections:
            cleaned = str(section or "").strip()
            if not cleaned:
                continue
            key = re.sub(r"\s+", " ", cleaned).lower()
            if key in seen:
                continue
            seen.add(key)
            output.append(cleaned)
        return "\n\n".join(output)

    def _merge_tags(self, tags: list[str], required: list[str]) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()
        for tag in [*required, *tags]:
            cleaned = str(tag or "").strip()
            key = cleaned.lower()
            if not cleaned or key in seen:
                continue
            seen.add(key)
            output.append(cleaned)
        return output

    def _infer_game_master_pattern(self, project: dict) -> str:
        combined = " ".join(
            [
                str(project.get("name", "") or ""),
                str(project.get("seed_sentence", "") or ""),
                str(project.get("scenario_text", "") or ""),
            ]
        ).lower()
        if any(token in combined for token in ("tavern", "inn", "barkeep", "bartender", "pub owner", "taverner")):
            return "tavern_story_listener"
        if any(token in combined for token in ("labyrinth", "maze", "minotaur", "dungeon", "catacomb")):
            return "labyrinth_explorer"
        return "generic_gm"

    def _game_master_guidance(self, project: dict, *, pattern: str, project_mode: str) -> dict[str, str]:
        if project_mode != "game_master":
            return {
                "user_role_hint": "The user participates in the scenario but is not the card's main authored character.",
                "sample_character_role_hint": "Characters should fit the scenario and support roleplay.",
                "scenario_focus": "Establish the setting, conflict, and interaction hooks for roleplay.",
            }
        if pattern == "tavern_story_listener":
            return {
                "user_role_hint": "The user persona is the tavern owner or barkeep who hears travelers' tales and decides what to do with the rumors, requests, and dangers that reach the bar.",
                "sample_character_role_hint": "Sample characters should be customers, heroes, mercenaries, rumor-bringers, and suspicious patrons arriving to tell stories or ask for help.",
                "scenario_focus": "The scenario loop is running the tavern, hearing heroes' tales, judging which stories matter, and letting outside adventures spill into the common room.",
            }
        if pattern == "labyrinth_explorer":
            return {
                "user_role_hint": "The user persona is the explorer moving through the labyrinth for a personal reason, choosing routes, handling traps, and pressing deeper.",
                "sample_character_role_hint": "Sample characters should be creatures, guardians, rivals, guides, and strange encounters the user might meet inside the labyrinth.",
                "scenario_focus": "The scenario loop is traversing the labyrinth, making choices under pressure, surviving encounters, and uncovering the truth waiting deeper inside.",
            }
        return {
            "user_role_hint": "The user persona is the active protagonist whose choices drive the scenario forward.",
            "sample_character_role_hint": "Sample characters are encounter examples around the user, never replacements for the user.",
            "scenario_focus": "The scenario loop should revolve around the user's decisions, consequences, and discoveries.",
        }

    def _user_role_summary(self, user_profile: dict) -> str:
        parts = [
            str(user_profile.get("description", "") or "").strip(),
            str(user_profile.get("title", "") or "").strip(),
            str(user_profile.get("scenario_role", "") or "").strip(),
            str(user_profile.get("personality", "") or "").strip(),
            str(user_profile.get("persona_note", "") or "").strip(),
        ]
        return "; ".join(part for part in parts if part)

    def _normalize_user_profile(self, project: dict, profile: dict) -> dict:
        project_mode = str(project.get("project_mode", "character") or "character")
        if project_mode != "game_master":
            return profile
        pattern = self._infer_game_master_pattern(project)
        if pattern == "generic_gm":
            return profile
        fallback = self._fallback_user_profile(project)
        combined = " ".join(
            [
                str(profile.get("description", "") or ""),
                str(profile.get("scenario_role", "") or ""),
                str(profile.get("personality", "") or ""),
                str(profile.get("first_message", "") or ""),
            ]
        ).lower()
        required_markers = {
            "tavern_story_listener": ("tavern owner", "owner", "barkeep", "bartender", "innkeeper", "publican", "proprietor"),
            "labyrinth_explorer": ("labyrinth", "maze", "dungeon", "delver", "explorer", "adventurer", "seeker"),
        }.get(pattern, ())
        normalized = dict(profile)
        if required_markers and any(marker in combined for marker in required_markers):
            if not normalized.get("description"):
                normalized["description"] = fallback["description"]
            if not normalized.get("title"):
                normalized["title"] = fallback["title"]
            if not normalized.get("scenario_role"):
                normalized["scenario_role"] = fallback["scenario_role"]
            if not normalized.get("first_message"):
                normalized["first_message"] = fallback["first_message"]
            if not normalized.get("tags"):
                normalized["tags"] = fallback["tags"]
            if not normalized.get("persona_note"):
                normalized["persona_note"] = fallback["persona_note"]
            if not normalized.get("persona_note_depth"):
                normalized["persona_note_depth"] = fallback["persona_note_depth"]
            if not normalized.get("persona_note_role"):
                normalized["persona_note_role"] = fallback["persona_note_role"]
            return normalized
        repaired = dict(fallback)
        for key in ("name", "appearance_summary", "booru_character_name", "booru_copyright"):
            value = str(profile.get(key, "") or "").strip()
            if value:
                repaired[key] = value
        return repaired

    def _filter_game_master_samples(self, project: dict, characters: list[dict]) -> list[dict]:
        pattern = self._infer_game_master_pattern(project)
        user_profile = self._effective_user_profile(project, project_mode="game_master")
        user_name = str(user_profile.get("name", "") or "").strip().lower()
        excluded_phrases: set[str] = set()
        if pattern == "tavern_story_listener":
            excluded_phrases.update(
                {
                    "tavern owner",
                    "owner of the tavern",
                    "innkeeper",
                    "keeper of the inn",
                    "barkeep",
                    "bartender",
                    "pub owner",
                    "publican",
                    "runs the tavern",
                    "runs the inn",
                    "proprietor of the tavern",
                    "proprietor of the inn",
                }
            )
        filtered: list[dict] = []
        for item in characters:
            name = str(item.get("name", "") or "").strip().lower()
            combined = " ".join(
                [
                    str(item.get("name", "") or ""),
                    str(item.get("description", "") or ""),
                    str(item.get("personality", "") or ""),
                    str(item.get("scenario", "") or ""),
                    str(item.get("first_message", "") or ""),
                    str(item.get("example_dialogue", "") or ""),
                ]
            ).lower()
            if user_name and name == user_name:
                continue
            if excluded_phrases and any(phrase in combined for phrase in excluded_phrases):
                continue
            filtered.append(item)
        return filtered

    def _as_list(self, parsed: object | None, *keys: str) -> list:
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            for key in keys:
                value = parsed.get(key)
                if isinstance(value, list):
                    return value
        return []

    def _clean_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [item.strip() for item in re.split(r"[,\\n]", value) if item.strip()]
        return []

    def _clean_int(self, value: Any, default: int) -> int:
        try:
            if value in {None, ""}:
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    def _clean_optional_int(self, value: Any) -> int | None:
        try:
            if value in {None, ""}:
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    def _clean_float(self, value: Any) -> float | None:
        try:
            if value in {None, ""}:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _clean_optional_bool(self, value: Any) -> bool | None:
        if value in {None, ""}:
            return None
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
        return None

    def _clean_role(self, value: Any, default: str = "system") -> str:
        candidate = str(value or "").strip().lower()
        if candidate in {"system", "user", "assistant"}:
            return candidate
        return default

    def _clean_lore_position(self, value: Any, default: str = "after_char") -> str:
        candidate = str(value or "").strip().lower()
        if candidate == "global":
            return "after_char"
        if candidate in {"before_char", "after_char", "before_examples", "after_examples"}:
            return candidate
        return default

    def _clean_json_string(self, value: Any, default: str) -> str:
        if value in {None, ""}:
            return default
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        text = str(value).strip()
        return text or default

    def _title_from_text(self, text: str) -> str:
        words = re.sub(r"[^a-zA-Z0-9\\s]", " ", text).split()
        return " ".join(words[:2]).title()

    def generate_image_prompt(
        self,
        *,
        project: dict,
        model_settings: dict,
        image_model_name: str,
        subject_type: str,
        shot_type: str,
        subject_name: str,
        subject_text: str,
        appearance_summary: str = "",
        booru_character_tag: str = "",
        instruction: str = "",
    ) -> dict[str, str]:
        style_profile = self._resolve_style_profile(image_model_name)
        style_guide = self._style_guide_for_profile(style_profile)
        context = {
            "project": {
                "name": project.get("name", ""),
                "genre": project.get("genre", ""),
                "tone": project.get("tone", ""),
                "scenario_text": project.get("scenario_text", ""),
            },
            "subject": {
                "type": subject_type,
                "shot_type": shot_type,
                "name": subject_name,
                "description": subject_text,
                "appearance_summary": appearance_summary,
                "booru_character_tag": booru_character_tag,
            },
            "style_profile": style_profile,
            "style_guide": style_guide,
            "instruction": instruction.strip() or DEFAULT_INSTRUCTION,
        }
        rendered = render_task_prompts(model_settings, "image_prompt_generation", context)
        task_config = rendered["task_config"]
        parsed = None
        try:
            parsed = self.runtime.run_json(
                system_prompt=rendered["system_prompt"],
                user_prompt=rendered["user_prompt"],
                runtime_config=task_config["runtime"],
                parameters=task_config["parameters"],
            )
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            prompt = self._normalize_prompt_string(parsed.get("prompt", ""))
            negative_prompt = self._normalize_prompt_string(parsed.get("negative_prompt", ""))
            if prompt:
                if not negative_prompt:
                    negative_prompt = self._default_negative_prompt(style_profile)
                return {
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "style_profile": style_profile,
                }
        if not bool(task_config["parameters"].get("fallback_to_heuristics", True)):
            raise RuntimeError("Image prompt generation failed: model did not return valid JSON.")
        return self._fallback_image_prompt(
            style_profile=style_profile,
            subject_type=subject_type,
            shot_type=shot_type,
            subject_name=subject_name,
            subject_text=subject_text,
            appearance_summary=appearance_summary,
            booru_character_tag=booru_character_tag,
            scenario_text=project.get("scenario_text", ""),
        )

    def _resolve_style_profile(self, image_model_name: str) -> str:
        normalized = str(image_model_name or "").strip().lower()
        if "noob" in normalized:
            return "noobai"
        if "illust" in normalized or "illustrious" in normalized:
            return "illustrious"
        return "generic_sdxl"

    def _style_guide_for_profile(self, style_profile: str) -> str:
        if style_profile == "noobai":
            return (
                "NoobAI guide: place quality tags early, then subject tags, then environment/style tags. "
                "Use Danbooru-style normalized tags (spaces, no underscores). "
                "Use quality anchors such as very awa, masterpiece, best quality, newest, year 2024 when relevant."
            )
        if style_profile == "illustrious":
            return (
                "Illustrious guide: prioritize clean, readable anime tags with strong composition and lighting tags. "
                "Use quality anchors like masterpiece, best quality, highres, absurdres, detailed background."
            )
        return (
            "Generic SDXL guide: concise visual tags for composition, subject, lighting, mood, and rendering quality."
        )

    def _normalize_prompt_string(self, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        text = text.replace("_", " ")
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\s*,\s*", ", ", text)
        text = re.sub(r"(,\s*){2,}", ", ", text)
        return text.strip(" ,")

    def _default_negative_prompt(self, style_profile: str) -> str:
        base = [
            "lowres",
            "blurry",
            "bad anatomy",
            "extra limbs",
            "deformed hands",
            "worst quality",
            "low quality",
            "jpeg artifacts",
            "watermark",
            "text",
            "logo",
        ]
        if style_profile in {"noobai", "illustrious"}:
            base.append("nsfw")
        return ", ".join(base)

    def _fallback_image_prompt(
        self,
        *,
        style_profile: str,
        subject_type: str,
        shot_type: str,
        subject_name: str,
        subject_text: str,
        appearance_summary: str,
        booru_character_tag: str,
        scenario_text: str,
    ) -> dict[str, str]:
        quality_prefix = {
            "noobai": ["very awa", "masterpiece", "best quality", "newest", "year 2024"],
            "illustrious": ["masterpiece", "best quality", "highres", "absurdres"],
        }.get(style_profile, ["masterpiece", "best quality", "high detail"])
        shot_tags = {
            "portrait": ["portrait", "upper body", "focus on face", "looking at viewer"],
            "cowboy_shot": ["cowboy shot", "thigh up", "balanced composition"],
            "fullbody_shot": ["full body", "standing pose", "full figure"],
        }.get(shot_type, ["illustration"])
        subject_tags: list[str] = []
        if subject_type == "scenario":
            subject_tags.extend(["environment concept art", "worldbuilding scene", "cinematic lighting"])
        elif subject_type == "lore":
            subject_tags.extend(["lore illustration", "symbolic storytelling", "atmospheric scene"])
        elif subject_type == "user":
            subject_tags.extend(["persona design", "character reference"])
        else:
            subject_tags.extend(["character design", "expressive face"])

        cleaned_name = self._normalize_prompt_string(subject_name)
        if cleaned_name:
            subject_tags.append(cleaned_name)

        identity_tag = self._normalize_prompt_string(booru_character_tag)
        if identity_tag:
            subject_tags.insert(0, identity_tag)

        appearance_tags = [
            chunk.strip()
            for chunk in re.split(r"[,.;\n]", self._normalize_prompt_string(appearance_summary))
            if chunk.strip()
        ]
        if appearance_tags:
            subject_tags.extend(appearance_tags[:6])

        text_source = self._normalize_prompt_string(subject_text or scenario_text)
        derived_tags = [chunk.strip() for chunk in re.split(r"[,.;\n]", text_source) if chunk.strip()]
        subject_tags.extend(derived_tags[:8])

        final_prompt = ", ".join(quality_prefix + shot_tags + subject_tags)
        return {
            "prompt": self._normalize_prompt_string(final_prompt),
            "negative_prompt": self._default_negative_prompt(style_profile),
            "style_profile": style_profile,
        }
