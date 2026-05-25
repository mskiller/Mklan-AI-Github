from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from media_indexer_backend.api.dependencies import get_session, require_authenticated
from media_indexer_backend.models.tables import User
from media_indexer_backend.schemas.platform import PlatformModuleRead
from media_indexer_backend.platform.service import list_resolved_platform_modules


router = APIRouter(tags=["modules"])


def _module_read(resolved) -> PlatformModuleRead:
    return PlatformModuleRead(
        module_id=resolved.row.module_id,
        name=resolved.manifest.name,
        kind=resolved.row.kind,
        version=resolved.row.version,
        description=resolved.manifest.description,
        platform_api_version=resolved.manifest.platform_api_version,
        source_ref=resolved.row.source_ref,
        enabled=resolved.row.enabled,
        status=resolved.row.status,
        error=resolved.row.error,
        permissions=resolved.manifest.permissions,
        dependencies=resolved.manifest.dependencies,
        backend_entrypoint=resolved.manifest.backend_entrypoint,
        worker_entrypoint=resolved.manifest.worker_entrypoint,
        frontend_entrypoint=resolved.manifest.frontend_entrypoint,
        backend_migrations=resolved.manifest.backend_migrations,
        api_mount=resolved.manifest.api_mount,
        user_mount=resolved.manifest.user_mount,
        admin_mount=resolved.manifest.admin_mount,
        nav_label=resolved.manifest.nav_label,
        nav_href=resolved.manifest.nav_href,
        nav_order=resolved.manifest.nav_order,
        admin_nav_label=resolved.manifest.admin_nav_label,
        admin_nav_href=resolved.manifest.admin_nav_href,
        admin_nav_order=resolved.manifest.admin_nav_order,
        user_visible=resolved.manifest.user_visible,
        admin_visible=resolved.manifest.admin_visible,
        settings_schema=[field.model_dump() for field in resolved.manifest.settings_fields],
        settings_json=resolved.settings_json,
        manifest_path=resolved.manifest.manifest_path,
        installed_at=resolved.row.installed_at,
        updated_at=resolved.row.updated_at,
    )


@router.get("/modules/registry", response_model=list[PlatformModuleRead])
def get_module_registry(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> list[PlatformModuleRead]:
    del current_user
    return [
        _module_read(resolved)
        for resolved in list_resolved_platform_modules(session)
        if resolved.manifest.user_visible or resolved.manifest.admin_visible
    ]
