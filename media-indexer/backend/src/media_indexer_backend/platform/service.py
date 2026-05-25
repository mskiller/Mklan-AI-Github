from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from media_indexer_backend.db.session import SessionLocal
from media_indexer_backend.models.tables import PlatformModule
from media_indexer_backend.platform.manifest import ModuleManifest
from media_indexer_backend.platform.registry import discover_manifest_map


PLATFORM_API_VERSION = "1"


@dataclass(slots=True)
class ResolvedModule:
    manifest: ModuleManifest
    row: PlatformModule
    settings_json: dict[str, Any]


def _field_defaults(manifest: ModuleManifest) -> dict[str, Any]:
    return {field.key: field.default for field in manifest.settings_fields}


def _merged_settings(row: PlatformModule, manifest: ModuleManifest) -> dict[str, Any]:
    merged = _field_defaults(manifest)
    merged.update(row.settings_json or {})
    return merged


def _validate_settings(manifest: ModuleManifest, payload: dict[str, Any]) -> dict[str, Any]:
    declared_fields = {field.key: field for field in manifest.settings_fields}
    normalized: dict[str, Any] = {}
    for key, value in payload.items():
        field = declared_fields.get(key)
        if field is None:
            continue
        if field.type == "boolean":
            normalized[key] = bool(value)
        elif field.type == "string":
            normalized[key] = str(value) if value is not None else None
        elif field.type == "integer":
            normalized[key] = int(value) if value is not None else None
        elif field.type == "number":
            normalized[key] = float(value) if value is not None else None
    return normalized


def ensure_platform_modules_synced(session: Session) -> dict[str, ModuleManifest]:
    manifest_map = discover_manifest_map()
    existing_rows = {row.module_id: row for row in session.query(PlatformModule).all()}

    for module_id, manifest in manifest_map.items():
        row = existing_rows.get(module_id)
        if row is None:
            row = PlatformModule(
                module_id=module_id,
                name=manifest.name,
                kind=manifest.kind,
                version=manifest.version,
                source_ref=manifest.source_ref,
                enabled=manifest.enabled_by_default and manifest.error is None,
                status="pending",
                error=manifest.error,
                settings_json=_field_defaults(manifest),
            )
            session.add(row)
            existing_rows[module_id] = row
            continue

        row.name = manifest.name
        row.kind = manifest.kind
        row.version = manifest.version
        row.source_ref = manifest.source_ref
        row.settings_json = _merged_settings(row, manifest)
        if manifest.error:
            row.error = manifest.error

    for module_id, row in existing_rows.items():
        if module_id not in manifest_map:
            row.status = "missing"
            row.error = "Module manifest is no longer installed."

    refresh_platform_module_statuses(session, manifest_map=manifest_map)
    session.flush()
    return manifest_map


def refresh_platform_module_statuses(
    session: Session,
    *,
    manifest_map: dict[str, ModuleManifest] | None = None,
) -> dict[str, ModuleManifest]:
    manifests = manifest_map or discover_manifest_map()
    rows = {row.module_id: row for row in session.query(PlatformModule).all()}

    for module_id, row in rows.items():
        manifest = manifests.get(module_id)
        if manifest is None:
            row.status = "missing"
            row.error = row.error or "Module manifest is no longer installed."
            continue
        if manifest.platform_api_version != PLATFORM_API_VERSION:
            row.status = "error"
            row.error = (
                f"Incompatible platform_api_version {manifest.platform_api_version!r}; "
                f"expected {PLATFORM_API_VERSION!r}."
            )
            continue
        if manifest.error:
            row.status = "error"
            row.error = manifest.error
            continue
        if not row.enabled:
            row.status = "disabled"
            row.error = None
            continue

        blocking = []
        for dependency in manifest.dependencies:
            dependency_row = rows.get(dependency)
            if dependency_row is None:
                blocking.append(dependency)
                continue
            if dependency_row.status not in {"active"}:
                blocking.append(dependency)
        if blocking:
            row.status = "blocked"
            row.error = f"Missing or disabled dependencies: {', '.join(sorted(blocking))}"
            continue
        row.status = "active"
        row.error = None

    session.flush()
    return manifests


def get_platform_module_or_404(session: Session, module_id: str) -> PlatformModule:
    row = session.get(PlatformModule, module_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found.")
    return row


def resolve_platform_module(session: Session, module_id: str) -> ResolvedModule:
    manifest_map = refresh_platform_module_statuses(session)
    manifest = manifest_map.get(module_id)
    if manifest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found.")
    row = get_platform_module_or_404(session, module_id)
    return ResolvedModule(manifest=manifest, row=row, settings_json=_merged_settings(row, manifest))


def ensure_module_enabled(session: Session, module_id: str) -> PlatformModule:
    resolved = resolve_platform_module(session, module_id)
    if resolved.row.status != "active":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Module {module_id!r} is not enabled.")
    return resolved.row


def module_is_enabled(session: Session, module_id: str) -> bool:
    try:
        ensure_module_enabled(session, module_id)
    except HTTPException:
        return False
    return True


def update_platform_module(
    session: Session,
    module_id: str,
    *,
    enabled: bool | None = None,
    settings_json: dict[str, Any] | None = None,
) -> ResolvedModule:
    manifest_map = ensure_platform_modules_synced(session)
    manifest = manifest_map.get(module_id)
    if manifest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found.")
    row = get_platform_module_or_404(session, module_id)

    if settings_json is not None:
        normalized = _validate_settings(manifest, settings_json)
        row.settings_json = {**_merged_settings(row, manifest), **normalized}
    if enabled is not None:
        row.enabled = enabled

    refresh_platform_module_statuses(session, manifest_map=manifest_map)

    if enabled and row.status == "blocked":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=row.error or "Module dependencies are not satisfied.")

    session.flush()
    return ResolvedModule(manifest=manifest, row=row, settings_json=_merged_settings(row, manifest))


def list_resolved_platform_modules(session: Session) -> list[ResolvedModule]:
    manifest_map = ensure_platform_modules_synced(session)
    rows = {row.module_id: row for row in session.query(PlatformModule).all()}
    resolved: list[ResolvedModule] = []
    for module_id in sorted(rows):
        manifest = manifest_map.get(module_id)
        if manifest is None:
            manifest = ModuleManifest(id=module_id, name=rows[module_id].name, version=rows[module_id].version)
        resolved.append(ResolvedModule(manifest=manifest, row=rows[module_id], settings_json=_merged_settings(rows[module_id], manifest)))
    return resolved


def get_live_resolved_module(module_id: str) -> ResolvedModule | None:
    try:
        with SessionLocal() as session:
            ensure_platform_modules_synced(session)
            session.commit()
        with SessionLocal() as session:
            return resolve_platform_module(session, module_id)
    except Exception:  # noqa: BLE001
        return None


def get_live_module_setting(module_id: str, key: str, default: Any) -> Any:
    resolved = get_live_resolved_module(module_id)
    if resolved is None:
        return default
    return resolved.settings_json.get(key, default)


def live_module_enabled(module_id: str, *, default: bool = False) -> bool:
    resolved = get_live_resolved_module(module_id)
    if resolved is None:
        return default
    return resolved.row.status == "active"
