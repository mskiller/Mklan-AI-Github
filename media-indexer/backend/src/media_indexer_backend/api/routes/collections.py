from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from media_indexer_backend.api.dependencies import get_session, require_authenticated, require_collection_manager, require_enabled_module
from media_indexer_backend.models.tables import User
from media_indexer_backend.schemas.collection import (
    CollectionAssetAddRequest,
    CollectionCreateRequest,
    CollectionDetail,
    CollectionSearchAddRequest,
    CollectionSummary,
    CollectionUpdateRequest,
)
from media_indexer_backend.services.audit import record_audit_event
from media_indexer_backend.services.collection_service import (
    add_assets_to_collection,
    add_search_results_to_collection,
    collection_summary,
    create_collection,
    delete_collection,
    get_collection_detail,
    get_collection_or_404,
    list_collections,
    remove_asset_from_collection,
    update_collection,
)
from media_indexer_backend.services.webhook_service import dispatch_webhook_event


router = APIRouter(prefix="/collections", tags=["collections"], dependencies=[Depends(require_enabled_module("collections"))])


@router.get("", response_model=list[CollectionSummary])
def get_collections(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> list[CollectionSummary]:
    return list_collections(session)


@router.post("", response_model=CollectionSummary, status_code=status.HTTP_201_CREATED)
def post_collection(
    payload: CollectionCreateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_collection_manager),
) -> CollectionSummary:
    collection = create_collection(session, payload, created_by=current_user.id)
    record_audit_event(
        session,
        actor=current_user.username,
        action="collection.create",
        resource_type="collection",
        resource_id=collection.id,
        details={"name": collection.name},
    )
    session.commit()
    dispatch_webhook_event("collection.updated", {"collection_id": str(collection.id), "action": "created"})
    return collection_summary(collection, 0)


@router.get("/{collection_id}", response_model=CollectionDetail)
def get_collection(
    collection_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=36, ge=1, le=100),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> CollectionDetail:
    return get_collection_detail(session, collection_id, page=page, page_size=page_size, current_user=current_user)


@router.patch("/{collection_id}", response_model=CollectionSummary)
def patch_collection(
    collection_id: UUID,
    payload: CollectionUpdateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_collection_manager),
) -> CollectionSummary:
    collection = update_collection(session, collection_id, payload)
    record_audit_event(
        session,
        actor=current_user.username,
        action="collection.update",
        resource_type="collection",
        resource_id=collection.id,
        details=payload.model_dump(exclude_none=True),
    )
    session.commit()
    dispatch_webhook_event("collection.updated", {"collection_id": str(collection.id), "action": "updated"})
    return collection_summary(
        collection,
        get_collection_detail(session, collection.id, page=1, page_size=1).total,
    )


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection_route(
    collection_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_collection_manager),
) -> Response:
    collection = delete_collection(session, collection_id)
    record_audit_event(
        session,
        actor=current_user.username,
        action="collection.delete",
        resource_type="collection",
        resource_id=collection.id,
        details={"name": collection.name},
    )
    session.commit()
    dispatch_webhook_event("collection.updated", {"collection_id": str(collection.id), "action": "deleted"})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{collection_id}/assets", response_model=CollectionDetail)
def post_collection_assets(
    collection_id: UUID,
    payload: CollectionAssetAddRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_collection_manager),
) -> CollectionDetail:
    detail = add_assets_to_collection(session, collection_id, payload, added_by=current_user.id, current_user=current_user)
    record_audit_event(
        session,
        actor=current_user.username,
        action="collection.assets_add",
        resource_type="collection",
        resource_id=collection_id,
        details={"asset_ids": [str(asset_id) for asset_id in payload.asset_ids]},
    )
    session.commit()
    dispatch_webhook_event("collection.updated", {"collection_id": str(collection_id), "action": "assets_add"})
    return detail


@router.post("/{collection_id}/search-results", response_model=CollectionDetail)
def post_collection_search_results(
    collection_id: UUID,
    payload: CollectionSearchAddRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_collection_manager),
) -> CollectionDetail:
    detail = add_search_results_to_collection(session, collection_id, payload, added_by=current_user.id, current_user=current_user)
    record_audit_event(
        session,
        actor=current_user.username,
        action="collection.search_results_add",
        resource_type="collection",
        resource_id=collection_id,
        details=payload.model_dump(),
    )
    session.commit()
    dispatch_webhook_event("collection.updated", {"collection_id": str(collection_id), "action": "search_results_add"})
    return detail


@router.delete("/{collection_id}/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection_asset(
    collection_id: UUID,
    asset_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_collection_manager),
) -> Response:
    remove_asset_from_collection(session, collection_id, asset_id)
    record_audit_event(
        session,
        actor=current_user.username,
        action="collection.asset_remove",
        resource_type="collection",
        resource_id=collection_id,
        details={"asset_id": str(asset_id)},
    )
    session.commit()
    dispatch_webhook_event("collection.updated", {"collection_id": str(collection_id), "action": "asset_remove"})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
