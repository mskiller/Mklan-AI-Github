from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, PngImagePlugin

from ..schemas import CharacterCardExport, LorebookExport, LorebookExportEntry, PersonaExport


WEBP_EXIF_USER_COMMENT = 37510
LORE_POSITION_EXTENSION_MAP = {
    "before_char": 0,
    "after_char": 1,
    "before_examples": 5,
    "after_examples": 6,
}
MESSAGE_ROLE_EXTENSION_MAP = {
    "system": 0,
    "user": 1,
    "assistant": 2,
}


def build_character_card_payload(project: dict, character: dict) -> dict[str, Any]:
    extensions = _build_card_extensions(
        project=project,
        character_note=str(character.get("character_note", "") or "").strip(),
        character_note_depth=int(character.get("character_note_depth") or 4),
        character_note_role=str(character.get("character_note_role", "system") or "system"),
        talkativeness=character.get("talkativeness"),
        world_name="",
        extra_metadata={
            "project": project.get("name", ""),
            "card_role": "character",
            "appearance_summary": str(character.get("appearance_summary", "") or "").strip(),
            "booru_character_name": str(character.get("booru_character_name", "") or "").strip(),
            "booru_copyright": str(character.get("booru_copyright", "") or "").strip(),
        },
    )
    payload = CharacterCardExport(
        data={
            "name": character["name"],
            "description": character.get("description", ""),
            "personality": character.get("personality", ""),
            "scenario": character.get("scenario", ""),
            "first_mes": character.get("first_message", ""),
            "mes_example": character.get("example_dialogue", ""),
            "creator_notes": character.get("creator_notes", ""),
            "system_prompt": character.get("system_prompt", ""),
            "post_history_instructions": character.get("post_history_instructions", ""),
            "alternate_greetings": character.get("alternate_greetings", []),
            "tags": character.get("tags", []),
            "creator": character.get("creator", ""),
            "character_version": character.get("character_version", ""),
            "avatar": "none",
            "extensions": extensions,
        }
    )
    return payload.model_dump(mode="json")


def build_gm_card_payload(project: dict) -> dict[str, Any]:
    profile = project.get("gm_card_profile", {}) or {}
    lorebook_name = _project_lorebook_name(project)
    extensions = _build_card_extensions(
        project=project,
        character_note=str(profile.get("character_note", "") or "").strip(),
        character_note_depth=int(profile.get("character_note_depth") or 4),
        character_note_role=str(profile.get("character_note_role", "system") or "system"),
        talkativeness=profile.get("talkativeness"),
        world_name=lorebook_name if project.get("lore_entries") else "",
        extra_metadata={
            "project": project.get("name", ""),
            "card_role": "game_master",
            "project_mode": project.get("project_mode", "character"),
        },
    )
    data: dict[str, Any] = {
        "name": profile.get("name", f"{project['name']} GM"),
        "description": profile.get("description", ""),
        "personality": profile.get("personality", ""),
        "scenario": profile.get("scenario", project.get("scenario_text", "")),
        "first_mes": profile.get("first_message", ""),
        "mes_example": profile.get("example_dialogue", ""),
        "creator_notes": profile.get("creator_notes", ""),
        "system_prompt": profile.get("system_prompt", ""),
        "post_history_instructions": profile.get("post_history_instructions", ""),
        "alternate_greetings": profile.get("alternate_greetings", []),
        "tags": profile.get("tags", []),
        "creator": profile.get("creator", ""),
        "character_version": profile.get("character_version", ""),
        "avatar": "none",
        "extensions": extensions,
    }
    if project.get("project_mode") == "game_master":
        data = _reinforce_gm_card_export(project, data)
    if project.get("lore_entries"):
        data["character_book"] = build_embedded_lorebook(project)
    payload = CharacterCardExport(data=data)
    return payload.model_dump(mode="json")


def build_lorebook_export(project: dict) -> dict[str, Any]:
    entries: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(project.get("lore_entries", []), start=1):
        entries[str(index)] = LorebookExportEntry(
            uid=index,
            key=item.get("keys", []),
            keysecondary=item.get("secondary_keys", []),
            name=item.get("name", ""),
            comment=item.get("comment", ""),
            content=item.get("content", ""),
            constant=bool(item.get("constant", False)),
            selective=True,
            insertion_order=int(item.get("insertion_order", 100)),
            enabled=bool(item.get("enabled", True)),
            position=_normalize_lore_position(item.get("position")),
            selective_logic=int(item.get("selective_logic", 0) or 0),
            probability=int(item.get("probability", 100) or 100),
            case_sensitive=bool(item.get("case_sensitive", False)),
            priority=int(item.get("priority", 0) or 0),
            scan_depth=_optional_int(item.get("scan_depth")),
            match_whole_words=_optional_bool(item.get("match_whole_words")),
            group=str(item.get("group_name", item.get("group", "")) or ""),
            group_weight=int(item.get("group_weight", 100) or 100),
            prevent_recursion=bool(item.get("prevent_recursion", True)),
            delay_until_recursion=bool(item.get("delay_until_recursion", False)),
            character_filter_json=str(item.get("character_filter_json", "") or ""),
            automation_id=str(item.get("automation_id", "") or ""),
            role=_normalize_role(item.get("role")),
            extensions=_build_lore_entry_extensions(index, item, project),
        ).model_dump(mode="json")
    payload = LorebookExport(
        name=_project_lorebook_name(project),
        description=f"Lore export for {project['name']}",
        scan_depth=int(project.get("lorebook_scan_depth") or 4),
        token_budget=int(project.get("lorebook_token_budget") or 512),
        recursive_scanning=bool(project.get("lorebook_recursive_scanning", False)),
        entries=entries,
    )
    return payload.model_dump(mode="json")


def build_persona_export(project: dict, *, avatar_url: str | None = None) -> dict[str, Any]:
    profile = project.get("user_profile", {}) or {}
    return PersonaExport(
        name=profile.get("name", "User"),
        description=_compose_persona_description(profile),
        title=str(profile.get("title", "") or "").strip(),
        avatar_url=avatar_url,
        personality=profile.get("personality", ""),
        scenario_role=profile.get("scenario_role", ""),
        first_message=profile.get("first_message", ""),
        tags=profile.get("tags", []),
        persona_note=str(profile.get("persona_note", "") or "").strip(),
        persona_note_depth=int(profile.get("persona_note_depth") or 4),
        persona_note_role=_normalize_role(profile.get("persona_note_role")),
        linked_lorebook=_project_lorebook_name(project) if project.get("lore_entries") else None,
        appearance_summary=str(profile.get("appearance_summary", "") or "").strip(),
        booru_character_name=str(profile.get("booru_character_name", "") or "").strip(),
        booru_copyright=str(profile.get("booru_copyright", "") or "").strip(),
    ).model_dump(mode="json")


def build_persona_card_payload(project: dict) -> dict[str, Any]:
    profile = project.get("user_profile", {}) or {}
    extensions = _build_card_extensions(
        project=project,
        character_note=str(profile.get("persona_note", "") or "").strip(),
        character_note_depth=int(profile.get("persona_note_depth") or 4),
        character_note_role=str(profile.get("persona_note_role", "system") or "system"),
        talkativeness=None,
        world_name="",
        extra_metadata={
            "project": project.get("name", ""),
            "card_role": "persona",
            "title": str(profile.get("title", "") or "").strip(),
            "appearance_summary": str(profile.get("appearance_summary", "") or "").strip(),
            "booru_character_name": str(profile.get("booru_character_name", "") or "").strip(),
            "booru_copyright": str(profile.get("booru_copyright", "") or "").strip(),
        },
    )
    payload = CharacterCardExport(
        data={
            "name": profile.get("name", "User"),
            "description": profile.get("description", ""),
            "personality": profile.get("personality", ""),
            "scenario": profile.get("scenario_role", ""),
            "first_mes": profile.get("first_message", ""),
            "mes_example": "",
            "creator_notes": f"Persona export from {project.get('name', 'project')}.",
            "system_prompt": "",
            "post_history_instructions": "",
            "alternate_greetings": [],
            "tags": profile.get("tags", []),
            "creator": "",
            "character_version": "2.0",
            "avatar": "none",
            "extensions": extensions,
        }
    )
    return payload.model_dump(mode="json")


def build_bundle_export(project: dict, *, avatar_url: str | None = None) -> dict[str, Any]:
    lorebook_name = _project_lorebook_name(project)
    return {
        "project": {
            "id": project["id"],
            "name": project["name"],
            "seed_sentence": project["seed_sentence"],
            "scenario_text": project["scenario_text"],
            "project_mode": project.get("project_mode", "character"),
            "sample_character_target_count": project.get("sample_character_target_count", 1),
            "genre": project["genre"],
            "tone": project["tone"],
            "lorebook_name": lorebook_name,
        },
        "gm_card": build_gm_card_payload(project),
        "characters": [build_character_card_payload(project, item) for item in project.get("characters", [])],
        "lorebook": build_lorebook_export(project),
        "persona_bundle": build_persona_export(project, avatar_url=avatar_url),
        "persona_card": build_persona_card_payload(project),
        "export_meta": {
            "spec": "stcc_export_bundle_v2",
            "gm_embeds_lorebook": bool(project.get("lore_entries")),
            "primary_lorebook_name": lorebook_name if project.get("lore_entries") else "",
            "character_count": len(project.get("characters", [])),
            "persona_card_available": True,
        },
    }


def build_embedded_lorebook(project: dict) -> dict[str, Any]:
    entries = [
        _build_embedded_lorebook_entry(index, item, project)
        for index, item in enumerate(project.get("lore_entries", []), start=1)
    ]
    return {
        "name": _project_lorebook_name(project),
        "description": f"Embedded lorebook for {project['name']}",
        "scan_depth": int(project.get("lorebook_scan_depth") or 4),
        "token_budget": int(project.get("lorebook_token_budget") or 512),
        "recursive_scanning": bool(project.get("lorebook_recursive_scanning", False)),
        "extensions": {},
        "entries": entries,
    }


def export_card_image(
    *,
    repository: Any,
    project: dict,
    payload: dict[str, Any],
    export_dir_name: str,
    image_basename: str,
    image_format: str,
    source_relative_paths: list[str | None],
    placeholder_title: str,
) -> Path:
    project_root = repository.ensure_project_assets(project["id"])
    export_dir = project_root / export_dir_name
    export_dir.mkdir(parents=True, exist_ok=True)
    output_path = export_dir / f"{image_basename}.{image_format}"
    write_card_image_file(
        output_path,
        project_root=project_root,
        payload=payload,
        image_format=image_format,
        source_relative_paths=source_relative_paths,
        placeholder_title=placeholder_title,
    )
    return output_path


def write_card_image_file(
    output_path: Path,
    *,
    project_root: Path,
    payload: dict[str, Any],
    image_format: str,
    source_relative_paths: list[str | None],
    placeholder_title: str,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = _load_card_source_image(project_root, source_relative_paths, placeholder_title)
    _write_card_image(output_path, image=image, image_format=image_format, payload=payload)


def _build_embedded_lorebook_entry(index: int, item: dict, project: dict) -> dict[str, Any]:
    return {
        "id": index,
        "name": item.get("name", ""),
        "keys": item.get("keys", []),
        "secondary_keys": item.get("secondary_keys", []),
        "content": item.get("content", ""),
        "enabled": bool(item.get("enabled", True)),
        "insertion_order": int(item.get("insertion_order", 100)),
        "case_sensitive": bool(item.get("case_sensitive", False)),
        "priority": int(item.get("priority", 0) or 0),
        "comment": item.get("comment", ""),
        "selective": True,
        "constant": bool(item.get("constant", False)),
        "position": _normalize_lore_position(item.get("position")),
        "probability": int(item.get("probability", 100) or 100),
        "selectiveLogic": int(item.get("selective_logic", 0) or 0),
        "extensions": _build_lore_entry_extensions(index, item, project),
    }


def _build_card_extensions(
    *,
    project: dict,
    character_note: str,
    character_note_depth: int,
    character_note_role: str,
    talkativeness: Any,
    world_name: str,
    extra_metadata: dict[str, Any],
) -> dict[str, Any]:
    extensions: dict[str, Any] = {
        "fav": False,
        "world": world_name,
        "stcc": extra_metadata,
    }
    if character_note:
        extensions["depth_prompt"] = {
            "prompt": character_note,
            "depth": int(character_note_depth or 4),
            "role": _normalize_role(character_note_role),
        }
    if talkativeness not in {None, ""}:
        try:
            extensions["talkativeness"] = f"{float(talkativeness):g}"
        except (TypeError, ValueError):
            pass
    if project.get("project_mode"):
        extensions["stcc"]["project_mode"] = project.get("project_mode")
    return extensions


def _build_lore_entry_extensions(index: int, item: dict, project: dict) -> dict[str, Any]:
    parsed_extensions = _parse_json_object(item.get("extensions_json"), default={})
    role_name = _normalize_role(item.get("role"))
    extensions = {
        "position": LORE_POSITION_EXTENSION_MAP[_normalize_lore_position(item.get("position"))],
        "exclude_recursion": bool(item.get("prevent_recursion", True)),
        "excludeRecursion": bool(item.get("prevent_recursion", True)),
        "display_index": index - 1,
        "displayIndex": index,
        "probability": int(item.get("probability", 100) or 100),
        "useProbability": True,
        "depth": _optional_int(item.get("scan_depth")) if _optional_int(item.get("scan_depth")) is not None else int(project.get("lorebook_scan_depth") or 4),
        "selectiveLogic": int(item.get("selective_logic", 0) or 0),
        "group": str(item.get("group_name", item.get("group", "")) or ""),
        "group_override": bool(str(item.get("group_name", item.get("group", "")) or "").strip()),
        "group_weight": int(item.get("group_weight", 100) or 100),
        "prevent_recursion": bool(item.get("prevent_recursion", True)),
        "delay_until_recursion": bool(item.get("delay_until_recursion", False)),
        "scan_depth": _optional_int(item.get("scan_depth")),
        "match_whole_words": _optional_bool(item.get("match_whole_words")),
        "use_group_scoring": False,
        "case_sensitive": bool(item.get("case_sensitive", False)),
        "automation_id": str(item.get("automation_id", "") or ""),
        "role": MESSAGE_ROLE_EXTENSION_MAP[role_name],
        "vectorized": False,
        "addMemo": True,
        "characterFilter": _parse_json_value(item.get("character_filter_json")),
        "weight": int(item.get("priority", 0) or 0),
    }
    extensions.update(parsed_extensions)
    return extensions


def _load_card_source_image(project_root: Path, source_relative_paths: list[str | None], placeholder_title: str) -> Image.Image:
    for relative_path in source_relative_paths:
        if not relative_path:
            continue
        candidate = project_root / str(relative_path)
        if candidate.exists():
            return Image.open(candidate).convert("RGBA")
    image = Image.new("RGBA", (1024, 1024), color=(28, 32, 40, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((24, 24, 1000, 1000), outline=(247, 206, 140, 255), width=6)
    draw.text((64, 96), placeholder_title, fill=(255, 255, 255, 255))
    draw.text((64, 152), "Generated export placeholder", fill=(200, 200, 200, 255))
    return image


def _write_card_image(output_path: Path, *, image: Image.Image, image_format: str, payload: dict[str, Any]) -> None:
    encoded_payload = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("ascii")
    if image_format == "png":
        png_info = PngImagePlugin.PngInfo()
        png_info.add_text("chara", encoded_payload)
        image.save(output_path, format="PNG", pnginfo=png_info)
        return
    exif = Image.Exif()
    exif[WEBP_EXIF_USER_COMMENT] = encoded_payload.encode("utf-8")
    image.save(output_path, format="WEBP", quality=95, exif=exif.tobytes())


def _compose_persona_description(profile: dict) -> str:
    sections: list[str] = []
    description = str(profile.get("description", "") or "").strip()
    title = str(profile.get("title", "") or "").strip()
    personality = str(profile.get("personality", "") or "").strip()
    scenario_role = str(profile.get("scenario_role", "") or "").strip()
    appearance_summary = str(profile.get("appearance_summary", "") or "").strip()

    if description:
        sections.append(description)
    if title:
        sections.append(f"Title: {title}")
    if personality:
        sections.append(f"Personality: {personality}")
    if scenario_role:
        sections.append(f"Role: {scenario_role}")
    if appearance_summary:
        sections.append(f"Appearance: {appearance_summary}")

    return "\n\n".join(sections).strip() or description


def _reinforce_gm_card_export(project: dict, data: dict[str, Any]) -> dict[str, Any]:
    profile = dict(data)
    pattern = _infer_export_gm_pattern(project)
    user_name = str((project.get("user_profile", {}) or {}).get("name", "") or "User").strip() or "User"
    project_name = str(project.get("name", "") or "Project").strip() or "Project"
    if _gm_export_name_confuses_user_role(str(profile.get("name", "") or ""), pattern):
        profile["name"] = f"{project_name} GM"

    description_contract = _export_gm_description_contract(pattern, user_name)
    scenario_contract = _export_gm_scenario_contract(
        project,
        pattern=pattern,
        user_name=user_name,
        scenario_text=str(profile.get("scenario", "") or project.get("scenario_text", "") or ""),
    )
    system_contract = _export_gm_system_contract(pattern)
    post_history_contract = _export_gm_post_history_contract(pattern)
    note_contract = _export_gm_note_contract(pattern)

    profile["description"] = _join_unique_sections(description_contract, str(profile.get("description", "") or ""))
    profile["scenario"] = scenario_contract
    profile["system_prompt"] = _join_unique_sections(system_contract, str(profile.get("system_prompt", "") or ""))
    profile["post_history_instructions"] = _join_unique_sections(
        str(profile.get("post_history_instructions", "") or ""),
        post_history_contract,
    )

    extensions = dict(profile.get("extensions", {}) or {})
    depth_prompt = dict(extensions.get("depth_prompt", {}) or {})
    depth_prompt["prompt"] = _join_unique_sections(note_contract, str(depth_prompt.get("prompt", "") or ""))
    depth_prompt["depth"] = int(depth_prompt.get("depth") or 4)
    depth_prompt["role"] = _normalize_role(depth_prompt.get("role"))
    extensions["depth_prompt"] = depth_prompt
    profile["extensions"] = extensions

    tags = profile.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    required_tags = ["game_master", "scenario", "narrator"]
    if pattern == "tavern_story_listener":
        required_tags.extend(["tavern", "npc-customers"])
    profile["tags"] = _merge_tags([str(tag) for tag in tags], required_tags)

    if not str(profile.get("first_mes", "") or "").strip():
        if pattern == "tavern_story_listener":
            profile["first_mes"] = (
                f"The tavern doors open, {user_name}, and three different customers want your attention at once. "
                "Who do you address first?"
            )
        else:
            profile["first_mes"] = "The scene is already moving. What do you do first?"
    return profile


def _infer_export_gm_pattern(project: dict) -> str:
    combined = " ".join(
        [
            str(project.get("name", "") or ""),
            str(project.get("seed_sentence", "") or ""),
            str(project.get("scenario_text", "") or ""),
            str((project.get("gm_card_profile", {}) or {}).get("scenario", "") or ""),
        ]
    ).lower()
    if any(token in combined for token in ("tavern", "inn", "barkeep", "bartender", "pub owner", "taverner")):
        return "tavern_story_listener"
    if any(token in combined for token in ("labyrinth", "maze", "minotaur", "dungeon", "catacomb")):
        return "labyrinth_explorer"
    return "generic_gm"


def _export_gm_description_contract(pattern: str, user_name: str) -> str:
    if pattern == "tavern_story_listener":
        return (
            "{{char}} is the Game Master and narrator. {{char}} is not the tavern owner and never replaces {{user}}. "
            f"{{{{user}}}}/{user_name} is the tavern owner. {{char}} creates and plays customers, travelers, staff, rumors, requests, and consequences."
        )
    return (
        "{{char}} is the Game Master and narrator. {{char}} is not {{user}} and never replaces {{user}}. "
        f"{{{{user}}}}/{user_name} is the active player character. {{char}} runs the world, NPCs, pacing, and consequences."
    )


def _export_gm_scenario_contract(project: dict, *, pattern: str, user_name: str, scenario_text: str) -> str:
    scenario = scenario_text.strip() or str(project.get("scenario_text", "") or "").strip()
    if pattern == "tavern_story_listener":
        lead = (
            f"{{{{user}}}}/{user_name} owns and runs the tavern. "
            "{{char}} narrates the tavern, introduces customers and other NPCs, speaks for those NPCs, and resolves consequences. "
            "{{char}} never writes {{user}}'s actions, dialogue, thoughts, or feelings."
        )
    else:
        lead = (
            f"{{{{user}}}}/{user_name} is the active protagonist. "
            "{{char}} runs the scenario as narrator and NPC handler while leaving every player choice to {{user}}."
        )
    return _join_unique_sections(lead, scenario)


def _export_gm_system_contract(pattern: str) -> str:
    if pattern == "tavern_story_listener":
        return (
            "You are {{char}}, the Game Master for a tavern-owner roleplay. Write as narrator and NPC customers only. "
            "Generate distinct patrons, heroes, workers, troublemakers, and rumor-bringers, then play them while they come and go. "
            "Never write as {{user}}, decide {{user}}'s actions, or make {{user}} speak."
        )
    return (
        "You are {{char}}, the Game Master for this roleplay. Write as narrator and NPCs only. "
        "Never write as {{user}}, decide {{user}}'s actions, or make {{user}} speak."
    )


def _export_gm_post_history_contract(pattern: str) -> str:
    if pattern == "tavern_story_listener":
        return (
            "Final reply rules: {{user}} owns the tavern; {{char}} runs the world and NPC customers. "
            "Respond to {{user}}'s latest action, advance the tavern scene through NPC behavior, and leave a clear opening for {{user}} to choose."
        )
    return (
        "Final reply rules: respond to {{user}}'s latest action, advance the scene through narration and NPC behavior, and leave the next decision to {{user}}."
    )


def _export_gm_note_contract(pattern: str) -> str:
    if pattern == "tavern_story_listener":
        return "Stay in GM mode. {{user}} is the tavern owner. Introduce and play NPC customers. Never act as {{user}}."
    return "Stay in GM mode. Present consequences clearly, play NPCs distinctly, and never act as {{user}}."


def _gm_export_name_confuses_user_role(name: str, pattern: str) -> bool:
    normalized = name.lower().strip()
    if normalized in {"user", "{{user}}", "player", "protagonist"}:
        return True
    if pattern == "tavern_story_listener":
        return any(token in normalized for token in ("tavern owner", "innkeeper", "barkeep", "bartender", "publican"))
    return False


def _join_unique_sections(*sections: str) -> str:
    output: list[str] = []
    seen: set[str] = set()
    for section in sections:
        cleaned = str(section or "").strip()
        if not cleaned:
            continue
        key = " ".join(cleaned.split()).lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(cleaned)
    return "\n\n".join(output)


def _merge_tags(tags: list[str], required: list[str]) -> list[str]:
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


def _project_lorebook_name(project: dict) -> str:
    return f"{project['name']} Lorebook"


def _normalize_role(value: Any) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in {"system", "user", "assistant"}:
        return candidate
    return "system"


def _normalize_lore_position(value: Any) -> str:
    candidate = str(value or "").strip().lower()
    if candidate == "global":
        return "after_char"
    if candidate in {"before_char", "after_char", "before_examples", "after_examples"}:
        return candidate
    return "after_char"


def _optional_int(value: Any) -> int | None:
    try:
        if value in {None, ""}:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_bool(value: Any) -> bool | None:
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


def _parse_json_object(value: Any, *, default: dict[str, Any]) -> dict[str, Any]:
    parsed = _parse_json_value(value)
    return parsed if isinstance(parsed, dict) else dict(default)


def _parse_json_value(value: Any) -> Any:
    if value in {None, ""}:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
