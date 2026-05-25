from __future__ import annotations

import json
import re
import uuid
from typing import Any

from ..database import Database, utc_now_iso


class CompatibilityInspector:
    def __init__(self, database: Database) -> None:
        self.database = database

    def inspect(self, project: dict[str, Any]) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        self._check_project(project, issues)
        for character in project.get("characters", []):
            self._check_character(character, issues)
        for entry in project.get("lore_entries", []):
            self._check_lore(entry, project, issues)
        self._check_user_profile(project.get("user_profile", {}) or {}, issues)
        if project.get("project_mode") == "game_master":
            self._check_gm_card(project, issues)

        critical_count = sum(1 for item in issues if item["severity"] == "critical")
        warning_count = sum(1 for item in issues if item["severity"] == "warning")
        status = "blocked" if critical_count else ("warnings" if warning_count else "ok")
        report = {
            "project_id": project["id"],
            "status": status,
            "critical_count": critical_count,
            "warning_count": warning_count,
            "issues": issues,
            "checked_at": utc_now_iso(),
        }
        self._save_report(report)
        return report

    def _save_report(self, report: dict[str, Any]) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO compatibility_reports (
                    id, project_id, status, critical_count, warning_count, report_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    report["project_id"],
                    report["status"],
                    report["critical_count"],
                    report["warning_count"],
                    json.dumps(report),
                    report["checked_at"],
                ),
            )

    @staticmethod
    def _add(issues: list[dict[str, Any]], severity: str, code: str, message: str, target: str) -> None:
        issues.append({"severity": severity, "code": code, "message": message, "target": target})

    def _check_project(self, project: dict[str, Any], issues: list[dict[str, Any]]) -> None:
        if not str(project.get("name") or "").strip():
            self._add(issues, "critical", "project_name_missing", "Project name is required.", "project.name")
        if not str(project.get("scenario_text") or "").strip():
            self._add(issues, "warning", "scenario_empty", "Scenario text is empty.", "project.scenario_text")
        token_budget = int(project.get("lorebook_token_budget") or 0)
        if token_budget < 128:
            self._add(issues, "warning", "lorebook_budget_low", "Lorebook token budget is very low.", "project.lorebook_token_budget")

    def _check_character(self, character: dict[str, Any], issues: list[dict[str, Any]]) -> None:
        target = f"characters.{character.get('id', 'unknown')}"
        if not str(character.get("name") or "").strip():
            self._add(issues, "critical", "character_name_missing", "Character card needs a name.", target)
        if not str(character.get("description") or "").strip():
            self._add(issues, "warning", "character_description_empty", "Character description is empty.", target)
        if not str(character.get("first_message") or "").strip():
            self._add(issues, "warning", "first_message_empty", "First message strongly affects character style.", target)
        self._check_macros(character.get("scenario", ""), issues, f"{target}.scenario")
        self._check_macros(character.get("first_message", ""), issues, f"{target}.first_message")

    def _check_lore(self, entry: dict[str, Any], project: dict[str, Any], issues: list[dict[str, Any]]) -> None:
        target = f"lore_entries.{entry.get('id', 'unknown')}"
        if not entry.get("keys"):
            self._add(issues, "warning", "lore_keys_empty", "Lorebook entry has no activation keys.", target)
        if not str(entry.get("content") or "").strip():
            self._add(issues, "critical", "lore_content_empty", "Lorebook entry content is empty.", target)
        if int(entry.get("insertion_order") or 0) < 0:
            self._add(issues, "warning", "lore_order_negative", "Insertion order should be non-negative.", target)
        if entry.get("position") not in {"before_char", "after_char", "before_examples", "after_examples"}:
            self._add(issues, "warning", "lore_position_unknown", "Lorebook position may not import as expected.", target)

    def _check_user_profile(self, profile: dict[str, Any], issues: list[dict[str, Any]]) -> None:
        if not str(profile.get("name") or "").strip():
            self._add(issues, "warning", "persona_name_empty", "Persona has no display name.", "user_profile.name")
        depth = int(profile.get("persona_note_depth") or 0)
        if depth < 0:
            self._add(issues, "warning", "persona_depth_invalid", "Persona note depth should be non-negative.", "user_profile.persona_note_depth")

    def _check_gm_card(self, project: dict[str, Any], issues: list[dict[str, Any]]) -> None:
        gm = project.get("gm_card_profile", {}) or {}
        user_name = str((project.get("user_profile") or {}).get("name") or "").strip().lower()
        gm_name = str(gm.get("name") or "").strip().lower()
        if user_name and gm_name and user_name == gm_name:
            self._add(issues, "critical", "gm_user_role_conflict", "GM card name matches the user persona name.", "gm_card.name")
        if not str(gm.get("first_message") or "").strip():
            self._add(issues, "warning", "gm_first_message_empty", "GM card first message is empty.", "gm_card.first_message")

    def _check_macros(self, text: Any, issues: list[dict[str, Any]], target: str) -> None:
        value = str(text or "")
        for macro in re.findall(r"\{\{([^}]+)\}\}", value):
            if macro not in {"user", "char"} and not macro.startswith("random:"):
                self._add(issues, "warning", "unknown_macro", f"Unknown or custom macro '{{{{{macro}}}}}' should be verified.", target)
