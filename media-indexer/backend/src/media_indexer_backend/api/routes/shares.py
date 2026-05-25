from __future__ import annotations

from uuid import UUID
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from media_indexer_backend.api.dependencies import get_session, require_authenticated
from media_indexer_backend.core.config import get_settings
from media_indexer_backend.models.enums import MediaType
from media_indexer_backend.models.tables import ShareLink, Asset, Collection, CollectionAsset, User
from media_indexer_backend.schemas.shares import PublicShareItem, PublicShareResponse, ShareLinkCreate, ShareLinkRead
from media_indexer_backend.services.image_service import ensure_cached_resized_image
from media_indexer_backend.services.path_safety import resolve_asset_path

router = APIRouter(prefix="/share", tags=["share"])


def _get_active_share(session: Session, share_id: str) -> ShareLink:
    share = session.execute(select(ShareLink).where(ShareLink.id == share_id)).scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail="Share link not found")
    if share.expires_at and share.expires_at < datetime.now(tz=timezone.utc):
        raise HTTPException(status_code=410, detail="Share link expired")
    return share


def _share_item(share: ShareLink, asset: Asset) -> PublicShareItem:
    return PublicShareItem(
        id=asset.id,
        filename=asset.filename,
        size_bytes=asset.size_bytes,
        preview_url=f"/share/{share.id}/asset/{asset.id}/preview",
        content_url=f"/share/{share.id}/asset/{asset.id}/content" if share.allow_download else None,
    )


def _asset_for_share(session: Session, share: ShareLink, asset_id: UUID) -> Asset:
    if share.target_type == "asset":
        if UUID(share.target_id) != asset_id:
            raise HTTPException(status_code=404, detail="Asset is not available for this share.")
        asset = session.execute(
            select(Asset)
            .where(Asset.id == asset_id)
            .options(selectinload(Asset.source))
        ).scalar_one_or_none()
    else:
        asset = session.execute(
            select(Asset)
            .join(CollectionAsset, CollectionAsset.asset_id == Asset.id)
            .where(CollectionAsset.collection_id == UUID(share.target_id), Asset.id == asset_id)
            .options(selectinload(Asset.source))
        ).scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset is not available for this share.")
    return asset


def _preview_file_path(asset: Asset, share: ShareLink) -> Path:
    settings = get_settings()
    if asset.preview_path:
        preview_path = (settings.preview_root_path / asset.preview_path).resolve(strict=False)
        if preview_path.is_relative_to(settings.preview_root_path) and preview_path.exists():
            return preview_path
    if asset.media_type == MediaType.IMAGE and asset.source is not None:
        return ensure_cached_resized_image(asset, asset.source, width=1600, height=1600, quality=82, fmt="webp")
    if share.allow_download and asset.source is not None:
        return resolve_asset_path(asset.source.root_path, asset.relative_path)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preview is not available for this asset.")


@router.get("/{share_id}", response_model=PublicShareResponse)
def get_share_content(
    share_id: str,
    session: Session = Depends(get_session),
) -> PublicShareResponse:
    share = _get_active_share(session, share_id)
    share.view_count += 1
    session.commit()
    if share.target_type == "asset":
        asset = session.execute(
            select(Asset)
            .where(Asset.id == UUID(share.target_id))
            .options(selectinload(Asset.source))
        ).scalar_one_or_none()
        if not asset:
            raise HTTPException(status_code=404, detail="Asset no longer exists")
        return PublicShareResponse(
            type="asset",
            label=share.label or asset.filename,
            item=_share_item(share, asset),
            allow_download=share.allow_download,
        )
    if share.target_type == "collection":
        collection = session.execute(
            select(Collection).where(Collection.id == UUID(share.target_id))
        ).scalar_one_or_none()
        if not collection:
            raise HTTPException(status_code=404, detail="Collection no longer exists")
        asset_ids = session.execute(
            select(CollectionAsset.asset_id).where(CollectionAsset.collection_id == collection.id)
        ).scalars().all()
        if not asset_ids:
            return PublicShareResponse(
                type="collection",
                label=share.label or collection.name,
                items=[],
                allow_download=share.allow_download,
            )
        assets = session.execute(
            select(Asset)
            .where(Asset.id.in_(asset_ids))
            .options(selectinload(Asset.source))
            .order_by(Asset.filename)
        ).scalars().all()
        return PublicShareResponse(
            type="collection",
            label=share.label or collection.name,
            items=[_share_item(share, asset) for asset in assets],
            allow_download=share.allow_download,
        )
    raise HTTPException(status_code=400, detail="Invalid share target type")


@router.get("/{share_id}/asset/{asset_id}/preview")
def get_share_asset_preview(
    share_id: str,
    asset_id: UUID,
    session: Session = Depends(get_session),
) -> FileResponse:
    share = _get_active_share(session, share_id)
    asset = _asset_for_share(session, share, asset_id)
    preview_path = _preview_file_path(asset, share)
    media_type = "image/webp" if preview_path.suffix.lower() == ".webp" else None
    return FileResponse(preview_path, media_type=media_type)


@router.get("/{share_id}/asset/{asset_id}/content")
def get_share_asset_content(
    share_id: str,
    asset_id: UUID,
    session: Session = Depends(get_session),
) -> FileResponse:
    share = _get_active_share(session, share_id)
    if not share.allow_download:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Downloads are disabled for this share.")
    asset = _asset_for_share(session, share, asset_id)
    if asset.source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source is no longer available.")
    original_path = resolve_asset_path(asset.source.root_path, asset.relative_path)
    return FileResponse(original_path, filename=asset.filename)


@router.post("", response_model=ShareLinkRead)
def create_share_link(
    payload: ShareLinkCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> ShareLinkRead:
    # Verify target exists
    if payload.target_type == "asset":
        exists = session.scalar(select(Asset.id).where(Asset.id == payload.target_id))
    else:
        exists = session.scalar(select(Collection.id).where(Collection.id == payload.target_id))
        
    if not exists:
        raise HTTPException(status_code=404, detail="Target not found")
        
    share = ShareLink(
        created_by=current_user.id,
        target_type=payload.target_type,
        target_id=str(payload.target_id),
        label=payload.label,
        expires_at=payload.expires_at,
        allow_download=payload.allow_download
    )
    session.add(share)
    session.commit()
    session.refresh(share)
    return ShareLinkRead.model_validate(share)
