from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from media_indexer_backend.api.dependencies import get_session, require_api_token_user
from media_indexer_backend.models.tables import Asset, AssetMetadata, CollectionAsset, Source, User
from media_indexer_backend.schemas.asset import AssetDetail, AssetListResponse
from media_indexer_backend.schemas.collection import CollectionDetail, CollectionSummary
from media_indexer_backend.schemas.source import SourceRead
from media_indexer_backend.services.asset_service import _allowed_source_ids, _apply_source_scope, _asset_summary, get_asset_detail
from media_indexer_backend.services.collection_service import get_collection_detail, list_collections
from media_indexer_backend.services.source_service import list_sources, source_read_for_user


router = APIRouter(prefix="/api/export/v1", tags=["export"])


def _versioned(payload):
    return JSONResponse(content=payload, headers={"X-MKLan-Version": "2.0.0"})


@router.get("/assets")
def export_assets(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    updated_after: datetime | None = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_api_token_user),
):
    query = (
        select(Asset)
        .join(AssetMetadata, AssetMetadata.asset_id == Asset.id, isouter=True)
        .options(
            selectinload(Asset.metadata_record),
            selectinload(Asset.tags),
            selectinload(Asset.annotations),
            selectinload(Asset.source),
        )
        .order_by(Asset.indexed_at.desc())
    )
    count_query = select(Asset.id).join(AssetMetadata, AssetMetadata.asset_id == Asset.id, isouter=True)
    query = _apply_source_scope(query, _allowed_source_ids(session, current_user))
    count_query = _apply_source_scope(count_query, _allowed_source_ids(session, current_user))
    if updated_after is not None:
        query = query.where(Asset.indexed_at >= updated_after)
        count_query = count_query.where(Asset.indexed_at >= updated_after)
    items = session.execute(query.offset((page - 1) * page_size).limit(page_size)).scalars().unique().all()
    total = len(session.execute(count_query).scalars().all())
    payload = AssetListResponse(
        items=[_asset_summary(item, user_id=current_user.id) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    ).model_dump(mode="json")
    return _versioned(payload)


@router.get("/assets/{asset_id}")
def export_asset(
    asset_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_api_token_user),
):
    payload = get_asset_detail(session, asset_id, current_user=current_user).model_dump(mode="json")
    return _versioned(payload)


@router.get("/collections")
def export_collections(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_api_token_user),
):
    payload = [item.model_dump(mode="json") for item in list_collections(session)]
    return _versioned(payload)


@router.get("/collections/{collection_id}/assets")
def export_collection_assets(
    collection_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_api_token_user),
):
    payload = get_collection_detail(session, collection_id, page=page, page_size=page_size, current_user=current_user).model_dump(mode="json")
    return _versioned(payload)


@router.get("/sources")
def export_sources(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_api_token_user),
):
    payload = [source_read_for_user(source, current_user).model_dump(mode="json") for source in list_sources(session, current_user=current_user)]
    return _versioned(payload)
