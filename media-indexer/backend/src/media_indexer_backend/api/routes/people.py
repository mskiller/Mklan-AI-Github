from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from media_indexer_backend.api.dependencies import get_session, require_authenticated, require_curator_or_admin, require_enabled_module
from media_indexer_backend.models.tables import User
from media_indexer_backend.schemas.asset import AssetBrowseItem
from media_indexer_backend.schemas.people import (
    AssetFacesResponse,
    PersonDetail,
    PersonMergeRequest,
    PersonSummary,
    PersonUpdateRequest,
    ReclusterPeopleResponse,
)
from media_indexer_backend.services.people_service import (
    get_asset_faces,
    get_face_crop_path_or_404,
    get_person_assets,
    get_person_detail,
    list_people,
    merge_people,
    recluster_people,
    update_person,
)


router = APIRouter(tags=["people"], dependencies=[Depends(require_enabled_module("people"))])


@router.get("/assets/{asset_id}/faces", response_model=AssetFacesResponse)
def get_asset_face_detections(
    asset_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> AssetFacesResponse:
    return get_asset_faces(session, asset_id, current_user=current_user)


@router.get("/people/faces/{face_id}/crop")
def get_face_crop(
    face_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> FileResponse:
    del current_user
    return FileResponse(get_face_crop_path_or_404(session, face_id))


@router.get("/people", response_model=list[PersonSummary])
def get_people(
    q: str | None = None,
    unnamed_only: bool = False,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> list[PersonSummary]:
    del current_user
    return list_people(session, q=q, unnamed_only=unnamed_only)


@router.get("/people/{person_id}", response_model=PersonDetail)
def get_person(
    person_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> PersonDetail:
    del current_user
    return get_person_detail(session, person_id)


@router.get("/people/{person_id}/assets", response_model=list[AssetBrowseItem])
def get_person_asset_items(
    person_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> list[AssetBrowseItem]:
    del current_user
    return get_person_assets(session, person_id)


@router.patch("/people/{person_id}", response_model=PersonDetail)
def patch_person(
    person_id: UUID,
    payload: PersonUpdateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_curator_or_admin),
) -> PersonDetail:
    del current_user
    update_person(session, person_id, payload)
    session.commit()
    return get_person_detail(session, person_id)


@router.post("/people/{person_id}/merge", response_model=PersonDetail)
def post_merge_person(
    person_id: UUID,
    payload: PersonMergeRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_curator_or_admin),
) -> PersonDetail:
    del current_user
    target = merge_people(session, person_id, payload.source_person_id)
    session.commit()
    return get_person_detail(session, target.id)


@router.post("/people/recluster", response_model=ReclusterPeopleResponse)
def post_recluster_people(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_curator_or_admin),
) -> ReclusterPeopleResponse:
    del current_user
    response = recluster_people(session)
    session.commit()
    return response
