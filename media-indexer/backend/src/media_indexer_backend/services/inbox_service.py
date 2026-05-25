from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from media_indexer_backend.core.config import get_settings
from media_indexer_backend.models.enums import MediaType, ScanStatus
from media_indexer_backend.models.tables import Asset, InboxItem, ScanJob, Source, SourceStatus, User
from media_indexer_backend.schemas.inbox import InboxItemRead
from media_indexer_backend.services.asset_service import _asset_summary
from media_indexer_backend.services.metadata import detect_media_type, guess_mime_type
from media_indexer_backend.services.path_safety import normalize_relative_path, resolve_asset_path, resolve_writable_directory_path
from media_indexer_backend.services.scan_service import queue_scan
from media_indexer_backend.services.source_service import get_source_or_404


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def inbox_item_read(item: InboxItem) -> InboxItemRead:
    return InboxItemRead(
        id=item.id,
        filename=item.filename,
        inbox_path=item.inbox_path,
        file_size=item.file_size,
        phash=item.phash,
        clip_distance_min=item.clip_distance_min,
        nearest_asset_id=item.nearest_asset_id,
        status=item.status,
        target_source_id=item.target_source_id,
        target_source_name=item.target_source.name if item.target_source is not None else None,
        created_at=item.created_at,
        reviewed_at=item.reviewed_at,
        reviewed_by=item.reviewed_by,
        error_message=item.error_message,
        thumbnail_url=f"/inbox/{item.id}/thumbnail",
    )


def _upload_source(session: Session) -> Source:
    settings = get_settings()
    source = session.execute(select(Source).where(Source.name == settings.upload_source_name)).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload source is not available.")
    return source


def _default_target_source(session: Session) -> Source | None:
    settings = get_settings()
    if not settings.inbox_default_target_source:
        return None
    return session.execute(
        select(Source).where(Source.root_path == str(Path(settings.inbox_default_target_source).resolve(strict=False)))
    ).scalar_one_or_none()


def list_inbox_items(session: Session, *, status_filter: str | None = None) -> list[InboxItemRead]:
    query = select(InboxItem).order_by(InboxItem.created_at.desc())
    if status_filter:
        query = query.where(InboxItem.status == status_filter)
    items = session.execute(query).scalars().all()
    return [inbox_item_read(item) for item in items]


def get_inbox_item_or_404(session: Session, item_id: UUID) -> InboxItem:
    item = session.get(InboxItem, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inbox item not found.")
    return item


def ingest_uploads_to_inbox(
    session: Session,
    *,
    folder: str | None,
    files: list[UploadFile],
) -> list[InboxItem]:
    source = _upload_source(session)
    default_target = _default_target_source(session)
    target_directory, normalized_folder = resolve_writable_directory_path(source.root_path, folder)
    target_directory.mkdir(parents=True, exist_ok=True)

    created: list[InboxItem] = []
    for upload in files:
        filename = Path(upload.filename or "").name.strip()
        if not filename:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file must have a filename.")
        media_type = detect_media_type(Path(filename), upload.content_type or guess_mime_type(Path(filename)))
        if media_type == MediaType.UNKNOWN:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{filename} is not a supported media file.")
        content = upload.file.read()
        if not content:
            continue

        relative_path = normalize_relative_path(f"{normalized_folder}/{filename}" if normalized_folder else filename)
        destination = target_directory / filename
        suffix = destination.suffix
        stem = destination.stem
        counter = 1
        while destination.exists():
            destination = target_directory / f"{stem}-{counter}{suffix}"
            relative_path = normalize_relative_path(
                f"{normalized_folder}/{destination.name}" if normalized_folder else destination.name
            )
            counter += 1
        destination.write_bytes(content)
        item = InboxItem(
            filename=destination.name,
            inbox_path=relative_path,
            file_size=len(content),
            status="pending",
            target_source_id=default_target.id if default_target is not None else None,
        )
        session.add(item)
        session.flush()
        created.append(item)
    if not created:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No file content was uploaded.")
    return created


def approve_inbox_item(
    session: Session,
    item_id: UUID,
    *,
    current_user: User,
    target_source_id: UUID | None = None,
) -> ScanJob | None:
    item = get_inbox_item_or_404(session, item_id)
    if item.status not in {"pending", "approved"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only pending inbox items can be approved.")

    resolved_target_source_id = target_source_id or item.target_source_id
    if resolved_target_source_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A target source is required before approving this inbox item.",
        )
    target_source = get_source_or_404(session, resolved_target_source_id)
    upload_source = _upload_source(session)
    source_path = resolve_asset_path(upload_source.root_path, item.inbox_path)
    destination_dir, _ = resolve_writable_directory_path(target_source.root_path, None)
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination_path = destination_dir / item.filename
    suffix = destination_path.suffix
    stem = destination_path.stem
    counter = 1
    while destination_path.exists():
        destination_path = destination_dir / f"{stem}-{counter}{suffix}"
        counter += 1
    shutil.copy2(source_path, destination_path)

    item.status = "imported"
    item.reviewed_at = utcnow()
    item.reviewed_by = current_user.id
    item.target_source_id = target_source.id
    source_path.unlink(missing_ok=True)

    active_job = session.execute(
        select(ScanJob).where(
            ScanJob.source_id == target_source.id,
            ScanJob.status.in_([ScanStatus.QUEUED, ScanStatus.RUNNING]),
        )
    ).scalar_one_or_none()
    if active_job:
        session.delete(item)
        session.flush()
        return active_job

    job = queue_scan(session, target_source.id)
    session.delete(item)
    session.flush()
    return job


def reject_inbox_item(session: Session, item_id: UUID, *, current_user: User) -> InboxItem:
    item = get_inbox_item_or_404(session, item_id)
    upload_source = _upload_source(session)
    try:
        resolve_asset_path(upload_source.root_path, item.inbox_path).unlink(missing_ok=True)
    except HTTPException:
        pass
    item.status = "rejected"
    item.reviewed_at = utcnow()
    item.reviewed_by = current_user.id
    session.flush()
    return item


def inbox_thumbnail_path(session: Session, item_id: UUID) -> Path:
    item = get_inbox_item_or_404(session, item_id)
    upload_source = _upload_source(session)
    return resolve_asset_path(upload_source.root_path, item.inbox_path)


def inbox_compare_payload(session: Session, item_id: UUID, *, current_user: User):
    item = get_inbox_item_or_404(session, item_id)
    nearest_asset = session.get(Asset, item.nearest_asset_id) if item.nearest_asset_id else None
    return {
        "item": inbox_item_read(item),
        "nearest_asset": _asset_summary(nearest_asset, user_id=current_user.id) if nearest_asset is not None else None,
    }
