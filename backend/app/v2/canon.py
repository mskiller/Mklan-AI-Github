from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class CanonExportRequest(BaseModel):
    project_id: str | None = None
    include_movie: bool = True
    include_cards: bool = True
    include_shared_vault: bool = True


router = APIRouter(prefix="/canon", tags=["v2-canon"])


def _data_root(request: Request) -> Path:
    return getattr(request.app.state, "data_root", Path(os.getenv("STUDIO_DATA_ROOT", "data")))


def _movie_db_path(request: Request) -> Path:
    return Path(os.getenv("MOVIE_DB", str(_data_root(request) / "movie" / "movie_tool.db")))


def _cards_db_path(request: Request) -> Path:
    return Path(os.getenv("CARDS_DB", str(_data_root(request) / "cards" / "card_creator.db")))


def _connect(path: Path) -> sqlite3.Connection | None:
    if not path.exists():
        return None
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _query_all(path: Path, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    conn = _connect(path)
    if conn is None:
        return []
    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def _movie_entities(path: Path, project_id: str | None) -> dict[str, list[dict[str, Any]]]:
    project_filter = "WHERE pc.project_id = ?" if project_id else ""
    params = (project_id,) if project_id else ()
    characters = [
        {
            "id": row["id"],
            "module": "movie",
            "project_id": row["project_id"],
            "name": row["name"],
            "role_summary": row["role_summary"],
            "prompt_tags": [tag.strip() for tag in str(row["prompt_tags"] or "").split(",") if tag.strip()],
            "portrait": row["portrait_image_url"],
        }
        for row in _query_all(
            path,
            f"""
            SELECT pc.id, pc.project_id, pc.name, pc.role_summary, pc.prompt_tags, pc.portrait_image_url
              FROM project_characters pc
              {project_filter}
             ORDER BY pc.project_id, pc.order_index
            """,
            params,
        )
    ]
    scenes = [
        {
            "id": row["id"],
            "module": "movie",
            "project_id": row["project_id"],
            "type": "scene",
            "name": row["title"],
            "summary": row["narrative_text"],
            "prompt": row["first_image_prompt_text"],
        }
        for row in _query_all(
            path,
            "SELECT id, project_id, title, narrative_text, first_image_prompt_text FROM story_scenes "
            + ("WHERE project_id = ? " if project_id else "")
            + "ORDER BY project_id, order_index",
            params,
        )
    ]
    return {"characters": characters, "lore": scenes}


def _cards_entities(path: Path, project_id: str | None, include_shared_vault: bool) -> dict[str, list[dict[str, Any]]]:
    params = (project_id,) if project_id else ()
    character_filter = "WHERE project_id = ?" if project_id else ""
    characters = [
        {
            "id": row["id"],
            "module": "cards",
            "project_id": row["project_id"],
            "name": row["name"],
            "description": row["description"],
            "personality": row["personality"],
            "role_summary": row["scenario"],
            "prompt_tags": _json_loads(row["tags_json"], []),
            "portrait": row["avatar_relative_path"] or row["portrait_relative_path"],
        }
        for row in _query_all(
            path,
            f"""
            SELECT id, project_id, name, description, personality, scenario, tags_json,
                   avatar_relative_path, portrait_relative_path
              FROM characters
              {character_filter}
             ORDER BY project_id, created_at
            """,
            params,
        )
    ]
    lore = [
        {
            "id": row["id"],
            "module": "cards",
            "project_id": row["project_id"],
            "name": row["name"],
            "keys": _json_loads(row["keys_json"], []),
            "content": row["content"],
            "image": row["image_relative_path"],
        }
        for row in _query_all(
            path,
            "SELECT id, project_id, name, keys_json, content, image_relative_path FROM lore_entries "
            + ("WHERE project_id = ? " if project_id else "")
            + "ORDER BY project_id, insertion_order, created_at",
            params,
        )
    ]
    if include_shared_vault:
        characters.extend(
            {
                "id": row["id"],
                "module": "shared_vault",
                "project_id": None,
                "name": row["name"],
                "description": row["description"],
                "personality": row["personality"],
                "role_summary": row["role_summary"],
                "prompt_tags": _json_loads(row["prompt_tags_json"], []),
                "portrait": row["avatar_path"],
            }
            for row in _query_all(
                path,
                "SELECT id, name, description, personality, role_summary, prompt_tags_json, avatar_path FROM shared_character_vault ORDER BY updated_at DESC",
            )
        )
        lore.extend(
            {
                "id": row["id"],
                "module": "shared_vault",
                "project_id": None,
                "name": row["name"],
                "keys": _json_loads(row["keys_json"], []),
                "content": row["content"],
                "image": None,
            }
            for row in _query_all(path, "SELECT id, name, keys_json, content FROM shared_lore_vault ORDER BY updated_at DESC")
        )
    return {"characters": characters, "lore": lore}


def _build_canon_pack(request: Request, payload: CanonExportRequest) -> dict[str, Any]:
    characters: list[dict[str, Any]] = []
    lore: list[dict[str, Any]] = []
    if payload.include_movie:
        movie = _movie_entities(_movie_db_path(request), payload.project_id)
        characters.extend(movie["characters"])
        lore.extend(movie["lore"])
    if payload.include_cards:
        cards = _cards_entities(_cards_db_path(request), payload.project_id, payload.include_shared_vault)
        characters.extend(cards["characters"])
        lore.extend(cards["lore"])
    return {
        "version": "v2-canon-pack",
        "created_at": utc_now_iso(),
        "project_id": payload.project_id,
        "entities": {
            "characters": characters,
            "lore": lore,
            "locations": [],
            "style_bible": [],
            "negative_constraints": [],
        },
        "summary": {
            "characters": len(characters),
            "lore": len(lore),
        },
    }


@router.get("/entities")
def get_canon_entities(request: Request, project_id: str | None = None) -> dict[str, Any]:
    return _build_canon_pack(request, CanonExportRequest(project_id=project_id))


@router.post("/export-pack")
def export_canon_pack(payload: CanonExportRequest, request: Request) -> dict[str, Any]:
    pack = _build_canon_pack(request, payload)
    audit = getattr(request.app.state, "v2_audit", None)
    if audit is not None:
        audit.record("canon.export_pack", target=payload.project_id or "all", payload=pack["summary"])
    return pack

