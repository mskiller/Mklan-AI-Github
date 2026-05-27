from __future__ import annotations

from datetime import UTC, datetime
import io
import json
from pathlib import Path
from pathlib import PurePosixPath
import re
from typing import Any
import uuid
import zipfile

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.v2.core_db import connect_core_db, core_db_enabled, default_data_root, initialize_core_db


DEFAULT_WORKSPACE_ID = "default"


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def slugify(value: str, fallback: str = "workspace") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("-._").lower()
    return cleaned[:72] or fallback


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


def _json_loads(value: Any) -> Any:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    activate: bool = True
    settings: dict[str, Any] = Field(default_factory=dict)


class WorkspaceUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    settings: dict[str, Any] | None = None


class WorkspaceRead(BaseModel):
    id: str
    name: str
    description: str = ""
    active: bool = False
    settings: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class WorkspaceListResponse(BaseModel):
    active_workspace_id: str
    workspaces: list[WorkspaceRead]


class WorkspaceImportResponse(BaseModel):
    workspace: WorkspaceRead
    mode: str
    remapped_from: str | None = None
    imported_assets: int = 0
    copied_files: int = 0
    imported_workflows: int = 0


class WorkspaceStore:
    def __init__(self, data_root: Path | None = None) -> None:
        self.data_root = data_root or default_data_root()
        self.path = self.data_root / "platform_workspaces.json"

    @property
    def storage_backend(self) -> str:
        return "postgres" if core_db_enabled() else "json"

    def initialize(self) -> None:
        if self.storage_backend == "postgres":
            initialize_core_db()
            return
        payload = self._load_json()
        self._write_json(payload)

    def list_workspaces(self) -> list[dict[str, Any]]:
        self.initialize()
        if self.storage_backend == "postgres":
            with connect_core_db() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT * FROM platform_workspaces ORDER BY active DESC, updated_at DESC, name ASC")
                    return [self._workspace_from_row(row) for row in cursor.fetchall()]
        payload = self._load_json()
        active_id = payload["active_workspace_id"]
        return sorted(
            [{**item, "active": item["id"] == active_id} for item in payload["workspaces"]],
            key=lambda item: (not item.get("active", False), str(item.get("updated_at") or ""), str(item.get("name") or "")),
        )

    def active_workspace_id(self) -> str:
        self.initialize()
        if self.storage_backend == "postgres":
            with connect_core_db() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT id FROM platform_workspaces WHERE active = TRUE ORDER BY updated_at DESC LIMIT 1")
                    row = cursor.fetchone()
            return str(row["id"]) if row else DEFAULT_WORKSPACE_ID
        return str(self._load_json()["active_workspace_id"])

    def create_workspace(self, payload: WorkspaceCreateRequest) -> dict[str, Any]:
        self.initialize()
        now = utc_now_iso()
        workspace_id = f"{slugify(payload.name)}-{uuid.uuid4().hex[:8]}"
        workspace = {
            "id": workspace_id,
            "name": payload.name.strip(),
            "description": payload.description.strip(),
            "active": bool(payload.activate),
            "settings": payload.settings,
            "created_at": now,
            "updated_at": now,
        }
        if self.storage_backend == "postgres":
            with connect_core_db() as conn:
                with conn.cursor() as cursor:
                    if payload.activate:
                        cursor.execute("UPDATE platform_workspaces SET active = FALSE")
                    cursor.execute(
                        """
                        INSERT INTO platform_workspaces (id, name, description, active, settings_json, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
                        """,
                        (
                            workspace["id"],
                            workspace["name"],
                            workspace["description"],
                            workspace["active"],
                            _json_dumps(workspace["settings"]),
                            workspace["created_at"],
                            workspace["updated_at"],
                        ),
                    )
                conn.commit()
            return self.get_workspace(workspace_id)

        state = self._load_json()
        if payload.activate:
            state["active_workspace_id"] = workspace_id
        state["workspaces"].append(workspace)
        self._write_json(state)
        return workspace

    def get_workspace(self, workspace_id: str) -> dict[str, Any]:
        self.initialize()
        if self.storage_backend == "postgres":
            with connect_core_db() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT * FROM platform_workspaces WHERE id = %s", (workspace_id,))
                    row = cursor.fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="Workspace not found.")
            return self._workspace_from_row(row)
        for item in self._load_json()["workspaces"]:
            if item["id"] == workspace_id:
                return {**item, "active": item["id"] == self.active_workspace_id()}
        raise HTTPException(status_code=404, detail="Workspace not found.")

    def update_workspace(self, workspace_id: str, payload: WorkspaceUpdateRequest) -> dict[str, Any]:
        if workspace_id == DEFAULT_WORKSPACE_ID and payload.name is not None and not payload.name.strip():
            raise HTTPException(status_code=400, detail="Default workspace needs a name.")
        now = utc_now_iso()
        if self.storage_backend == "postgres":
            current = self.get_workspace(workspace_id)
            next_name = payload.name.strip() if payload.name is not None else current["name"]
            next_description = payload.description.strip() if payload.description is not None else current["description"]
            next_settings = payload.settings if payload.settings is not None else current["settings"]
            with connect_core_db() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE platform_workspaces
                           SET name = %s,
                               description = %s,
                               settings_json = %s::jsonb,
                               updated_at = %s
                         WHERE id = %s
                        """,
                        (next_name, next_description, _json_dumps(next_settings), now, workspace_id),
                    )
                conn.commit()
            return self.get_workspace(workspace_id)

        state = self._load_json()
        for item in state["workspaces"]:
            if item["id"] == workspace_id:
                if payload.name is not None:
                    item["name"] = payload.name.strip()
                if payload.description is not None:
                    item["description"] = payload.description.strip()
                if payload.settings is not None:
                    item["settings"] = payload.settings
                item["updated_at"] = now
                self._write_json(state)
                return {**item, "active": item["id"] == state["active_workspace_id"]}
        raise HTTPException(status_code=404, detail="Workspace not found.")

    def activate_workspace(self, workspace_id: str) -> dict[str, Any]:
        self.initialize()
        now = utc_now_iso()
        if self.storage_backend == "postgres":
            self.get_workspace(workspace_id)
            with connect_core_db() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("UPDATE platform_workspaces SET active = FALSE")
                    cursor.execute(
                        "UPDATE platform_workspaces SET active = TRUE, updated_at = %s WHERE id = %s",
                        (now, workspace_id),
                    )
                conn.commit()
            return self.get_workspace(workspace_id)
        state = self._load_json()
        if not any(item["id"] == workspace_id for item in state["workspaces"]):
            raise HTTPException(status_code=404, detail="Workspace not found.")
        state["active_workspace_id"] = workspace_id
        for item in state["workspaces"]:
            if item["id"] == workspace_id:
                item["updated_at"] = now
        self._write_json(state)
        return self.get_workspace(workspace_id)

    def _load_json(self) -> dict[str, Any]:
        now = utc_now_iso()
        default = {
            "active_workspace_id": DEFAULT_WORKSPACE_ID,
            "workspaces": [
                {
                    "id": DEFAULT_WORKSPACE_ID,
                    "name": "Default Workspace",
                    "description": "Shared local Studio workspace.",
                    "active": True,
                    "settings": {},
                    "created_at": now,
                    "updated_at": now,
                }
            ],
        }
        if not self.path.exists():
            return default
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return default
        workspaces = payload.get("workspaces") if isinstance(payload, dict) else None
        if not isinstance(workspaces, list) or not workspaces:
            return default
        active_id = str(payload.get("active_workspace_id") or DEFAULT_WORKSPACE_ID)
        if not any(isinstance(item, dict) and item.get("id") == DEFAULT_WORKSPACE_ID for item in workspaces):
            workspaces.insert(0, default["workspaces"][0])
        if not any(isinstance(item, dict) and item.get("id") == active_id for item in workspaces):
            active_id = DEFAULT_WORKSPACE_ID
        normalized = []
        for item in workspaces:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id") or "").strip()
            if not item_id:
                continue
            normalized.append(
                {
                    "id": item_id,
                    "name": str(item.get("name") or item_id).strip() or item_id,
                    "description": str(item.get("description") or ""),
                    "active": item_id == active_id,
                    "settings": item.get("settings") if isinstance(item.get("settings"), dict) else {},
                    "created_at": str(item.get("created_at") or now),
                    "updated_at": str(item.get("updated_at") or now),
                }
            )
        return {"active_workspace_id": active_id, "workspaces": normalized or default["workspaces"]}

    def _write_json(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        active_id = str(payload.get("active_workspace_id") or DEFAULT_WORKSPACE_ID)
        for item in payload.get("workspaces", []):
            if isinstance(item, dict):
                item["active"] = item.get("id") == active_id
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _workspace_from_row(row: Any) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"] or "",
            "active": bool(row["active"]),
            "settings": _json_loads(row["settings_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


def active_workspace_id(data_root: Path | None = None) -> str:
    try:
        return WorkspaceStore(data_root).active_workspace_id()
    except Exception:
        return DEFAULT_WORKSPACE_ID


router = APIRouter(prefix="/workspaces", tags=["v2-workspaces"])


def _store(request: Request) -> WorkspaceStore:
    data_root = getattr(request.app.state, "data_root", None)
    return WorkspaceStore(Path(data_root) if data_root else default_data_root())


def _data_root(request: Request) -> Path:
    data_root = getattr(request.app.state, "data_root", None)
    return Path(data_root) if data_root else default_data_root()


def _package_safe_path(value: str) -> PurePosixPath:
    normalized = value.replace("\\", "/").strip("/")
    path = PurePosixPath(normalized)
    if not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise HTTPException(status_code=400, detail="Workspace package contains an unsafe path.")
    return path


def _generated_relative_from_asset(asset: dict[str, Any], generated_root: Path) -> str | None:
    url = str(asset.get("url") or "").replace("\\", "/")
    if url.startswith("/generated/"):
        return url.split("/generated/", 1)[1].strip("/")
    path_value = str(asset.get("path") or "")
    if path_value:
        try:
            return Path(path_value).resolve(strict=False).relative_to(generated_root.resolve(strict=False)).as_posix()
        except ValueError:
            return None
    return None


def _workspace_package_bytes(request: Request, workspace_id: str) -> tuple[bytes, str]:
    data_root = _data_root(request)
    store = WorkspaceStore(data_root)
    workspace = store.get_workspace(workspace_id)
    generated_root = data_root / "generated"
    from app.v2.assets import AssetRegistry
    from app.v2.jobs import JobManager
    from app.v2.workflows import load_workflow_templates

    registry = AssetRegistry(data_root)
    registry.initialize()
    assets = registry.list_assets(workspace_id=workspace_id, limit=5000)
    manager = getattr(request.app.state, "v2_jobs", None)
    if manager is None:
        manager = JobManager(data_root)
        manager.initialize(mark_running_failed=False)
    jobs = manager.list_jobs(limit=500, workspace_id=workspace_id)
    workflows = load_workflow_templates()
    exported_files: list[dict[str, Any]] = []

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for asset in assets:
            relative = _generated_relative_from_asset(asset, generated_root)
            if not relative:
                continue
            try:
                safe_relative = _package_safe_path(relative)
            except HTTPException:
                continue
            source_path = (generated_root / Path(*safe_relative.parts)).resolve(strict=False)
            try:
                source_path.relative_to(generated_root.resolve(strict=False))
            except ValueError:
                continue
            if not source_path.exists() or not source_path.is_file():
                continue
            package_path = f"generated/{safe_relative.as_posix()}"
            archive.write(source_path, package_path)
            exported_files.append({"asset_id": asset["id"], "path": package_path, "size": source_path.stat().st_size})
            sidecar = source_path.with_suffix(".json")
            if sidecar.exists() and sidecar.is_file():
                archive.write(sidecar, f"generated/{safe_relative.with_suffix('.json').as_posix()}")

        manifest = {
            "format": "mklan.studio.workspace.zip",
            "version": 1,
            "exported_at": utc_now_iso(),
            "workspace_id": workspace_id,
            "workspace": workspace,
            "counts": {
                "assets": len(assets),
                "jobs": len(jobs),
                "workflow_templates": len(workflows),
                "files": len(exported_files),
            },
            "files": exported_files,
            "legacy_sqlite_included": False,
        }
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("workspace.json", json.dumps(workspace, ensure_ascii=False, indent=2))
        archive.writestr("platform/assets.json", json.dumps(assets, ensure_ascii=False, indent=2))
        archive.writestr("platform/jobs.json", json.dumps(jobs, ensure_ascii=False, indent=2))
        archive.writestr("workflows/templates.json", json.dumps(workflows, ensure_ascii=False, indent=2))

    filename = f"{slugify(workspace['name'], 'workspace')}-{workspace_id[:12]}.zip"
    return buffer.getvalue(), filename


def _package_asset_relative(asset: dict[str, Any]) -> str | None:
    url = str(asset.get("url") or "").replace("\\", "/")
    if url.startswith("/generated/"):
        return url.split("/generated/", 1)[1].strip("/")
    path = str(asset.get("path") or "").replace("\\", "/")
    marker = "/generated/"
    if marker in path:
        return path.split(marker, 1)[1].strip("/")
    return None


def _copy_generated_entry(archive: zipfile.ZipFile, entry_name: str, generated_root: Path) -> str:
    safe_relative = _package_safe_path(entry_name.removeprefix("generated/"))
    target = (generated_root / Path(*safe_relative.parts)).resolve(strict=False)
    root = generated_root.resolve(strict=False)
    if root != target and root not in target.parents:
        raise HTTPException(status_code=400, detail="Workspace package generated file escapes the generated root.")
    if target.exists():
        target = target.with_name(f"{target.stem}-import-{uuid.uuid4().hex[:8]}{target.suffix}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(archive.read(entry_name))
    return target.relative_to(root).as_posix()


def _import_workflows(data_root: Path, workflows: list[dict[str, Any]]) -> int:
    if not workflows:
        return 0
    root = data_root / "integrations" / "comfyui" / "workflow_templates"
    root.mkdir(parents=True, exist_ok=True)
    imported = 0
    for item in workflows:
        if not isinstance(item, dict):
            continue
        template_id = slugify(str(item.get("id") or item.get("label") or "imported-workflow"), "imported-workflow")
        target = root / f"{template_id}.json"
        if target.exists():
            target = root / f"{template_id}-import-{uuid.uuid4().hex[:8]}.json"
        target.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
        imported += 1
    return imported


@router.get("", response_model=WorkspaceListResponse)
def list_workspaces(request: Request) -> WorkspaceListResponse:
    store = _store(request)
    workspaces = [WorkspaceRead.model_validate(item) for item in store.list_workspaces()]
    active_id = next((item.id for item in workspaces if item.active), DEFAULT_WORKSPACE_ID)
    return WorkspaceListResponse(active_workspace_id=active_id, workspaces=workspaces)


@router.post("", response_model=WorkspaceRead, status_code=201)
def create_workspace(payload: WorkspaceCreateRequest, request: Request) -> WorkspaceRead:
    return WorkspaceRead.model_validate(_store(request).create_workspace(payload))


@router.get("/active", response_model=WorkspaceRead)
def get_active_workspace(request: Request) -> WorkspaceRead:
    store = _store(request)
    return WorkspaceRead.model_validate(store.get_workspace(store.active_workspace_id()))


@router.get("/{workspace_id}/export.zip")
def export_workspace_package(workspace_id: str, request: Request) -> Response:
    payload, filename = _workspace_package_bytes(request, workspace_id)
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import", response_model=WorkspaceImportResponse, status_code=201)
async def import_workspace_package(
    request: Request,
    file: UploadFile = File(...),
    mode: str = Form("create_new"),
    target_workspace_id: str | None = Form(default=None),
) -> WorkspaceImportResponse:
    raw_mode = mode.strip().lower() or "create_new"
    if raw_mode not in {"create_new", "merge"}:
        raise HTTPException(status_code=400, detail="Workspace import mode must be create_new or merge.")
    payload = await file.read()
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="Uploaded file is not a readable workspace zip.") from exc

    data_root = _data_root(request)
    generated_root = data_root / "generated"
    generated_root.mkdir(parents=True, exist_ok=True)
    store = WorkspaceStore(data_root)

    with archive:
        if "manifest.json" not in archive.namelist():
            raise HTTPException(status_code=400, detail="Workspace package is missing manifest.json.")
        try:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            workspace_meta = json.loads(archive.read("workspace.json").decode("utf-8")) if "workspace.json" in archive.namelist() else manifest.get("workspace") or {}
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail="Workspace package metadata is not readable.") from exc
        if manifest.get("format") != "mklan.studio.workspace.zip":
            raise HTTPException(status_code=400, detail="Workspace package format is not supported.")

        if raw_mode == "merge":
            workspace_id = target_workspace_id or store.active_workspace_id()
            workspace = store.activate_workspace(workspace_id)
            remapped_from = str(workspace_meta.get("id") or manifest.get("workspace_id") or "")
        else:
            imported_name = str(workspace_meta.get("name") or manifest.get("workspace_id") or "Imported Workspace")
            workspace = store.create_workspace(
                WorkspaceCreateRequest(
                    name=f"{imported_name} Import",
                    description=str(workspace_meta.get("description") or "Imported V2 workspace package."),
                    activate=True,
                    settings=workspace_meta.get("settings") if isinstance(workspace_meta.get("settings"), dict) else {},
                )
            )
            workspace_id = workspace["id"]
            remapped_from = str(workspace_meta.get("id") or manifest.get("workspace_id") or "") or None

        try:
            assets = json.loads(archive.read("platform/assets.json").decode("utf-8")) if "platform/assets.json" in archive.namelist() else []
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail="Workspace package asset metadata is not readable.") from exc
        assets = assets if isinstance(assets, list) else []
        entries = set(archive.namelist())

        from app.v2.assets import AssetRegistry, GeneratedAssetIngestRequest

        registry = AssetRegistry(data_root)
        registry.initialize()
        imported_assets = 0
        copied_files = 0
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            relative = _package_asset_relative(asset)
            if not relative:
                continue
            entry_name = f"generated/{_package_safe_path(relative).as_posix()}"
            if entry_name not in entries:
                continue
            copied_relative = _copy_generated_entry(archive, entry_name, generated_root)
            copied_files += 1
            metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
            sidecar = (generated_root / Path(*PurePosixPath(copied_relative).parts)).with_suffix(".json")
            sidecar.write_text(json.dumps({**metadata, "imported_from_workspace": remapped_from}, ensure_ascii=False, indent=2), encoding="utf-8")
            registry.ingest_generated(
                GeneratedAssetIngestRequest(
                    file=copied_relative,
                    kind=str(asset.get("kind") or "asset"),
                    source_module=str(asset.get("source_module") or "workspace_import"),
                    source_id=str(asset.get("source_id") or asset.get("id") or ""),
                    metadata={**metadata, "workspace_package_import": True},
                    provenance={
                        "imported_from_workspace": remapped_from,
                        "original_asset_id": asset.get("id"),
                    },
                    workspace_id=workspace_id,
                )
            )
            imported_assets += 1

        try:
            workflows = json.loads(archive.read("workflows/templates.json").decode("utf-8")) if "workflows/templates.json" in archive.namelist() else []
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            workflows = []
        imported_workflows = _import_workflows(data_root, workflows if isinstance(workflows, list) else [])

    return WorkspaceImportResponse(
        workspace=WorkspaceRead.model_validate(store.get_workspace(workspace_id)),
        mode=raw_mode,
        remapped_from=remapped_from,
        imported_assets=imported_assets,
        copied_files=copied_files,
        imported_workflows=imported_workflows,
    )


@router.post("/{workspace_id}/activate", response_model=WorkspaceRead)
def activate_workspace(workspace_id: str, request: Request) -> WorkspaceRead:
    return WorkspaceRead.model_validate(_store(request).activate_workspace(workspace_id))


@router.patch("/{workspace_id}", response_model=WorkspaceRead)
def update_workspace(workspace_id: str, payload: WorkspaceUpdateRequest, request: Request) -> WorkspaceRead:
    return WorkspaceRead.model_validate(_store(request).update_workspace(workspace_id, payload))
