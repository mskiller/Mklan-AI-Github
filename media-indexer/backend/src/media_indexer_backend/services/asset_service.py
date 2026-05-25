from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import Float, Integer, and_, case, cast, desc, func, literal, or_, select
from sqlalchemy.orm import Session, aliased, selectinload

from media_indexer_backend.models.enums import MatchType, MediaType, ReviewStatus
from media_indexer_backend.models.tables import Asset, AssetAnnotation, AssetMetadata, AssetSearch, AssetSimilarity, AssetTag, SimilarityLink, TagSuggestion, User
from media_indexer_backend.schemas.asset import (
    AssetAnnotationRead,
    AssetBrowseItem,
    AssetBrowseResponse,
    AssetDetail,
    AssetListResponse,
    AssetSummary,
    SimilarAsset,
    TagCount,
)
from media_indexer_backend.services.metadata import (
    compute_prompt_tag_overlap,
    display_prompt_from_normalized,
    normalized_metadata_for_api,
    prompt_excerpt,
    prompt_tag_string,
    prompt_tags_from_normalized,
    score_from_distance,
)
from media_indexer_backend.services.user_service import capabilities_for_user
from media_indexer_backend.services.workflow_export import build_workflow_export


def _allowed_source_ids(session: Session, current_user: User | None):
    if current_user is None:
        return None
    allowed = capabilities_for_user(session, current_user).allowed_source_ids
    return None if allowed == "all" else list(allowed)


def _apply_source_scope(query, allowed_source_ids):
    if allowed_source_ids is None:
        return query
    if not allowed_source_ids:
        return query.where(literal(False))
    return query.where(Asset.source_id.in_(allowed_source_ids))


def _annotation_for_asset(asset: Asset, user_id: UUID | None) -> AssetAnnotationRead | None:
    if user_id is None:
        return None
    for annotation in asset.annotations:
        if annotation.user_id == user_id:
            return AssetAnnotationRead(
                id=annotation.id,
                user_id=annotation.user_id,
                rating=annotation.rating,
                review_status=annotation.review_status,
                note=annotation.note,
                flagged=annotation.flagged,
                created_at=annotation.created_at,
                updated_at=annotation.updated_at,
            )
    return None


def _is_workflow_export_available(asset: Asset) -> bool:
    # Visual workflow extracted from image (Tesseract OCR pipeline)
    if asset.visual_workflow_json:
        return True
    if not asset.metadata_record:
        return False
    normalized = asset.metadata_record.normalized_json or {}
    raw_meta = asset.metadata_record.raw_json or {}

    # ComfyUI
    if normalized.get("generator") == "comfyui":
        return bool(raw_meta.get("Prompt") or raw_meta.get("Workflow"))
    
    # A1111
    if normalized.get("generator") == "automatic1111":
        return bool(normalized.get("workflow_text"))
    
    return False


def _asset_summary(asset: Asset, user_id: UUID | None = None) -> AssetSummary:
    normalized = normalized_metadata_for_api(asset.metadata_record.normalized_json if asset.metadata_record else {})
    return AssetSummary(
        id=asset.id,
        source_id=asset.source_id,
        relative_path=asset.relative_path,
        filename=asset.filename,
        extension=asset.extension,
        media_type=asset.media_type,
        mime_type=asset.mime_type,
        size_bytes=asset.size_bytes,
        modified_at=asset.modified_at,
        created_at=asset.created_at,
        indexed_at=asset.indexed_at,
        preview_url=f"/assets/{asset.id}/preview" if asset.preview_path else None,
        content_url=f"/assets/{asset.id}/content",
        blur_hash=asset.blur_hash,
        deepzoom_available=False,
        deepzoom_url=None,
        tags=sorted(tag.tag for tag in asset.tags),
        normalized_metadata=normalized,
        caption=normalized.get("caption") if isinstance(normalized.get("caption"), str) else None,
        caption_source=normalized.get("caption_source") if isinstance(normalized.get("caption_source"), str) else None,
        ocr_text=normalized.get("ocr_text") if isinstance(normalized.get("ocr_text"), str) else None,
        ocr_confidence=float(normalized["ocr_confidence"]) if isinstance(normalized.get("ocr_confidence"), (float, int)) else None,
        annotation=_annotation_for_asset(asset, user_id),
        workflow_export_available=_is_workflow_export_available(asset),
        waveform_url=f"/assets/{asset.id}/preview?variant=waveform" if asset.waveform_preview_path else None,
        video_keyframes=[f"/assets/{asset.id}/preview?variant=keyframe&index={index}" for index, _ in enumerate(asset.video_keyframes or [])] or None,
    )


def asset_browse_item(asset: Asset, user_id: UUID | None = None) -> AssetBrowseItem:
    normalized = normalized_metadata_for_api(asset.metadata_record.normalized_json if asset.metadata_record else {})
    tags = prompt_tags_from_normalized(normalized)
    workflow_available = _is_workflow_export_available(asset)
    return AssetBrowseItem(
        id=asset.id,
        source_id=asset.source_id,
        source_name=asset.source.name,
        filename=asset.filename,
        relative_path=asset.relative_path,
        preview_url=f"/assets/{asset.id}/preview" if asset.preview_path else None,
        content_url=f"/assets/{asset.id}/content",
        blur_hash=asset.blur_hash,
        deepzoom_available=False,
        deepzoom_url=None,
        width=normalized.get("width") if isinstance(normalized.get("width"), int) else None,
        height=normalized.get("height") if isinstance(normalized.get("height"), int) else None,
        modified_at=asset.modified_at,
        created_at=asset.created_at,
        size_bytes=asset.size_bytes,
        generator=normalized.get("generator") if isinstance(normalized.get("generator"), str) else None,
        prompt_excerpt=prompt_excerpt(display_prompt_from_normalized(normalized)),
        prompt_tags=tags,
        prompt_tag_string=prompt_tag_string(tags),
        caption=normalized.get("caption") if isinstance(normalized.get("caption"), str) else None,
        ocr_text=normalized.get("ocr_text") if isinstance(normalized.get("ocr_text"), str) else None,
        annotation=_annotation_for_asset(asset, user_id),
        workflow_export_available=workflow_available,
        media_type=asset.media_type,
        waveform_url=f"/assets/{asset.id}/preview?variant=waveform" if asset.waveform_preview_path else None,
        video_keyframes=[f"/assets/{asset.id}/preview?variant=keyframe&index={index}" for index, _ in enumerate(asset.video_keyframes or [])] or None,
    )


def get_asset_or_404(session: Session, asset_id: UUID, current_user: User | None = None) -> Asset:
    query = (
        select(Asset)
        .where(Asset.id == asset_id)
        .options(
            selectinload(Asset.metadata_record),
            selectinload(Asset.tags),
            selectinload(Asset.source),
            selectinload(Asset.similarity),
            selectinload(Asset.annotations),
        )
    )
    query = _apply_source_scope(query, _allowed_source_ids(session, current_user))
    asset = session.execute(query).scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found.")
    return asset


def get_asset_detail(session: Session, asset_id: UUID, current_user: User | None = None) -> AssetDetail:
    asset = get_asset_or_404(session, asset_id, current_user=current_user)
    summary = _asset_summary(asset, user_id=current_user.id if current_user else None)
    raw_metadata = asset.metadata_record.raw_json if asset.metadata_record else {}
    return AssetDetail(
        **summary.model_dump(),
        raw_metadata=raw_metadata,
        source_name=asset.source.name,
        workflow_export_url=f"/assets/{asset.id}/workflow/download" if summary.workflow_export_available else None,
        visual_workflow_json=asset.visual_workflow_json,
        visual_workflow_confidence=asset.visual_workflow_confidence,
        visual_workflow_updated_at=asset.visual_workflow_updated_at,
    )


def _apply_search_filters(
    query,
    *,
    q: str | None,
    media_type: str | None,
    caption: str | None,
    ocr_text: str | None,
    camera_make: str | None,
    camera_model: str | None,
    year: int | None,
    width_min: int | None,
    width_max: int | None,
    height_min: int | None,
    height_max: int | None,
    duration_min: float | None,
    duration_max: float | None,
    has_gps: bool | None,
    tags: list[str],
    auto_tags: list[str] | None,
    exclude_tags: list[str] | None,
    min_rating: int | None,
    review_status: ReviewStatus | None,
    flagged: bool | None,
    annotation_alias,
):
    normalized = AssetMetadata.normalized_json
    conditions = []
    rank = literal(0.0)

    if media_type:
        conditions.append(Asset.media_type == media_type)
    if caption:
        conditions.append(func.lower(normalized["caption"].astext).contains(caption.lower()))
    if ocr_text:
        conditions.append(func.lower(normalized["ocr_text"].astext).contains(ocr_text.lower()))
    if camera_make:
        conditions.append(func.lower(normalized["camera_make"].astext) == camera_make.lower())
    if camera_model:
        conditions.append(func.lower(normalized["camera_model"].astext) == camera_model.lower())
    if year:
        conditions.append(func.extract("year", Asset.created_at) == year)
    if width_min is not None:
        conditions.append(cast(normalized["width"].astext, Integer) >= width_min)
    if width_max is not None:
        conditions.append(cast(normalized["width"].astext, Integer) <= width_max)
    if height_min is not None:
        conditions.append(cast(normalized["height"].astext, Integer) >= height_min)
    if height_max is not None:
        conditions.append(cast(normalized["height"].astext, Integer) <= height_max)
    if duration_min is not None:
        conditions.append(cast(normalized["duration_seconds"].astext, Float) >= duration_min)
    if duration_max is not None:
        conditions.append(cast(normalized["duration_seconds"].astext, Float) <= duration_max)
    if has_gps is True:
        conditions.append(normalized["gps_latitude"].astext.is_not(None))
        conditions.append(normalized["gps_longitude"].astext.is_not(None))
    if min_rating is not None and annotation_alias is not None:
        conditions.append(annotation_alias.rating >= min_rating)
    if review_status is not None and annotation_alias is not None:
        conditions.append(annotation_alias.review_status == review_status)
    if flagged is True and annotation_alias is not None:
        conditions.append(annotation_alias.flagged == True)
    for tag in [tag.strip().lower() for tag in tags if tag.strip()]:
        subquery = select(AssetTag.asset_id).where(AssetTag.tag == tag)
        conditions.append(Asset.id.in_(subquery))
    if auto_tags:
        for tag in [tag.strip().lower() for tag in auto_tags if tag.strip()]:
            subquery = select(TagSuggestion.asset_id).where(TagSuggestion.status == "accepted", TagSuggestion.tag == tag)
            conditions.append(Asset.id.in_(subquery))
    if exclude_tags:
        for tag in [tag.strip().lower() for tag in exclude_tags if tag.strip()]:
            subquery = select(AssetTag.asset_id).where(AssetTag.tag == tag)
            conditions.append(Asset.id.notin_(subquery))

    if q:
        ts_query = func.plainto_tsquery("simple", q)
        rank = func.ts_rank_cd(AssetSearch.document, ts_query)
        query = query.join(AssetSearch, AssetSearch.asset_id == Asset.id)
        conditions.append(AssetSearch.document.op("@@")(ts_query))

    if conditions:
        query = query.where(*conditions)
    return query, rank


def _review_sort_expression(annotation_alias):
    return case(
        (annotation_alias.review_status == ReviewStatus.FAVORITE, 0),
        (annotation_alias.review_status == ReviewStatus.APPROVED, 1),
        (annotation_alias.review_status == ReviewStatus.UNREVIEWED, 2),
        (annotation_alias.review_status == ReviewStatus.REJECTED, 3),
        else_=4,
    )


def search_assets(
    session: Session,
    *,
    q: str | None,
    media_type: str | None,
    caption: str | None,
    ocr_text: str | None,
    camera_make: str | None,
    camera_model: str | None,
    year: int | None,
    width_min: int | None,
    width_max: int | None,
    height_min: int | None,
    height_max: int | None,
    duration_min: float | None,
    duration_max: float | None,
    has_gps: bool | None,
    tags: list[str],
    source_id: UUID | None = None,
    auto_tags: list[str] | None = None,
    exclude_tags: list[str] | None = None,
    min_rating: int | None = None,
    review_status: ReviewStatus | None = None,
    flagged: bool | None = None,
    sort: str = "relevance",
    page: int = 1,
    page_size: int = 24,
    current_user: User | None = None,
) -> AssetListResponse:
    allowed_source_ids = _allowed_source_ids(session, current_user)
    annotation_alias = aliased(AssetAnnotation) if current_user else None
    base_query = (
        select(Asset)
        .join(AssetMetadata, AssetMetadata.asset_id == Asset.id, isouter=True)
        .options(selectinload(Asset.metadata_record), selectinload(Asset.tags), selectinload(Asset.annotations))
    )
    count_query = select(func.count(func.distinct(Asset.id))).select_from(Asset).join(
        AssetMetadata, AssetMetadata.asset_id == Asset.id, isouter=True
    )
    if annotation_alias is not None:
        join_condition = and_(annotation_alias.asset_id == Asset.id, annotation_alias.user_id == current_user.id)
        base_query = base_query.outerjoin(annotation_alias, join_condition)
        count_query = count_query.outerjoin(annotation_alias, join_condition)
    base_query = _apply_source_scope(base_query, allowed_source_ids)
    count_query = _apply_source_scope(count_query, allowed_source_ids)
    if source_id is not None:
        base_query = base_query.where(Asset.source_id == source_id)
        count_query = count_query.where(Asset.source_id == source_id)
    base_query, rank = _apply_search_filters(
        base_query,
        q=q,
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
        tags=tags,
        auto_tags=auto_tags,
        exclude_tags=exclude_tags,
        min_rating=min_rating,
        review_status=review_status,
        flagged=flagged,
        annotation_alias=annotation_alias,
    )
    count_query, _ = _apply_search_filters(
        count_query,
        q=q,
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
        tags=tags,
        auto_tags=auto_tags,
        exclude_tags=exclude_tags,
        min_rating=min_rating,
        review_status=review_status,
        flagged=flagged,
        annotation_alias=annotation_alias,
    )

    if sort == "created_at":
        base_query = base_query.order_by(desc(Asset.created_at), Asset.filename)
    elif sort == "modified_at":
        base_query = base_query.order_by(desc(Asset.modified_at), Asset.filename)
    elif sort == "filename":
        base_query = base_query.order_by(Asset.filename)
    elif sort == "rating" and annotation_alias is not None:
        base_query = base_query.order_by(desc(annotation_alias.rating), desc(Asset.modified_at), Asset.filename)
    elif sort == "review_status" and annotation_alias is not None:
        base_query = base_query.order_by(_review_sort_expression(annotation_alias), desc(Asset.modified_at), Asset.filename)
    else:
        base_query = base_query.order_by(desc(rank), desc(Asset.modified_at), Asset.filename)

    total = session.execute(count_query).scalar_one()
    assets = session.execute(base_query.offset((page - 1) * page_size).limit(page_size)).scalars().unique().all()
    user_id = current_user.id if current_user else None
    return AssetListResponse(items=[_asset_summary(asset, user_id=user_id) for asset in assets], total=total, page=page, page_size=page_size)


def matching_asset_ids_for_search(
    session: Session,
    *,
    q: str | None,
    media_type: str | None,
    caption: str | None,
    ocr_text: str | None,
    camera_make: str | None,
    camera_model: str | None,
    year: int | None,
    width_min: int | None,
    width_max: int | None,
    height_min: int | None,
    height_max: int | None,
    duration_min: float | None,
    duration_max: float | None,
    has_gps: bool | None,
    tags: list[str],
    auto_tags: list[str] | None = None,
    exclude_tags: list[str] | None = None,
    min_rating: int | None = None,
    review_status: ReviewStatus | None = None,
    flagged: bool | None = None,
    current_user: User | None = None,
) -> list[UUID]:
    annotation_alias = aliased(AssetAnnotation) if current_user else None
    query = select(Asset.id).join(AssetMetadata, AssetMetadata.asset_id == Asset.id, isouter=True)
    if annotation_alias is not None:
        query = query.outerjoin(annotation_alias, and_(annotation_alias.asset_id == Asset.id, annotation_alias.user_id == current_user.id))
    query = _apply_source_scope(query, _allowed_source_ids(session, current_user))
    query, rank = _apply_search_filters(
        query,
        q=q,
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
        tags=tags,
        auto_tags=auto_tags,
        exclude_tags=exclude_tags,
        min_rating=min_rating,
        review_status=review_status,
        flagged=flagged,
        annotation_alias=annotation_alias,
    )

    if q:
        query = query.order_by(desc(rank), desc(Asset.modified_at), Asset.filename)
    else:
        query = query.order_by(desc(Asset.modified_at), Asset.filename)
    return list(session.execute(query).scalars().all())


def browse_assets(
    session: Session,
    *,
    source_id: UUID | None,
    exclude_tags: list[str] | None = None,
    min_rating: int | None,
    review_status: ReviewStatus | None,
    flagged: bool | None,
    sort: str,
    page: int,
    page_size: int,
    current_user: User | None = None,
) -> AssetBrowseResponse:
    allowed_source_ids = _allowed_source_ids(session, current_user)
    annotation_alias = aliased(AssetAnnotation) if current_user else None
    base_query = (
        select(Asset)
        .where(Asset.media_type == MediaType.IMAGE)
        .options(selectinload(Asset.metadata_record), selectinload(Asset.tags), selectinload(Asset.source), selectinload(Asset.annotations))
    )
    count_query = select(func.count(Asset.id)).where(Asset.media_type == MediaType.IMAGE)
    if annotation_alias is not None:
        join_condition = and_(annotation_alias.asset_id == Asset.id, annotation_alias.user_id == current_user.id)
        base_query = base_query.outerjoin(annotation_alias, join_condition)
        count_query = count_query.outerjoin(annotation_alias, join_condition)
    base_query = _apply_source_scope(base_query, allowed_source_ids)
    count_query = _apply_source_scope(count_query, allowed_source_ids)

    if source_id is not None:
        base_query = base_query.where(Asset.source_id == source_id)
        count_query = count_query.where(Asset.source_id == source_id)
    if min_rating is not None and annotation_alias is not None:
        base_query = base_query.where(annotation_alias.rating >= min_rating)
        count_query = count_query.where(annotation_alias.rating >= min_rating)
    if review_status is not None and annotation_alias is not None:
        base_query = base_query.where(annotation_alias.review_status == review_status)
        count_query = count_query.where(annotation_alias.review_status == review_status)
    if flagged is not None and annotation_alias is not None:
        base_query = base_query.where(annotation_alias.flagged == flagged)
        count_query = count_query.where(annotation_alias.flagged == flagged)

    if exclude_tags:
        for tag in [tag.strip().lower() for tag in exclude_tags if tag.strip()]:
            subquery = select(AssetTag.asset_id).where(AssetTag.tag == tag)
            base_query = base_query.where(Asset.id.notin_(subquery))
            count_query = count_query.where(Asset.id.notin_(subquery))

    if sort == "created_at":
        base_query = base_query.order_by(desc(Asset.created_at), desc(Asset.modified_at), Asset.filename)
    elif sort == "filename":
        base_query = base_query.order_by(Asset.filename, desc(Asset.modified_at))
    elif sort == "rating" and annotation_alias is not None:
        base_query = base_query.order_by(desc(annotation_alias.rating), desc(Asset.modified_at), Asset.filename)
    elif sort == "review_status" and annotation_alias is not None:
        base_query = base_query.order_by(_review_sort_expression(annotation_alias), desc(Asset.modified_at), Asset.filename)
    else:
        base_query = base_query.order_by(desc(Asset.modified_at), desc(Asset.created_at), Asset.filename)

    total = session.execute(count_query).scalar_one()
    assets = session.execute(base_query.offset((page - 1) * page_size).limit(page_size)).scalars().unique().all()
    user_id = current_user.id if current_user else None
    return AssetBrowseResponse(
        items=[asset_browse_item(asset, user_id=user_id) for asset in assets],
        total=total,
        page=page,
        page_size=page_size,
    )


def list_tags(session: Session, limit: int = 100, current_user: User | None = None) -> list[TagCount]:
    rows = session.execute(
        _apply_source_scope(
            select(AssetTag.tag, func.count(AssetTag.asset_id)).join(Asset, Asset.id == AssetTag.asset_id),
            _allowed_source_ids(session, current_user),
        )
        .group_by(AssetTag.tag)
        .order_by(desc(func.count(AssetTag.asset_id)), AssetTag.tag)
        .limit(limit)
    ).all()
    return [TagCount(tag=tag, count=count) for tag, count in rows]


def get_assets_for_tag(session: Session, tag: str, page: int, page_size: int, current_user: User | None = None) -> AssetListResponse:
    return search_assets(
        session,
        q=None,
        media_type=None,
        caption=None,
        ocr_text=None,
        camera_make=None,
        camera_model=None,
        year=None,
        width_min=None,
        width_max=None,
        height_min=None,
        height_max=None,
        duration_min=None,
        duration_max=None,
        has_gps=None,
        tags=[tag],
        auto_tags=None,
        exclude_tags=None,
        min_rating=None,
        review_status=None,
        flagged=None,
        sort="modified_at",
        page=page,
        page_size=page_size,
        current_user=current_user,
    )


def get_similar_assets(session: Session, asset_id: UUID, match_type: MatchType, limit: int, current_user: User | None = None) -> list[SimilarAsset]:
    target_asset = get_asset_or_404(session, asset_id, current_user=current_user)
    target_normalized = target_asset.metadata_record.normalized_json if target_asset.metadata_record else {}
    links = session.execute(
        select(SimilarityLink)
        .where(
            SimilarityLink.match_type == match_type,
            or_(SimilarityLink.asset_id_a == asset_id, SimilarityLink.asset_id_b == asset_id),
        )
        .order_by(SimilarityLink.distance)
    ).scalars().all()

    related_ids = [link.asset_id_b if link.asset_id_a == asset_id else link.asset_id_a for link in links][:limit]
    if not related_ids:
        return []

    _sim_allowed = _allowed_source_ids(session, current_user)
    assets = session.execute(
        select(Asset)
        .where(Asset.id.in_(related_ids))
        .options(selectinload(Asset.metadata_record), selectinload(Asset.tags), selectinload(Asset.annotations))
        .where(
            Asset.source_id.in_(_sim_allowed)
            if _sim_allowed is not None
            else literal(True)
        )
    ).scalars().unique().all()
    asset_map = {asset.id: asset for asset in assets}
    user_id = current_user.id if current_user else None

    results = []
    for link in links[:limit]:
        other_id = link.asset_id_b if link.asset_id_a == asset_id else link.asset_id_a
        asset = asset_map.get(other_id)
        if not asset:
            continue
        prompt_tag_overlap, shared_prompt_tags, _, _ = compute_prompt_tag_overlap(
            target_normalized,
            asset.metadata_record.normalized_json if asset.metadata_record else {},
        )
        results.append(
            SimilarAsset(
                asset=_asset_summary(asset, user_id=user_id),
                match_type=link.match_type,
                distance=link.distance,
                score=score_from_distance(link.match_type, link.distance),
                prompt_tag_overlap=prompt_tag_overlap,
                shared_prompt_tags=shared_prompt_tags,
            )
        )
    return results


def search_similar_by_image(session: Session, asset_id: UUID, limit: int, current_user: User | None = None) -> list[SimilarAsset]:
    target_asset = get_asset_or_404(session, asset_id, current_user=current_user)
    if not target_asset.similarity or target_asset.similarity.embedding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No embedding for this asset.")

    distance_expr = AssetSimilarity.embedding.cosine_distance(target_asset.similarity.embedding)
    query = (
        select(Asset, distance_expr.label("distance"))
        .join(AssetSimilarity, AssetSimilarity.asset_id == Asset.id)
        .where(Asset.id != asset_id, AssetSimilarity.embedding.is_not(None))
        .options(selectinload(Asset.metadata_record), selectinload(Asset.tags), selectinload(Asset.annotations))
        .order_by(distance_expr)
        .limit(limit)
    )
    query = _apply_source_scope(query, _allowed_source_ids(session, current_user))
    rows = session.execute(query).all()
    target_normalized = target_asset.metadata_record.normalized_json if target_asset.metadata_record else {}
    user_id = current_user.id if current_user else None

    results: list[SimilarAsset] = []
    for asset, distance in rows:
        prompt_tag_overlap, shared_prompt_tags, _, _ = compute_prompt_tag_overlap(
            target_normalized,
            asset.metadata_record.normalized_json if asset.metadata_record else {},
        )
        results.append(
            SimilarAsset(
                asset=_asset_summary(asset, user_id=user_id),
                match_type=MatchType.SEMANTIC,
                distance=float(distance),
                score=score_from_distance(MatchType.SEMANTIC, float(distance)),
                prompt_tag_overlap=prompt_tag_overlap,
                shared_prompt_tags=shared_prompt_tags,
            )
        )
    return results
