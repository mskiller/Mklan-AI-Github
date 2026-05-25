from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from media_indexer_backend.api.dependencies import get_session, require_authenticated, require_enabled_module
from media_indexer_backend.models.tables import User
from media_indexer_backend.schemas.smart_album import (
    SmartAlbumCreateRequest,
    SmartAlbumDetail,
    SmartAlbumSummary,
    SmartAlbumUpdateRequest,
)
from media_indexer_backend.services.smart_album_service import (
    get_smart_album_or_404,
    create_smart_album,
    delete_smart_album,
    get_smart_album_detail,
    list_smart_albums,
    smart_album_summary,
    sync_album,
    update_smart_album,
)


router = APIRouter(prefix="/smart-albums", tags=["smart-albums"], dependencies=[Depends(require_enabled_module("smart_albums"))])


@router.get("", response_model=list[SmartAlbumSummary])
def get_smart_albums(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> list[SmartAlbumSummary]:
    return list_smart_albums(session, current_user.id)


@router.post("", response_model=SmartAlbumSummary, status_code=status.HTTP_201_CREATED)
def post_smart_album(
    payload: SmartAlbumCreateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> SmartAlbumSummary:
    album = create_smart_album(session, current_user.id, payload)
    session.commit()
    session.refresh(album)
    return smart_album_summary(album)


@router.get("/{album_id}", response_model=SmartAlbumDetail)
def get_smart_album(
    album_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> SmartAlbumDetail:
    return get_smart_album_detail(session, album_id, current_user.id)


@router.patch("/{album_id}", response_model=SmartAlbumSummary)
def patch_smart_album(
    album_id: UUID,
    payload: SmartAlbumUpdateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> SmartAlbumSummary:
    album = update_smart_album(session, album_id, current_user.id, payload)
    session.commit()
    return smart_album_summary(album)


@router.delete("/{album_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_smart_album_route(
    album_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> Response:
    delete_smart_album(session, album_id, current_user.id)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{album_id}/sync", response_model=SmartAlbumSummary)
def post_sync_smart_album(
    album_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> SmartAlbumSummary:
    album = get_smart_album_or_404(session, album_id, current_user.id)
    sync_album(session, album, owner=current_user)
    session.commit()
    return smart_album_summary(album)
