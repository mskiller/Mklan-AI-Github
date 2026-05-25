from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

import requests

from ..config import Settings
from .card_exports import (
    build_bundle_export,
    build_character_card_payload,
    build_gm_card_payload,
    build_lorebook_export,
    build_persona_card_payload,
    build_persona_export,
    write_card_image_file,
)


DEFAULT_USER_HANDLE = "default-user"


class SillyTavernBridgeError(RuntimeError):
    pass


class SillyTavernBridge:
    def __init__(self, settings: Settings):
        self.settings = settings

    def status(self) -> dict[str, Any]:
        warnings: list[str] = []
        healthy = False
        if not self.settings.sillytavern_enabled:
            warnings.append("SillyTavern integration is disabled.")
        if not self.settings.sillytavern_data_root.exists():
            warnings.append(f"SillyTavern data root is not mounted: {self.settings.sillytavern_data_root}")
        if self.settings.sillytavern_enabled:
            probe_warnings: list[str] = []
            for label, url in _status_probe_urls(
                internal_url=self.settings.sillytavern_internal_url,
                public_url=self.settings.sillytavern_public_url,
            ):
                try:
                    response = requests.get(url, timeout=2)
                    if response.status_code < 500:
                        healthy = True
                        if label == "public":
                            warnings.append(
                                "SillyTavern internal Docker URL is not reachable from this backend; using the public URL."
                            )
                        break
                    probe_warnings.append(f"{label} URL returned HTTP {response.status_code}: {url}")
                except requests.RequestException as exc:
                    probe_warnings.append(f"{label} URL is not reachable: {exc}")
            if not healthy:
                warnings.extend(f"SillyTavern is not reachable yet: {item}" for item in probe_warnings)
        return {
            "enabled": self.settings.sillytavern_enabled,
            "healthy": healthy,
            "public_url": self.settings.sillytavern_public_url,
            "internal_url": self.settings.sillytavern_internal_url,
            "data_root": str(self.settings.sillytavern_data_root),
            "warnings": warnings,
        }

    def sync_project(self, *, repository: Any, project: dict) -> dict[str, Any]:
        if not self.settings.sillytavern_enabled:
            raise SillyTavernBridgeError("SillyTavern integration is disabled.")
        if not self.settings.sillytavern_data_root.exists():
            raise SillyTavernBridgeError(
                f"SillyTavern data root is not mounted: {self.settings.sillytavern_data_root}"
            )

        warnings: list[str] = []
        synced_files: list[dict[str, str]] = []
        user_root = self.settings.sillytavern_data_root / DEFAULT_USER_HANDLE
        characters_dir = user_root / "characters"
        worlds_dir = user_root / "worlds"
        stcc_files_dir = user_root / "user" / "files" / "stcc" / str(project["id"])
        for directory in (characters_dir, worlds_dir, stcc_files_dir):
            directory.mkdir(parents=True, exist_ok=True)

        project_root = repository.ensure_project_assets(project["id"])
        project_slug = _safe_stem(project.get("name") or "project")
        project_suffix = str(project["id"])[:8]

        if project.get("project_mode") == "game_master":
            gm_name = str(project.get("gm_card_profile", {}).get("name") or project["name"])
            gm_path = characters_dir / f"{project_slug}-gm-{project_suffix}.png"
            write_card_image_file(
                gm_path,
                project_root=project_root,
                payload=build_gm_card_payload(project),
                image_format="png",
                source_relative_paths=[project.get("scenario_image_relative_path")],
                placeholder_title=gm_name,
            )
            synced_files.append({"kind": "gm_card", "path": str(gm_path)})
        elif not project.get("characters"):
            warnings.append("No character cards were available to sync.")

        for character in project.get("characters", []):
            character_slug = _safe_stem(character.get("name") or "character")
            character_suffix = str(character["id"])[:8]
            character_path = characters_dir / f"{project_slug}-{character_slug}-{character_suffix}.png"
            write_card_image_file(
                character_path,
                project_root=project_root,
                payload=build_character_card_payload(project, character),
                image_format="png",
                source_relative_paths=[
                    character.get("avatar_relative_path"),
                    character.get("portrait_relative_path"),
                    character.get("cowboy_shot_relative_path"),
                    character.get("fullbody_shot_relative_path"),
                ],
                placeholder_title=str(character.get("name") or "Character"),
            )
            synced_files.append({"kind": "character_card", "path": str(character_path)})

        if not project.get("lore_entries"):
            warnings.append("No lore entries were available to sync.")
        lorebook_path = worlds_dir / f"{project_slug}-lorebook-{project_suffix}.json"
        _write_json(lorebook_path, build_lorebook_export(project))
        synced_files.append({"kind": "lorebook", "path": str(lorebook_path)})

        persona_path = stcc_files_dir / "persona.json"
        _write_json(persona_path, build_persona_export(project, avatar_url=None))
        synced_files.append({"kind": "persona_bundle", "path": str(persona_path)})

        persona_card_path = stcc_files_dir / "persona-card.json"
        _write_json(persona_card_path, build_persona_card_payload(project))
        synced_files.append({"kind": "persona_card_json", "path": str(persona_card_path)})

        bundle_path = stcc_files_dir / "bundle.json"
        _write_json(bundle_path, build_bundle_export(project, avatar_url=None))
        synced_files.append({"kind": "project_bundle", "path": str(bundle_path)})

        return {
            "project_id": project["id"],
            "public_url": self.settings.sillytavern_public_url,
            "synced_files": synced_files,
            "warnings": warnings,
        }


def _safe_stem(value: str) -> str:
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip()).strip("-")
    return stem[:80] or "export"


def _status_probe_urls(*, internal_url: str, public_url: str) -> list[tuple[str, str]]:
    urls: list[tuple[str, str]] = []
    normalized_internal = str(internal_url or "").strip()
    normalized_public = str(public_url or "").strip()
    if normalized_internal:
        urls.append(("internal", normalized_internal))
    if normalized_public and normalized_public != normalized_internal:
        urls.append(("public", normalized_public))
    return urls


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
