from __future__ import annotations

import json
import uuid
from typing import Any

from ..database import Database, utc_now_iso


def _loads(value: Any, default: Any) -> Any:
    if value is None:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


class SharedVaultService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_characters(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM shared_character_vault ORDER BY updated_at DESC, name ASC"
            ).fetchall()
        return [self._character_from_row(row) for row in rows]

    def list_lore(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM shared_lore_vault ORDER BY updated_at DESC, name ASC"
            ).fetchall()
        return [self._lore_from_row(row) for row in rows]

    def upsert_character(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = utc_now_iso()
        source_module = str(payload.get("source_module") or "cards")
        source_id = str(payload.get("source_id") or payload.get("id") or uuid.uuid4())
        with self.database.connect() as connection:
            existing = connection.execute(
                "SELECT id, created_at FROM shared_character_vault WHERE source_module = ? AND source_id = ?",
                (source_module, source_id),
            ).fetchone()
            vault_id = existing["id"] if existing else str(uuid.uuid4())
            created_at = existing["created_at"] if existing else now
            connection.execute(
                """
                INSERT OR REPLACE INTO shared_character_vault (
                    id, source_module, source_id, name, description, personality, role_summary,
                    prompt_tags_json, avatar_path, source_metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    vault_id,
                    source_module,
                    source_id,
                    str(payload.get("name") or "Unnamed Character"),
                    str(payload.get("description") or ""),
                    str(payload.get("personality") or ""),
                    str(payload.get("role_summary") or payload.get("scenario") or ""),
                    json.dumps(payload.get("prompt_tags") or payload.get("tags") or []),
                    payload.get("avatar_path") or payload.get("avatar_url"),
                    json.dumps(payload.get("source_metadata") or {}),
                    created_at,
                    now,
                ),
            )
        return self.get_character(vault_id)

    def upsert_lore(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = utc_now_iso()
        source_module = str(payload.get("source_module") or "cards")
        source_id = str(payload.get("source_id") or payload.get("id") or uuid.uuid4())
        with self.database.connect() as connection:
            existing = connection.execute(
                "SELECT id, created_at FROM shared_lore_vault WHERE source_module = ? AND source_id = ?",
                (source_module, source_id),
            ).fetchone()
            vault_id = existing["id"] if existing else str(uuid.uuid4())
            created_at = existing["created_at"] if existing else now
            connection.execute(
                """
                INSERT OR REPLACE INTO shared_lore_vault (
                    id, source_module, source_id, name, keys_json, content,
                    source_metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    vault_id,
                    source_module,
                    source_id,
                    str(payload.get("name") or "Unnamed Lore"),
                    json.dumps(payload.get("keys") or []),
                    str(payload.get("content") or ""),
                    json.dumps(payload.get("source_metadata") or {}),
                    created_at,
                    now,
                ),
            )
        return self.get_lore(vault_id)

    def get_character(self, vault_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM shared_character_vault WHERE id = ?", (vault_id,)).fetchone()
        if row is None:
            raise KeyError(vault_id)
        return self._character_from_row(row)

    def get_lore(self, vault_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM shared_lore_vault WHERE id = ?", (vault_id,)).fetchone()
        if row is None:
            raise KeyError(vault_id)
        return self._lore_from_row(row)

    @staticmethod
    def _character_from_row(row: Any) -> dict[str, Any]:
        return {
            "id": row["id"],
            "source_module": row["source_module"],
            "source_id": row["source_id"],
            "name": row["name"],
            "description": row["description"],
            "personality": row["personality"],
            "role_summary": row["role_summary"],
            "prompt_tags": _loads(row["prompt_tags_json"], []),
            "avatar_path": row["avatar_path"],
            "source_metadata": _loads(row["source_metadata_json"], {}),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _lore_from_row(row: Any) -> dict[str, Any]:
        return {
            "id": row["id"],
            "source_module": row["source_module"],
            "source_id": row["source_id"],
            "name": row["name"],
            "keys": _loads(row["keys_json"], []),
            "content": row["content"],
            "source_metadata": _loads(row["source_metadata_json"], {}),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
