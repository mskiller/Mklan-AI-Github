from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from fastapi import UploadFile
from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from media_indexer_backend.core.config import get_settings
from media_indexer_backend.models.enums import MediaType, ScanStatus, SourceStatus, SourceType, UserRole
from media_indexer_backend.models.tables import Asset, ScanJob, Source, User
from media_indexer_backend.schemas.source import (
    SourceBreadcrumb,
    SourceBrowseEntry,
    SourceBrowseInspect,
    SourceBrowseResponse,
    SourceCreate,
    SourceRead,
    SourceUploadRead,
    SourceTreeFileEntry,
    SourceTreeResponse,
)
from media_indexer_backend.services.extractors import extract_exiftool
from media_indexer_backend.services.metadata import METADATA_SCHEMA_VERSION, detect_media_type, guess_mime_type, metadata_version
from media_indexer_backend.services.path_safety import display_source_root, normalize_relative_path, resolve_asset_path, resolve_directory_path, resolve_writable_directory_path, validate_source_root
from media_indexer_backend.services.metadata import display_prompt_from_normalized, normalize_metadata, prompt_excerpt, prompt_tag_string, prompt_tags_from_normalized
from media_indexer_backend.services.user_service import capabilities_for_user


def _allowed_source_ids(session: Session, current_user: User | None):
    if current_user is None:
        return None
    allowed = capabilities_for_user(session, current_user).allowed_source_ids
    return None if allowed == "all" else {str(value) for value in allowed}


def _assert_source_access(session: Session, current_user: User | None, source: Source) -> None:
    allowed_source_ids = _allowed_source_ids(session, current_user)
    if allowed_source_ids is not None and str(source.id) not in allowed_source_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found.")


def list_sources(session: Session, current_user: User | None = None) -> list[Source]:
    sources = session.execute(select(Source).order_by(Source.name)).scalars().all()
    allowed_source_ids = _allowed_source_ids(session, current_user)
    if allowed_source_ids is None:
        return sources
    return [source for source in sources if str(source.id) in allowed_source_ids]


def source_read_for_user(source: Source, current_user: User) -> SourceRead:
    is_admin = current_user.role == UserRole.ADMIN
    display_root_path = display_source_root(source.root_path) if is_admin else f"{source.name} / approved root"
    return SourceRead(
        id=source.id,
        name=source.name,
        type=source.type,
        root_path=source.root_path if is_admin else None,
        display_root_path=display_root_path,
        status=source.status,
        last_scan_at=source.last_scan_at,
        created_at=source.created_at,
    )


def reconcile_source_statuses(session: Session) -> bool:
    active_source_ids = {
        source_id
        for source_id in session.execute(
            select(ScanJob.source_id).where(
                ScanJob.source_id.is_not(None),
                ScanJob.status.in_([ScanStatus.QUEUED, ScanStatus.RUNNING]),
            )
        ).scalars()
        if source_id is not None
    }

    changed = False
    for source in session.execute(select(Source)).scalars():
        if source.id in active_source_ids:
            if source.status != SourceStatus.SCANNING:
                source.status = SourceStatus.SCANNING
                changed = True
        elif source.status == SourceStatus.SCANNING:
            source.status = SourceStatus.READY
            changed = True

    if changed:
        session.flush()
    return changed


def get_source_or_404(session: Session, source_id, current_user: User | None = None) -> Source:
    source = session.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found.")
    _assert_source_access(session, current_user, source)
    return source


def create_source(session: Session, payload: SourceCreate) -> Source:
    if payload.type != SourceType.MOUNTED_FS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The MVP only supports mounted_fs sources.",
        )

    root_path = validate_source_root(payload.root_path)
    existing = session.execute(
        select(Source).where(or_(Source.name == payload.name, Source.root_path == root_path))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Source name or root path already exists.")

    source = Source(name=payload.name, type=payload.type, root_path=root_path)
    session.add(source)
    session.flush()
    return source


def _ensure_system_source(session: Session, *, name: str, root_path: str) -> None:
    source_root = Path(root_path).resolve(strict=False)
    source_root.mkdir(parents=True, exist_ok=True)
    validated_root = validate_source_root(str(source_root))
    existing = session.execute(
        select(Source).where(or_(Source.name == name, Source.root_path == validated_root))
    ).scalar_one_or_none()
    if existing:
        existing.name = name
        if existing.root_path != validated_root:
            existing.root_path = validated_root
        if existing.type != SourceType.MOUNTED_FS:
            existing.type = SourceType.MOUNTED_FS
        if existing.status == SourceStatus.DISABLED:
            existing.status = SourceStatus.READY
        session.flush()
        return

    session.add(
        Source(
            name=name,
            type=SourceType.MOUNTED_FS,
            root_path=validated_root,
            status=SourceStatus.READY,
        )
    )
    session.flush()


def ensure_system_sources(session: Session) -> None:
    settings = get_settings()
    _ensure_system_source(session, name=settings.upload_source_name, root_path=settings.upload_source_root)
    _ensure_system_source(session, name=settings.generated_source_name, root_path=settings.generated_source_root)


def delete_source(session: Session, source_id) -> Source:
    source = get_source_or_404(session, source_id)
    active_job = session.execute(
        select(ScanJob).where(
            ScanJob.source_id == source_id,
            ScanJob.status.in_([ScanStatus.QUEUED, ScanStatus.RUNNING]),
        )
    ).scalar_one_or_none()
    if active_job:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A scan job is still active for this source.")

    session.delete(source)
    return source


def _breadcrumbs(current_path: str) -> list[SourceBreadcrumb]:
    breadcrumbs = [SourceBreadcrumb(label="Root", path="")]
    if not current_path:
        return breadcrumbs

    parts = [part for part in current_path.split("/") if part]
    for index in range(len(parts)):
        partial = "/".join(parts[: index + 1])
        breadcrumbs.append(SourceBreadcrumb(label=parts[index], path=partial))
    return breadcrumbs


def _modified_at(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def _annotation_payload(asset: Asset | None, user_id) -> dict | None:
    if asset is None or user_id is None:
        return None
    for annotation in asset.annotations:
        if annotation.user_id == user_id:
            return {
                "id": annotation.id,
                "user_id": annotation.user_id,
                "rating": annotation.rating,
                "review_status": annotation.review_status,
                "note": annotation.note,
                "flagged": annotation.flagged,
                "created_at": annotation.created_at,
                "updated_at": annotation.updated_at,
            }
    return None


def browse_source(session: Session, source_id, relative_path: str | None, current_user: User | None = None) -> SourceBrowseResponse:
    source = get_source_or_404(session, source_id, current_user=current_user)
    directory_path, current_path = resolve_directory_path(source.root_path, relative_path)
    root = Path(source.root_path).resolve(strict=True)

    directory_entries: list[SourceBrowseEntry] = []
    file_entries: list[tuple[Path, str, str, MediaType]] = []

    for child in sorted(directory_path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
        child_relative_path = child.relative_to(root).as_posix()
        if child.is_dir():
            directory_entries.append(
                SourceBrowseEntry(
                    name=child.name,
                    relative_path=child_relative_path,
                    entry_type="directory",
                    modified_at=_modified_at(child),
                )
            )
            continue

        if not child.is_file():
            continue

        mime_type = guess_mime_type(child)
        media_type = detect_media_type(child, mime_type)
        if media_type == MediaType.UNKNOWN:
            continue
        file_entries.append((child, child_relative_path, mime_type, media_type))

    indexed_assets: dict[str, Asset] = {}
    if file_entries:
        indexed_assets = {
            asset.relative_path: asset
            for asset in session.execute(
                select(Asset).where(
                    Asset.source_id == source.id,
                    Asset.relative_path.in_([relative_path for _, relative_path, _, _ in file_entries]),
                )
                .options(selectinload(Asset.metadata_record), selectinload(Asset.annotations))
            ).scalars()
        }

    entries = directory_entries
    for child, child_relative_path, mime_type, media_type in file_entries:
        indexed_asset = indexed_assets.get(child_relative_path)
        quoted_path = quote(child_relative_path, safe="/")
        content_url = f"/sources/{source.id}/browse/content?path={quoted_path}"
        preview_url = None
        if indexed_asset and indexed_asset.preview_path:
            preview_url = f"/assets/{indexed_asset.id}/preview"
        elif media_type == MediaType.IMAGE:
            preview_url = content_url
        if indexed_asset:
            normalized = indexed_asset.metadata_record.normalized_json if indexed_asset.metadata_record else {}
            index_state = (
                "metadata_refresh_pending"
                if metadata_version(normalized) < METADATA_SCHEMA_VERSION
                else "indexed"
            )
        else:
            index_state = "processing" if source.status == SourceStatus.SCANNING else "live_browse"
        entries.append(
            SourceBrowseEntry(
                name=child.name,
                relative_path=child_relative_path,
                entry_type="file",
                media_type=media_type,
                mime_type=mime_type,
                size_bytes=child.stat().st_size,
                modified_at=_modified_at(child),
                indexed_asset_id=indexed_asset.id if indexed_asset else None,
                index_state=index_state,
                preview_url=preview_url,
                content_url=content_url,
            )
        )

    parent_path = None
    if current_path:
        parent_path = "/".join(current_path.split("/")[:-1]) or None
    return SourceBrowseResponse(
        source_id=source.id,
        current_path=current_path,
        parent_path=parent_path,
        breadcrumbs=_breadcrumbs(current_path),
        entries=entries,
    )


def inspect_source_entry(session: Session, source_id, relative_path: str, current_user: User | None = None) -> SourceBrowseInspect:
    source = get_source_or_404(session, source_id, current_user=current_user)
    asset_path = resolve_asset_path(source.root_path, relative_path)
    mime_type = guess_mime_type(asset_path)
    media_type = detect_media_type(asset_path, mime_type)
    if media_type != MediaType.IMAGE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only images are supported by source inspection overlays in V4.",
        )

    indexed_asset = session.execute(
        select(Asset)
        .where(Asset.source_id == source.id, Asset.relative_path == relative_path)
        .options(selectinload(Asset.metadata_record), selectinload(Asset.annotations))
    ).scalar_one_or_none()

    if indexed_asset:
        normalized = indexed_asset.metadata_record.normalized_json if indexed_asset.metadata_record else {}
        tags = prompt_tags_from_normalized(normalized)
        return SourceBrowseInspect(
            source_id=source.id,
            relative_path=relative_path,
            indexed_asset_id=indexed_asset.id,
            index_state="metadata_refresh_pending" if metadata_version(normalized) < METADATA_SCHEMA_VERSION else "indexed",
            preview_url=f"/assets/{indexed_asset.id}/preview" if indexed_asset.preview_path else f"/sources/{source.id}/browse/content?path={quote(relative_path, safe='/')}",
            content_url=f"/sources/{source.id}/browse/content?path={quote(relative_path, safe='/')}",
            blur_hash=indexed_asset.blur_hash,
            deepzoom_available=False,
            deepzoom_url=None,
            width=normalized.get("width") if isinstance(normalized.get("width"), int) else None,
            height=normalized.get("height") if isinstance(normalized.get("height"), int) else None,
            generator=normalized.get("generator") if isinstance(normalized.get("generator"), str) else None,
            prompt_excerpt=prompt_excerpt(display_prompt_from_normalized(normalized)),
            prompt_tags=tags,
            prompt_tag_string=prompt_tag_string(tags),
            annotation=_annotation_payload(indexed_asset, current_user.id if current_user else None),
        )

    exif = extract_exiftool(asset_path)
    normalized = normalize_metadata(media_type=MediaType.IMAGE, exif=exif, ffprobe=None)
    tags = prompt_tags_from_normalized(normalized)
    return SourceBrowseInspect(
        source_id=source.id,
        relative_path=relative_path,
        indexed_asset_id=None,
        index_state="processing" if source.status == SourceStatus.SCANNING else "live_browse",
        preview_url=f"/sources/{source.id}/browse/content?path={quote(relative_path, safe='/')}",
        content_url=f"/sources/{source.id}/browse/content?path={quote(relative_path, safe='/')}",
        blur_hash=None,
        deepzoom_available=False,
        deepzoom_url=None,
        width=normalized.get("width") if isinstance(normalized.get("width"), int) else None,
        height=normalized.get("height") if isinstance(normalized.get("height"), int) else None,
        generator=normalized.get("generator") if isinstance(normalized.get("generator"), str) else None,
        prompt_excerpt=prompt_excerpt(display_prompt_from_normalized(normalized)),
        prompt_tags=tags,
        prompt_tag_string=prompt_tag_string(tags),
        annotation=None,
    )


def get_source_tree(session: Session, source_id, path: str = "", current_user: User | None = None) -> SourceTreeResponse:
    source = get_source_or_404(session, source_id, current_user=current_user)
    directory_path, normalized_path = resolve_directory_path(source.root_path, path or None)
    entries = list(directory_path.iterdir())
    dir_names = sorted(child.name for child in entries if child.is_dir() and not child.name.startswith("."))
    file_names = sorted(child.name for child in entries if child.is_file())

    relative_files = [
        (directory_path / name).relative_to(Path(source.root_path).resolve(strict=True)).as_posix()
        for name in file_names
    ]
    indexed_paths = set()
    if relative_files:
        indexed_paths = set(
            session.execute(
                select(Asset.relative_path).where(
                    Asset.source_id == source.id,
                    Asset.relative_path.in_(relative_files),
                )
            ).scalars()
        )

    return SourceTreeResponse(
        path=normalized_path,
        dirs=dir_names,
        files=[
            SourceTreeFileEntry(name=name, relative_path=relative_path, indexed=relative_path in indexed_paths)
            for name, relative_path in zip(file_names, relative_files, strict=False)
        ],
    )


def _safe_upload_filename(filename: str) -> str:
    candidate = Path(filename).name.strip()
    if not candidate:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file must have a filename.")
    return candidate


def _unique_upload_path(directory: Path, filename: str) -> Path:
    base = Path(filename)
    candidate = directory / base.name
    if not candidate.exists():
        return candidate
    stem = base.stem
    suffix = base.suffix
    return directory / f"{stem}-{uuid4().hex[:8]}{suffix}"


def upload_images_to_source(
    session: Session,
    source_id,
    *,
    folder: str | None,
    files: list[UploadFile],
) -> SourceUploadRead:
    from media_indexer_backend.services.inbox_service import ingest_uploads_to_inbox

    settings = get_settings()
    source = get_source_or_404(session, source_id)
    if source.name != settings.upload_source_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploads are only allowed into the system upload source.")
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select at least one media file to upload.")

    inbox_items = ingest_uploads_to_inbox(session, folder=folder, files=files)

    return SourceUploadRead(
        source_id=source.id,
        folder=normalize_relative_path(folder),
        uploaded_files=[item.inbox_path for item in inbox_items],
        scan_job_id=None,
    )
