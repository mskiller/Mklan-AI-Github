from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
import shutil
import uuid

from .config import Settings
from .database import Database, utc_now_iso
from app.movie.media_generation_settings import MEDIA_GENERATION_SETTINGS_KEY, normalize_media_generation_settings
from .model_settings import (
    build_default_model_settings,
    build_task_catalog,
    default_project_model_settings_override,
    normalize_model_settings,
    normalize_project_model_settings_override,
    resolve_model_settings,
)


def _loads(raw_value: str | None, fallback: object) -> object:
    if not raw_value:
        return fallback
    try:
        return json.loads(raw_value)
    except Exception:
        return fallback


def _clean_text(value: object, fallback: str = "") -> str:
    if value is None:
        return fallback
    if isinstance(value, Enum):
        value = value.value
    return str(value).strip()


def _clean_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        items = [part.strip() for part in value.replace("\n", ",").split(",")]
        return [item for item in items if item]
    return []


def _normalize_project_mode(value: object) -> str:
    mode = _clean_text(value, "character").lower() or "character"
    if mode not in {"game_master", "character"}:
        return "character"
    return mode


def _normalize_message_role(value: object, default: str = "system") -> str:
    role = _clean_text(value, default).lower() or default
    if role not in {"system", "user", "assistant"}:
        return default
    return role


def _normalize_lore_position(value: object) -> str:
    position = _clean_text(value, "after_char").lower() or "after_char"
    if position == "global":
        return "after_char"
    if position not in {"before_char", "after_char", "before_examples", "after_examples"}:
        return "after_char"
    return position


def _normalize_probability(value: object, default: int = 100) -> int:
    try:
        probability = int(value)
    except (TypeError, ValueError):
        probability = default
    return max(0, min(100, probability))


def _normalize_weight(value: object, default: int = 100) -> int:
    try:
        weight = int(value)
    except (TypeError, ValueError):
        weight = default
    return max(0, weight)


def _normalize_priority(value: object, default: int = 0) -> int:
    try:
        priority = int(value)
    except (TypeError, ValueError):
        priority = default
    return max(0, priority)


def _normalize_optional_int(value: object) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_optional_float(value: object) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_sample_character_target_count(value: object, default: int = 5) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        count = default
    return max(1, min(10, count))


def _default_gm_card_profile(project_name: str = "Game Master Card", scenario_text: str = "") -> dict:
    return {
        "name": project_name or "Game Master Card",
        "description": "",
        "personality": "",
        "scenario": scenario_text or "",
        "first_message": "",
        "example_dialogue": "",
        "tags": ["game_master", "scenario"],
        "creator_notes": "",
        "system_prompt": "",
        "post_history_instructions": "",
        "alternate_greetings": [],
        "creator": "",
        "character_version": "",
        "character_note": "",
        "character_note_depth": 4,
        "character_note_role": "system",
        "talkativeness": None,
    }


def _normalize_gm_card_profile(raw_value: object, project_name: str = "", scenario_text: str = "") -> dict:
    base = _default_gm_card_profile(project_name, scenario_text)
    source = raw_value if isinstance(raw_value, dict) else {}
    tags_source = source["tags"] if "tags" in source else base["tags"]
    greetings_source = source["alternate_greetings"] if "alternate_greetings" in source else base["alternate_greetings"]
    return {
        "name": _clean_text(source.get("name"), base["name"]),
        "description": _clean_text(source.get("description"), ""),
        "personality": _clean_text(source.get("personality"), ""),
        "scenario": _clean_text(source.get("scenario"), base["scenario"]),
        "first_message": _clean_text(source.get("first_message"), ""),
        "example_dialogue": _clean_text(source.get("example_dialogue"), ""),
        "tags": _clean_string_list(tags_source),
        "creator_notes": _clean_text(source.get("creator_notes"), ""),
        "system_prompt": _clean_text(source.get("system_prompt"), ""),
        "post_history_instructions": _clean_text(source.get("post_history_instructions"), ""),
        "alternate_greetings": _clean_string_list(greetings_source),
        "creator": _clean_text(source.get("creator"), ""),
        "character_version": _clean_text(source.get("character_version"), ""),
        "character_note": _clean_text(source.get("character_note"), ""),
        "character_note_depth": _normalize_optional_int(source.get("character_note_depth")) or 4,
        "character_note_role": _normalize_message_role(source.get("character_note_role"), "system"),
        "talkativeness": _normalize_optional_float(source.get("talkativeness")),
    }


@dataclass
class MovieRepository:
    database: Database
    settings: Settings

    MODEL_SETTINGS_KEY = "model_settings_json"
    MEDIA_SETTINGS_KEY = MEDIA_GENERATION_SETTINGS_KEY

    ASSISTANT_SETTING_KEYS = {
        "provider": "scenario_assistant_provider",
        "base_url": "scenario_assistant_base_url",
        "model": "scenario_assistant_model",
        "api_key": "scenario_assistant_api_key",
        "timeout_s": "scenario_assistant_timeout_s",
    }

    def initialize(self) -> None:
        self.database.initialize()
        self.settings.projects_root.mkdir(parents=True, exist_ok=True)
        self.settings.models_root.mkdir(parents=True, exist_ok=True)
        self.settings.default_image_model_root.mkdir(parents=True, exist_ok=True)
        self.settings.templates_root.mkdir(parents=True, exist_ok=True)
        self.get_model_settings()
        self.get_media_generation_settings()

    def list_projects(self, scope: str = "active") -> list[dict]:
        scope = scope.lower()
        where_clause = ""
        if scope == "active":
            where_clause = "WHERE p.archived_at IS NULL"
        elif scope == "archived":
            where_clause = "WHERE p.archived_at IS NOT NULL"
        elif scope != "all":
            raise ValueError(f"Unsupported project scope: {scope}")

        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    p.*,
                    (SELECT COUNT(*) FROM characters c WHERE c.project_id = p.id) AS character_count,
                    (SELECT COUNT(*) FROM lore_entries l WHERE l.project_id = p.id) AS lore_count
                FROM projects p
                {where_clause}
                ORDER BY p.updated_at DESC
                """
            ).fetchall()
        return [self._project_list_item_from_row(row) for row in rows]

    def create_project(self, data: dict) -> dict:
        project_id = str(uuid.uuid4())
        now = utc_now_iso()
        project_mode = _normalize_project_mode(data.get("project_mode"))
        sample_character_target_count = _normalize_sample_character_target_count(
            data.get("sample_character_target_count"),
            5,
        )
        default_gm_profile = _default_gm_card_profile(
            project_name=_clean_text(data.get("name"), "Game Master Card"),
            scenario_text=_clean_text(data.get("scenario_text"), ""),
        )
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO projects (
                    id, name, seed_sentence, scenario_text, project_mode, sample_character_target_count,
                    lorebook_scan_depth, lorebook_token_budget, lorebook_recursive_scanning,
                    scenario_image_relative_path, genre, tone,
                    gm_card_profile_json, model_settings_override_json, archived_at, created_at, updated_at
                , workspace_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, \'default\')
                """,
                (
                    project_id,
                    data["name"],
                    data.get("seed_sentence", ""),
                    data.get("scenario_text", ""),
                    project_mode,
                    sample_character_target_count,
                    int(data.get("lorebook_scan_depth", 4) or 4),
                    int(data.get("lorebook_token_budget", 512) or 512),
                    1 if data.get("lorebook_recursive_scanning", False) else 0,
                    data.get("scenario_image_relative_path"),
                    data.get("genre", "roleplay"),
                    data.get("tone", "immersive"),
                    json.dumps(default_gm_profile),
                    json.dumps(default_project_model_settings_override()),
                    None,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO user_profiles (
                    project_id, name, description, title, personality, scenario_role,
                    first_message, tags_json, persona_note, persona_note_depth, persona_note_role,
                    appearance_summary, booru_character_name,
                    booru_copyright, portrait_relative_path, cowboy_shot_relative_path,
                    fullbody_shot_relative_path, created_at, updated_at, workspace_id
                ) VALUES (%s, %s, '', '', '', '', '', '[]', '', 4, 'system', '', '', '', NULL, NULL, NULL, %s, %s, 'default')
                """,
                (project_id, "User", now, now),
            )
        self.ensure_project_assets(project_id)
        return self.get_project_detail(project_id)

    def get_project_record(self, project_id: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM projects WHERE id = %s AND workspace_id = \'default\'", (project_id,)).fetchone()
        return None if row is None else self._project_from_row(row)

    def get_project_detail(self, project_id: str) -> dict | None:
        with self.database.connect() as connection:
            project_row = connection.execute("SELECT * FROM projects WHERE id = %s AND workspace_id = \'default\'", (project_id,)).fetchone()
            if project_row is None:
                return None
            character_rows = connection.execute(
                "SELECT * FROM characters WHERE project_id = %s AND workspace_id = \'default\' ORDER BY created_at ASC", (project_id,)
            ).fetchall()
            lore_rows = connection.execute(
                "SELECT * FROM lore_entries WHERE project_id = %s AND workspace_id = \'default\' ORDER BY insertion_order ASC, created_at ASC",
                (project_id,),
            ).fetchall()
            user_row = connection.execute("SELECT * FROM user_profiles WHERE project_id = %s AND workspace_id = \'default\'", (project_id,)).fetchone()
            run_rows = connection.execute(
                "SELECT * FROM generation_runs WHERE project_id = %s AND workspace_id = \'default\' ORDER BY created_at DESC LIMIT 25", (project_id,)
            ).fetchall()

        project = self._project_from_row(project_row)
        project["characters"] = [self._character_from_row(row) for row in character_rows]
        project["lore_entries"] = [self._lore_entry_from_row(row) for row in lore_rows]
        project["user_profile"] = self._user_profile_from_row(user_row) if user_row else self._default_user_profile(project_id)
        project["generation_runs"] = [self._generation_run_from_row(row) for row in run_rows]
        return project

    def update_project(self, project_id: str, updates: dict) -> dict | None:
        clean_updates = {key: value for key, value in updates.items() if value is not None}
        if "project_mode" in clean_updates:
            clean_updates["project_mode"] = _normalize_project_mode(clean_updates["project_mode"])
        if "sample_character_target_count" in clean_updates:
            clean_updates["sample_character_target_count"] = _normalize_sample_character_target_count(
                clean_updates["sample_character_target_count"],
                5,
            )
        if "lorebook_scan_depth" in clean_updates:
            clean_updates["lorebook_scan_depth"] = _normalize_optional_int(clean_updates["lorebook_scan_depth"]) or 4
        if "lorebook_token_budget" in clean_updates:
            clean_updates["lorebook_token_budget"] = _normalize_optional_int(clean_updates["lorebook_token_budget"]) or 512
        if "lorebook_recursive_scanning" in clean_updates:
            clean_updates["lorebook_recursive_scanning"] = 1 if clean_updates["lorebook_recursive_scanning"] else 0
        if not clean_updates:
            return self.get_project_detail(project_id)

        assignments = []
        values: list[object] = []
        now = utc_now_iso()
        for key, value in clean_updates.items():
            assignments.append(f"{key} = %s")
            values.append(value)
        assignments.append("updated_at = %s")
        values.append(now)
        values.append(project_id)

        with self.database.connect() as connection:
            cursor = connection.execute(
                f"UPDATE projects SET {', '.join(assignments)} WHERE id = %s AND workspace_id = \'default\'",
                values,
            )
            if cursor.rowcount == 0:
                return None
        return self.get_project_detail(project_id)

    def get_gm_card_profile(self, project_id: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT name, scenario_text, gm_card_profile_json FROM projects WHERE id = %s AND workspace_id = \'default\'",
                (project_id,),
            ).fetchone()
        if row is None:
            return None
        return _normalize_gm_card_profile(
            _loads(row["gm_card_profile_json"], {}),
            project_name=row["name"] or "",
            scenario_text=row["scenario_text"] or "",
        )

    def update_gm_card_profile(self, project_id: str, updates: dict) -> dict | None:
        existing_project = self.get_project_record(project_id)
        if existing_project is None:
            return None
        current = self.get_gm_card_profile(project_id) or _default_gm_card_profile(
            project_name=existing_project.get("name", "Game Master Card"),
            scenario_text=existing_project.get("scenario_text", ""),
        )
        merged = {**current, **{key: value for key, value in updates.items() if value is not None}}
        normalized = _normalize_gm_card_profile(
            merged,
            project_name=existing_project.get("name", "Game Master Card"),
            scenario_text=existing_project.get("scenario_text", ""),
        )
        now = utc_now_iso()
        with self.database.connect() as connection:
            cursor = connection.execute(
                "UPDATE projects SET gm_card_profile_json = %s, updated_at = %s WHERE id = %s AND workspace_id = \'default\'",
                (json.dumps(normalized), now, project_id),
            )
            if cursor.rowcount == 0:
                return None
        return normalized

    def archive_project(self, project_id: str) -> dict | None:
        now = utc_now_iso()
        with self.database.connect() as connection:
            row = connection.execute("SELECT archived_at FROM projects WHERE id = %s AND workspace_id = \'default\'", (project_id,)).fetchone()
            if row is None:
                return None
            archived_at = row["archived_at"] or now
            connection.execute(
                "UPDATE projects SET archived_at = %s, updated_at = %s WHERE id = %s AND workspace_id = \'default\'",
                (archived_at, now, project_id),
            )
        return self.get_project_detail(project_id)

    def restore_project(self, project_id: str) -> dict | None:
        now = utc_now_iso()
        with self.database.connect() as connection:
            cursor = connection.execute(
                "UPDATE projects SET archived_at = NULL, updated_at = %s WHERE id = %s AND workspace_id = \'default\'",
                (now, project_id),
            )
            if cursor.rowcount == 0:
                return None
        return self.get_project_detail(project_id)

    def delete_project(self, project_id: str) -> bool | None:
        root = self.settings.projects_root / project_id
        with self.database.connect() as connection:
            row = connection.execute("SELECT archived_at FROM projects WHERE id = %s AND workspace_id = \'default\'", (project_id,)).fetchone()
            if row is None:
                return None
            if not row["archived_at"]:
                return False
            connection.execute("DELETE FROM projects WHERE id = %s AND workspace_id = \'default\'", (project_id,))
        if root.exists():
            shutil.rmtree(root, ignore_errors=False)
        return True

    def list_characters(self, project_id: str) -> list[dict]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM characters WHERE project_id = %s AND workspace_id = \'default\' ORDER BY created_at ASC", (project_id,)
            ).fetchall()
        return [self._character_from_row(row) for row in rows]

    def get_character(self, character_id: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM characters WHERE id = %s AND workspace_id = \'default\'", (character_id,)).fetchone()
        return None if row is None else self._character_from_row(row)

    def create_character(self, project_id: str, payload: dict) -> dict | None:
        if self.get_project_record(project_id) is None:
            return None
        char_id = str(uuid.uuid4())
        now = utc_now_iso()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO characters (
                    id, project_id, name, description, personality, scenario,
                    first_message, example_dialogue, tags_json, creator_notes,
                    system_prompt, post_history_instructions, alternate_greetings_json,
                    creator, character_version, character_note, character_note_depth, character_note_role, talkativeness,
                    appearance_summary, booru_character_name, booru_copyright,
                    avatar_relative_path, portrait_relative_path, cowboy_shot_relative_path,
                    fullbody_shot_relative_path, created_at, updated_at, workspace_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'default')
                """,
                (
                    char_id,
                    project_id,
                    payload.get("name", "Character"),
                    payload.get("description", ""),
                    payload.get("personality", ""),
                    payload.get("scenario", ""),
                    payload.get("first_message", ""),
                    payload.get("example_dialogue", ""),
                    json.dumps(payload.get("tags") or []),
                    payload.get("creator_notes", ""),
                    payload.get("system_prompt", ""),
                    payload.get("post_history_instructions", ""),
                    json.dumps(payload.get("alternate_greetings") or []),
                    payload.get("creator", ""),
                    payload.get("character_version", ""),
                    payload.get("character_note", ""),
                    _normalize_optional_int(payload.get("character_note_depth")) or 4,
                    _normalize_message_role(payload.get("character_note_role"), "system"),
                    _normalize_optional_float(payload.get("talkativeness")),
                    payload.get("appearance_summary", ""),
                    payload.get("booru_character_name", ""),
                    payload.get("booru_copyright", ""),
                    payload.get("avatar_relative_path"),
                    payload.get("portrait_relative_path"),
                    payload.get("cowboy_shot_relative_path"),
                    payload.get("fullbody_shot_relative_path"),
                    now,
                    now,
                ),
            )
            connection.execute("UPDATE projects SET updated_at = %s WHERE id = %s AND workspace_id = \'default\'", (now, project_id))
        return self.get_character(char_id)

    def replace_characters(self, project_id: str, characters: list[dict]) -> list[dict]:
        now = utc_now_iso()
        with self.database.connect() as connection:
            connection.execute("DELETE FROM characters WHERE project_id = %s AND workspace_id = \'default\'", (project_id,))
            for item in characters:
                char_id = str(uuid.uuid4())
                connection.execute(
                    """
                    INSERT INTO characters (
                        id, project_id, name, description, personality, scenario,
                        first_message, example_dialogue, tags_json, creator_notes,
                        system_prompt, post_history_instructions, alternate_greetings_json,
                        creator, character_version, character_note, character_note_depth, character_note_role, talkativeness,
                        appearance_summary, booru_character_name, booru_copyright,
                        avatar_relative_path, portrait_relative_path, cowboy_shot_relative_path,
                        fullbody_shot_relative_path, created_at, updated_at, workspace_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'default')
                    """,
                    (
                        char_id,
                        project_id,
                        item.get("name", "Character"),
                        item.get("description", ""),
                        item.get("personality", ""),
                        item.get("scenario", ""),
                        item.get("first_message", ""),
                        item.get("example_dialogue", ""),
                        json.dumps(item.get("tags") or []),
                        item.get("creator_notes", ""),
                        item.get("system_prompt", ""),
                        item.get("post_history_instructions", ""),
                        json.dumps(item.get("alternate_greetings") or []),
                        item.get("creator", ""),
                        item.get("character_version", ""),
                        item.get("character_note", ""),
                        _normalize_optional_int(item.get("character_note_depth")) or 4,
                        _normalize_message_role(item.get("character_note_role"), "system"),
                        _normalize_optional_float(item.get("talkativeness")),
                        item.get("appearance_summary", ""),
                        item.get("booru_character_name", ""),
                        item.get("booru_copyright", ""),
                        item.get("avatar_relative_path"),
                        item.get("portrait_relative_path"),
                        item.get("cowboy_shot_relative_path"),
                        item.get("fullbody_shot_relative_path"),
                        now,
                        now,
                    ),
                )
            connection.execute("UPDATE projects SET updated_at = %s WHERE id = %s AND workspace_id = \'default\'", (now, project_id))
        return self.list_characters(project_id)

    def update_character(self, character_id: str, updates: dict) -> dict | None:
        clean = {key: value for key, value in updates.items() if value is not None}
        if not clean:
            return self.get_character(character_id)
        if "tags" in clean:
            clean["tags_json"] = json.dumps(clean.pop("tags"))
        if "alternate_greetings" in clean:
            clean["alternate_greetings_json"] = json.dumps(clean.pop("alternate_greetings"))
        if "character_note_depth" in clean:
            clean["character_note_depth"] = _normalize_optional_int(clean["character_note_depth"]) or 4
        if "character_note_role" in clean:
            clean["character_note_role"] = _normalize_message_role(clean["character_note_role"], "system")
        if "talkativeness" in clean:
            clean["talkativeness"] = _normalize_optional_float(clean["talkativeness"])

        assignments = []
        values: list[object] = []
        for key, value in clean.items():
            assignments.append(f"{key} = %s")
            values.append(value)
        now = utc_now_iso()
        assignments.append("updated_at = %s")
        values.append(now)
        values.append(character_id)

        with self.database.connect() as connection:
            row = connection.execute("SELECT project_id FROM characters WHERE id = %s AND workspace_id = \'default\'", (character_id,)).fetchone()
            if row is None:
                return None
            connection.execute(f"UPDATE characters SET {', '.join(assignments)} WHERE id = %s AND workspace_id = \'default\'", values)
            connection.execute("UPDATE projects SET updated_at = %s WHERE id = %s AND workspace_id = \'default\'", (now, row["project_id"]))
        return self.get_character(character_id)

    def delete_character(self, character_id: str) -> bool:
        now = utc_now_iso()
        with self.database.connect() as connection:
            row = connection.execute("SELECT project_id FROM characters WHERE id = %s AND workspace_id = \'default\'", (character_id,)).fetchone()
            if row is None:
                return False
            connection.execute("DELETE FROM characters WHERE id = %s AND workspace_id = \'default\'", (character_id,))
            connection.execute("UPDATE projects SET updated_at = %s WHERE id = %s AND workspace_id = \'default\'", (now, row["project_id"]))
        return True

    def list_lore_entries(self, project_id: str) -> list[dict]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM lore_entries WHERE project_id = %s AND workspace_id = \'default\' ORDER BY insertion_order ASC, created_at ASC",
                (project_id,),
            ).fetchall()
        return [self._lore_entry_from_row(row) for row in rows]

    def get_lore_entry(self, lore_id: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM lore_entries WHERE id = %s AND workspace_id = \'default\'", (lore_id,)).fetchone()
        return None if row is None else self._lore_entry_from_row(row)

    def create_lore_entry(self, project_id: str, payload: dict) -> dict | None:
        if self.get_project_record(project_id) is None:
            return None
        lore_id = str(uuid.uuid4())
        now = utc_now_iso()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO lore_entries (
                    id, project_id, name, keys_json, secondary_keys_json,
                    content, comment, image_relative_path, enabled, insertion_order, position,
                    constant, selective_logic, probability, case_sensitive, priority,
                    scan_depth, match_whole_words, group_name, group_weight, prevent_recursion,
                    delay_until_recursion, character_filter_json, automation_id, role, extensions_json,
                    created_at, updated_at, workspace_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'default')
                """,
                (
                    lore_id,
                    project_id,
                    payload.get("name", "Lore Entry"),
                    json.dumps(payload.get("keys") or []),
                    json.dumps(payload.get("secondary_keys") or []),
                    payload.get("content", ""),
                    payload.get("comment", ""),
                    payload.get("image_relative_path"),
                    1 if payload.get("enabled", True) else 0,
                    int(payload.get("insertion_order", 100)),
                    _normalize_lore_position(payload.get("position", "after_char")),
                    1 if payload.get("constant", False) else 0,
                    _normalize_optional_int(payload.get("selective_logic")) or 0,
                    _normalize_probability(payload.get("probability", 100), 100),
                    1 if payload.get("case_sensitive", False) else 0,
                    _normalize_priority(payload.get("priority", 0), 0),
                    _normalize_optional_int(payload.get("scan_depth")),
                    None if payload.get("match_whole_words") is None else (1 if payload.get("match_whole_words") else 0),
                    _clean_text(payload.get("group_name", payload.get("group")), ""),
                    _normalize_weight(payload.get("group_weight", 100), 100),
                    1 if payload.get("prevent_recursion", True) else 0,
                    1 if payload.get("delay_until_recursion", False) else 0,
                    _clean_text(payload.get("character_filter_json"), ""),
                    _clean_text(payload.get("automation_id"), ""),
                    _normalize_message_role(payload.get("role"), "system"),
                    _clean_text(payload.get("extensions_json"), "{}") or "{}",
                    now,
                    now,
                ),
            )
            connection.execute("UPDATE projects SET updated_at = %s WHERE id = %s AND workspace_id = \'default\'", (now, project_id))
        return self.get_lore_entry(lore_id)

    def replace_lore_entries(self, project_id: str, entries: list[dict]) -> list[dict]:
        now = utc_now_iso()
        with self.database.connect() as connection:
            connection.execute("DELETE FROM lore_entries WHERE project_id = %s AND workspace_id = \'default\'", (project_id,))
            for item in entries:
                lore_id = str(uuid.uuid4())
                connection.execute(
                    """
                    INSERT INTO lore_entries (
                        id, project_id, name, keys_json, secondary_keys_json,
                        content, comment, image_relative_path, enabled, insertion_order, position,
                        constant, selective_logic, probability, case_sensitive, priority,
                        scan_depth, match_whole_words, group_name, group_weight, prevent_recursion,
                        delay_until_recursion, character_filter_json, automation_id, role, extensions_json,
                        created_at, updated_at, workspace_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'default')
                    """,
                    (
                        lore_id,
                        project_id,
                        item.get("name", "Lore Entry"),
                        json.dumps(item.get("keys") or []),
                        json.dumps(item.get("secondary_keys") or []),
                        item.get("content", ""),
                        item.get("comment", ""),
                        item.get("image_relative_path"),
                        1 if item.get("enabled", True) else 0,
                        int(item.get("insertion_order", 100)),
                        _normalize_lore_position(item.get("position", "after_char")),
                        1 if item.get("constant", False) else 0,
                        _normalize_optional_int(item.get("selective_logic")) or 0,
                        _normalize_probability(item.get("probability", 100), 100),
                        1 if item.get("case_sensitive", False) else 0,
                        _normalize_priority(item.get("priority", 0), 0),
                        _normalize_optional_int(item.get("scan_depth")),
                        None if item.get("match_whole_words") is None else (1 if item.get("match_whole_words") else 0),
                        _clean_text(item.get("group_name", item.get("group")), ""),
                        _normalize_weight(item.get("group_weight", 100), 100),
                        1 if item.get("prevent_recursion", True) else 0,
                        1 if item.get("delay_until_recursion", False) else 0,
                        _clean_text(item.get("character_filter_json"), ""),
                        _clean_text(item.get("automation_id"), ""),
                        _normalize_message_role(item.get("role"), "system"),
                        _clean_text(item.get("extensions_json"), "{}") or "{}",
                        now,
                        now,
                    ),
                )
            connection.execute("UPDATE projects SET updated_at = %s WHERE id = %s AND workspace_id = \'default\'", (now, project_id))
        return self.list_lore_entries(project_id)

    def update_lore_entry(self, lore_id: str, updates: dict) -> dict | None:
        clean = {key: value for key, value in updates.items() if value is not None}
        if not clean:
            return self.get_lore_entry(lore_id)

        if "keys" in clean:
            clean["keys_json"] = json.dumps(clean.pop("keys"))
        if "secondary_keys" in clean:
            clean["secondary_keys_json"] = json.dumps(clean.pop("secondary_keys"))
        if "enabled" in clean:
            clean["enabled"] = 1 if clean["enabled"] else 0
        if "constant" in clean:
            clean["constant"] = 1 if clean["constant"] else 0
        if "case_sensitive" in clean:
            clean["case_sensitive"] = 1 if clean["case_sensitive"] else 0
        if "match_whole_words" in clean:
            value = clean["match_whole_words"]
            clean["match_whole_words"] = None if value is None else (1 if value else 0)
        if "prevent_recursion" in clean:
            clean["prevent_recursion"] = 1 if clean["prevent_recursion"] else 0
        if "delay_until_recursion" in clean:
            clean["delay_until_recursion"] = 1 if clean["delay_until_recursion"] else 0
        if "position" in clean:
            clean["position"] = _normalize_lore_position(clean["position"])
        if "probability" in clean:
            clean["probability"] = _normalize_probability(clean["probability"], 100)
        if "priority" in clean:
            clean["priority"] = _normalize_priority(clean["priority"], 0)
        if "scan_depth" in clean:
            clean["scan_depth"] = _normalize_optional_int(clean["scan_depth"])
        if "selective_logic" in clean:
            clean["selective_logic"] = _normalize_optional_int(clean["selective_logic"]) or 0
        if "group_weight" in clean:
            clean["group_weight"] = _normalize_weight(clean["group_weight"], 100)
        if "group" in clean and "group_name" not in clean:
            clean["group_name"] = clean.pop("group")
        if "role" in clean:
            clean["role"] = _normalize_message_role(clean["role"], "system")

        assignments = []
        values: list[object] = []
        for key, value in clean.items():
            assignments.append(f"{key} = %s")
            values.append(value)
        now = utc_now_iso()
        assignments.append("updated_at = %s")
        values.append(now)
        values.append(lore_id)

        with self.database.connect() as connection:
            row = connection.execute("SELECT project_id FROM lore_entries WHERE id = %s AND workspace_id = \'default\'", (lore_id,)).fetchone()
            if row is None:
                return None
            connection.execute(f"UPDATE lore_entries SET {', '.join(assignments)} WHERE id = %s AND workspace_id = \'default\'", values)
            connection.execute("UPDATE projects SET updated_at = %s WHERE id = %s AND workspace_id = \'default\'", (now, row["project_id"]))
        return self.get_lore_entry(lore_id)

    def delete_lore_entry(self, lore_id: str) -> bool:
        now = utc_now_iso()
        with self.database.connect() as connection:
            row = connection.execute("SELECT project_id FROM lore_entries WHERE id = %s AND workspace_id = \'default\'", (lore_id,)).fetchone()
            if row is None:
                return False
            connection.execute("DELETE FROM lore_entries WHERE id = %s AND workspace_id = \'default\'", (lore_id,))
            connection.execute("UPDATE projects SET updated_at = %s WHERE id = %s AND workspace_id = \'default\'", (now, row["project_id"]))
        return True

    def get_user_profile(self, project_id: str) -> dict:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM user_profiles WHERE project_id = %s AND workspace_id = \'default\'", (project_id,)).fetchone()
            if row is None:
                now = utc_now_iso()
                connection.execute(
                    """
                    INSERT INTO user_profiles (
                        project_id, name, description, title, personality, scenario_role,
                        first_message, tags_json, persona_note, persona_note_depth, persona_note_role,
                        appearance_summary, booru_character_name,
                        booru_copyright, avatar_relative_path, portrait_relative_path,
                        cowboy_shot_relative_path, fullbody_shot_relative_path, created_at, updated_at, workspace_id
                    ) VALUES (%s, %s, '', '', '', '', '', '[]', '', 4, 'system', '', '', '', NULL, NULL, NULL, NULL, %s, %s, 'default')
                    """,
                    (project_id, "User", now, now),
                )
                row = connection.execute("SELECT * FROM user_profiles WHERE project_id = %s AND workspace_id = \'default\'", (project_id,)).fetchone()
        return self._user_profile_from_row(row)

    def update_user_profile(self, project_id: str, updates: dict) -> dict:
        clean = {key: value for key, value in updates.items() if value is not None}
        if "tags" in clean:
            clean["tags_json"] = json.dumps(clean.pop("tags"))
        if "persona_note_depth" in clean:
            clean["persona_note_depth"] = _normalize_optional_int(clean["persona_note_depth"]) or 4
        if "persona_note_role" in clean:
            clean["persona_note_role"] = _normalize_message_role(clean["persona_note_role"], "system")

        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM user_profiles WHERE project_id = %s AND workspace_id = \'default\'", (project_id,)).fetchone()
            if row is None:
                now = utc_now_iso()
                connection.execute(
                    """
                    INSERT INTO user_profiles (
                        project_id, name, description, title, personality, scenario_role,
                        first_message, tags_json, persona_note, persona_note_depth, persona_note_role,
                        appearance_summary, booru_character_name,
                        booru_copyright, avatar_relative_path, portrait_relative_path,
                        cowboy_shot_relative_path, fullbody_shot_relative_path, created_at, updated_at, workspace_id
                    ) VALUES (%s, %s, '', '', '', '', '', '[]', '', 4, 'system', '', '', '', NULL, NULL, NULL, NULL, %s, %s, 'default')
                    """,
                    (project_id, "User", now, now),
                )
            if clean:
                assignments = []
                values: list[object] = []
                for key, value in clean.items():
                    assignments.append(f"{key} = %s")
                    values.append(value)
                now = utc_now_iso()
                assignments.append("updated_at = %s")
                values.append(now)
                values.append(project_id)
                connection.execute(f"UPDATE user_profiles SET {', '.join(assignments)} WHERE project_id = %s AND workspace_id = \'default\'", values)
                connection.execute("UPDATE projects SET updated_at = %s WHERE id = %s AND workspace_id = \'default\'", (now, project_id))
            row = connection.execute("SELECT * FROM user_profiles WHERE project_id = %s AND workspace_id = \'default\'", (project_id,)).fetchone()
        return self._user_profile_from_row(row)

    def add_image_candidate(
        self,
        *,
        project_id: str,
        owner_type: str,
        owner_id: str,
        image_slot: str,
        relative_path: str,
        prompt_text: str = "",
        negative_prompt: str = "",
    ) -> dict:
        candidate_id = str(uuid.uuid4())
        now = utc_now_iso()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO image_candidates (
                    id, project_id, owner_type, owner_id, image_slot,
                    relative_path, prompt_text, negative_prompt, created_at, workspace_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'default')
                """,
                (
                    candidate_id,
                    project_id,
                    owner_type,
                    owner_id,
                    image_slot,
                    relative_path,
                    prompt_text,
                    negative_prompt,
                    now,
                ),
            )
            connection.execute("UPDATE projects SET updated_at = %s WHERE id = %s AND workspace_id = \'default\'", (now, project_id))
            row = connection.execute("SELECT * FROM image_candidates WHERE id = %s AND workspace_id = \'default\'", (candidate_id,)).fetchone()
        return self._image_candidate_from_row(row)

    def list_image_candidates(
        self,
        *,
        project_id: str,
        owner_type: str | None = None,
        owner_id: str | None = None,
        image_slot: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        where_parts = ["project_id = %s"]
        values: list[object] = [project_id]
        if owner_type:
            where_parts.append("owner_type = %s")
            values.append(owner_type)
        if owner_id:
            where_parts.append("owner_id = %s")
            values.append(owner_id)
        if image_slot:
            where_parts.append("image_slot = %s")
            values.append(image_slot)
        values.append(max(1, int(limit)))
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM image_candidates
                WHERE {' AND '.join(where_parts)}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                values,
            ).fetchall()
        return [self._image_candidate_from_row(row) for row in rows]

    def get_image_candidate(self, candidate_id: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM image_candidates WHERE id = %s AND workspace_id = \'default\'", (candidate_id,)).fetchone()
        return None if row is None else self._image_candidate_from_row(row)

    def create_generation_run(self, project_id: str, task_type: str) -> dict:
        run_id = str(uuid.uuid4())
        now = utc_now_iso()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO generation_runs (
                    id, project_id, task_type, status, progress, error_text,
                    created_at, updated_at, completed_at, workspace_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'default')
                """,
                (run_id, project_id, task_type, "queued", 0.0, None, now, now, None),
            )
        return self.get_generation_run(run_id)

    def update_generation_run(
        self,
        run_id: str,
        *,
        status: str | None = None,
        progress: float | None = None,
        error_text: str | None = None,
        completed: bool = False,
    ) -> dict | None:
        assignments = []
        values: list[object] = []
        if status is not None:
            assignments.append("status = %s")
            values.append(status)
        if progress is not None:
            assignments.append("progress = %s")
            values.append(progress)
        assignments.append("error_text = %s")
        values.append(error_text)
        now = utc_now_iso()
        assignments.append("updated_at = %s")
        values.append(now)
        if completed:
            assignments.append("completed_at = %s")
            values.append(now)
        values.append(run_id)

        with self.database.connect() as connection:
            cursor = connection.execute(f"UPDATE generation_runs SET {', '.join(assignments)} WHERE id = %s AND workspace_id = \'default\'", values)
            if cursor.rowcount == 0:
                return None
        return self.get_generation_run(run_id)

    def get_generation_run(self, run_id: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM generation_runs WHERE id = %s AND workspace_id = \'default\'", (run_id,)).fetchone()
        return None if row is None else self._generation_run_from_row(row)

    def get_model_settings(self) -> dict:
        legacy_runtime = self._get_legacy_assistant_settings_from_store()
        defaults = build_default_model_settings(self.settings, legacy_runtime)
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT value_text FROM app_settings WHERE key = %s AND workspace_id = \'default\'",
                (self.MODEL_SETTINGS_KEY,),
            ).fetchone()
        raw_settings = _loads(row["value_text"] if row else None, {})
        normalized = normalize_model_settings(raw_settings if isinstance(raw_settings, dict) else {}, self.settings, legacy_runtime)
        if row is None or raw_settings != normalized:
            self._set_app_setting_json(self.MODEL_SETTINGS_KEY, normalized)
        return {
            **normalized,
            "defaults": defaults,
            "task_catalog": build_task_catalog(),
        }

    def update_model_settings(self, updates: dict) -> dict:
        payload = normalize_model_settings(updates, self.settings, self._get_legacy_assistant_settings_from_store())
        self._set_app_setting_json(self.MODEL_SETTINGS_KEY, payload)
        return self.get_model_settings()

    def get_media_generation_settings(self) -> dict:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT value_text FROM app_settings WHERE key = %s AND workspace_id = \'default\'",
                (self.MEDIA_SETTINGS_KEY,),
            ).fetchone()
        raw_settings = _loads(row["value_text"] if row else None, {})
        normalized = normalize_media_generation_settings(raw_settings if isinstance(raw_settings, dict) else {}, self.settings)
        if row is None or raw_settings != normalized:
            self._set_app_setting_json(self.MEDIA_SETTINGS_KEY, normalized)
        return normalized

    def update_media_generation_settings(self, updates: dict) -> dict:
        payload = normalize_media_generation_settings(updates, self.settings)
        self._set_app_setting_json(self.MEDIA_SETTINGS_KEY, payload)
        return self.get_media_generation_settings()

    def get_project_model_settings_override(self, project_id: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT model_settings_override_json FROM projects WHERE id = %s AND workspace_id = \'default\'", (project_id,)).fetchone()
        if row is None:
            return None
        return normalize_project_model_settings_override(_loads(row["model_settings_override_json"], {}))

    def update_project_model_settings_override(self, project_id: str, updates: dict) -> dict | None:
        payload = normalize_project_model_settings_override(updates)
        now = utc_now_iso()
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE projects
                SET model_settings_override_json = %s, updated_at = %s
                WHERE id = %s AND workspace_id = \'default\'
                """,
                (json.dumps(payload), now, project_id),
            )
            if cursor.rowcount == 0:
                return None
        return self.get_project_model_settings_override(project_id)

    def get_resolved_model_settings(self, project_id: str | None = None) -> dict:
        global_settings = self.get_model_settings()
        raw_global = {
            "runtime": global_settings["runtime"],
            "generation_defaults": global_settings["generation_defaults"],
            "task_profiles": global_settings["task_profiles"],
        }
        if not project_id:
            return raw_global
        project_override = self.get_project_model_settings_override(project_id)
        if project_override is None:
            return raw_global
        return resolve_model_settings(raw_global, project_override)

    def get_assistant_settings(self) -> dict:
        model_settings = self.get_model_settings()
        runtime = model_settings["runtime"]
        return {
            "provider": runtime["provider"],
            "base_url": runtime["base_url"],
            "model": runtime["default_model"],
            "api_key": runtime["api_key"],
            "timeout_s": runtime["timeout_s"],
        }

    def update_assistant_settings(self, updates: dict) -> dict:
        current = self.get_model_settings()
        next_settings = {
            "runtime": {
                **current["runtime"],
                "provider": updates.get("provider", current["runtime"]["provider"]),
                "base_url": updates.get("base_url", current["runtime"]["base_url"]),
                "api_key": updates.get("api_key", current["runtime"]["api_key"]),
                "default_model": updates.get("model", current["runtime"]["default_model"]),
                "timeout_s": updates.get("timeout_s", current["runtime"]["timeout_s"]),
            },
            "generation_defaults": current["generation_defaults"],
            "task_profiles": current["task_profiles"],
        }
        saved = self.update_model_settings(next_settings)
        runtime = saved["runtime"]
        return {
            "provider": runtime["provider"],
            "base_url": runtime["base_url"],
            "model": runtime["default_model"],
            "api_key": runtime["api_key"],
            "timeout_s": runtime["timeout_s"],
        }

    def _get_legacy_assistant_settings_from_store(self) -> dict:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT key, value_text FROM app_settings WHERE key IN (%s, %s, %s, %s, %s)",
                tuple(self.ASSISTANT_SETTING_KEYS.values()),
            ).fetchall()
        stored = {row["key"]: row["value_text"] for row in rows}
        return {
            "provider": stored.get(self.ASSISTANT_SETTING_KEYS["provider"], self.settings.scenario_assistant_provider),
            "base_url": stored.get(self.ASSISTANT_SETTING_KEYS["base_url"], self.settings.scenario_assistant_base_url),
            "model": stored.get(self.ASSISTANT_SETTING_KEYS["model"], self.settings.scenario_assistant_model),
            "api_key": stored.get(self.ASSISTANT_SETTING_KEYS["api_key"], self.settings.scenario_assistant_api_key or ""),
            "timeout_s": int(
                stored.get(self.ASSISTANT_SETTING_KEYS["timeout_s"], str(self.settings.scenario_assistant_timeout_s))
            ),
        }

    def _set_app_setting_json(self, key: str, value: dict) -> None:
        now = utc_now_iso()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO app_settings (key, value_text, updated_at, workspace_id)
                VALUES (%s, %s, %s, \'default\')
                ON CONFLICT(key) DO UPDATE SET
                    value_text = excluded.value_text,
                    updated_at = excluded.updated_at
                """,
                (key, json.dumps(value), now),
            )

    def ensure_project_assets(self, project_id: str) -> Path:
        root = self.settings.projects_root / project_id
        for directory in (
            root,
            root / "scenario-images",
            root / "scenario-images" / "generated",
            root / "character-images",
            root / "character-images" / "generated",
            root / "lore-images",
            root / "lore-images" / "generated",
            root / "user-images",
            root / "user-images" / "generated",
            root / "character-exports",
            root / "gm-exports",
            root / "persona-exports",
        ):
            directory.mkdir(parents=True, exist_ok=True)
        return root

    def _default_user_profile(self, project_id: str) -> dict:
        now = utc_now_iso()
        return {
            "project_id": project_id,
            "name": "User",
            "description": "",
            "title": "",
            "personality": "",
            "scenario_role": "",
            "first_message": "",
            "tags": [],
            "persona_note": "",
            "persona_note_depth": 4,
            "persona_note_role": "system",
            "appearance_summary": "",
            "booru_character_name": "",
            "booru_copyright": "",
            "avatar_relative_path": None,
            "portrait_relative_path": None,
            "cowboy_shot_relative_path": None,
            "fullbody_shot_relative_path": None,
            "created_at": now,
            "updated_at": now,
        }

    def _project_list_item_from_row(self, row) -> dict:
        return {
            "id": row["id"],
            "name": row["name"],
            "seed_sentence": row["seed_sentence"],
            "project_mode": _normalize_project_mode(row["project_mode"]),
            "sample_character_target_count": _normalize_sample_character_target_count(
                row["sample_character_target_count"],
                5,
            ),
            "archived_at": row["archived_at"],
            "character_count": int(row["character_count"]),
            "lore_count": int(row["lore_count"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _project_from_row(self, row) -> dict:
        return {
            "id": row["id"],
            "name": row["name"],
            "seed_sentence": row["seed_sentence"],
            "scenario_text": row["scenario_text"],
            "project_mode": _normalize_project_mode(row["project_mode"]),
            "sample_character_target_count": _normalize_sample_character_target_count(
                row["sample_character_target_count"],
                5,
            ),
            "lorebook_scan_depth": _normalize_optional_int(row["lorebook_scan_depth"]) or 4,
            "lorebook_token_budget": _normalize_optional_int(row["lorebook_token_budget"]) or 512,
            "lorebook_recursive_scanning": bool(row["lorebook_recursive_scanning"]),
            "scenario_image_relative_path": row["scenario_image_relative_path"],
            "genre": row["genre"],
            "tone": row["tone"],
            "gm_card_profile": _normalize_gm_card_profile(
                _loads(row["gm_card_profile_json"], {}),
                project_name=row["name"] or "",
                scenario_text=row["scenario_text"] or "",
            ),
            "model_settings_override": normalize_project_model_settings_override(
                _loads(row["model_settings_override_json"], {})
            ),
            "archived_at": row["archived_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _character_from_row(self, row) -> dict:
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "name": row["name"],
            "description": row["description"] or "",
            "personality": row["personality"] or "",
            "scenario": row["scenario"] or "",
            "first_message": row["first_message"] or "",
            "example_dialogue": row["example_dialogue"] or "",
            "tags": _loads(row["tags_json"], []),
            "creator_notes": row["creator_notes"] or "",
            "system_prompt": row["system_prompt"] or "",
            "post_history_instructions": row["post_history_instructions"] or "",
            "alternate_greetings": _loads(row["alternate_greetings_json"], []),
            "creator": row["creator"] or "",
            "character_version": row["character_version"] or "",
            "character_note": row["character_note"] or "",
            "character_note_depth": _normalize_optional_int(row["character_note_depth"]) or 4,
            "character_note_role": _normalize_message_role(row["character_note_role"], "system"),
            "talkativeness": _normalize_optional_float(row["talkativeness"]),
            "appearance_summary": row["appearance_summary"] or "",
            "booru_character_name": row["booru_character_name"] or "",
            "booru_copyright": row["booru_copyright"] or "",
            "avatar_relative_path": row["avatar_relative_path"],
            "portrait_relative_path": row["portrait_relative_path"],
            "cowboy_shot_relative_path": row["cowboy_shot_relative_path"],
            "fullbody_shot_relative_path": row["fullbody_shot_relative_path"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _lore_entry_from_row(self, row) -> dict:
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "name": row["name"],
            "keys": _loads(row["keys_json"], []),
            "secondary_keys": _loads(row["secondary_keys_json"], []),
            "content": row["content"] or "",
            "comment": row["comment"] or "",
            "image_relative_path": row["image_relative_path"],
            "enabled": bool(row["enabled"]),
            "insertion_order": int(row["insertion_order"]),
            "position": _normalize_lore_position(row["position"]),
            "constant": bool(row["constant"]),
            "selective_logic": _normalize_optional_int(row["selective_logic"]) or 0,
            "probability": _normalize_probability(row["probability"], 100),
            "case_sensitive": bool(row["case_sensitive"]),
            "priority": _normalize_priority(row["priority"], 0),
            "scan_depth": _normalize_optional_int(row["scan_depth"]),
            "match_whole_words": None if row["match_whole_words"] is None else bool(row["match_whole_words"]),
            "group": row["group_name"] or "",
            "group_weight": _normalize_weight(row["group_weight"], 100),
            "prevent_recursion": bool(row["prevent_recursion"]),
            "delay_until_recursion": bool(row["delay_until_recursion"]),
            "character_filter_json": row["character_filter_json"] or "",
            "automation_id": row["automation_id"] or "",
            "role": _normalize_message_role(row["role"], "system"),
            "extensions_json": row["extensions_json"] or "{}",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _user_profile_from_row(self, row) -> dict:
        return {
            "project_id": row["project_id"],
            "name": row["name"] or "User",
            "description": row["description"] or "",
            "title": row["title"] or "",
            "personality": row["personality"] or "",
            "scenario_role": row["scenario_role"] or "",
            "first_message": row["first_message"] or "",
            "tags": _loads(row["tags_json"], []),
            "persona_note": row["persona_note"] or "",
            "persona_note_depth": _normalize_optional_int(row["persona_note_depth"]) or 4,
            "persona_note_role": _normalize_message_role(row["persona_note_role"], "system"),
            "appearance_summary": row["appearance_summary"] or "",
            "booru_character_name": row["booru_character_name"] or "",
            "booru_copyright": row["booru_copyright"] or "",
            "avatar_relative_path": row["avatar_relative_path"],
            "portrait_relative_path": row["portrait_relative_path"],
            "cowboy_shot_relative_path": row["cowboy_shot_relative_path"],
            "fullbody_shot_relative_path": row["fullbody_shot_relative_path"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _generation_run_from_row(self, row) -> dict:
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "task_type": row["task_type"],
            "status": row["status"],
            "progress": float(row["progress"]),
            "error_text": row["error_text"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "completed_at": row["completed_at"],
        }

    def _image_candidate_from_row(self, row) -> dict:
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "owner_type": row["owner_type"],
            "owner_id": row["owner_id"],
            "image_slot": row["image_slot"],
            "relative_path": row["relative_path"],
            "prompt_text": row["prompt_text"] or "",
            "negative_prompt": row["negative_prompt"] or "",
            "created_at": row["created_at"],
        }
