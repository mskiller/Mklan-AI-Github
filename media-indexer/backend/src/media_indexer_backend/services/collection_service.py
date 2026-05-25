from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from media_indexer_backend.models.tables import Asset, Collection, CollectionAsset, User
from media_indexer_backend.platform.events import publish_event
from media_indexer_backend.schemas.asset import AssetBrowseItem
from media_indexer_backend.schemas.collection import (
    CollectionAssetAddRequest,
    CollectionCreateRequest,
    CollectionDetail,
    CollectionSearchAddRequest,
    CollectionSummary,
    CollectionUpdateRequest,
)
from media_indexer_backend.services.asset_service import asset_browse_item, matching_asset_ids_for_search


def get_collection_or_404(session: Session, collection_id: UUID) -> Collection:
    collection = session.get(Collection, collection_id)
    if not collection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found.")
    return collection


def _collection_counts(session: Session) -> dict[UUID, int]:
    rows = session.execute(
        select(CollectionAsset.collection_id, func.count(CollectionAsset.asset_id))
        .group_by(CollectionAsset.collection_id)
    ).all()
    return {collection_id: count for collection_id, count in rows}


def collection_summary(collection: Collection, asset_count: int) -> CollectionSummary:
    return CollectionSummary(
        id=collection.id,
        name=collection.name,
        description=collection.description,
        created_by=collection.created_by,
        asset_count=asset_count,
        created_at=collection.created_at,
        updated_at=collection.updated_at,
    )


def list_collections(session: Session) -> list[CollectionSummary]:
    collections = session.execute(select(Collection).order_by(Collection.updated_at.desc(), Collection.name)).scalars().all()
    counts = _collection_counts(session)
    return [collection_summary(collection, counts.get(collection.id, 0)) for collection in collections]


def create_collection(session: Session, payload: CollectionCreateRequest, *, created_by: UUID) -> Collection:
    name = payload.name.strip()
    existing = session.execute(select(Collection).where(Collection.name == name)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Collection name already exists.")
    collection = Collection(name=name, description=payload.description.strip(), created_by=created_by)
    session.add(collection)
    session.flush()
    return collection


def update_collection(session: Session, collection_id: UUID, payload: CollectionUpdateRequest) -> Collection:
    collection = get_collection_or_404(session, collection_id)
    if payload.name is not None:
        next_name = payload.name.strip()
        existing = session.execute(select(Collection).where(Collection.name == next_name, Collection.id != collection_id)).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Collection name already exists.")
        collection.name = next_name
    if payload.description is not None:
        collection.description = payload.description.strip()
    session.flush()
    return collection


def delete_collection(session: Session, collection_id: UUID) -> Collection:
    collection = get_collection_or_404(session, collection_id)
    session.delete(collection)
    return collection


def get_collection_detail(session: Session, collection_id: UUID, *, page: int, page_size: int, current_user: User | None = None) -> CollectionDetail:
    collection = get_collection_or_404(session, collection_id)
    total = session.execute(
        select(func.count(CollectionAsset.asset_id)).where(CollectionAsset.collection_id == collection_id)
    ).scalar_one()
    assets = session.execute(
        select(Asset)
        .join(CollectionAsset, CollectionAsset.asset_id == Asset.id)
        .where(CollectionAsset.collection_id == collection_id)
        .options(selectinload(Asset.metadata_record), selectinload(Asset.tags), selectinload(Asset.source), selectinload(Asset.annotations))
        .order_by(CollectionAsset.created_at.desc(), Asset.filename)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).scalars().unique().all()
    return CollectionDetail(
        **collection_summary(collection, total).model_dump(),
        items=[asset_browse_item(asset, user_id=current_user.id if current_user else None) for asset in assets],
        page=page,
        page_size=page_size,
        total=total,
    )


def add_assets_to_collection(
    session: Session,
    collection_id: UUID,
    payload: CollectionAssetAddRequest,
    *,
    added_by: UUID,
    current_user: User | None = None,
) -> CollectionDetail:
    collection = get_collection_or_404(session, collection_id)
    assets = session.execute(
        select(Asset).where(Asset.id.in_(payload.asset_ids)).options(selectinload(Asset.source), selectinload(Asset.metadata_record), selectinload(Asset.tags), selectinload(Asset.annotations))
    ).scalars().unique().all()
    asset_map = {asset.id: asset for asset in assets}
    for asset_id in payload.asset_ids:
        if asset_id not in asset_map:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more assets were not found.")
        existing = session.execute(
            select(CollectionAsset).where(CollectionAsset.collection_id == collection_id, CollectionAsset.asset_id == asset_id)
        ).scalar_one_or_none()
        if existing:
            continue
        session.add(CollectionAsset(collection_id=collection_id, asset_id=asset_id, added_by=added_by))
    session.flush()
    publish_event(
        session,
        "collection.asset_added",
        {
            "user_id": str(added_by),
            "collection_id": str(collection.id),
            "asset_ids": [str(asset_id) for asset_id in payload.asset_ids if asset_id in asset_map],
        },
    )
    return get_collection_detail(session, collection.id, page=1, page_size=48, current_user=current_user)


def add_search_results_to_collection(
    session: Session,
    collection_id: UUID,
    payload: CollectionSearchAddRequest,
    *,
    added_by: UUID,
    current_user: User | None = None,
) -> CollectionDetail:
    asset_ids = matching_asset_ids_for_search(
        session,
        q=payload.q,
        media_type=payload.media_type,
        caption=payload.caption,
        ocr_text=payload.ocr_text,
        camera_make=payload.camera_make,
        camera_model=payload.camera_model,
        year=payload.year,
        width_min=payload.width_min,
        width_max=payload.width_max,
        height_min=payload.height_min,
        height_max=payload.height_max,
        duration_min=payload.duration_min,
        duration_max=payload.duration_max,
        has_gps=None,
        tags=payload.tags,
        auto_tags=payload.auto_tags,
        current_user=current_user,
    )
    if not asset_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No assets matched this search.")
    return add_assets_to_collection(
        session,
        collection_id,
        CollectionAssetAddRequest(asset_ids=asset_ids),
        added_by=added_by,
        current_user=current_user,
    )


def remove_asset_from_collection(session: Session, collection_id: UUID, asset_id: UUID) -> None:
    collection = get_collection_or_404(session, collection_id)
    membership = session.execute(
        select(CollectionAsset).where(CollectionAsset.collection_id == collection.id, CollectionAsset.asset_id == asset_id)
    ).scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset is not part of this collection.")
    session.delete(membership)
