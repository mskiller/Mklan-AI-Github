from __future__ import annotations

import io
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from media_indexer_backend.api.dependencies import get_session, require_admin
from media_indexer_backend.core.config import get_settings
from media_indexer_backend.core.rate_limit import enforce_rate_limit
from media_indexer_backend.db.session import SessionLocal
import uuid
from media_indexer_backend.models.enums import ScanStatus
from media_indexer_backend.models.tables import Collection, CollectionAsset, ScanJob, ScheduledScan, Source, User, WebhookEndpoint
from media_indexer_backend.schemas.admin import (
    AuditLogRead,
    GroupCreateRequest,
    GroupRead,
    GroupUpdateRequest,
    UserCreateRequest,
    UserPasswordResetRequest,
    UserRead,
    UserUpdateRequest,
)
from media_indexer_backend.schemas.health import AdminHealthResponse
from media_indexer_backend.schemas.integrations import (
    ApiTokenCreateRequest,
    ApiTokenCreateResponse,
    ApiTokenRead,
    ScheduledScanCreateRequest,
    ScheduledScanRead,
    ScheduledScanUpdateRequest,
    WebhookEndpointCreateRequest,
    WebhookEndpointRead,
    WebhookEndpointUpdateRequest,
)
from media_indexer_backend.schemas.maintenance import ResetRequest, ResetResponse
from media_indexer_backend.schemas.platform import PlatformModuleRead, PlatformModuleUpdateRequest
from media_indexer_backend.schemas.settings import AdminSettings, AdminSettingsUpdateRequest, TagSimilarityRebuildResponse
from media_indexer_backend.schemas.clustering import ClusterProposal, ClusteringRequest, ClusteringAcceptAllRequest
from media_indexer_backend.platform.events import publish_event
from media_indexer_backend.platform.service import ensure_platform_modules_synced, list_resolved_platform_modules, resolve_platform_module, update_platform_module
from media_indexer_backend.services.api_token_service import api_token_read, create_api_token, list_api_tokens, revoke_api_token
from media_indexer_backend.services.clustering_service import run_clustering
from media_indexer_backend.services.audit import record_audit_event
from media_indexer_backend.services.backup_service import create_backup_archive, restore_backup_sql, validate_backup_archive
from media_indexer_backend.services.health_service import build_admin_health
from media_indexer_backend.services.maintenance_service import purge_deepzoom_tiles, reset_application_data
from media_indexer_backend.services.scheduler_service import reload_schedules, validate_cron_expression
from media_indexer_backend.services.search_reindex_service import reindex_search_documents
from media_indexer_backend.services.settings_service import get_admin_settings, update_admin_settings
from media_indexer_backend.services.tag_similarity_service import rebuild_all_tag_similarity
from media_indexer_backend.services.user_service import (
    create_group,
    create_user,
    delete_group,
    group_reads,
    list_audit_logs,
    list_groups,
    list_users,
    set_user_password,
    update_group,
    update_user,
    user_reads,
)
from media_indexer_backend.services.webhook_service import WEBHOOK_EVENTS, dispatch_webhook_test


router = APIRouter(prefix="/admin", tags=["admin"])

# In-memory storage for clustering results for simplicity
_clustering_results: dict[str, list[ClusterProposal] | str] = {}


def _platform_module_read(resolved) -> PlatformModuleRead:
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


def _assert_no_active_scans(session: Session) -> None:
    active_scan = session.execute(
        select(ScanJob.id).where(ScanJob.status.in_([ScanStatus.QUEUED, ScanStatus.RUNNING]))
    ).scalar_one_or_none()
    if active_scan is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Stop active scans before performing this maintenance action.")


@router.post("/reset", response_model=ResetResponse)
def reset_data(
    payload: ResetRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> ResetResponse:
    enforce_rate_limit(
        key=f"admin-reset:{current_user.id}",
        limit=5,
        window_seconds=60,
        detail="Too many destructive admin actions. Please wait a minute.",
    )
    result = reset_application_data(session, delete_sources=payload.mode == "all")
    record_audit_event(
        session,
        actor=current_user.username,
        action=f"admin.reset.{payload.mode}",
        resource_type="maintenance",
        details=result,
    )
    session.commit()
    return ResetResponse(**result)


@router.get("/users", response_model=list[UserRead])
def get_users(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> list[UserRead]:
    return user_reads(list_users(session))


@router.post("/users", response_model=UserRead, status_code=201)
def post_user(
    payload: UserCreateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> UserRead:
    user = create_user(session, payload)
    record_audit_event(
        session,
        actor=current_user.username,
        action="user.create",
        resource_type="user",
        resource_id=user.id,
        details={"username": user.username, "role": user.role.value},
    )
    session.commit()
    return user_reads([user])[0]


@router.patch("/users/{user_id}", response_model=UserRead)
def patch_user(
    user_id: UUID,
    payload: UserUpdateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> UserRead:
    user = update_user(session, user_id, payload)
    record_audit_event(
        session,
        actor=current_user.username,
        action="user.update",
        resource_type="user",
        resource_id=user.id,
        details=payload.model_dump(exclude_none=True),
    )
    session.commit()
    return user_reads([user])[0]


@router.post("/users/{user_id}/password", status_code=204)
def post_user_password(
    user_id: UUID,
    payload: UserPasswordResetRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> None:
    user = set_user_password(session, user_id, payload.new_password)
    record_audit_event(
        session,
        actor=current_user.username,
        action="user.password_reset",
        resource_type="user",
        resource_id=user.id,
        details={"username": user.username},
    )
    session.commit()


@router.get("/groups", response_model=list[GroupRead])
def get_groups(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> list[GroupRead]:
    return group_reads(list_groups(session))


@router.post("/groups", response_model=GroupRead, status_code=201)
def post_group(
    payload: GroupCreateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> GroupRead:
    group = create_group(session, payload)
    record_audit_event(
        session,
        actor=current_user.username,
        action="group.create",
        resource_type="group",
        resource_id=group.id,
        details=payload.model_dump(),
    )
    session.commit()
    return GroupRead.model_validate(group)


@router.patch("/groups/{group_id}", response_model=GroupRead)
def patch_group(
    group_id: UUID,
    payload: GroupUpdateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> GroupRead:
    group = update_group(session, group_id, payload)
    record_audit_event(
        session,
        actor=current_user.username,
        action="group.update",
        resource_type="group",
        resource_id=group.id,
        details=payload.model_dump(exclude_none=True),
    )
    session.commit()
    return GroupRead.model_validate(group)


@router.delete("/groups/{group_id}", status_code=204)
def remove_group(
    group_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> None:
    group = delete_group(session, group_id)
    record_audit_event(
        session,
        actor=current_user.username,
        action="group.delete",
        resource_type="group",
        resource_id=group.id,
        details={"name": group.name},
    )
    session.commit()


@router.get("/audit-logs", response_model=list[AuditLogRead])
def get_audit_logs(
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> list[AuditLogRead]:
    return list_audit_logs(session, limit)


@router.get("/modules", response_model=list[PlatformModuleRead])
def get_admin_modules(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> list[PlatformModuleRead]:
    del current_user
    return [_platform_module_read(resolved) for resolved in list_resolved_platform_modules(session)]


@router.get("/modules/{module_id}", response_model=PlatformModuleRead)
def get_admin_module(
    module_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> PlatformModuleRead:
    del current_user
    return _platform_module_read(resolve_platform_module(session, module_id))


@router.patch("/modules/{module_id}", response_model=PlatformModuleRead)
def patch_admin_module(
    module_id: str,
    payload: PlatformModuleUpdateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> PlatformModuleRead:
    before = resolve_platform_module(session, module_id)
    updated = update_platform_module(
        session,
        module_id,
        enabled=payload.enabled,
        settings_json=payload.settings_json,
    )
    record_audit_event(
        session,
        actor=current_user.username,
        action="admin.module.update",
        resource_type="platform_module",
        resource_id=module_id,
        details={
            "module_id": module_id,
            "enabled": updated.row.enabled,
            "status": updated.row.status,
            "settings_keys": sorted((payload.settings_json or {}).keys()),
        },
    )
    if payload.enabled is not None and payload.enabled != before.row.enabled:
        publish_event(
            session,
            "module.enabled" if payload.enabled else "module.disabled",
            {"module_id": module_id},
        )
    session.commit()
    reload_schedules()
    return _platform_module_read(updated)


@router.post("/modules/rescan", response_model=list[PlatformModuleRead])
def post_admin_modules_rescan(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> list[PlatformModuleRead]:
    del current_user
    ensure_platform_modules_synced(session)
    session.commit()
    reload_schedules()
    return [_platform_module_read(resolved) for resolved in list_resolved_platform_modules(session)]


@router.get("/backup", response_class=StreamingResponse)
def get_backup(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> StreamingResponse:
    filename, buffer, manifest = create_backup_archive(session)
    record_audit_event(
        session,
        actor=current_user.username,
        action="admin.backup.create",
        resource_type="maintenance",
        details={"filename": filename, **manifest},
    )
    session.commit()
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/restore")
async def post_restore(
    file: UploadFile = File(...),
    dry_run: bool = Query(default=False),
    confirm: str = Query(default=""),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> dict:
    enforce_rate_limit(
        key=f"admin-restore:{current_user.id}",
        limit=5,
        window_seconds=300,
        detail="Too many restore attempts. Please wait a few minutes.",
    )
    content = await file.read()
    validation, sql_bytes = validate_backup_archive(content)
    if dry_run:
        return validation

    if confirm != "RESTORE":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Pass confirm=RESTORE to execute a real restore.")
    _assert_no_active_scans(session)
    restore_backup_sql(sql_bytes)
    record_audit_event(
        session,
        actor=current_user.username,
        action="admin.backup.restore",
        resource_type="maintenance",
        details={"manifest": validation.get("manifest", {}), "dry_run": False},
    )
    session.commit()
    return {"status": "restored", **validation}


@router.post("/purge-deepzoom")
def post_purge_deepzoom(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> dict[str, int]:
    enforce_rate_limit(
        key=f"admin-purge-deepzoom:{current_user.id}",
        limit=10,
        window_seconds=300,
        detail="Too many maintenance requests. Please wait a few minutes.",
    )
    result = purge_deepzoom_tiles(get_settings().preview_root_path)
    record_audit_event(
        session,
        actor=current_user.username,
        action="admin.preview.purge_deepzoom",
        resource_type="maintenance",
        details=result,
    )
    session.commit()
    return result


@router.post("/reindex-search")
def post_reindex_search(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> dict[str, int]:
    _assert_no_active_scans(session)
    rebuilt_assets = reindex_search_documents(session)
    record_audit_event(
        session,
        actor=current_user.username,
        action="admin.search.reindex",
        resource_type="maintenance",
        details={"rebuilt_assets": rebuilt_assets},
    )
    session.commit()
    return {"rebuilt_assets": rebuilt_assets}


@router.get("/settings", response_model=AdminSettings)
def get_admin_settings_route(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> AdminSettings:
    return get_admin_settings(session)


@router.patch("/settings", response_model=AdminSettings)
def patch_admin_settings(
    payload: AdminSettingsUpdateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> AdminSettings:
    result = update_admin_settings(session, payload)
    record_audit_event(
        session,
        actor=current_user.username,
        action="admin.settings.update",
        resource_type="app_settings",
        details=payload.model_dump(),
    )
    session.commit()
    return result


@router.post("/settings/rebuild-tag-similarity", response_model=TagSimilarityRebuildResponse)
def post_rebuild_tag_similarity(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> TagSimilarityRebuildResponse:
    rebuilt_assets, rebuilt_links = rebuild_all_tag_similarity(session)
    record_audit_event(
        session,
        actor=current_user.username,
        action="admin.settings.rebuild_tag_similarity",
        resource_type="app_settings",
        details={"rebuilt_assets": rebuilt_assets, "rebuilt_links": rebuilt_links},
    )
    session.commit()
    return TagSimilarityRebuildResponse(rebuilt_assets=rebuilt_assets, rebuilt_links=rebuilt_links)


@router.post("/clustering/suggest")
async def post_clustering_suggest(
    payload: ClusteringRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> dict[str, str]:
    job_id = str(uuid.uuid4())
    _clustering_results[job_id] = "processing"
    
    def task():
        try:
            with SessionLocal() as background_session:
                results = run_clustering(background_session, k=payload.k, min_size=payload.min_size)
            _clustering_results[job_id] = results
        except Exception as e:
            _clustering_results[job_id] = f"error: {str(e)}"
            
    background_tasks.add_task(task)
    return {"job_id": job_id}


@router.get("/clustering/results/{job_id}", response_model=list[ClusterProposal] | dict)
def get_clustering_results(
    job_id: str,
    current_user: User = Depends(require_admin),
) -> list[ClusterProposal] | dict:
    result = _clustering_results.get(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if result == "processing":
        return {"status": "processing"}
    if isinstance(result, str) and result.startswith("error"):
        return {"status": "error", "message": result}
    return result


@router.post("/clustering/accept")
def post_clustering_accept(
    payload: ClusteringAcceptAllRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> dict[str, int]:
    created_count = 0
    from datetime import datetime, timezone

    for prop in payload.proposals:
        coll = Collection(
            name=prop.label,
            created_by=current_user.id,
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
        )
        session.add(coll)
        session.flush()

        for asset_id in prop.asset_ids:
            link = CollectionAsset(
                collection_id=coll.id,
                asset_id=asset_id,
                added_by=current_user.id,
                created_at=datetime.now(tz=timezone.utc),
            )
            session.add(link)
        created_count += 1

    session.commit()
    return {"created_collections": created_count}


@router.get("/health", response_model=AdminHealthResponse)
def get_admin_health(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> AdminHealthResponse:
    return build_admin_health(session)


def _schedule_read(schedule: ScheduledScan) -> ScheduledScanRead:
    return ScheduledScanRead(
        id=schedule.id,
        source_id=schedule.source_id,
        source_name=schedule.source.name if schedule.source is not None else "Unknown",
        cron_expression=schedule.cron_expression,
        enabled=schedule.enabled,
        last_triggered_at=schedule.last_triggered_at,
        last_job_id=schedule.last_job_id,
        created_at=schedule.created_at,
        updated_at=schedule.updated_at,
    )


def _webhook_read(endpoint: WebhookEndpoint) -> WebhookEndpointRead:
    return WebhookEndpointRead(
        id=endpoint.id,
        url=endpoint.url,
        events=list(endpoint.events or []),
        enabled=endpoint.enabled,
        created_at=endpoint.created_at,
        last_delivered_at=endpoint.last_delivered_at,
        last_status_code=endpoint.last_status_code,
    )


@router.get("/webhook-events", response_model=list[str])
def get_webhook_events(
    current_user: User = Depends(require_admin),
) -> list[str]:
    return WEBHOOK_EVENTS


@router.get("/schedules", response_model=list[ScheduledScanRead])
def get_schedules(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> list[ScheduledScanRead]:
    schedules = session.execute(
        select(ScheduledScan).join(Source).options(selectinload(ScheduledScan.source)).order_by(Source.name)
    ).scalars().all()
    return [_schedule_read(schedule) for schedule in schedules]


@router.post("/schedules", response_model=ScheduledScanRead, status_code=201)
def post_schedule(
    payload: ScheduledScanCreateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> ScheduledScanRead:
    validate_cron_expression(payload.cron_expression)
    source = session.get(Source, payload.source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found.")
    schedule = ScheduledScan(
        source_id=payload.source_id,
        cron_expression=payload.cron_expression,
        enabled=payload.enabled,
    )
    session.add(schedule)
    session.flush()
    record_audit_event(
        session,
        actor=current_user.username,
        action="admin.schedule.create",
        resource_type="scheduled_scan",
        resource_id=schedule.id,
        details=payload.model_dump(),
    )
    session.commit()
    reload_schedules()
    schedule = session.execute(
        select(ScheduledScan).options(selectinload(ScheduledScan.source)).where(ScheduledScan.id == schedule.id)
    ).scalar_one()
    return _schedule_read(schedule)


@router.patch("/schedules/{schedule_id}", response_model=ScheduledScanRead)
def patch_schedule(
    schedule_id: UUID,
    payload: ScheduledScanUpdateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> ScheduledScanRead:
    schedule = session.get(ScheduledScan, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Scheduled scan not found.")
    if payload.cron_expression is not None:
        validate_cron_expression(payload.cron_expression)
        schedule.cron_expression = payload.cron_expression
    if payload.enabled is not None:
        schedule.enabled = payload.enabled
    record_audit_event(
        session,
        actor=current_user.username,
        action="admin.schedule.update",
        resource_type="scheduled_scan",
        resource_id=schedule.id,
        details=payload.model_dump(exclude_none=True),
    )
    session.commit()
    reload_schedules()
    schedule = session.execute(
        select(ScheduledScan).options(selectinload(ScheduledScan.source)).where(ScheduledScan.id == schedule.id)
    ).scalar_one()
    return _schedule_read(schedule)


@router.delete("/schedules/{schedule_id}", status_code=204)
def delete_schedule(
    schedule_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> Response:
    schedule = session.get(ScheduledScan, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Scheduled scan not found.")
    session.delete(schedule)
    record_audit_event(
        session,
        actor=current_user.username,
        action="admin.schedule.delete",
        resource_type="scheduled_scan",
        resource_id=schedule_id,
        details={},
    )
    session.commit()
    reload_schedules()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/webhooks", response_model=list[WebhookEndpointRead])
def get_webhooks(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> list[WebhookEndpointRead]:
    endpoints = session.execute(select(WebhookEndpoint).order_by(WebhookEndpoint.created_at.desc())).scalars().all()
    return [_webhook_read(endpoint) for endpoint in endpoints]


@router.post("/webhooks", response_model=WebhookEndpointRead, status_code=201)
def post_webhook(
    payload: WebhookEndpointCreateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> WebhookEndpointRead:
    endpoint = WebhookEndpoint(
        url=payload.url,
        secret=payload.secret,
        events=payload.events,
        enabled=payload.enabled,
    )
    session.add(endpoint)
    session.flush()
    record_audit_event(
        session,
        actor=current_user.username,
        action="admin.webhook.create",
        resource_type="webhook_endpoint",
        resource_id=endpoint.id,
        details={"url": endpoint.url, "events": endpoint.events},
    )
    session.commit()
    return _webhook_read(endpoint)


@router.patch("/webhooks/{webhook_id}", response_model=WebhookEndpointRead)
def patch_webhook(
    webhook_id: UUID,
    payload: WebhookEndpointUpdateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> WebhookEndpointRead:
    endpoint = session.get(WebhookEndpoint, webhook_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail="Webhook not found.")
    if payload.url is not None:
        endpoint.url = payload.url
    if payload.secret is not None:
        endpoint.secret = payload.secret
    if payload.events is not None:
        endpoint.events = payload.events
    if payload.enabled is not None:
        endpoint.enabled = payload.enabled
    record_audit_event(
        session,
        actor=current_user.username,
        action="admin.webhook.update",
        resource_type="webhook_endpoint",
        resource_id=endpoint.id,
        details=payload.model_dump(exclude_none=True, exclude={"secret"}),
    )
    session.commit()
    return _webhook_read(endpoint)


@router.delete("/webhooks/{webhook_id}", status_code=204)
def delete_webhook(
    webhook_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> Response:
    endpoint = session.get(WebhookEndpoint, webhook_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail="Webhook not found.")
    session.delete(endpoint)
    record_audit_event(
        session,
        actor=current_user.username,
        action="admin.webhook.delete",
        resource_type="webhook_endpoint",
        resource_id=webhook_id,
        details={},
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/webhooks/{webhook_id}/test", status_code=204)
def test_webhook(
    webhook_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> Response:
    endpoint = session.get(WebhookEndpoint, webhook_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail="Webhook not found.")
    dispatch_webhook_test(endpoint.id, "scan.completed", {"message": "test delivery"})
    record_audit_event(
        session,
        actor=current_user.username,
        action="admin.webhook.test",
        resource_type="webhook_endpoint",
        resource_id=webhook_id,
        details={"url": endpoint.url},
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api-tokens", response_model=list[ApiTokenRead])
def get_api_tokens(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> list[ApiTokenRead]:
    return list_api_tokens(session)


@router.post("/api-tokens", response_model=ApiTokenCreateResponse, status_code=201)
def post_api_token(
    payload: ApiTokenCreateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> ApiTokenCreateResponse:
    item, token = create_api_token(session, payload, current_user)
    record_audit_event(
        session,
        actor=current_user.username,
        action="admin.api_token.create",
        resource_type="api_token",
        resource_id=item.id,
        details={"name": item.name, "expires_at": item.expires_at.isoformat() if item.expires_at else None},
    )
    session.commit()
    return ApiTokenCreateResponse(token=token, item=api_token_read(item))


@router.delete("/api-tokens/{token_id}", status_code=204)
def delete_api_token(
    token_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> Response:
    item = revoke_api_token(session, token_id)
    record_audit_event(
        session,
        actor=current_user.username,
        action="admin.api_token.revoke",
        resource_type="api_token",
        resource_id=item.id,
        details={"name": item.name},
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
