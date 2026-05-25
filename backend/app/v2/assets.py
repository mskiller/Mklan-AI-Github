from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sqlite3
from typing import Any
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
import requests


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


class GeneratedAssetIngestRequest(BaseModel):
    file: str | None = None
    url: str | None = None
    source_module: str = Field(default="studio", max_length=80)
    source_id: str | None = Field(default=None, max_length=160)
    kind: str = Field(default="image", max_length=40)
    metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)


class AssetRead(BaseModel):
    id: str
    url: str
    path: str
    kind: str
    source_module: str
    source_id: str | None = None
    metadata: dict[str, Any]
    provenance: dict[str, Any]
    media_indexer_status: str
    created_at: str
    updated_at: str


class AssetSearchResponse(BaseModel):
    canonical: str
    query: str
    media_indexer: dict[str, Any]
    assets: list[AssetRead]


class MediaIndexerSyncRequest(BaseModel):
    scan_mode: str = Field(default="metadata", pattern="^(none|basic|metadata|ai)$")
    path_filter: str | None = Field(default=None, max_length=500)


class MediaIndexerSyncResponse(BaseModel):
    ok: bool
    status: str
    base_url: str | None = None
    source: dict[str, Any] | None = None
    scan_job: dict[str, Any] | None = None
    error: str | None = None


class AssetRegistry:
    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root
        self.generated_root = data_root / "generated"
        self.db_path = data_root / "platform_assets.db"

    def initialize(self) -> None:
        self.generated_root.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS assets (
                    id TEXT PRIMARY KEY,
                    path TEXT NOT NULL UNIQUE,
                    url TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    source_module TEXT NOT NULL,
                    source_id TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    provenance_json TEXT NOT NULL DEFAULT '{}',
                    media_indexer_status TEXT NOT NULL DEFAULT 'registered',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_platform_assets_source ON assets(source_module, source_id);
                CREATE INDEX IF NOT EXISTS idx_platform_assets_kind_created ON assets(kind, created_at DESC);
                """
            )
            conn.commit()

    def ingest_generated(self, payload: GeneratedAssetIngestRequest) -> dict[str, Any]:
        path, url = self._resolve_generated_path(payload.file, payload.url)
        metadata = dict(payload.metadata)
        metadata_path = path.with_suffix(".json")
        if metadata_path.exists():
            try:
                metadata = {**_json_loads(metadata_path.read_text(encoding="utf-8"), {}), **metadata}
            except OSError:
                pass
        provenance = {
            "canonical_target": "media-indexer",
            "ingested_from": "generated",
            **payload.provenance,
        }
        asset_id = uuid.uuid4().hex
        now = utc_now_iso()
        with self._connect() as conn:
            existing = conn.execute("SELECT * FROM assets WHERE path = ?", (str(path),)).fetchone()
            if existing is not None:
                conn.execute(
                    """
                    UPDATE assets
                       SET source_module = ?,
                           source_id = ?,
                           kind = ?,
                           metadata_json = ?,
                           provenance_json = ?,
                           media_indexer_status = ?,
                           updated_at = ?
                     WHERE id = ?
                    """,
                    (
                        payload.source_module,
                        payload.source_id,
                        payload.kind,
                        _json_dumps(metadata),
                        _json_dumps(provenance),
                        "registered",
                        now,
                        existing["id"],
                    ),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM assets WHERE id = ?", (existing["id"],)).fetchone()
                asset = self._asset_from_row(row)
                self._maybe_sync_generated_with_media_indexer(asset, path.name)
                return asset
            conn.execute(
                """
                INSERT INTO assets (
                    id, path, url, kind, source_module, source_id, metadata_json,
                    provenance_json, media_indexer_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'registered', ?, ?)
                """,
                (
                    asset_id,
                    str(path),
                    url,
                    payload.kind,
                    payload.source_module,
                    payload.source_id,
                    _json_dumps(metadata),
                    _json_dumps(provenance),
                    now,
                    now,
                ),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
        asset = self._asset_from_row(row)
        self._maybe_sync_generated_with_media_indexer(asset, path.name)
        return asset

    def get_asset(self, asset_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Asset provenance was not found.")
        return self._asset_from_row(row)

    def search_local(self, query: str, *, limit: int = 40) -> list[dict[str, Any]]:
        query_text = query.strip().lower()
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM assets ORDER BY created_at DESC LIMIT ?", (max(limit, 1),)).fetchall()
        assets = [self._asset_from_row(row) for row in rows]
        if not query_text:
            return assets[:limit]
        matched = []
        for asset in assets:
            haystack = " ".join(
                [
                    asset["url"],
                    asset["source_module"],
                    json.dumps(asset["metadata"], ensure_ascii=False),
                    json.dumps(asset["provenance"], ensure_ascii=False),
                ]
            ).lower()
            if query_text in haystack:
                matched.append(asset)
        if matched:
            return matched[:limit]
        return self._search_generated_files(query_text, limit=limit)

    def _search_generated_files(self, query_text: str, *, limit: int) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        for image_path in sorted(self.generated_root.glob("*"), key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True):
            if image_path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
                continue
            metadata = {}
            metadata_path = image_path.with_suffix(".json")
            if metadata_path.exists():
                try:
                    metadata = _json_loads(metadata_path.read_text(encoding="utf-8"), {})
                except OSError:
                    metadata = {}
            haystack = f"{image_path.name} {json.dumps(metadata, ensure_ascii=False)}".lower()
            if query_text and query_text not in haystack:
                continue
            stat = image_path.stat()
            matches.append(
                {
                    "id": f"generated:{image_path.stem}",
                    "path": str(image_path),
                    "url": f"/generated/{image_path.name}",
                    "kind": "image",
                    "source_module": "generated",
                    "source_id": image_path.stem,
                    "metadata": metadata,
                    "provenance": {"canonical_target": "media-indexer", "ingested_from": "generated-scan"},
                    "media_indexer_status": "not_registered",
                    "created_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
                    "updated_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
                }
            )
            if len(matches) >= limit:
                break
        return matches

    def search_media_indexer(self, query: str, *, limit: int = 40) -> dict[str, Any]:
        base_url = self._media_indexer_base_url()
        if not base_url:
            return {"ok": False, "status": "disabled", "items": []}
        try:
            endpoint = "/search/nl" if query.strip() else "/assets"
            params = {"q": query, "limit": limit} if query.strip() else {"page_size": limit, "sort": "modified_at"}
            response = requests.get(f"{base_url}{endpoint}", params=params, timeout=self._media_indexer_timeout_s())
            response.raise_for_status()
            data = response.json()
            items = data.get("items") if isinstance(data, dict) else data
            return {"ok": True, "status": "available", "base_url": base_url, "items": items or []}
        except Exception as exc:
            return {"ok": False, "status": "unavailable", "base_url": base_url, "error": str(exc), "items": []}

    def sync_generated_source(self, *, scan_mode: str = "metadata", path_filter: str | None = None) -> dict[str, Any]:
        base_url = self._media_indexer_base_url()
        if not base_url:
            return {"ok": False, "status": "disabled", "error": "MEDIA_INDEXER_INTERNAL_URL is not configured."}

        try:
            source = self._ensure_media_indexer_generated_source(base_url)
            if scan_mode == "none":
                return {"ok": True, "status": "source_ready", "base_url": base_url, "source": source}

            payload: dict[str, Any] = {"scan_mode": scan_mode}
            if path_filter:
                payload["path_filter"] = path_filter.replace("\\", "/").strip().strip("/")
            response = requests.post(
                f"{base_url}/sources/{source['id']}/scan",
                json=payload,
                timeout=self._media_indexer_timeout_s(),
            )
            response.raise_for_status()
            return {
                "ok": True,
                "status": "scan_queued",
                "base_url": base_url,
                "source": source,
                "scan_job": response.json(),
            }
        except Exception as exc:
            return {"ok": False, "status": "unavailable", "base_url": base_url, "error": str(exc)}

    def _maybe_sync_generated_with_media_indexer(self, asset: dict[str, Any], filename: str) -> None:
        if not self._auto_sync_enabled():
            return
        scan_mode = os.getenv("MEDIA_INDEXER_AUTO_SCAN_MODE", "metadata").strip().lower() or "metadata"
        if scan_mode not in {"none", "basic", "metadata", "ai"}:
            scan_mode = "metadata"
        result = self.sync_generated_source(scan_mode=scan_mode, path_filter=filename if scan_mode != "none" else None)
        status = result.get("status") if result.get("ok") else f"sync_failed:{result.get('status', 'unavailable')}"
        with self._connect() as conn:
            conn.execute(
                "UPDATE assets SET media_indexer_status = ?, updated_at = ? WHERE id = ?",
                (str(status), utc_now_iso(), asset["id"]),
            )
            conn.commit()
        asset["media_indexer_status"] = str(status)

    def _ensure_media_indexer_generated_source(self, base_url: str) -> dict[str, Any]:
        source_name = os.getenv("MEDIA_INDEXER_GENERATED_SOURCE_NAME", "Mklan Studio Generated")
        source_root = os.getenv("MEDIA_INDEXER_GENERATED_SOURCE_ROOT", "/data/sources/generated")
        response = requests.get(f"{base_url}/sources", timeout=self._media_indexer_timeout_s())
        response.raise_for_status()
        sources = response.json()
        if isinstance(sources, list):
            for source in sources:
                if not isinstance(source, dict):
                    continue
                if source.get("root_path") == source_root or source.get("name") == source_name:
                    return source

        create_response = requests.post(
            f"{base_url}/sources",
            json={"name": source_name, "root_path": source_root, "type": "mounted_fs"},
            timeout=self._media_indexer_timeout_s(),
        )
        if create_response.status_code == 409:
            response = requests.get(f"{base_url}/sources", timeout=self._media_indexer_timeout_s())
            response.raise_for_status()
            for source in response.json():
                if isinstance(source, dict) and (source.get("root_path") == source_root or source.get("name") == source_name):
                    return source
        create_response.raise_for_status()
        return create_response.json()

    @staticmethod
    def _auto_sync_enabled() -> bool:
        raw = os.getenv("MEDIA_INDEXER_AUTO_SYNC_GENERATED")
        if raw is not None:
            return raw.strip().lower() in {"1", "true", "yes", "on"}
        return os.getenv("ENVIRONMENT") == "production" or Path("/.dockerenv").exists()

    @staticmethod
    def _media_indexer_base_url() -> str:
        return os.getenv("MEDIA_INDEXER_INTERNAL_URL", "http://media_indexer_backend:8000").rstrip("/")

    @staticmethod
    def _media_indexer_timeout_s() -> float:
        return float(os.getenv("MEDIA_INDEXER_TIMEOUT_S", "3"))

    def _resolve_generated_path(self, file_value: str | None, url_value: str | None) -> tuple[Path, str]:
        raw = (file_value or url_value or "").strip()
        if not raw:
            raise HTTPException(status_code=400, detail="Provide a generated file or URL.")
        if raw.startswith("/generated/"):
            filename = raw.split("/generated/", 1)[1]
        elif raw.startswith("generated/"):
            filename = raw.split("generated/", 1)[1]
        else:
            filename = raw
        if "/" in filename or "\\" in filename or filename in {"", ".", ".."}:
            raise HTTPException(status_code=400, detail="Generated asset filename is invalid.")
        path = (self.generated_root / filename).resolve(strict=False)
        root = self.generated_root.resolve(strict=False)
        if root not in path.parents:
            raise HTTPException(status_code=400, detail="Generated asset path is outside the generated directory.")
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="Generated asset file was not found.")
        return path, f"/generated/{path.name}"

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _asset_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "path": row["path"],
            "url": row["url"],
            "kind": row["kind"],
            "source_module": row["source_module"],
            "source_id": row["source_id"],
            "metadata": _json_loads(row["metadata_json"], {}),
            "provenance": _json_loads(row["provenance_json"], {}),
            "media_indexer_status": row["media_indexer_status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


router = APIRouter(prefix="/assets", tags=["v2-assets"])


def get_registry(request: Request) -> AssetRegistry:
    registry = getattr(request.app.state, "v2_assets", None)
    if registry is None:
        raise HTTPException(status_code=503, detail="V2 asset registry is not available.")
    return registry


@router.post("/ingest-generated", response_model=AssetRead)
def ingest_generated(payload: GeneratedAssetIngestRequest, request: Request) -> AssetRead:
    asset = get_registry(request).ingest_generated(payload)
    audit = getattr(request.app.state, "v2_audit", None)
    if audit is not None:
        audit.record("assets.ingest_generated", target=asset["id"], payload={"url": asset["url"], "source_module": asset["source_module"]})
    return AssetRead.model_validate(asset)


@router.get("/search", response_model=AssetSearchResponse)
def search_assets(request: Request, q: str = "", limit: int = 40) -> AssetSearchResponse:
    registry = get_registry(request)
    media_indexer = registry.search_media_indexer(q, limit=limit)
    local_assets = registry.search_local(q, limit=limit)
    return AssetSearchResponse(
        canonical="media-indexer",
        query=q,
        media_indexer=media_indexer,
        assets=[AssetRead.model_validate(asset) for asset in local_assets],
    )


@router.post("/sync-media-indexer", response_model=MediaIndexerSyncResponse)
def sync_media_indexer(payload: MediaIndexerSyncRequest, request: Request) -> MediaIndexerSyncResponse:
    registry = get_registry(request)
    result = registry.sync_generated_source(scan_mode=payload.scan_mode, path_filter=payload.path_filter)
    audit = getattr(request.app.state, "v2_audit", None)
    if audit is not None:
        audit.record("assets.sync_media_indexer", payload={"status": result.get("status"), "scan_mode": payload.scan_mode})
    return MediaIndexerSyncResponse.model_validate(result)


@router.get("/{asset_id}/provenance", response_model=AssetRead)
def get_asset_provenance(asset_id: str, request: Request) -> AssetRead:
    return AssetRead.model_validate(get_registry(request).get_asset(asset_id))
