from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from media_indexer_backend.api.dependencies import get_session, require_admin, require_authenticated, require_upload_access
from media_indexer_backend.models.tables import ScanJob, User
from media_indexer_backend.models.enums import MediaType, ScanStatus
from media_indexer_backend.schemas.scan_job import ScanJobCreate, ScanJobRead
from media_indexer_backend.schemas.source import SourceBrowseInspect, SourceBrowseResponse, SourceCreate, SourceRead, SourceTreeResponse, SourceUploadRead
from media_indexer_backend.services.audit import record_audit_event
from media_indexer_backend.services.metadata import detect_media_type, guess_mime_type
from media_indexer_backend.services.path_safety import resolve_asset_path
from media_indexer_backend.services.scan_service import queue_scan
from media_indexer_backend.services.source_service import (
    browse_source,
    create_source,
    delete_source,
    get_source_or_404,
    get_source_tree,
    inspect_source_entry,
    list_sources,
    source_read_for_user,
    upload_images_to_source,
)


router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", response_model=list[SourceRead])
def get_sources(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> list[SourceRead]:
    return [source_read_for_user(source, current_user) for source in list_sources(session, current_user=current_user)]


@router.post("", response_model=SourceRead, status_code=status.HTTP_201_CREATED)
def post_source(
    payload: SourceCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> SourceRead:
    source = create_source(session, payload)
    record_audit_event(
        session,
        actor=current_user.username,
        action="source.create",
        resource_type="source",
        resource_id=source.id,
        details={"root_path": source.root_path, "type": source.type.value},
    )
    session.commit()
    return source_read_for_user(source, current_user)


@router.get("/{source_id}", response_model=SourceRead)
def get_source(
    source_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> SourceRead:
    return source_read_for_user(get_source_or_404(session, source_id, current_user=current_user), current_user)


@router.get("/{source_id}/browse", response_model=SourceBrowseResponse)
def get_source_browse(
    source_id: UUID,
    path: str | None = Query(default=None),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> SourceBrowseResponse:
    return browse_source(session, source_id, path, current_user=current_user)


@router.get("/{source_id}/browse/inspect", response_model=SourceBrowseInspect)
def get_source_browse_inspect(
    source_id: UUID,
    path: str = Query(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> SourceBrowseInspect:
    return inspect_source_entry(session, source_id, path, current_user=current_user)


@router.get("/{source_id}/tree", response_model=SourceTreeResponse)
def get_source_tree_route(
    source_id: UUID,
    path: str = Query(default=""),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> SourceTreeResponse:
    return get_source_tree(session, source_id, path, current_user=current_user)


@router.get("/{source_id}/browse/content")
def get_source_browse_content(
    source_id: UUID,
    path: str = Query(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> FileResponse:
    source = get_source_or_404(session, source_id, current_user=current_user)
    media_path = resolve_asset_path(source.root_path, path)
    media_type = detect_media_type(media_path, guess_mime_type(media_path))
    if media_type == MediaType.UNKNOWN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only supported image and video files can be previewed from source browse.",
        )
    return FileResponse(media_path, filename=media_path.name)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_source(
    source_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> Response:
    source = delete_source(session, source_id)
    record_audit_event(
        session,
        actor=current_user.username,
        action="source.delete",
        resource_type="source",
        resource_id=source.id,
        details={"name": source.name},
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{source_id}/scan", response_model=ScanJobRead)
def trigger_scan(
    source_id: UUID,
    payload: ScanJobCreate | None = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> ScanJobRead:
    payload = payload or ScanJobCreate()
    job = queue_scan(session, source_id, scan_mode=payload.scan_mode, path_filter=payload.path_filter)
    record_audit_event(
        session,
        actor=current_user.username,
        action="scan.requested",
        resource_type="scan_job",
        resource_id=job.id,
        details={"source_id": str(source_id), "scan_mode": job.scan_mode, "path_filter": job.path_filter},
    )
    session.commit()
    return ScanJobRead.model_validate(job)


@router.post("/{source_id}/upload", response_model=SourceUploadRead)
def upload_source_images(
    source_id: UUID,
    folder: str | None = Form(default=None),
    files: list[UploadFile] = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_upload_access),
) -> SourceUploadRead:
    get_source_or_404(session, source_id, current_user=current_user)
    payload = upload_images_to_source(session, source_id, folder=folder, files=files)
    record_audit_event(
        session,
        actor=current_user.username,
        action="source.upload",
        resource_type="source",
        resource_id=source_id,
        details={"folder": payload.folder, "uploaded_files": payload.uploaded_files},
    )
    session.commit()
    return payload
