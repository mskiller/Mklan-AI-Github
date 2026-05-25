from __future__ import annotations

from uuid import UUID
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import base64
import json

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import Float, cast, select
from sqlalchemy.orm import Session

from media_indexer_backend.api.dependencies import get_session, require_authenticated, require_enabled_module
from media_indexer_backend.core.config import get_settings
from media_indexer_backend.models.tables import Asset, AssetMetadata
from media_indexer_backend.models.tables import User
from media_indexer_backend.models.enums import MatchType, MediaType, ReviewStatus
from media_indexer_backend.schemas.asset import AssetBrowseResponse, AssetDetail, AssetListResponse, BulkAnnotateRequest, SimilarAsset
from media_indexer_backend.services.annotation_service import bulk_annotate_assets
from media_indexer_backend.services.asset_service import _allowed_source_ids, _apply_source_scope, browse_assets, get_asset_detail, get_asset_or_404, get_similar_assets, search_assets, search_similar_by_image
from media_indexer_backend.services.audit import record_audit_event
from media_indexer_backend.services.deepzoom import deepzoom_manifest_absolute_path, deepzoom_tile_absolute_path, deepzoom_tiles_absolute_dir
from media_indexer_backend.services.image_service import ensure_cached_resized_image
from media_indexer_backend.services.path_safety import resolve_asset_path
from media_indexer_backend.services.workflow_export import build_workflow_export
from media_indexer_backend.services.extractors import extract_png_metadata_from_file
from media_indexer_backend.services.workflow_extractor import workflow_extractor
from media_indexer_backend.services.metadata import normalize_metadata, sanitize_json_value
from media_indexer_backend.services.webhook_service import dispatch_webhook_event


router = APIRouter(tags=["assets"])


def _normalize_openai_base_url(endpoint: str) -> str:
    parsed = urlparse((endpoint or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Vision LLM endpoint must be an http(s) URL.")
    hostname = (parsed.hostname or "").lower()
    netloc = parsed.netloc
    if Path("/.dockerenv").exists() and hostname in {"127.0.0.1", "localhost"}:
        netloc = parsed.netloc.replace(parsed.hostname or hostname, "host.docker.internal", 1)
    return urlunparse((parsed.scheme, netloc, parsed.path.rstrip("/"), "", "", "")).rstrip("/")


def _extract_chat_text(payload: dict) -> str | None:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message") if isinstance(first, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content.strip() or None
    if isinstance(content, list):
        parts = [part.get("text") for part in content if isinstance(part, dict) and isinstance(part.get("text"), str)]
        text = "\n".join(part.strip() for part in parts if part.strip())
        return text or None
    return None


@router.get("/assets", response_model=AssetListResponse)
def get_assets(
    q: str | None = None,
    source_id: UUID | None = None,
    media_type: str | None = None,
    caption: str | None = None,
    ocr_text: str | None = None,
    camera_make: str | None = None,
    camera_model: str | None = None,
    year: int | None = None,
    width_min: int | None = None,
    width_max: int | None = None,
    height_min: int | None = None,
    height_max: int | None = None,
    duration_min: float | None = None,
    duration_max: float | None = None,
    has_gps: bool | None = None,
    tags: str | None = None,
    auto_tags: str | None = None,
    exclude_tags: str | None = None,
    min_rating: int | None = Query(default=None, ge=1, le=5),
    review_status: ReviewStatus | None = None,
    flagged: bool | None = None,
    sort: str = "relevance",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=100),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> AssetListResponse:
    return search_assets(
        session,
        q=q,
        source_id=source_id,
        media_type=media_type,
        caption=caption,
        ocr_text=ocr_text,
        camera_make=camera_make,
        camera_model=camera_model,
        year=year,
        width_min=width_min,
        width_max=width_max,
        height_min=height_min,
        height_max=height_max,
        duration_min=duration_min,
        duration_max=duration_max,
        has_gps=has_gps,
        tags=[value.strip() for value in (tags or "").split(",") if value.strip()],
        auto_tags=[value.strip() for value in (auto_tags or "").split(",") if value.strip()],
        exclude_tags=[value.strip() for value in (exclude_tags or "").split(",") if value.strip()],
        min_rating=min_rating,
        review_status=review_status,
        flagged=flagged,
        sort=sort,
        page=page,
        page_size=page_size,
        current_user=current_user,
    )


@router.get("/assets/browse", response_model=AssetBrowseResponse)
def get_assets_browse(
    source_id: UUID | None = None,
    exclude_tags: str | None = None,
    min_rating: int | None = Query(default=None, ge=1, le=5),
    review_status: ReviewStatus | None = None,
    flagged: bool | None = None,
    sort: str = "modified_at",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=36, ge=1, le=100),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> AssetBrowseResponse:
    return browse_assets(
        session,
        source_id=source_id,
        exclude_tags=[value.strip() for value in (exclude_tags or "").split(",") if value.strip()],
        min_rating=min_rating,
        review_status=review_status,
        flagged=flagged,
        sort=sort,
        page=page,
        page_size=page_size,
        current_user=current_user,
    )


@router.get("/assets/geo")
def get_assets_geo(
    bbox: str | None = None,
    session: Session = Depends(get_session),
    _: None = Depends(require_enabled_module("geo")),
    current_user: User = Depends(require_authenticated),
):
    normalized = AssetMetadata.normalized_json
    query = (
        select(Asset)
        .join(AssetMetadata, AssetMetadata.asset_id == Asset.id)
        .options()
    )
    query = query.where(normalized["gps_latitude"].astext.is_not(None), normalized["gps_longitude"].astext.is_not(None))
    if bbox:
        min_lon, min_lat, max_lon, max_lat = [float(value.strip()) for value in bbox.split(",")]
        query = query.where(
            cast(normalized["gps_longitude"].astext, Float) >= min_lon,
            cast(normalized["gps_longitude"].astext, Float) <= max_lon,
            cast(normalized["gps_latitude"].astext, Float) >= min_lat,
            cast(normalized["gps_latitude"].astext, Float) <= max_lat,
        )
    query = _apply_source_scope(query, _allowed_source_ids(session, current_user))
    assets = session.execute(query.limit(10000)).scalars().all()
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [
                        float(asset.metadata_record.normalized_json.get("gps_longitude")),
                        float(asset.metadata_record.normalized_json.get("gps_latitude")),
                    ],
                },
                "properties": {
                    "id": str(asset.id),
                    "thumbnail_url": f"/assets/{asset.id}/preview" if asset.preview_path else None,
                    "filename": asset.filename,
                    "taken_at": asset.created_at.isoformat() if asset.created_at else None,
                },
            }
            for asset in assets
            if asset.metadata_record is not None
        ],
    }


@router.get("/assets/{asset_id}", response_model=AssetDetail)
def get_asset(
    asset_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> AssetDetail:
    return get_asset_detail(session, asset_id, current_user=current_user)


@router.post("/assets/{asset_id}/vision-llm")
def post_asset_vision_llm(
    asset_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> dict:
    asset = get_asset_or_404(session, asset_id, current_user=current_user)
    if asset.media_type != MediaType.IMAGE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Vision LLM analysis only supports images.")

    settings = get_settings()
    base_url = _normalize_openai_base_url(settings.vision_llm_endpoint)
    image_path = ensure_cached_resized_image(asset, asset.source, width=1536, height=1536, quality=82, fmt="jpeg")
    image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    prompt = (
        "Analyze this image for a media library. Return concise, useful details for search and curation: "
        "visible subjects, scene, style, mood, notable objects, quality issues, and any text you can read. "
        "If it appears to be AI generated, mention generation clues. Keep the answer under 180 words."
    )
    body = {
        "model": settings.vision_llm_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                ],
            }
        ],
        "temperature": 0.2,
        "max_tokens": 320,
    }

    try:
        with httpx.Client(timeout=settings.vision_llm_timeout_seconds) as client:
            response = client.post(f"{base_url}/chat/completions", json=body)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Vision LLM request failed: {exc}") from exc

    analysis = _extract_chat_text(payload)
    if not analysis:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Vision LLM did not return readable text.")

    metadata_record = asset.metadata_record or session.get(AssetMetadata, asset.id)
    normalized = dict(metadata_record.normalized_json if metadata_record else {})
    normalized.update(
        sanitize_json_value(
            {
                "vision_llm_analysis": analysis,
                "vision_llm_source": f"koboldcpp:{settings.vision_llm_model}",
                "vision_llm_endpoint": base_url,
                "vision_llm_updated_at": datetime.now(tz=timezone.utc).isoformat(),
            }
        )
    )
    if metadata_record is None:
        metadata_record = AssetMetadata(asset_id=asset.id, raw_json={}, normalized_json=normalized, extracted_at=datetime.now(tz=timezone.utc))
        asset.metadata_record = metadata_record
        session.add(metadata_record)
    else:
        metadata_record.normalized_json = normalized
        metadata_record.extracted_at = datetime.now(tz=timezone.utc)
    record_audit_event(
        session,
        actor=current_user.username,
        action="asset.vision_llm",
        resource_type="asset",
        resource_id=asset.id,
        details={"endpoint": base_url, "model": settings.vision_llm_model},
    )
    session.commit()
    dispatch_webhook_event("asset.updated", {"asset_id": str(asset.id), "action": "vision_llm"})
    return {"ok": True, "analysis": analysis, "source": f"koboldcpp:{settings.vision_llm_model}"}


@router.get("/assets/{asset_id}/preview")
def get_asset_preview(
    asset_id: UUID,
    variant: str | None = Query(default=None),
    index: int | None = Query(default=None, ge=0, le=20),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> FileResponse:
    asset = get_asset_or_404(session, asset_id, current_user=current_user)
    settings = get_settings()
    if variant == "waveform" and asset.waveform_preview_path:
        waveform_path = (settings.preview_root_path / asset.waveform_preview_path).resolve(strict=False)
        if waveform_path.is_relative_to(settings.preview_root_path) and waveform_path.exists():
            return FileResponse(waveform_path)
    if variant == "keyframe" and asset.video_keyframes and index is not None and 0 <= index < len(asset.video_keyframes):
        keyframe_path = (settings.preview_root_path / asset.video_keyframes[index]).resolve(strict=False)
        if keyframe_path.is_relative_to(settings.preview_root_path) and keyframe_path.exists():
            return FileResponse(keyframe_path)
    if asset.preview_path:
        preview_path = (settings.preview_root_path / asset.preview_path).resolve(strict=False)
        if preview_path.is_relative_to(settings.preview_root_path) and preview_path.exists():
            return FileResponse(preview_path)

    original_path = resolve_asset_path(asset.source.root_path, asset.relative_path)
    return FileResponse(original_path)


@router.get("/assets/{asset_id}/deepzoom.dzi")
def get_asset_deepzoom_manifest(
    asset_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> FileResponse:
    get_asset_or_404(session, asset_id, current_user=current_user)
    manifest_path = deepzoom_manifest_absolute_path(asset_id)
    if not manifest_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deep zoom manifest is not available for this asset.")
    return FileResponse(manifest_path, media_type="application/xml")


@router.get("/assets/{asset_id}/deepzoom/{tile_path:path}")
def get_asset_deepzoom_tile(
    asset_id: UUID,
    tile_path: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> FileResponse:
    get_asset_or_404(session, asset_id, current_user=current_user)
    tiles_root = deepzoom_tiles_absolute_dir(asset_id)
    requested_path = deepzoom_tile_absolute_path(asset_id, tile_path)
    if not requested_path.is_relative_to(tiles_root) or not requested_path.exists() or not requested_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deep zoom tile was not found.")
    return FileResponse(requested_path)


@router.get("/assets/{asset_id}/content")
def get_asset_content(
    asset_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> FileResponse:
    asset = get_asset_or_404(session, asset_id, current_user=current_user)
    original_path = resolve_asset_path(asset.source.root_path, asset.relative_path)
    return FileResponse(original_path, filename=asset.filename)


def _parse_range_header(range_header: str | None, file_size: int) -> tuple[int, int] | None:
    if not range_header or not range_header.startswith("bytes="):
        return None
    raw_range = range_header.replace("bytes=", "", 1).split(",", 1)[0]
    start_text, end_text = raw_range.split("-", 1)
    start = int(start_text) if start_text else 0
    end = int(end_text) if end_text else file_size - 1
    start = max(0, min(start, file_size - 1))
    end = max(start, min(end, file_size - 1))
    return (start, end)


@router.get("/assets/{asset_id}/stream")
def get_asset_stream(
    asset_id: UUID,
    range: str | None = Header(default=None),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
):
    asset = get_asset_or_404(session, asset_id, current_user=current_user)
    original_path = resolve_asset_path(asset.source.root_path, asset.relative_path)
    file_size = original_path.stat().st_size
    byte_range = _parse_range_header(range, file_size)
    if byte_range is None:
        return FileResponse(original_path, media_type=asset.mime_type, headers={"Accept-Ranges": "bytes"})

    start, end = byte_range

    def iter_file():
        with original_path.open("rb") as handle:
            handle.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = handle.read(min(remaining, 64 * 1024))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(
        iter_file(),
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        media_type=asset.mime_type,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(end - start + 1),
            "Content-Disposition": "inline",
        },
    )


@router.get("/assets/{asset_id}/image")
def get_asset_image(
    asset_id: UUID,
    w: int | None = Query(default=None, ge=64, le=4096),
    h: int | None = Query(default=None, ge=64, le=4096),
    quality: int = Query(default=82, ge=40, le=100),
    fmt: str = Query(default="webp", pattern="^(webp|jpeg)$"),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> FileResponse:
    asset = get_asset_or_404(session, asset_id, current_user=current_user)
    cache_path = ensure_cached_resized_image(
        asset,
        asset.source,
        width=w,
        height=h,
        quality=quality,
        fmt=fmt,
    )
    return FileResponse(cache_path, media_type=f"image/{fmt}", headers={"Cache-Control": "private, max-age=86400"})


@router.get("/assets/{asset_id}/similar", response_model=list[SimilarAsset])
def get_asset_similar(
    asset_id: UUID,
    type: MatchType,
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> list[SimilarAsset]:
    return get_similar_assets(session, asset_id, type, limit, current_user=current_user)


@router.get("/assets/{asset_id}/search-similar-by-image", response_model=list[SimilarAsset])
def get_asset_similar_by_image(
    asset_id: UUID,
    limit: int = Query(default=24, ge=1, le=100),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> list[SimilarAsset]:
    return search_similar_by_image(session, asset_id, limit, current_user=current_user)


@router.post("/assets/bulk-annotate", status_code=status.HTTP_204_NO_CONTENT)
def post_assets_bulk_annotate(
    payload: BulkAnnotateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> Response:
    bulk_annotate_assets(session, payload, current_user)
    record_audit_event(
        session,
        actor=current_user.username,
        action="asset.bulk_annotate",
        resource_type="asset_annotation",
        details={
            "asset_ids": [str(asset_id) for asset_id in payload.asset_ids],
            **payload.model_dump(exclude_none=True, exclude={"asset_ids"}),
        },
    )
    session.commit()
    for asset_id in payload.asset_ids:
        dispatch_webhook_event("asset.updated", {"asset_id": str(asset_id), "action": "bulk_annotate"})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/assets/{asset_id}/workflow/download")
def get_asset_workflow_download(
    asset_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> Response:
    asset = get_asset_or_404(session, asset_id, current_user=current_user)
    raw_metadata = asset.metadata_record.raw_json if asset.metadata_record else {}
    normalized_metadata = asset.metadata_record.normalized_json if asset.metadata_record else {}
    payload = build_workflow_export(
        asset_id=str(asset.id),
        filename=asset.filename,
        normalized_metadata=normalized_metadata,
        raw_metadata=raw_metadata,
    )
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="No exportable workflow is available for this asset."
        )
    filename = f"{asset.filename.rsplit('.', 1)[0]}-workflow.json"
    return Response(
        content=json.dumps(payload, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/assets/{asset_id}/workflow/extract-from-file")
def extract_asset_workflow_from_file(
    asset_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> Response:
    """
    Re-reads the asset file directly and extracts embedded workflow/prompt data.
    Unlike /workflow/download (which reads from DB), this always goes to the file.
    Returns 404 if no workflow is found in the file.
    """
    asset = get_asset_or_404(session, asset_id, current_user=current_user)
    original_path = resolve_asset_path(asset.source.root_path, asset.relative_path)
    
    # Re-run extraction on the live file
    raw = extract_png_metadata_from_file(original_path)
    normalized = normalize_metadata(media_type=asset.media_type, exif=raw, ffprobe={})
    
    payload = build_workflow_export(
        asset_id=str(asset.id),
        filename=asset.filename,
        normalized_metadata=normalized,
        raw_metadata=raw,
    )
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No exportable workflow found in this file.",
        )
    
    filename = f"{asset.filename.rsplit('.', 1)[0]}-workflow.json"
    return Response(
        content=json.dumps(payload, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/assets/{asset_id}/workflow/visual-extract")
def trigger_visual_workflow_extraction(
    asset_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> dict:
    """
    Trigger Tesseract-based visual workflow extraction from the asset image.
    Stores structure in DB and returns it.
    """
    asset = get_asset_or_404(session, asset_id, current_user=current_user)
    original_path = resolve_asset_path(asset.source.root_path, asset.relative_path)
    
    # 1. Run extraction
    result = workflow_extractor.extract_visual_workflow(original_path)
    
    # 2. Persist to asset
    asset.visual_workflow_json = {
        "nodes": result.get("nodes", []),
        "edges": result.get("edges", [])
    }
    asset.visual_workflow_confidence = result.get("confidence", 0)
    asset.visual_workflow_updated_at = datetime.now(tz=timezone.utc)
    
    session.commit()
    
    return result
