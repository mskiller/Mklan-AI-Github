from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import uuid

from .config import Settings
from .database import Database, utc_now_iso
from .media_generation_settings import (
    MEDIA_GENERATION_SETTINGS_KEY,
    normalize_media_generation_settings,
)
from .model_settings import (
    build_default_model_settings,
    build_task_catalog,
    default_project_model_settings_override,
    normalize_model_settings,
    normalize_project_model_settings_override,
    resolve_model_settings,
)
from .schemas import JobStatus, JobType

MOVIE_MIN_DURATION_S = 180
MOVIE_MAX_DURATION_S = 300
SCENE_MIN_DURATION_S = 30
SCENE_MAX_DURATION_S = 90
SEQUENCE_MIN_DURATION_S = 5
SEQUENCE_MAX_DURATION_S = 10


def _loads(raw_value: str | None) -> dict:
    if not raw_value:
        return {}
    return json.loads(raw_value)


class DurationConflictError(ValueError):
    pass


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
        self.settings.default_video_model_root.mkdir(parents=True, exist_ok=True)
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
                    CASE
                        WHEN p.workflow_version >= 2 THEN (
                            SELECT COUNT(*) FROM story_scenes ss WHERE ss.project_id = p.id
                        )
                        ELSE (
                            SELECT COUNT(*) FROM scenes s WHERE s.project_id = p.id
                        )
                    END AS scene_count,
                    (
                        SELECT COUNT(*)
                        FROM scenes s
                        WHERE s.project_id = p.id AND s.story_scene_id IS NULL
                    ) AS legacy_sequence_count
                FROM projects p
                {where_clause}
                ORDER BY p.updated_at DESC
                """
            ).fetchall()
        return [self._project_list_item_from_row(row) for row in rows]

    def create_project(self, data: dict) -> dict:
        project_id = str(uuid.uuid4())
        now = utc_now_iso()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO projects (
                    id, name, scenario_text, genre, tone, target_duration_s,
                    output_width, output_height, output_fps, aspect_ratio,
                    workflow_version, style_anchor_text, model_settings_override_json, opening_image_prompt_text,
                    opening_image_relative_path, opening_image_original_filename,
                    opening_image_mime_type, opening_image_size_bytes,
                    opening_image_uploaded_at, beat_board_status, archived_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    data["name"],
                    data.get("scenario_text", ""),
                    data.get("genre", "cinematic drama"),
                    data.get("tone", "grounded and atmospheric"),
                    data.get("target_duration_s", self.settings.default_target_duration_s),
                    data.get("output_width", self.settings.default_width),
                    data.get("output_height", self.settings.default_height),
                    data.get("output_fps", self.settings.default_fps),
                    data.get("aspect_ratio", "16:9"),
                    2,
                    data.get("style_anchor_text", ""),
                    json.dumps(default_project_model_settings_override()),
                    "",
                    None,
                    None,
                    None,
                    0,
                    None,
                    "empty",
                    None,
                    now,
                    now,
                ),
            )
        self.ensure_project_assets(project_id)
        return self.get_project_detail(project_id)

    def get_model_settings(self) -> dict:
        legacy_runtime = self._get_legacy_assistant_settings_from_store()
        defaults = build_default_model_settings(self.settings, legacy_runtime)
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT value_text FROM app_settings WHERE key = ?",
                (self.MODEL_SETTINGS_KEY,),
            ).fetchone()
        raw_settings = _loads(row["value_text"]) if row is not None else {}
        normalized = normalize_model_settings(raw_settings, self.settings, legacy_runtime)
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
                "SELECT value_text FROM app_settings WHERE key = ?",
                (self.MEDIA_SETTINGS_KEY,),
            ).fetchone()
        raw_settings = _loads(row["value_text"]) if row is not None else {}
        normalized = normalize_media_generation_settings(raw_settings, self.settings)
        if row is None or raw_settings != normalized:
            self._set_app_setting_json(self.MEDIA_SETTINGS_KEY, normalized)
        return normalized

    def update_media_generation_settings(self, updates: dict) -> dict:
        payload = normalize_media_generation_settings(updates, self.settings)
        self._set_app_setting_json(self.MEDIA_SETTINGS_KEY, payload)
        return self.get_media_generation_settings()

    def get_project_model_settings_override(self, project_id: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT model_settings_override_json FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
        if row is None:
            return None
        return normalize_project_model_settings_override(_loads(row["model_settings_override_json"]))

    def update_project_model_settings_override(self, project_id: str, updates: dict) -> dict | None:
        payload = normalize_project_model_settings_override(updates)
        now = utc_now_iso()
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE projects
                SET model_settings_override_json = ?, updated_at = ?
                WHERE id = ?
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
                "SELECT key, value_text FROM app_settings WHERE key IN (?, ?, ?, ?, ?)",
                tuple(self.ASSISTANT_SETTING_KEYS.values()),
            ).fetchall()
        stored = {row["key"]: row["value_text"] for row in rows}
        return {
            "provider": stored.get(self.ASSISTANT_SETTING_KEYS["provider"], self.settings.scenario_assistant_provider),
            "base_url": stored.get(self.ASSISTANT_SETTING_KEYS["base_url"], self.settings.scenario_assistant_base_url),
            "model": stored.get(self.ASSISTANT_SETTING_KEYS["model"], self.settings.scenario_assistant_model),
            "api_key": stored.get(self.ASSISTANT_SETTING_KEYS["api_key"], self.settings.scenario_assistant_api_key or ""),
            "timeout_s": int(
                stored.get(
                    self.ASSISTANT_SETTING_KEYS["timeout_s"],
                    str(self.settings.scenario_assistant_timeout_s),
                )
            ),
        }

    def _set_app_setting_json(self, key: str, value: dict) -> None:
        now = utc_now_iso()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO app_settings (key, value_text, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value_text = excluded.value_text,
                    updated_at = excluded.updated_at
                """,
                (key, json.dumps(value), now),
            )

    def update_project(self, project_id: str, updates: dict) -> dict | None:
        clean_updates = {key: value for key, value in updates.items() if value is not None}
        if not clean_updates:
            return self.get_project_detail(project_id)

        now = utc_now_iso()
        with self.database.connect() as connection:
            project_row = connection.execute(
                "SELECT * FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
            if project_row is None:
                return None
            if (
                "scenario_text" in clean_updates
                and clean_updates["scenario_text"] != project_row["scenario_text"]
                and "beat_board_status" not in clean_updates
            ):
                beat_count_row = connection.execute(
                    "SELECT COUNT(*) AS count FROM story_beats WHERE project_id = ?",
                    (project_id,),
                ).fetchone()
                clean_updates["beat_board_status"] = "stale" if int(beat_count_row["count"]) > 0 else "empty"
            self._update_project_row(connection, project_id, clean_updates, now)
            if "target_duration_s" in clean_updates and (project_row["workflow_version"] or 1) >= 2:
                self._rebalance_project_scenes_to_total(
                    connection,
                    project_id,
                    int(clean_updates["target_duration_s"]),
                    now,
                )
        return self.get_project_detail(project_id)

    def archive_project(self, project_id: str) -> dict | None:
        now = utc_now_iso()
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT archived_at FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
            if row is None:
                return None
            archived_at = row["archived_at"] or now
            connection.execute(
                "UPDATE projects SET archived_at = ?, updated_at = ? WHERE id = ?",
                (archived_at, now, project_id),
            )
        return self.get_project_detail(project_id)

    def restore_project(self, project_id: str) -> dict | None:
        now = utc_now_iso()
        with self.database.connect() as connection:
            cursor = connection.execute(
                "UPDATE projects SET archived_at = NULL, updated_at = ? WHERE id = ?",
                (now, project_id),
            )
            if cursor.rowcount == 0:
                return None
        return self.get_project_detail(project_id)

    def delete_project(self, project_id: str) -> bool | None:
        project_root = self.settings.projects_root / project_id
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT archived_at FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
            if row is None:
                return None
            if not row["archived_at"]:
                return False
            connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        if project_root.exists():
            shutil.rmtree(project_root, ignore_errors=False)
        return True

    def get_project_detail(self, project_id: str) -> dict | None:
        with self.database.connect() as connection:
            project_row = connection.execute(
                "SELECT * FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
            if project_row is None:
                return None

            job_rows = connection.execute(
                "SELECT * FROM jobs WHERE project_id = ? ORDER BY created_at DESC LIMIT 10",
                (project_id,),
            ).fetchall()
            export_rows = connection.execute(
                "SELECT * FROM export_assets WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            ).fetchall()

            project = self._project_from_row(project_row)
            beat_rows = connection.execute(
                """
                SELECT *
                FROM story_beats
                WHERE project_id = ?
                ORDER BY act_index ASC, order_index ASC, created_at ASC
                """,
                (project_id,),
            ).fetchall()
            project["beat_board"] = {
                "project_id": project_id,
                "status": project.get("beat_board_status", "empty"),
                "beats": [self._story_beat_from_row(row) for row in beat_rows],
                "updated_at": project["updated_at"],
            }
            char_rows = connection.execute(
                """
                SELECT *
                FROM project_characters
                WHERE project_id = ?
                ORDER BY order_index ASC, created_at ASC
                """,
                (project_id,),
            ).fetchall()
            project["characters"] = [self._project_character_from_row(row) for row in char_rows]
            if project["workflow_version"] >= 2:
                scene_rows = connection.execute(
                    "SELECT * FROM story_scenes WHERE project_id = ? ORDER BY order_index ASC, created_at ASC",
                    (project_id,),
                ).fetchall()
                sequence_rows = connection.execute(
                    """
                    SELECT *
                    FROM scenes
                    WHERE project_id = ? AND story_scene_id IS NOT NULL
                    ORDER BY absolute_order ASC, order_index ASC, created_at ASC
                    """,
                    (project_id,),
                ).fetchall()
                continuity_review_rows = connection.execute(
                    """
                    SELECT *
                    FROM continuity_reviews
                    WHERE project_id = ?
                    ORDER BY updated_at DESC
                    """,
                    (project_id,),
                ).fetchall()
                scene_image_variant_rows = connection.execute(
                    """
                    SELECT *
                    FROM scene_image_variants
                    WHERE project_id = ?
                    ORDER BY created_at DESC
                    """,
                    (project_id,),
                ).fetchall()
                sequence_video_variant_rows = connection.execute(
                    """
                    SELECT *
                    FROM sequence_video_variants
                    WHERE project_id = ?
                    ORDER BY created_at DESC
                    """,
                    (project_id,),
                ).fetchall()
                sequences_by_scene: dict[str, list[dict]] = {}
                for row in sequence_rows:
                    sequence = self._sequence_from_row(row)
                    sequences_by_scene.setdefault(sequence["scene_id"], []).append(sequence)
                continuity_by_scene = {
                    row["scene_id"]: self._continuity_review_from_row(row)
                    for row in continuity_review_rows
                }
                image_variants_by_scene: dict[str, list[dict]] = {}
                for row in scene_image_variant_rows:
                    variant = self._scene_image_variant_from_row(row)
                    image_variants_by_scene.setdefault(variant["scene_id"], []).append(variant)
                video_variants_by_sequence: dict[str, list[dict]] = {}
                for row in sequence_video_variant_rows:
                    variant = self._sequence_video_variant_from_row(row)
                    video_variants_by_sequence.setdefault(variant["sequence_id"], []).append(variant)

                project["scenes"] = []
                for row in scene_rows:
                    story_scene = self._story_scene_from_row(row)
                    story_scene["generated_image_variants"] = image_variants_by_scene.get(story_scene["id"], [])
                    story_scene["sequences"] = sequences_by_scene.get(story_scene["id"], [])
                    for sequence in story_scene["sequences"]:
                        sequence["generated_video_variants"] = video_variants_by_sequence.get(sequence["id"], [])
                    self._refresh_scene_chain_state(story_scene)
                    story_scene["continuity_review"] = continuity_by_scene.get(story_scene["id"])
                    project["scenes"].append(story_scene)
                project["legacy_sequence_count"] = 0
                project["upgrade_available"] = False
            else:
                legacy_sequence_rows = connection.execute(
                    """
                    SELECT *
                    FROM scenes
                    WHERE project_id = ? AND story_scene_id IS NULL
                    ORDER BY order_index ASC, created_at ASC
                    """,
                    (project_id,),
                ).fetchall()
                project["scenes"] = []
                project["legacy_sequence_count"] = len(legacy_sequence_rows)
                project["upgrade_available"] = len(legacy_sequence_rows) > 0

            project["recent_jobs"] = [self._job_from_row(row) for row in job_rows]
            project["exports"] = [self._export_from_row(row) for row in export_rows]
            return project

    def get_project_record(self, project_id: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
        return None if row is None else self._project_from_row(row)

    def get_beat_board(self, project_id: str) -> dict | None:
        project = self.get_project_record(project_id)
        if project is None:
            return None
        beats = self.list_story_beats(project_id)
        return {
            "project_id": project_id,
            "status": project.get("beat_board_status", "empty"),
            "beats": beats,
            "updated_at": project.get("updated_at"),
        }

    def list_story_beats(self, project_id: str) -> list[dict]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM story_beats
                WHERE project_id = ?
                ORDER BY act_index ASC, order_index ASC, created_at ASC
                """,
                (project_id,),
            ).fetchall()
        return [self._story_beat_from_row(row) for row in rows]

    def get_story_beat(self, beat_id: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM story_beats WHERE id = ?",
                (beat_id,),
            ).fetchone()
        return None if row is None else self._story_beat_from_row(row)

    def replace_story_beats(self, project_id: str, beats: list[dict], *, status: str = "generated") -> list[dict]:
        now = utc_now_iso()
        with self.database.connect() as connection:
            project_row = connection.execute(
                "SELECT id FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
            if project_row is None:
                return []
            connection.execute("DELETE FROM story_beats WHERE project_id = ?", (project_id,))
            for beat in beats:
                connection.execute(
                    """
                    INSERT INTO story_beats (
                        id, project_id, act_index, order_index, title,
                        summary_text, purpose_text, source, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        project_id,
                        int(beat["act_index"]),
                        int(beat["order_index"]),
                        beat["title"],
                        beat.get("summary_text", ""),
                        beat.get("purpose_text", ""),
                        beat.get("source", "generated"),
                        now,
                        now,
                    ),
                )
            connection.execute(
                "UPDATE projects SET beat_board_status = ?, updated_at = ? WHERE id = ?",
                (status if beats else "empty", now, project_id),
            )
        return self.list_story_beats(project_id)

    def create_story_beat(self, project_id: str, payload: dict) -> dict | None:
        now = utc_now_iso()
        with self.database.connect() as connection:
            project_row = connection.execute(
                "SELECT id FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
            if project_row is None:
                return None
            order_row = connection.execute(
                """
                SELECT COALESCE(MAX(order_index), 0) AS max_order
                FROM story_beats
                WHERE project_id = ? AND act_index = ?
                """,
                (project_id, int(payload["act_index"])),
            ).fetchone()
            beat_id = str(uuid.uuid4())
            connection.execute(
                """
                INSERT INTO story_beats (
                    id, project_id, act_index, order_index, title,
                    summary_text, purpose_text, source, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    beat_id,
                    project_id,
                    int(payload["act_index"]),
                    int(order_row["max_order"]) + 1,
                    payload["title"],
                    payload.get("summary_text", ""),
                    payload.get("purpose_text", ""),
                    payload.get("source", "manual"),
                    now,
                    now,
                ),
            )
            connection.execute(
                "UPDATE projects SET beat_board_status = ?, updated_at = ? WHERE id = ?",
                ("edited", now, project_id),
            )
        return self.get_story_beat(beat_id)

    def update_story_beat(self, beat_id: str, updates: dict) -> dict | None:
        clean_updates = {key: value for key, value in updates.items() if value is not None}
        if not clean_updates:
            return self.get_story_beat(beat_id)
        now = utc_now_iso()
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT project_id FROM story_beats WHERE id = ?",
                (beat_id,),
            ).fetchone()
            if row is None:
                return None
            assignments = []
            values: list[object] = []
            for key, value in clean_updates.items():
                assignments.append(f"{key} = ?")
                values.append(value)
            assignments.append("updated_at = ?")
            values.append(now)
            values.append(beat_id)
            connection.execute(
                f"UPDATE story_beats SET {', '.join(assignments)} WHERE id = ?",
                values,
            )
            connection.execute(
                "UPDATE projects SET beat_board_status = ?, updated_at = ? WHERE id = ?",
                ("edited", now, row["project_id"]),
            )
            if "act_index" in clean_updates or "order_index" in clean_updates:
                self._normalize_story_beats(connection, row["project_id"])
        return self.get_story_beat(beat_id)

    def reorder_story_beats(self, project_id: str, beats: list[dict]) -> list[dict]:
        now = utc_now_iso()
        with self.database.connect() as connection:
            project_row = connection.execute(
                "SELECT id FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
            if project_row is None:
                return []
            for beat in beats:
                connection.execute(
                    """
                    UPDATE story_beats
                    SET act_index = ?, order_index = ?, updated_at = ?
                    WHERE id = ? AND project_id = ?
                    """,
                    (int(beat["act_index"]), int(beat["order_index"]), now, beat["beat_id"], project_id),
                )
            self._normalize_story_beats(connection, project_id)
            connection.execute(
                "UPDATE projects SET beat_board_status = ?, updated_at = ? WHERE id = ?",
                ("edited", now, project_id),
            )
        return self.list_story_beats(project_id)

    def delete_story_beat(self, beat_id: str) -> bool:
        now = utc_now_iso()
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT project_id FROM story_beats WHERE id = ?",
                (beat_id,),
            ).fetchone()
            if row is None:
                return False
            project_id = row["project_id"]
            connection.execute("DELETE FROM story_beats WHERE id = ?", (beat_id,))
            self._normalize_story_beats(connection, project_id)
            beat_count_row = connection.execute(
                "SELECT COUNT(*) AS count FROM story_beats WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            next_status = "edited" if int(beat_count_row["count"]) > 0 else "empty"
            connection.execute(
                "UPDATE projects SET beat_board_status = ?, updated_at = ? WHERE id = ?",
                (next_status, now, project_id),
            )
        return True

    def apply_beat_board_to_scenario(self, project_id: str) -> dict | None:
        beats = self.list_story_beats(project_id)
        project = self.get_project_record(project_id)
        if project is None:
            return None
        scenario_text = self._scenario_text_from_beats(project, beats)
        status = "generated" if project.get("beat_board_status") == "generated" else "edited"
        return self.update_project(
            project_id,
            {
                "scenario_text": scenario_text,
                "beat_board_status": status,
            },
        )

    def list_project_characters(self, project_id: str) -> list[dict]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM project_characters
                WHERE project_id = ?
                ORDER BY order_index ASC, created_at ASC
                """,
                (project_id,),
            ).fetchall()
        return [self._project_character_from_row(row) for row in rows]

    def get_project_character(self, character_id: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM project_characters WHERE id = ?",
                (character_id,),
            ).fetchone()
        return None if row is None else self._project_character_from_row(row)

    def create_project_character(self, project_id: str, payload: dict) -> dict | None:
        now = utc_now_iso()
        with self.database.connect() as connection:
            project_row = connection.execute(
                "SELECT id FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
            if project_row is None:
                return None
            order_row = connection.execute(
                """
                SELECT COALESCE(MAX(order_index), 0) AS max_order
                FROM project_characters
                WHERE project_id = ?
                """,
                (project_id,),
            ).fetchone()
            character_id = str(uuid.uuid4())
            connection.execute(
                """
                INSERT INTO project_characters (
                    id, project_id, name, role_summary, prompt_tags, order_index, 
                    portrait_image_url, cowboyshot_image_url, fullbody_image_url,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    character_id,
                    project_id,
                    payload["name"],
                    payload.get("role_summary", ""),
                    payload.get("prompt_tags", ""),
                    payload.get("order_index", int(order_row["max_order"]) + 1),
                    payload.get("portrait_image_url"),
                    payload.get("cowboyshot_image_url"),
                    payload.get("fullbody_image_url"),
                    now,
                    now,
                ),
            )
        return self.get_project_character(character_id)

    def update_project_character(self, character_id: str, updates: dict) -> dict | None:
        clean_updates = {key: value for key, value in updates.items() if value is not None}
        if not clean_updates:
            return self.get_project_character(character_id)
        now = utc_now_iso()
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT project_id FROM project_characters WHERE id = ?",
                (character_id,),
            ).fetchone()
            if row is None:
                return None
            assignments = []
            values: list[object] = []
            for key, value in clean_updates.items():
                assignments.append(f"{key} = ?")
                values.append(value)
            assignments.append("updated_at = ?")
            values.append(now)
            values.append(character_id)
            connection.execute(
                f"UPDATE project_characters SET {', '.join(assignments)} WHERE id = ?",
                values,
            )
            if "order_index" in clean_updates:
                self._normalize_project_characters(connection, row["project_id"])
        return self.get_project_character(character_id)

    def delete_project_character(self, character_id: str) -> bool:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT project_id FROM project_characters WHERE id = ?",
                (character_id,),
            ).fetchone()
            if row is None:
                return False
            connection.execute("DELETE FROM project_characters WHERE id = ?", (character_id,))
            self._normalize_project_characters(connection, row["project_id"])
        return True

    def replace_project_characters(self, project_id: str, characters: list[dict]) -> list[dict]:
        now = utc_now_iso()
        with self.database.connect() as connection:
            connection.execute("DELETE FROM project_characters WHERE project_id = ?", (project_id,))
            for index, char in enumerate(characters, start=1):
                connection.execute(
                    """
                    INSERT INTO project_characters (
                        id, project_id, name, role_summary, prompt_tags, order_index, 
                        portrait_image_url, cowboyshot_image_url, fullbody_image_url,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        project_id,
                        char["name"],
                        char.get("role_summary", ""),
                        char.get("prompt_tags", ""),
                        char.get("order_index", index),
                        char.get("portrait_image_url"),
                        char.get("cowboyshot_image_url"),
                        char.get("fullbody_image_url"),
                        now,
                        now,
                    ),
                )
        return self.list_project_characters(project_id)

    def replace_story_scenes(self, project_id: str, scenes: list[dict]) -> list[dict]:
        now = utc_now_iso()
        with self.database.connect() as connection:
            connection.execute("DELETE FROM scenes WHERE project_id = ? AND story_scene_id IS NOT NULL", (project_id,))
            connection.execute("DELETE FROM story_scenes WHERE project_id = ?", (project_id,))
            for index, scene in enumerate(scenes, start=1):
                scene_id = str(uuid.uuid4())
                connection.execute(
                    """
                    INSERT INTO story_scenes (
                        id, project_id, order_index, title, target_duration_s,
                        narrative_text, duration_locked, first_image_prompt_text,
                        first_image_relative_path, first_image_original_filename,
                        first_image_mime_type, first_image_size_bytes,
                        first_image_uploaded_at, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        scene_id,
                        project_id,
                        index,
                        scene["title"],
                        scene["target_duration_s"],
                        scene["narrative_text"],
                        0,
                        scene.get("first_image_prompt_text", ""),
                        None,
                        None,
                        None,
                        0,
                        None,
                        now,
                        now,
                    ),
                )
            connection.execute(
                "UPDATE projects SET workflow_version = 2, updated_at = ? WHERE id = ?",
                (now, project_id),
            )
        detail = self.get_project_detail(project_id)
        return [] if detail is None else detail["scenes"]

    def get_story_scene(self, scene_id: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM story_scenes WHERE id = ?",
                (scene_id,),
            ).fetchone()
        if row is None:
            return None
        scene = self._story_scene_from_row(row)
        scene["sequences"] = self.list_sequences(scene_id)
        scene["generated_image_variants"] = self.list_scene_image_variants(scene_id)
        self._refresh_scene_chain_state(scene)
        scene["continuity_review"] = self.get_continuity_review(scene_id)
        return scene

    def update_story_scene(self, scene_id: str, updates: dict) -> dict | None:
        clean_updates = {key: value for key, value in updates.items() if value is not None}
        if not clean_updates:
            return self.get_story_scene(scene_id)

        now = utc_now_iso()
        with self.database.connect() as connection:
            scene_row = connection.execute(
                "SELECT project_id, target_duration_s FROM story_scenes WHERE id = ?",
                (scene_id,),
            ).fetchone()
            if scene_row is None:
                return None
            project_id = scene_row["project_id"]
            order = clean_updates.pop("order", None)
            next_duration = clean_updates.pop("target_duration_s", None)
            self._update_story_scene_row(connection, scene_id, clean_updates, now, order=order)
            if order is not None:
                self._normalize_story_scene_order(connection, project_id)
                self._normalize_sequence_orders(connection, project_id)
            if next_duration is not None:
                self._rebalance_project_after_scene_duration_change(
                    connection,
                    scene_id,
                    int(next_duration),
                    now,
                )
            else:
                connection.execute(
                    "UPDATE projects SET updated_at = ? WHERE id = ?",
                    (now, project_id),
                )
            if any(
                key in clean_updates
                for key in {
                    "title",
                    "narrative_text",
                    "first_image_prompt_text",
                    "first_image_relative_path",
                    "first_image_original_filename",
                    "first_image_mime_type",
                    "first_image_size_bytes",
                    "first_image_uploaded_at",
                }
            ):
                connection.execute("DELETE FROM continuity_reviews WHERE scene_id = ?", (scene_id,))
        return self.get_story_scene(scene_id)

    def set_story_scene_first_image_asset(
        self,
        scene_id: str,
        *,
        relative_path: str,
        original_filename: str,
        mime_type: str | None,
        size_bytes: int,
        source: str = "uploaded",
    ) -> dict | None:
        now = utc_now_iso()
        return self.update_story_scene(
            scene_id,
            {
                "first_image_relative_path": relative_path,
                "first_image_original_filename": original_filename,
                "first_image_mime_type": mime_type,
                "first_image_size_bytes": size_bytes,
                "first_image_uploaded_at": now,
                "first_image_source": source,
                "image_generation_status": "ready",
            },
        )

    def set_scene_image_generation_status(self, scene_id: str, status: str) -> dict | None:
        return self.update_story_scene(scene_id, {"image_generation_status": status})

    def list_scene_image_variants(self, scene_id: str) -> list[dict]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM scene_image_variants
                WHERE scene_id = ?
                ORDER BY created_at DESC
                """,
                (scene_id,),
            ).fetchall()
        return [self._scene_image_variant_from_row(row) for row in rows]

    def create_scene_image_variant(
        self,
        scene_id: str,
        *,
        relative_path: str,
        original_filename: str,
        mime_type: str | None,
        size_bytes: int,
        provider: str,
        model_name: str,
        seed: int | None,
        prompt_text: str,
    ) -> dict:
        variant_id = str(uuid.uuid4())
        now = utc_now_iso()
        with self.database.connect() as connection:
            scene_row = connection.execute(
                "SELECT project_id FROM story_scenes WHERE id = ?",
                (scene_id,),
            ).fetchone()
            if scene_row is None:
                raise RuntimeError("Scene not found for generated image variant.")
            connection.execute(
                """
                INSERT INTO scene_image_variants (
                    id, project_id, scene_id, provider, model_name, seed, prompt_text,
                    relative_path, original_filename, mime_type, size_bytes, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    variant_id,
                    scene_row["project_id"],
                    scene_id,
                    provider,
                    model_name,
                    seed,
                    prompt_text,
                    relative_path,
                    original_filename,
                    mime_type,
                    size_bytes,
                    now,
                ),
            )
            connection.execute(
                "UPDATE story_scenes SET image_generation_status = ?, updated_at = ? WHERE id = ?",
                ("generated", now, scene_id),
            )
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (now, scene_row["project_id"]),
            )
        variants = self.list_scene_image_variants(scene_id)
        return next(variant for variant in variants if variant["id"] == variant_id)

    def approve_scene_image_variant(self, scene_id: str, asset_id: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM scene_image_variants WHERE id = ? AND scene_id = ?",
                (asset_id, scene_id),
            ).fetchone()
            if row is None:
                return None
        return self.set_story_scene_first_image_asset(
            scene_id,
            relative_path=row["relative_path"],
            original_filename=row["original_filename"],
            mime_type=row["mime_type"],
            size_bytes=row["size_bytes"],
            source="generated",
        )

    def replace_sequences_for_scene(self, scene_id: str, sequences: list[dict]) -> list[dict]:
        now = utc_now_iso()
        with self.database.connect() as connection:
            scene_row = connection.execute(
                "SELECT project_id FROM story_scenes WHERE id = ?",
                (scene_id,),
            ).fetchone()
            if scene_row is None:
                return []
            project_id = scene_row["project_id"]
            connection.execute("DELETE FROM scenes WHERE story_scene_id = ?", (scene_id,))
            for index, sequence in enumerate(sequences, start=1):
                sequence_id = str(uuid.uuid4())
                connection.execute(
                    """
                    INSERT INTO scenes (
                        id, project_id, story_scene_id, order_index, absolute_order,
                        title, target_duration_s, narrative_text, duration_locked, prompt_text,
                        camera_direction, action_direction, wan_prompt_text,
                        uploaded_sequence_relative_path, uploaded_sequence_original_filename,
                        uploaded_sequence_mime_type, uploaded_sequence_size_bytes,
                        uploaded_sequence_uploaded_at, trim_in_ms, trim_out_ms,
                        include_in_assembly, render_status, approved_clip_id,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sequence_id,
                        project_id,
                        scene_id,
                        index,
                        0,
                        sequence["title"],
                        sequence["target_duration_s"],
                        sequence["narrative_text"],
                        0,
                        sequence.get("wan_prompt_text", ""),
                        sequence.get("camera_direction", ""),
                        sequence.get("action_direction", ""),
                        sequence.get("wan_prompt_text", ""),
                        None,
                        None,
                        None,
                        0,
                        None,
                        0,
                        0,
                        1,
                        "draft",
                        None,
                        now,
                        now,
                    ),
                )
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (now, project_id),
            )
            self._normalize_sequence_orders(connection, project_id)
            connection.execute("DELETE FROM continuity_reviews WHERE scene_id = ?", (scene_id,))
        return self.list_sequences(scene_id)

    def list_sequences(self, scene_id: str) -> list[dict]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM scenes
                WHERE story_scene_id = ?
                ORDER BY order_index ASC, absolute_order ASC, created_at ASC
                """,
                (scene_id,),
            ).fetchall()
        sequences = [self._sequence_from_row(row) for row in rows]
        for sequence in sequences:
            sequence["generated_video_variants"] = self.list_sequence_video_variants(sequence["id"])
        scene = self.get_story_scene_record(scene_id)
        if scene is not None:
            lightweight_scene = self._story_scene_from_row(scene)
            lightweight_scene["sequences"] = sequences
            self._refresh_scene_chain_state(lightweight_scene)
            return lightweight_scene["sequences"]
        return sequences

    def get_story_scene_record(self, scene_id: str):
        with self.database.connect() as connection:
            return connection.execute(
                "SELECT * FROM story_scenes WHERE id = ?",
                (scene_id,),
            ).fetchone()

    def get_sequence(self, sequence_id: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM scenes WHERE id = ?",
                (sequence_id,),
            ).fetchone()
        if row is None:
            return None
        sequence = self._sequence_from_row(row)
        if not sequence["scene_id"]:
            return None
        sequence["generated_video_variants"] = self.list_sequence_video_variants(sequence["id"])
        scene = self.get_story_scene(sequence["scene_id"])
        if scene is not None:
            for candidate in scene["sequences"]:
                if candidate["id"] == sequence_id:
                    return candidate
        return sequence

    def update_sequence(self, sequence_id: str, updates: dict) -> dict | None:
        clean_updates = {key: value for key, value in updates.items() if value is not None}
        if not clean_updates:
            return self.get_sequence(sequence_id)

        now = utc_now_iso()
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT project_id, story_scene_id, target_duration_s FROM scenes WHERE id = ?",
                (sequence_id,),
            ).fetchone()
            if row is None or row["story_scene_id"] is None:
                return None
            project_id = row["project_id"]
            order = clean_updates.pop("order", None)
            next_duration = clean_updates.pop("target_duration_s", None)
            self._update_sequence_row(connection, sequence_id, clean_updates, now, order=order)
            if order is not None:
                self._normalize_sequence_orders(connection, project_id)
            if next_duration is not None:
                self._rebalance_scene_sequence_durations(
                    connection,
                    row["story_scene_id"],
                    now,
                    fixed_sequence_id=sequence_id,
                    fixed_duration=int(next_duration),
                )
            else:
                connection.execute(
                    "UPDATE projects SET updated_at = ? WHERE id = ?",
                    (now, project_id),
                )
            connection.execute("DELETE FROM continuity_reviews WHERE scene_id = ?", (row["story_scene_id"],))
        return self.get_sequence(sequence_id)

    def list_sequence_video_variants(self, sequence_id: str) -> list[dict]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM sequence_video_variants
                WHERE sequence_id = ?
                ORDER BY created_at DESC
                """,
                (sequence_id,),
            ).fetchall()
        return [self._sequence_video_variant_from_row(row) for row in rows]

    def set_uploaded_sequence_video_asset(
        self,
        sequence_id: str,
        *,
        relative_path: str,
        original_filename: str,
        mime_type: str | None,
        size_bytes: int,
        input_frame: dict | None = None,
        last_frame: dict | None = None,
    ) -> dict | None:
        now = utc_now_iso()
        return self.update_sequence(
            sequence_id,
            {
                "uploaded_sequence_relative_path": relative_path,
                "uploaded_sequence_original_filename": original_filename,
                "uploaded_sequence_mime_type": mime_type,
                "uploaded_sequence_size_bytes": size_bytes,
                "uploaded_sequence_uploaded_at": now,
                "approved_video_relative_path": relative_path,
                "approved_video_original_filename": original_filename,
                "approved_video_mime_type": mime_type,
                "approved_video_size_bytes": size_bytes,
                "approved_video_created_at": now,
                "approved_video_source": "uploaded",
                "input_frame_relative_path": input_frame["relative_path"] if input_frame else None,
                "input_frame_original_filename": input_frame["original_filename"] if input_frame else None,
                "input_frame_mime_type": input_frame["mime_type"] if input_frame else None,
                "input_frame_size_bytes": input_frame["size_bytes"] if input_frame else None,
                "input_frame_created_at": input_frame["created_at"] if input_frame else None,
                "last_frame_relative_path": last_frame["relative_path"] if last_frame else None,
                "last_frame_original_filename": last_frame["original_filename"] if last_frame else None,
                "last_frame_mime_type": last_frame["mime_type"] if last_frame else None,
                "last_frame_size_bytes": last_frame["size_bytes"] if last_frame else None,
                "last_frame_created_at": last_frame["created_at"] if last_frame else None,
            },
        )

    def create_sequence_video_variant(
        self,
        sequence_id: str,
        *,
        relative_path: str,
        original_filename: str,
        mime_type: str | None,
        size_bytes: int,
        provider: str,
        model_name: str,
        seed: int | None,
        prompt_text: str,
        native_duration_s: float,
        output_duration_s: float,
        input_frame: dict | None = None,
        last_frame: dict | None = None,
    ) -> dict:
        variant_id = str(uuid.uuid4())
        now = utc_now_iso()
        with self.database.connect() as connection:
            sequence_row = connection.execute(
                "SELECT project_id, story_scene_id FROM scenes WHERE id = ?",
                (sequence_id,),
            ).fetchone()
            if sequence_row is None or sequence_row["story_scene_id"] is None:
                raise RuntimeError("Sequence not found for generated video variant.")
            connection.execute(
                """
                INSERT INTO sequence_video_variants (
                    id, project_id, scene_id, sequence_id, provider, model_name, seed, prompt_text,
                    relative_path, original_filename, mime_type, size_bytes,
                    native_duration_s, output_duration_s,
                    input_frame_relative_path, input_frame_original_filename, input_frame_mime_type,
                    input_frame_size_bytes, input_frame_created_at,
                    last_frame_relative_path, last_frame_original_filename, last_frame_mime_type,
                    last_frame_size_bytes, last_frame_created_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    variant_id,
                    sequence_row["project_id"],
                    sequence_row["story_scene_id"],
                    sequence_id,
                    provider,
                    model_name,
                    seed,
                    prompt_text,
                    relative_path,
                    original_filename,
                    mime_type,
                    size_bytes,
                    native_duration_s,
                    output_duration_s,
                    input_frame["relative_path"] if input_frame else None,
                    input_frame["original_filename"] if input_frame else None,
                    input_frame["mime_type"] if input_frame else None,
                    input_frame["size_bytes"] if input_frame else 0,
                    input_frame["created_at"] if input_frame else None,
                    last_frame["relative_path"] if last_frame else None,
                    last_frame["original_filename"] if last_frame else None,
                    last_frame["mime_type"] if last_frame else None,
                    last_frame["size_bytes"] if last_frame else 0,
                    last_frame["created_at"] if last_frame else None,
                    now,
                ),
            )
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (now, sequence_row["project_id"]),
            )
        variants = self.list_sequence_video_variants(sequence_id)
        return next(variant for variant in variants if variant["id"] == variant_id)

    def approve_sequence_video_variant(self, sequence_id: str, asset_id: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM sequence_video_variants WHERE id = ? AND sequence_id = ?",
                (asset_id, sequence_id),
            ).fetchone()
            if row is None:
                return None
        return self.update_sequence(
            sequence_id,
            {
                "approved_video_relative_path": row["relative_path"],
                "approved_video_original_filename": row["original_filename"],
                "approved_video_mime_type": row["mime_type"],
                "approved_video_size_bytes": row["size_bytes"],
                "approved_video_created_at": row["created_at"],
                "approved_video_source": "generated",
                "input_frame_relative_path": row["input_frame_relative_path"],
                "input_frame_original_filename": row["input_frame_original_filename"],
                "input_frame_mime_type": row["input_frame_mime_type"],
                "input_frame_size_bytes": row["input_frame_size_bytes"],
                "input_frame_created_at": row["input_frame_created_at"],
                "last_frame_relative_path": row["last_frame_relative_path"],
                "last_frame_original_filename": row["last_frame_original_filename"],
                "last_frame_mime_type": row["last_frame_mime_type"],
                "last_frame_size_bytes": row["last_frame_size_bytes"],
                "last_frame_created_at": row["last_frame_created_at"],
            },
        )

    def update_sequence_wan_prompt(self, sequence_id: str, wan_prompt_text: str) -> dict | None:
        return self.update_sequence(sequence_id, {"wan_prompt_text": wan_prompt_text})

    def batch_update_sequences(self, scene_id: str, sequence_ids: list[str], updates: dict) -> list[dict]:
        now = utc_now_iso()
        with self.database.connect() as connection:
            scene_row = connection.execute(
                "SELECT project_id FROM story_scenes WHERE id = ?",
                (scene_id,),
            ).fetchone()
            if scene_row is None:
                return []
            valid_rows = connection.execute(
                """
                SELECT id
                FROM scenes
                WHERE story_scene_id = ?
                """,
                (scene_id,),
            ).fetchall()
            valid_ids = {row["id"] for row in valid_rows}
            target_ids = [sequence_id for sequence_id in sequence_ids if sequence_id in valid_ids]
            for sequence_id in target_ids:
                self._update_sequence_row(connection, sequence_id, updates, now)
            if target_ids:
                connection.execute("DELETE FROM continuity_reviews WHERE scene_id = ?", (scene_id,))
                connection.execute(
                    "UPDATE projects SET updated_at = ? WHERE id = ?",
                    (now, scene_row["project_id"]),
                )
        return self.list_sequences(scene_id)

    def get_continuity_review(self, scene_id: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM continuity_reviews WHERE scene_id = ?",
                (scene_id,),
            ).fetchone()
        return None if row is None else self._continuity_review_from_row(row)

    def save_continuity_review(self, project_id: str, scene_id: str, review: dict) -> dict:
        now = utc_now_iso()
        with self.database.connect() as connection:
            existing = connection.execute(
                "SELECT id, created_at FROM continuity_reviews WHERE scene_id = ?",
                (scene_id,),
            ).fetchone()
            review_id = existing["id"] if existing is not None else str(uuid.uuid4())
            created_at = existing["created_at"] if existing is not None else now
            connection.execute(
                """
                INSERT INTO continuity_reviews (
                    id, project_id, scene_id, source, summary_text,
                    findings_json, sequence_suggestions_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scene_id) DO UPDATE SET
                    source = excluded.source,
                    summary_text = excluded.summary_text,
                    findings_json = excluded.findings_json,
                    sequence_suggestions_json = excluded.sequence_suggestions_json,
                    updated_at = excluded.updated_at
                """,
                (
                    review_id,
                    project_id,
                    scene_id,
                    review.get("source", "rules_only"),
                    review.get("summary_text", ""),
                    json.dumps(review.get("findings", [])),
                    json.dumps(review.get("sequence_suggestions", [])),
                    created_at,
                    now,
                ),
            )
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (now, project_id),
            )
        saved = self.get_continuity_review(scene_id)
        if saved is None:
            raise RuntimeError("Continuity review could not be persisted.")
        return saved

    def clear_continuity_review(self, scene_id: str) -> None:
        now = utc_now_iso()
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT project_id
                FROM continuity_reviews
                WHERE scene_id = ?
                """,
                (scene_id,),
            ).fetchone()
            connection.execute("DELETE FROM continuity_reviews WHERE scene_id = ?", (scene_id,))
            if row is not None:
                connection.execute(
                    "UPDATE projects SET updated_at = ? WHERE id = ?",
                    (now, row["project_id"]),
                )

    def set_sequence_video_asset(
        self,
        sequence_id: str,
        *,
        relative_path: str,
        original_filename: str,
        mime_type: str | None,
        size_bytes: int,
    ) -> dict | None:
        now = utc_now_iso()
        return self.update_sequence(
            sequence_id,
            {
                "uploaded_sequence_relative_path": relative_path,
                "uploaded_sequence_original_filename": original_filename,
                "uploaded_sequence_mime_type": mime_type,
                "uploaded_sequence_size_bytes": size_bytes,
                "uploaded_sequence_uploaded_at": now,
            },
        )

    def set_project_style_anchor(self, project_id: str, style_anchor_text: str) -> dict | None:
        return self.update_project(project_id, {"style_anchor_text": style_anchor_text})

    def duplicate_project_to_v2(self, source_project_id: str) -> dict | None:
        source_detail = self.get_project_detail(source_project_id)
        if source_detail is None:
            return None
        if source_detail["workflow_version"] >= 2:
            return source_detail

        source_root = self.ensure_project_assets(source_project_id)
        target_project_id = str(uuid.uuid4())
        now = utc_now_iso()
        target_name = f"{source_detail['name']} (2.0)"

        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO projects (
                    id, name, scenario_text, genre, tone, target_duration_s,
                    output_width, output_height, output_fps, aspect_ratio,
                    workflow_version, style_anchor_text, model_settings_override_json, opening_image_prompt_text,
                    opening_image_relative_path, opening_image_original_filename,
                    opening_image_mime_type, opening_image_size_bytes,
                    opening_image_uploaded_at, beat_board_status, archived_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    target_project_id,
                    target_name,
                    source_detail["scenario_text"],
                    source_detail["genre"],
                    source_detail["tone"],
                    source_detail["target_duration_s"],
                    source_detail["output_width"],
                    source_detail["output_height"],
                    source_detail["output_fps"],
                    source_detail["aspect_ratio"],
                    2,
                    source_detail.get("style_anchor_text", ""),
                    json.dumps(default_project_model_settings_override()),
                    "",
                    None,
                    None,
                    None,
                    0,
                    None,
                    "empty",
                    None,
                    now,
                    now,
                ),
            )

            legacy_rows = connection.execute(
                """
                SELECT *
                FROM scenes
                WHERE project_id = ? AND story_scene_id IS NULL
                ORDER BY order_index ASC, created_at ASC
                """,
                (source_project_id,),
            ).fetchall()
            grouped = self._group_legacy_sequences(legacy_rows)

            absolute_order = 0
            for story_scene_index, group in enumerate(grouped, start=1):
                story_scene_id = str(uuid.uuid4())
                connection.execute(
                    """
                    INSERT INTO story_scenes (
                        id, project_id, order_index, title, target_duration_s,
                        narrative_text, duration_locked, first_image_prompt_text,
                        first_image_relative_path, first_image_original_filename,
                        first_image_mime_type, first_image_size_bytes,
                        first_image_uploaded_at, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        story_scene_id,
                        target_project_id,
                        story_scene_index,
                        group["title"],
                        group["target_duration_s"],
                        group["narrative_text"],
                        0,
                        "",
                        None,
                        None,
                        None,
                        0,
                        None,
                        now,
                        now,
                    ),
                )
                for sequence_index, row in enumerate(group["rows"], start=1):
                    absolute_order += 1
                    new_sequence_id = str(uuid.uuid4())
                    copied_relative_path = None
                    copied_original_filename = row["uploaded_sequence_original_filename"]
                    copied_mime_type = row["uploaded_sequence_mime_type"]
                    copied_size_bytes = row["uploaded_sequence_size_bytes"] or 0
                    copied_uploaded_at = row["uploaded_sequence_uploaded_at"]
                    if row["uploaded_sequence_relative_path"]:
                        copied_relative_path = row["uploaded_sequence_relative_path"]
                        source_path = source_root / copied_relative_path
                        target_root = self.ensure_project_assets(target_project_id)
                        target_path = target_root / copied_relative_path
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        if source_path.exists():
                            shutil.copy2(source_path, target_path)
                    connection.execute(
                        """
                        INSERT INTO scenes (
                            id, project_id, story_scene_id, order_index, absolute_order,
                            title, target_duration_s, narrative_text, duration_locked, prompt_text,
                            camera_direction, action_direction, wan_prompt_text,
                            uploaded_sequence_relative_path, uploaded_sequence_original_filename,
                            uploaded_sequence_mime_type, uploaded_sequence_size_bytes,
                            uploaded_sequence_uploaded_at, trim_in_ms, trim_out_ms,
                            include_in_assembly, render_status, approved_clip_id,
                            created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            new_sequence_id,
                            target_project_id,
                            story_scene_id,
                            sequence_index,
                            absolute_order,
                            row["title"],
                            row["target_duration_s"],
                            row["narrative_text"],
                            0,
                            row["prompt_text"],
                            row["camera_direction"],
                            row["action_direction"],
                            row["wan_prompt_text"] or row["prompt_text"] or "",
                            copied_relative_path,
                            copied_original_filename,
                            copied_mime_type,
                            copied_size_bytes,
                            copied_uploaded_at,
                            row["trim_in_ms"] or 0,
                            row["trim_out_ms"] or 0,
                            1 if row["include_in_assembly"] else 0,
                            row["render_status"],
                            row["approved_clip_id"],
                            row["created_at"],
                            row["updated_at"],
                        ),
                    )
        return self.get_project_detail(target_project_id)

    def create_job(self, project_id: str, job_type: JobType, payload: dict, scene_id: str | None = None) -> dict:
        job_id = str(uuid.uuid4())
        now = utc_now_iso()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs (
                    id, project_id, scene_id, job_type, status, progress,
                    payload_json, result_json, error_text, cancel_requested,
                    created_at, updated_at, started_at, completed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    project_id,
                    scene_id,
                    job_type.value,
                    JobStatus.queued.value,
                    0.0,
                    json.dumps(payload),
                    json.dumps({}),
                    None,
                    0,
                    now,
                    now,
                    None,
                    None,
                ),
            )
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        return None if row is None else self._job_from_row(row)

    def mark_job_running(self, job_id: str) -> dict | None:
        now = utc_now_iso()
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET status = ?, started_at = COALESCE(started_at, ?), updated_at = ?
                WHERE id = ?
                """,
                (JobStatus.running.value, now, now, job_id),
            )
        return self.get_job(job_id)

    def update_job(
        self,
        job_id: str,
        *,
        status: JobStatus | None = None,
        progress: float | None = None,
        result: dict | None = None,
        error_text: str | None = None,
        cancel_requested: bool | None = None,
    ) -> dict | None:
        assignments = []
        values: list[object] = []
        if status is not None:
            assignments.append("status = ?")
            values.append(status.value)
        if progress is not None:
            assignments.append("progress = ?")
            values.append(progress)
        if result is not None:
            assignments.append("result_json = ?")
            values.append(json.dumps(result))
        if error_text is not None or status == JobStatus.failed:
            assignments.append("error_text = ?")
            values.append(error_text)
        if cancel_requested is not None:
            assignments.append("cancel_requested = ?")
            values.append(1 if cancel_requested else 0)
        now = utc_now_iso()
        assignments.append("updated_at = ?")
        values.append(now)
        if status in {JobStatus.succeeded, JobStatus.failed, JobStatus.canceled}:
            assignments.append("completed_at = ?")
            values.append(now)
        values.append(job_id)

        with self.database.connect() as connection:
            connection.execute(
                f"UPDATE jobs SET {', '.join(assignments)} WHERE id = ?",
                values,
            )
        return self.get_job(job_id)

    def request_job_cancel(self, job_id: str) -> dict | None:
        return self.update_job(job_id, cancel_requested=True)

    def requeue_pending_jobs(self) -> list[str]:
        with self.database.connect() as connection:
            running_jobs = connection.execute(
                "SELECT id FROM jobs WHERE status = ?",
                (JobStatus.running.value,),
            ).fetchall()
            queued_jobs = connection.execute(
                "SELECT id FROM jobs WHERE status = ? ORDER BY created_at ASC",
                (JobStatus.queued.value,),
            ).fetchall()
            now = utc_now_iso()
            if running_jobs:
                connection.execute(
                    """
                    UPDATE jobs
                    SET status = ?, error_text = ?, completed_at = ?, updated_at = ?
                    WHERE status = ?
                    """,
                    (
                        JobStatus.failed.value,
                        "Job interrupted by application restart.",
                        now,
                        now,
                        JobStatus.running.value,
                    ),
                )
        return [row["id"] for row in queued_jobs]

    def create_export_asset(self, project_id: str, job_id: str, relative_path: str, duration_s: float) -> dict:
        export_id = str(uuid.uuid4())
        now = utc_now_iso()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO export_assets (id, project_id, job_id, relative_path, duration_s, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (export_id, project_id, job_id, relative_path, duration_s, now),
            )
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (now, project_id),
            )
        detail = self.get_project_detail(project_id)
        if detail is None:
            raise RuntimeError("Failed to create export asset.")
        return next(export for export in detail["exports"] if export["id"] == export_id)

    def ensure_project_assets(self, project_id: str) -> Path:
        project_root = self.settings.projects_root / project_id
        for path in (
            project_root,
            project_root / "clips",
            project_root / "exports",
            project_root / "scene-images",
            project_root / "scene-images" / "generated",
            project_root / "scene-images" / "uploads",
            project_root / "sequence-videos",
            project_root / "sequence-videos" / "generated",
            project_root / "sequence-videos" / "uploads",
            project_root / "sequence-frames",
            project_root / "tmp",
        ):
            path.mkdir(parents=True, exist_ok=True)
        return project_root

    def _update_project_row(self, connection, project_id: str, updates: dict, now: str) -> None:
        assignments = []
        values: list[object] = []
        for key, value in updates.items():
            assignments.append(f"{key} = ?")
            values.append(value)
        assignments.append("updated_at = ?")
        values.append(now)
        values.append(project_id)
        connection.execute(
            f"UPDATE projects SET {', '.join(assignments)} WHERE id = ?",
            values,
        )

    def _update_story_scene_row(
        self,
        connection,
        scene_id: str,
        updates: dict,
        now: str,
        *,
        order: int | None = None,
    ) -> None:
        assignments = []
        values: list[object] = []
        for key, value in updates.items():
            if key == "duration_locked":
                value = 1 if value else 0
            assignments.append(f"{key} = ?")
            values.append(value)
        if order is not None:
            assignments.append("order_index = ?")
            values.append(order)
        if not assignments:
            return
        assignments.append("updated_at = ?")
        values.append(now)
        values.append(scene_id)
        connection.execute(
            f"UPDATE story_scenes SET {', '.join(assignments)} WHERE id = ?",
            values,
        )

    def _update_sequence_row(
        self,
        connection,
        sequence_id: str,
        updates: dict,
        now: str,
        *,
        order: int | None = None,
    ) -> None:
        assignments = []
        values: list[object] = []
        for key, value in updates.items():
            if key in {"include_in_assembly", "duration_locked"}:
                value = 1 if value else 0
            assignments.append(f"{key} = ?")
            values.append(value)
        if order is not None:
            assignments.append("order_index = ?")
            values.append(order)
        if not assignments:
            return
        assignments.append("updated_at = ?")
        values.append(now)
        values.append(sequence_id)
        connection.execute(
            f"UPDATE scenes SET {', '.join(assignments)} WHERE id = ?",
            values,
        )

    def _rebalance_project_scenes_to_total(self, connection, project_id: str, total_duration_s: int, now: str) -> None:
        scene_rows = connection.execute(
            "SELECT * FROM story_scenes WHERE project_id = ? ORDER BY order_index ASC, created_at ASC",
            (project_id,),
        ).fetchall()
        if not scene_rows:
            return
        duration_map = self._rebalance_duration_map(
            scene_rows,
            total_duration_s,
            min_duration_s=SCENE_MIN_DURATION_S,
            max_duration_s=SCENE_MAX_DURATION_S,
            label="scene",
        )
        changed_scene_ids = self._apply_story_scene_duration_map(connection, scene_rows, duration_map, now)
        for scene_id in changed_scene_ids:
            self._rebalance_scene_sequence_durations(connection, scene_id, now)

    def _rebalance_project_after_scene_duration_change(
        self,
        connection,
        scene_id: str,
        target_duration_s: int,
        now: str,
    ) -> None:
        scene_row = connection.execute(
            "SELECT project_id FROM story_scenes WHERE id = ?",
            (scene_id,),
        ).fetchone()
        if scene_row is None:
            return
        project_row = connection.execute(
            "SELECT target_duration_s FROM projects WHERE id = ?",
            (scene_row["project_id"],),
        ).fetchone()
        scene_rows = connection.execute(
            "SELECT * FROM story_scenes WHERE project_id = ? ORDER BY order_index ASC, created_at ASC",
            (scene_row["project_id"],),
        ).fetchall()
        if project_row is None or not scene_rows:
            return
        duration_map = self._rebalance_duration_map(
            scene_rows,
            int(project_row["target_duration_s"]),
            min_duration_s=SCENE_MIN_DURATION_S,
            max_duration_s=SCENE_MAX_DURATION_S,
            fixed_durations={scene_id: target_duration_s},
            label="scene",
        )
        changed_scene_ids = self._apply_story_scene_duration_map(connection, scene_rows, duration_map, now)
        for changed_scene_id in changed_scene_ids:
            self._rebalance_scene_sequence_durations(connection, changed_scene_id, now)
        connection.execute(
            "UPDATE projects SET updated_at = ? WHERE id = ?",
            (now, scene_row["project_id"]),
        )

    def _rebalance_scene_sequence_durations(
        self,
        connection,
        scene_id: str,
        now: str,
        *,
        fixed_sequence_id: str | None = None,
        fixed_duration: int | None = None,
    ) -> None:
        scene_row = connection.execute(
            "SELECT project_id, target_duration_s FROM story_scenes WHERE id = ?",
            (scene_id,),
        ).fetchone()
        if scene_row is None:
            return
        sequence_rows = connection.execute(
            """
            SELECT *
            FROM scenes
            WHERE story_scene_id = ?
            ORDER BY order_index ASC, absolute_order ASC, created_at ASC
            """,
            (scene_id,),
        ).fetchall()
        if not sequence_rows:
            return
        fixed_durations = None
        if fixed_sequence_id is not None and fixed_duration is not None:
            fixed_durations = {fixed_sequence_id: fixed_duration}
        duration_map = self._rebalance_duration_map(
            sequence_rows,
            int(scene_row["target_duration_s"]),
            min_duration_s=SEQUENCE_MIN_DURATION_S,
            max_duration_s=SEQUENCE_MAX_DURATION_S,
            fixed_durations=fixed_durations,
            label="sequence",
        )
        self._apply_sequence_duration_map(connection, sequence_rows, duration_map, now)
        connection.execute(
            "UPDATE projects SET updated_at = ? WHERE id = ?",
            (now, scene_row["project_id"]),
        )

    def _apply_story_scene_duration_map(self, connection, scene_rows, duration_map: dict[str, int], now: str) -> list[str]:
        changed_scene_ids: list[str] = []
        for row in scene_rows:
            next_duration = int(duration_map[row["id"]])
            if int(row["target_duration_s"]) == next_duration:
                continue
            changed_scene_ids.append(row["id"])
            connection.execute(
                "UPDATE story_scenes SET target_duration_s = ?, updated_at = ? WHERE id = ?",
                (next_duration, now, row["id"]),
            )
        return changed_scene_ids

    def _apply_sequence_duration_map(self, connection, sequence_rows, duration_map: dict[str, int], now: str) -> list[str]:
        changed_sequence_ids: list[str] = []
        for row in sequence_rows:
            next_duration = int(duration_map[row["id"]])
            if int(row["target_duration_s"]) == next_duration:
                continue
            changed_sequence_ids.append(row["id"])
            connection.execute(
                "UPDATE scenes SET target_duration_s = ?, updated_at = ? WHERE id = ?",
                (next_duration, now, row["id"]),
            )
        return changed_sequence_ids

    def _rebalance_duration_map(
        self,
        rows,
        total_duration_s: int,
        *,
        min_duration_s: int,
        max_duration_s: int,
        fixed_durations: dict[str, int] | None = None,
        label: str,
    ) -> dict[str, int]:
        fixed_durations = fixed_durations or {}
        result: dict[str, int] = {}
        adjustable: list[dict[str, int]] = []
        fixed_total = 0

        for row in rows:
            row_id = row["id"]
            current_duration = int(row["target_duration_s"])
            requested_duration = fixed_durations.get(row_id)
            if requested_duration is not None:
                requested_duration = int(requested_duration)
            if requested_duration is not None:
                if requested_duration < min_duration_s or requested_duration > max_duration_s:
                    raise DurationConflictError(
                        f"{label.title()} duration must stay between {min_duration_s}s and {max_duration_s}s."
                    )
                result[row_id] = requested_duration
                fixed_total += requested_duration
                continue
            if bool(row["duration_locked"]):
                if current_duration < min_duration_s or current_duration > max_duration_s:
                    raise DurationConflictError(
                        f"Locked {label} durations are outside the allowed {min_duration_s}s-{max_duration_s}s range."
                    )
                result[row_id] = current_duration
                fixed_total += current_duration
                continue
            adjustable.append({"id": row_id, "current": current_duration})

        remaining_total = int(total_duration_s) - fixed_total
        if not adjustable:
            if remaining_total != 0:
                raise DurationConflictError(
                    f"Locked {label} durations already consume {fixed_total}s, which does not match the requested total."
                )
            return result

        min_remaining = len(adjustable) * min_duration_s
        max_remaining = len(adjustable) * max_duration_s
        if remaining_total < min_remaining or remaining_total > max_remaining:
            raise DurationConflictError(
                f"Cannot rebalance {label} durations with the current locks. Remaining {label}s need {remaining_total}s, "
                f"but the allowed range is {min_remaining}s to {max_remaining}s."
            )

        result.update(
            self._distribute_durations(
                adjustable,
                remaining_total,
                min_duration_s=min_duration_s,
                max_duration_s=max_duration_s,
            )
        )
        return result

    def _distribute_durations(
        self,
        items: list[dict[str, int]],
        total_duration_s: int,
        *,
        min_duration_s: int,
        max_duration_s: int,
    ) -> dict[str, int]:
        remaining = [
            {"id": item["id"], "weight": max(1, int(item["current"]))}
            for item in items
        ]
        remaining_total = int(total_duration_s)
        resolved: dict[str, int] = {}

        while remaining:
            weight_sum = sum(item["weight"] for item in remaining) or len(remaining)
            next_remaining: list[dict[str, int]] = []
            clamped = False
            for item in remaining:
                raw_value = remaining_total * item["weight"] / weight_sum
                if raw_value <= min_duration_s:
                    resolved[item["id"]] = min_duration_s
                    remaining_total -= min_duration_s
                    clamped = True
                elif raw_value >= max_duration_s:
                    resolved[item["id"]] = max_duration_s
                    remaining_total -= max_duration_s
                    clamped = True
                else:
                    next_remaining.append(item)
            if not clamped:
                break
            remaining = next_remaining

        if not remaining:
            return resolved

        weight_sum = sum(item["weight"] for item in remaining) or len(remaining)
        assigned_total = 0
        fractional_parts: list[tuple[float, int, str]] = []
        for item in remaining:
            raw_value = remaining_total * item["weight"] / weight_sum
            whole_value = int(raw_value)
            resolved[item["id"]] = whole_value
            assigned_total += whole_value
            fractional_parts.append((raw_value - whole_value, item["weight"], item["id"]))

        for _, _, row_id in sorted(fractional_parts, reverse=True)[: remaining_total - assigned_total]:
            resolved[row_id] += 1
        return resolved

    def _normalize_story_scene_order(self, connection, project_id: str) -> None:
        rows = connection.execute(
            "SELECT id FROM story_scenes WHERE project_id = ? ORDER BY order_index ASC, created_at ASC",
            (project_id,),
        ).fetchall()
        for index, row in enumerate(rows, start=1):
            connection.execute(
                "UPDATE story_scenes SET order_index = ? WHERE id = ?",
                (index, row["id"]),
            )

    def _normalize_sequence_orders(self, connection, project_id: str) -> None:
        story_scene_rows = connection.execute(
            "SELECT id FROM story_scenes WHERE project_id = ? ORDER BY order_index ASC, created_at ASC",
            (project_id,),
        ).fetchall()
        absolute_order = 0
        for story_scene_row in story_scene_rows:
            sequence_rows = connection.execute(
                """
                SELECT id
                FROM scenes
                WHERE project_id = ? AND story_scene_id = ?
                ORDER BY order_index ASC, absolute_order ASC, created_at ASC
                """,
                (project_id, story_scene_row["id"]),
            ).fetchall()
            for index, sequence_row in enumerate(sequence_rows, start=1):
                absolute_order += 1
                connection.execute(
                    "UPDATE scenes SET order_index = ?, absolute_order = ? WHERE id = ?",
                    (index, absolute_order, sequence_row["id"]),
                )

    def _normalize_story_beats(self, connection, project_id: str) -> None:
        for act_index in range(1, 4):
            beat_rows = connection.execute(
                """
                SELECT id
                FROM story_beats
                WHERE project_id = ? AND act_index = ?
                ORDER BY order_index ASC, created_at ASC
                """,
                (project_id, act_index),
            ).fetchall()
            for index, beat_row in enumerate(beat_rows, start=1):
                connection.execute(
                    "UPDATE story_beats SET order_index = ? WHERE id = ?",
                    (index, beat_row["id"]),
                )

    def _normalize_project_characters(self, connection, project_id: str) -> None:
        rows = connection.execute(
            """
            SELECT id
            FROM project_characters
            WHERE project_id = ?
            ORDER BY order_index ASC, created_at ASC
            """,
            (project_id,),
        ).fetchall()
        for index, row in enumerate(rows, start=1):
            connection.execute(
                "UPDATE project_characters SET order_index = ? WHERE id = ?",
                (index, row["id"]),
            )

    def _scenario_text_from_beats(self, project: dict, beats: list[dict]) -> str:
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

    def _refresh_scene_chain_state(self, scene: dict) -> None:
        required_input = scene.get("first_image_asset")
        ordered_sequences = sorted(
            scene.get("sequences", []),
            key=lambda item: (item.get("order", 0), item.get("absolute_order", 0), item.get("created_at", "")),
        )
        for sequence in ordered_sequences:
            approved_asset = sequence.get("approved_video_asset")
            saved_input = sequence.get("input_frame_asset")
            if required_input is None:
                sequence["chain_state"] = "missing_input"
            elif approved_asset is None:
                sequence["chain_state"] = "ready"
            elif (
                saved_input is None
                or saved_input.get("relative_path") != required_input.get("relative_path")
                or saved_input.get("created_at") != required_input.get("created_at")
            ):
                sequence["chain_state"] = "stale_upstream"
            else:
                sequence["chain_state"] = "generated"
            required_input = sequence.get("last_frame_asset")

    def _group_legacy_sequences(self, rows) -> list[dict]:
        sequence_rows = list(rows)
        if not sequence_rows:
            return []
        total_duration = sum(int(row["target_duration_s"]) for row in sequence_rows)
        desired_scene_count = max(3, min(4, round(total_duration / 75)))
        target_duration = max(30, min(90, round(total_duration / desired_scene_count)))
        groups: list[list] = []
        current_group: list = []
        current_duration = 0
        remaining_groups = desired_scene_count

        for index, row in enumerate(sequence_rows, start=1):
            remaining_rows = len(sequence_rows) - index
            current_group.append(row)
            current_duration += int(row["target_duration_s"])
            need_split = current_duration >= target_duration and remaining_groups > 1
            must_split = remaining_rows < remaining_groups - 1
            if need_split or must_split:
                groups.append(current_group)
                current_group = []
                current_duration = 0
                remaining_groups -= 1
        if current_group:
            groups.append(current_group)

        normalized: list[dict] = []
        for group_index, group in enumerate(groups, start=1):
            title = self._title_from_legacy_group(group, group_index)
            narrative = " ".join(str(row["narrative_text"]).strip() for row in group if str(row["narrative_text"]).strip())
            normalized.append(
                {
                    "title": title,
                    "target_duration_s": sum(int(row["target_duration_s"]) for row in group),
                    "narrative_text": narrative or f"Scene {group_index:02d}",
                    "rows": group,
                }
            )
        return normalized

    def _title_from_legacy_group(self, group, group_index: int) -> str:
        first_title = str(group[0]["title"]).strip()
        if first_title:
            parts = first_title.split(" ", 1)
            candidate = parts[1] if len(parts) > 1 and parts[0].rstrip(".").isdigit() else first_title
            return f"{group_index:02d}. {candidate}"
        return f"{group_index:02d}. Scene {group_index:02d}"

    def _project_list_item_from_row(self, row) -> dict:
        return {
            "id": row["id"],
            "name": row["name"],
            "target_duration_s": row["target_duration_s"],
            "genre": row["genre"],
            "tone": row["tone"],
            "scene_count": row["scene_count"],
            "workflow_version": row["workflow_version"] or 1,
            "upgrade_available": bool((row["workflow_version"] or 1) < 2 and row["legacy_sequence_count"]),
            "archived_at": row["archived_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _project_from_row(self, row) -> dict:
        return {
            "id": row["id"],
            "name": row["name"],
            "scenario_text": row["scenario_text"],
            "genre": row["genre"],
            "tone": row["tone"],
            "target_duration_s": row["target_duration_s"],
            "output_width": row["output_width"],
            "output_height": row["output_height"],
            "output_fps": row["output_fps"],
            "aspect_ratio": row["aspect_ratio"],
            "workflow_version": row["workflow_version"] or 1,
            "upgrade_available": bool((row["workflow_version"] or 1) < 2),
            "legacy_sequence_count": 0,
            "beat_board_status": row["beat_board_status"] or "empty",
            "style_anchor_text": row["style_anchor_text"] or "",
            "model_settings_override": normalize_project_model_settings_override(_loads(row["model_settings_override_json"])),
            "opening_image_prompt_text": row["opening_image_prompt_text"] or "",
            "archived_at": row["archived_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _story_scene_from_row(self, row) -> dict:
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "order": row["order_index"],
            "title": row["title"],
            "target_duration_s": row["target_duration_s"],
            "narrative_text": row["narrative_text"],
            "duration_locked": bool(row["duration_locked"]),
            "first_image_prompt_text": row["first_image_prompt_text"] or "",
            "first_image_asset": self._story_scene_media_asset_from_row(row),
            "first_image_source": row["first_image_source"] or None,
            "generated_image_variants": [],
            "image_generation_status": row["image_generation_status"] or "idle",
            "sequences": [],
            "continuity_review": None,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _sequence_from_row(self, row) -> dict:
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "scene_id": row["story_scene_id"],
            "order": row["order_index"],
            "absolute_order": row["absolute_order"] or row["order_index"],
            "title": row["title"],
            "target_duration_s": row["target_duration_s"],
            "narrative_text": row["narrative_text"],
            "duration_locked": bool(row["duration_locked"]),
            "camera_direction": row["camera_direction"] or "",
            "action_direction": row["action_direction"] or "",
            "wan_prompt_text": row["wan_prompt_text"] or row["prompt_text"] or "",
            "uploaded_video_asset": self._sequence_media_asset_from_row(row),
            "approved_video_asset": self._sequence_approved_video_asset_from_row(row),
            "approved_video_source": row["approved_video_source"] or None,
            "generated_video_variants": [],
            "input_frame_asset": self._sequence_input_frame_asset_from_row(row),
            "last_frame_asset": self._sequence_last_frame_asset_from_row(row),
            "chain_state": "missing_input",
            "trim_in_ms": row["trim_in_ms"] or 0,
            "trim_out_ms": row["trim_out_ms"] or 0,
            "include_in_assembly": bool(row["include_in_assembly"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _story_scene_media_asset_from_row(self, row) -> dict | None:
        return self._media_asset_from_fields(
            asset_id=f"scene-image-{row['id']}",
            project_id=row["project_id"],
            scene_id=row["id"],
            sequence_id=None,
            relative_path=row["first_image_relative_path"],
            original_filename=row["first_image_original_filename"],
            mime_type=row["first_image_mime_type"],
            size_bytes=row["first_image_size_bytes"],
            created_at=row["first_image_uploaded_at"] or row["updated_at"],
        )

    def _sequence_media_asset_from_row(self, row) -> dict | None:
        return self._media_asset_from_fields(
            asset_id=f"sequence-upload-{row['id']}",
            project_id=row["project_id"],
            scene_id=row["story_scene_id"],
            sequence_id=row["id"],
            relative_path=row["uploaded_sequence_relative_path"],
            original_filename=row["uploaded_sequence_original_filename"],
            mime_type=row["uploaded_sequence_mime_type"],
            size_bytes=row["uploaded_sequence_size_bytes"],
            created_at=row["uploaded_sequence_uploaded_at"] or row["updated_at"],
        )

    def _sequence_approved_video_asset_from_row(self, row) -> dict | None:
        return self._media_asset_from_fields(
            asset_id=f"sequence-approved-{row['id']}",
            project_id=row["project_id"],
            scene_id=row["story_scene_id"],
            sequence_id=row["id"],
            relative_path=row["approved_video_relative_path"],
            original_filename=row["approved_video_original_filename"],
            mime_type=row["approved_video_mime_type"],
            size_bytes=row["approved_video_size_bytes"],
            created_at=row["approved_video_created_at"] or row["updated_at"],
        )

    def _sequence_input_frame_asset_from_row(self, row) -> dict | None:
        return self._media_asset_from_fields(
            asset_id=f"sequence-input-frame-{row['id']}",
            project_id=row["project_id"],
            scene_id=row["story_scene_id"],
            sequence_id=row["id"],
            relative_path=row["input_frame_relative_path"],
            original_filename=row["input_frame_original_filename"],
            mime_type=row["input_frame_mime_type"],
            size_bytes=row["input_frame_size_bytes"],
            created_at=row["input_frame_created_at"] or row["updated_at"],
        )

    def _sequence_last_frame_asset_from_row(self, row) -> dict | None:
        return self._media_asset_from_fields(
            asset_id=f"sequence-last-frame-{row['id']}",
            project_id=row["project_id"],
            scene_id=row["story_scene_id"],
            sequence_id=row["id"],
            relative_path=row["last_frame_relative_path"],
            original_filename=row["last_frame_original_filename"],
            mime_type=row["last_frame_mime_type"],
            size_bytes=row["last_frame_size_bytes"],
            created_at=row["last_frame_created_at"] or row["updated_at"],
        )

    def _media_asset_from_fields(
        self,
        *,
        asset_id: str,
        project_id: str,
        scene_id: str | None,
        sequence_id: str | None,
        relative_path: str | None,
        original_filename: str | None,
        mime_type: str | None,
        size_bytes: int | None,
        created_at: str | None,
    ) -> dict | None:
        if not relative_path:
            return None
        return {
            "id": asset_id,
            "project_id": project_id,
            "scene_id": scene_id,
            "sequence_id": sequence_id,
            "relative_path": relative_path,
            "original_filename": original_filename or Path(relative_path).name,
            "mime_type": mime_type,
            "size_bytes": size_bytes or 0,
            "created_at": created_at or utc_now_iso(),
        }

    def _scene_image_variant_from_row(self, row) -> dict:
        return {
            "id": row["id"],
            "scene_id": row["scene_id"],
            "provider": row["provider"],
            "model_name": row["model_name"],
            "seed": row["seed"],
            "prompt_text": row["prompt_text"] or "",
            "asset": self._media_asset_from_fields(
                asset_id=f"scene-image-variant-{row['id']}",
                project_id=row["project_id"],
                scene_id=row["scene_id"],
                sequence_id=None,
                relative_path=row["relative_path"],
                original_filename=row["original_filename"],
                mime_type=row["mime_type"],
                size_bytes=row["size_bytes"],
                created_at=row["created_at"],
            ),
            "created_at": row["created_at"],
        }

    def _sequence_video_variant_from_row(self, row) -> dict:
        return {
            "id": row["id"],
            "sequence_id": row["sequence_id"],
            "provider": row["provider"],
            "model_name": row["model_name"],
            "seed": row["seed"],
            "prompt_text": row["prompt_text"] or "",
            "native_duration_s": row["native_duration_s"] or 0.0,
            "output_duration_s": row["output_duration_s"] or 0.0,
            "asset": self._media_asset_from_fields(
                asset_id=f"sequence-video-variant-{row['id']}",
                project_id=row["project_id"],
                scene_id=row["scene_id"],
                sequence_id=row["sequence_id"],
                relative_path=row["relative_path"],
                original_filename=row["original_filename"],
                mime_type=row["mime_type"],
                size_bytes=row["size_bytes"],
                created_at=row["created_at"],
            ),
            "input_frame_asset": self._media_asset_from_fields(
                asset_id=f"sequence-video-variant-input-{row['id']}",
                project_id=row["project_id"],
                scene_id=row["scene_id"],
                sequence_id=row["sequence_id"],
                relative_path=row["input_frame_relative_path"],
                original_filename=row["input_frame_original_filename"],
                mime_type=row["input_frame_mime_type"],
                size_bytes=row["input_frame_size_bytes"],
                created_at=row["input_frame_created_at"],
            ),
            "last_frame_asset": self._media_asset_from_fields(
                asset_id=f"sequence-video-variant-last-{row['id']}",
                project_id=row["project_id"],
                scene_id=row["scene_id"],
                sequence_id=row["sequence_id"],
                relative_path=row["last_frame_relative_path"],
                original_filename=row["last_frame_original_filename"],
                mime_type=row["last_frame_mime_type"],
                size_bytes=row["last_frame_size_bytes"],
                created_at=row["last_frame_created_at"],
            ),
            "created_at": row["created_at"],
        }

    def _story_beat_from_row(self, row) -> dict:
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "act_index": row["act_index"],
            "order_index": row["order_index"],
            "title": row["title"],
            "summary_text": row["summary_text"] or "",
            "purpose_text": row["purpose_text"] or "",
            "source": row["source"] or "generated",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _project_character_from_row(self, row) -> dict:
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "name": row["name"],
            "role_summary": row["role_summary"] or "",
            "prompt_tags": row["prompt_tags"] or "",
            "order_index": row["order_index"],
            "portrait_image_url": row["portrait_image_url"],
            "cowboyshot_image_url": row["cowboyshot_image_url"],
            "fullbody_image_url": row["fullbody_image_url"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _continuity_review_from_row(self, row) -> dict:
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "scene_id": row["scene_id"],
            "source": row["source"],
            "summary_text": row["summary_text"] or "",
            "findings": _loads(row["findings_json"]) if row["findings_json"] else [],
            "sequence_suggestions": _loads(row["sequence_suggestions_json"]) if row["sequence_suggestions_json"] else [],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _job_from_row(self, row) -> dict:
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "scene_id": row["scene_id"],
            "job_type": row["job_type"],
            "status": row["status"],
            "progress": row["progress"],
            "payload": _loads(row["payload_json"]),
            "result": _loads(row["result_json"]),
            "error_text": row["error_text"],
            "cancel_requested": bool(row["cancel_requested"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
        }

    def _export_from_row(self, row) -> dict:
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "job_id": row["job_id"],
            "relative_path": row["relative_path"],
            "duration_s": row["duration_s"],
            "created_at": row["created_at"],
        }
