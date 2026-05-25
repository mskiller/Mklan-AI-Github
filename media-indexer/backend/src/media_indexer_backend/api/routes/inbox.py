from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from media_indexer_backend.api.dependencies import get_session, require_admin, require_authenticated, require_upload_access
from media_indexer_backend.models.tables import User
from media_indexer_backend.schemas.inbox import InboxApproveRequest, InboxCompareResponse, InboxCountResponse, InboxItemRead
from media_indexer_backend.services.audit import record_audit_event
from media_indexer_backend.services.inbox_service import (
    approve_inbox_item,
    get_inbox_item_or_404,
    inbox_compare_payload,
    inbox_item_read,
    inbox_thumbnail_path,
    list_inbox_items,
    reject_inbox_item,
)


router = APIRouter(prefix="/inbox", tags=["inbox"])


@router.get("", response_model=list[InboxItemRead] | InboxCountResponse)
def get_inbox(
    status_filter: str | None = Query(default=None, alias="status"),
    count_only: bool = Query(default=False),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
):
    items = list_inbox_items(session, status_filter=status_filter)
    if count_only:
        return InboxCountResponse(count=len(items))
    return items


@router.get("/{item_id}", response_model=InboxItemRead)
def get_inbox_item(
    item_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> InboxItemRead:
    return inbox_item_read(get_inbox_item_or_404(session, item_id))


@router.get("/{item_id}/thumbnail")
def get_inbox_thumbnail(
    item_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> FileResponse:
    return FileResponse(inbox_thumbnail_path(session, item_id))


@router.get("/{item_id}/compare", response_model=InboxCompareResponse)
def get_inbox_compare(
    item_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> InboxCompareResponse:
    return InboxCompareResponse(**inbox_compare_payload(session, item_id, current_user=current_user))


@router.post("/{item_id}/approve", status_code=204)
def post_inbox_approve(
    item_id: UUID,
    payload: InboxApproveRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_upload_access),
) -> Response:
    job = approve_inbox_item(session, item_id, current_user=current_user, target_source_id=payload.target_source_id)
    record_audit_event(
        session,
        actor=current_user.username,
        action="inbox.approve",
        resource_type="inbox_item",
        resource_id=item_id,
        details={"scan_job_id": str(job.id) if job else None},
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{item_id}/reject", status_code=204)
def post_inbox_reject(
    item_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_upload_access),
) -> Response:
    reject_inbox_item(session, item_id, current_user=current_user)
    record_audit_event(
        session,
        actor=current_user.username,
        action="inbox.reject",
        resource_type="inbox_item",
        resource_id=item_id,
        details={},
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
