from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from media_indexer_backend.api.dependencies import get_session, require_authenticated, require_admin, require_enabled_module
from media_indexer_backend.models.enums import MediaType
from media_indexer_backend.models.tables import Asset, User, TagVocabularyEntry, TagSuggestion, AssetTag
from media_indexer_backend.platform.events import publish_event
from media_indexer_backend.schemas.asset import AssetListResponse, TagCount
from media_indexer_backend.schemas.tags import (
    RelatedTagRead,
    TagProviderRead,
    TagProvidersResponse,
    TagRebuildRequest,
    TagRebuildResponse,
    TagSuggestionAction,
    TagSuggestionRead,
    TagVocabularyCreate,
    TagVocabularyRead,
)
from media_indexer_backend.services.asset_service import get_asset_or_404, get_assets_for_tag, list_tags
from media_indexer_backend.services.curation_service import log_curation_event
from media_indexer_backend.services.image_enrichment import get_image_enrichment_service
from media_indexer_backend.services.metadata import canonicalize_tag
from media_indexer_backend.services.path_safety import resolve_asset_path


router = APIRouter(tags=["tags"])


@router.get("/tags", response_model=list[TagCount])
def get_tags(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> list[TagCount]:
    return list_tags(session, current_user=current_user)


@router.get("/tags/{tag}/assets", response_model=AssetListResponse)
def get_tag_assets(
    tag: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=100),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> AssetListResponse:
    return get_assets_for_tag(session, tag, page, page_size, current_user=current_user)


# AI Tag Vocabulary Management
@router.get("/tags/vocabulary", response_model=list[TagVocabularyRead])
def get_tag_vocabulary(
    session: Session = Depends(get_session),
    _: None = Depends(require_enabled_module("ai_tagging")),
    current_user: User = Depends(require_admin),
) -> list[TagVocabularyRead]:
    entries = session.execute(select(TagVocabularyEntry).order_by(TagVocabularyEntry.tag)).scalars().all()
    return [TagVocabularyRead.model_validate(entry) for entry in entries]


@router.post("/tags/vocabulary", response_model=TagVocabularyRead, status_code=201)
def create_tag_vocabulary_entry(
    payload: TagVocabularyCreate,
    session: Session = Depends(get_session),
    _: None = Depends(require_enabled_module("ai_tagging")),
    current_user: User = Depends(require_admin),
) -> TagVocabularyRead:
    normalized_tag = canonicalize_tag(payload.tag)
    if not normalized_tag:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tag must not be empty.")
    existing = session.execute(select(TagVocabularyEntry).where(TagVocabularyEntry.tag == normalized_tag)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tag vocabulary entry already exists.")
    entry = TagVocabularyEntry(
        tag=normalized_tag,
        description=payload.description,
        clip_prompt=payload.clip_prompt,
        enabled=payload.enabled,
        created_by=current_user.id,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return TagVocabularyRead.model_validate(entry)


@router.get("/tags/providers", response_model=TagProvidersResponse)
def get_tag_providers(
    _: None = Depends(require_enabled_module("ai_tagging")),
    current_user: User = Depends(require_admin),
) -> TagProvidersResponse:
    del current_user
    enrichment = get_image_enrichment_service()
    return TagProvidersResponse(providers=[TagProviderRead.model_validate(item) for item in enrichment.provider_statuses()])


@router.post("/tags/providers/preload", response_model=TagProvidersResponse)
def preload_tag_providers(
    _: None = Depends(require_enabled_module("ai_tagging")),
    current_user: User = Depends(require_admin),
) -> TagProvidersResponse:
    del current_user
    enrichment = get_image_enrichment_service()
    return TagProvidersResponse(providers=[TagProviderRead.model_validate(item) for item in enrichment.preload()])


@router.post("/tags/rebuild", response_model=TagRebuildResponse)
def rebuild_asset_tags(
    payload: TagRebuildRequest,
    session: Session = Depends(get_session),
    _: None = Depends(require_enabled_module("ai_tagging")),
    current_user: User = Depends(require_admin),
) -> TagRebuildResponse:
    del current_user
    if payload.scope == "asset" and payload.asset_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="asset_id is required for asset rebuild scope.")
    if payload.scope == "source" and payload.source_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="source_id is required for source rebuild scope.")

    query = (
        select(Asset)
        .where(Asset.media_type == MediaType.IMAGE)
        .options(selectinload(Asset.source), selectinload(Asset.metadata_record), selectinload(Asset.tags))
        .order_by(Asset.modified_at.desc(), Asset.filename)
    )
    if payload.scope == "asset" and payload.asset_id is not None:
        query = query.where(Asset.id == payload.asset_id)
    elif payload.scope == "source" and payload.source_id is not None:
        query = query.where(Asset.source_id == payload.source_id)

    assets = session.execute(query).scalars().unique().all()
    enrichment = get_image_enrichment_service()
    processed_assets = 0
    created_suggestions = 0

    for asset in assets:
        image_path = resolve_asset_path(asset.source.root_path, asset.relative_path)
        result = enrichment.enrich_asset(
            session,
            asset,
            image_path,
            compare_mode=payload.compare_mode,
            provider_override=payload.provider,
        )
        processed_assets += 1
        created_suggestions += result.get("suggestion_count", 0)
        session.commit()

    return TagRebuildResponse(processed_assets=processed_assets, created_suggestions=created_suggestions)


@router.get("/tags/related", response_model=list[RelatedTagRead])
def get_related_tags(
    tag: str,
    limit: int = Query(default=12, ge=1, le=50),
    session: Session = Depends(get_session),
    _: None = Depends(require_enabled_module("ai_tagging")),
    current_user: User = Depends(require_authenticated),
) -> list[RelatedTagRead]:
    del session, current_user
    enrichment = get_image_enrichment_service()
    return [RelatedTagRead.model_validate(item) for item in enrichment.related_tags(tag, limit=limit)]


@router.get("/tags/suggestions/asset/{asset_id}", response_model=list[TagSuggestionRead])
def get_asset_suggestions(
    asset_id: UUID,
    session: Session = Depends(get_session),
    _: None = Depends(require_enabled_module("ai_tagging")),
    current_user: User = Depends(require_authenticated),
) -> list[TagSuggestionRead]:
    get_asset_or_404(session, asset_id, current_user=current_user)
    suggestions = session.execute(
        select(TagSuggestion)
        .where(TagSuggestion.asset_id == asset_id, TagSuggestion.status == "pending")
        .order_by(TagSuggestion.tag_group.asc().nullslast(), TagSuggestion.rank.asc().nullslast(), TagSuggestion.confidence.desc())
    ).scalars().all()
    return [TagSuggestionRead.model_validate(item) for item in suggestions]


@router.post("/tags/suggestions/action")
def post_suggestion_action(
    payload: TagSuggestionAction,
    session: Session = Depends(get_session),
    _: None = Depends(require_enabled_module("ai_tagging")),
    current_user: User = Depends(require_authenticated),
) -> dict[str, str]:
    suggestion = session.get(TagSuggestion, payload.suggestion_id)
    if not suggestion:
        return {"status": "not_found"}
    get_asset_or_404(session, suggestion.asset_id, current_user=current_user)

    if payload.action == "accept":
        exists = session.scalar(
            select(AssetTag).where(AssetTag.asset_id == suggestion.asset_id, AssetTag.tag == suggestion.tag)
        )
        if not exists:
            session.add(AssetTag(asset_id=suggestion.asset_id, tag=suggestion.tag))
        suggestion.status = "accepted"
        log_curation_event(
            session,
            user_id=current_user.id,
            asset_id=suggestion.asset_id,
            event_type="tag.accept",
            details_json={"tag": suggestion.tag, "suggestion_id": suggestion.id},
        )
        publish_event(
            session,
            "tag.accepted",
            {
                "user_id": str(current_user.id),
                "asset_id": str(suggestion.asset_id),
                "tag": suggestion.tag,
            },
        )
    else:
        suggestion.status = "rejected"
    session.commit()
    return {"status": "success"}
