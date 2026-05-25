from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_, desc, or_, select
from sqlalchemy.orm import Session, aliased, selectinload

from media_indexer_backend.models.tables import (
    Asset,
    AssetAnnotation,
    AssetMetadata,
    AssetTag,
    CurationEvent,
    FaceDetection,
    FacePerson,
    SmartAlbum,
    TagSuggestion,
    User,
)
from media_indexer_backend.schemas.smart_album import (
    SmartAlbumCreateRequest,
    SmartAlbumDetail,
    SmartAlbumRule,
    SmartAlbumSummary,
    SmartAlbumUpdateRequest,
)
from media_indexer_backend.platform.runtime import get_smart_album_runtime_settings
from media_indexer_backend.platform.service import module_is_enabled
from media_indexer_backend.services.asset_service import _allowed_source_ids, _apply_source_scope, asset_browse_item
from media_indexer_backend.services.curation_service import log_curation_event


def _normalized_rule(rule: SmartAlbumRule | dict | None) -> SmartAlbumRule:
    payload = rule if isinstance(rule, dict) else (rule.model_dump(mode="json") if rule is not None else {})
    normalized = SmartAlbumRule.model_validate(payload or {})
    normalized.tags_any = sorted({item.strip().lower() for item in normalized.tags_any if item.strip()})
    normalized.auto_tags_any = sorted({item.strip().lower() for item in normalized.auto_tags_any if item.strip()})
    normalized.source_ids = sorted(normalized.source_ids, key=str)
    normalized.people_ids = sorted(normalized.people_ids, key=str)
    return normalized


def _rule_json(rule: SmartAlbumRule | dict | None) -> dict:
    return _normalized_rule(rule).model_dump(mode="json")


def _rule_identity(rule: SmartAlbumRule | dict | None) -> str:
    return json.dumps(_rule_json(rule), sort_keys=True, separators=(",", ":"))


def smart_album_summary(album: SmartAlbum) -> SmartAlbumSummary:
    return SmartAlbumSummary(
        id=album.id,
        name=album.name,
        description=album.description,
        owner_id=album.owner_id,
        enabled=album.enabled,
        last_synced_at=album.last_synced_at,
        asset_count=album.asset_count,
        cover_asset_id=album.cover_asset_id,
        source=album.source,
        status=album.status,
        degraded_reason=album.degraded_reason,
        created_at=album.created_at,
        updated_at=album.updated_at,
        rule=_normalized_rule(album.rule_json),
    )


def _owner_or_404(session: Session, owner_id: UUID) -> User:
    owner = session.get(User, owner_id)
    if owner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Album owner not found.")
    return owner


def _album_or_404(session: Session, album_id: UUID, owner_id: UUID) -> SmartAlbum:
    album = session.execute(
        select(SmartAlbum)
        .where(SmartAlbum.id == album_id, SmartAlbum.owner_id == owner_id)
    ).scalar_one_or_none()
    if album is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Smart album not found.")
    return album


# Public alias so routes can import without reaching into private helpers
get_smart_album_or_404 = _album_or_404


def _rule_query(session: Session, owner: User, rule: SmartAlbumRule):
    annotation_alias = aliased(AssetAnnotation)
    query = (
        select(Asset)
        .join(AssetMetadata, AssetMetadata.asset_id == Asset.id, isouter=True)
        .outerjoin(
            annotation_alias,
            and_(annotation_alias.asset_id == Asset.id, annotation_alias.user_id == owner.id),
        )
        .options(selectinload(Asset.metadata_record), selectinload(Asset.tags), selectinload(Asset.source), selectinload(Asset.annotations))
    )
    allowed_source_ids = _allowed_source_ids(session, owner)
    query = _apply_source_scope(query, allowed_source_ids)

    normalized = AssetMetadata.normalized_json
    conditions = []
    if rule.media_type is not None:
        conditions.append(Asset.media_type == rule.media_type)
    if rule.source_ids:
        conditions.append(Asset.source_id.in_(rule.source_ids))
    if rule.tags_any:
        tag_subquery = select(AssetTag.asset_id).where(AssetTag.tag.in_(rule.tags_any))
        conditions.append(Asset.id.in_(tag_subquery))
    if rule.auto_tags_any:
        auto_tag_subquery = select(TagSuggestion.asset_id).where(
            TagSuggestion.status == "accepted",
            TagSuggestion.tag.in_(rule.auto_tags_any),
        )
        conditions.append(Asset.id.in_(auto_tag_subquery))
    if rule.people_ids:
        people_subquery = select(FaceDetection.asset_id).where(FaceDetection.person_id.in_(rule.people_ids))
        conditions.append(Asset.id.in_(people_subquery))
    if rule.review_status is not None:
        conditions.append(annotation_alias.review_status == rule.review_status)
    if rule.min_rating is not None:
        conditions.append(annotation_alias.rating >= rule.min_rating)
    if rule.flagged is not None:
        conditions.append(annotation_alias.flagged == rule.flagged)
    if rule.has_gps is True:
        # Assets with no metadata row are excluded here because NULL["key"] IS NOT NULL → FALSE
        conditions.extend(
            [
                normalized["gps_latitude"].astext.is_not(None),
                normalized["gps_longitude"].astext.is_not(None),
            ]
        )
    elif rule.has_gps is False:
        # Assets with no metadata row are included here because NULL["key"] IS NULL → TRUE (correct)
        conditions.append(
            or_(
                normalized["gps_latitude"].astext.is_(None),
                normalized["gps_longitude"].astext.is_(None),
            )
        )
    if rule.date_from is not None:
        conditions.append(Asset.created_at >= datetime.combine(rule.date_from, time.min, tzinfo=timezone.utc))
    if rule.date_to is not None:
        conditions.append(Asset.created_at <= datetime.combine(rule.date_to, time.max, tzinfo=timezone.utc))
    if conditions:
        query = query.where(*conditions)
    return query


def _query_assets_for_album(session: Session, owner: User, rule: SmartAlbumRule) -> list[Asset]:
    query = _rule_query(session, owner, rule).order_by(desc(Asset.created_at), desc(Asset.modified_at), Asset.filename)
    return session.execute(query).scalars().unique().all()


def _required_rule_modules(rule: SmartAlbumRule) -> list[str]:
    required: list[str] = []
    if rule.people_ids:
        required.append("people")
    if rule.auto_tags_any:
        required.append("ai_tagging")
    if rule.has_gps is not None:
        required.append("geo")
    return sorted(set(required))


def _missing_rule_modules(session: Session, rule: SmartAlbumRule) -> list[str]:
    return [module_id for module_id in _required_rule_modules(rule) if not module_is_enabled(session, module_id)]


def sync_album(session: Session, album: SmartAlbum, *, owner: User | None = None) -> SmartAlbum:
    runtime = get_smart_album_runtime_settings()
    if not runtime.module_enabled:
        album.status = "disabled"
        album.degraded_reason = "Smart albums module is disabled."
        session.flush()
        return album
    resolved_owner = owner or _owner_or_404(session, album.owner_id)
    rule = _normalized_rule(album.rule_json)
    missing_modules = _missing_rule_modules(session, rule)
    if missing_modules:
        album.status = "degraded"
        album.degraded_reason = f"Waiting for modules: {', '.join(missing_modules)}"
        session.flush()
        return album
    assets = _query_assets_for_album(session, resolved_owner, rule)
    album.asset_count = len(assets)
    album.cover_asset_id = assets[0].id if assets else None
    album.last_synced_at = datetime.now(tz=timezone.utc)
    album.rule_json = rule.model_dump(mode="json")
    album.status = "active"
    album.degraded_reason = None
    session.flush()
    return album


def sync_smart_albums_for_user(session: Session, owner_id: UUID) -> None:
    owner = _owner_or_404(session, owner_id)
    albums = session.execute(
        select(SmartAlbum).where(SmartAlbum.owner_id == owner_id, SmartAlbum.enabled == True)  # noqa: E712
    ).scalars().all()
    for album in albums:
        sync_album(session, album, owner=owner)
    session.flush()


def sync_all_smart_albums(session: Session) -> None:
    owners = session.execute(select(User)).scalars().all()
    for owner in owners:
        sync_smart_albums_for_user(session, owner.id)


def list_smart_albums(session: Session, owner_id: UUID) -> list[SmartAlbumSummary]:
    albums = session.execute(
        select(SmartAlbum)
        .where(SmartAlbum.owner_id == owner_id)
        .order_by(desc(SmartAlbum.updated_at), SmartAlbum.name)
    ).scalars().all()
    return [smart_album_summary(album) for album in albums]


def get_smart_album_detail(
    session: Session,
    album_id: UUID,
    owner_id: UUID,
) -> SmartAlbumDetail:
    album = _album_or_404(session, album_id, owner_id)
    owner = _owner_or_404(session, owner_id)
    assets = _query_assets_for_album(session, owner, _normalized_rule(album.rule_json))
    items = [asset_browse_item(asset, user_id=owner_id) for asset in assets[:120]]
    summary = smart_album_summary(album)
    return SmartAlbumDetail(**summary.model_dump(), items=items, suggested=album.source == "suggested")


def create_smart_album(session: Session, owner_id: UUID, payload: SmartAlbumCreateRequest) -> SmartAlbum:
    album = SmartAlbum(
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        owner_id=owner_id,
        enabled=payload.enabled,
        rule_json=_rule_json(payload.rule),
        source="user",
    )
    session.add(album)
    session.flush()
    return sync_album(session, album)


def update_smart_album(session: Session, album_id: UUID, owner_id: UUID, payload: SmartAlbumUpdateRequest) -> SmartAlbum:
    album = _album_or_404(session, album_id, owner_id)
    if payload.name is not None:
        album.name = payload.name.strip()
    if payload.description is not None:
        album.description = payload.description.strip() or None
    if payload.enabled is not None:
        album.enabled = payload.enabled
    if payload.rule is not None:
        album.rule_json = _rule_json(payload.rule)
    session.flush()
    return sync_album(session, album)


def delete_smart_album(session: Session, album_id: UUID, owner_id: UUID) -> SmartAlbum:
    album = _album_or_404(session, album_id, owner_id)
    session.delete(album)
    session.flush()
    return album


def record_collection_add_curation_events(
    session: Session,
    *,
    user_id: UUID,
    collection_id: UUID,
    asset_ids: list[UUID],
) -> None:
    for asset_id in asset_ids:
        log_curation_event(
            session,
            user_id=user_id,
            asset_id=asset_id,
            event_type="collection.asset_add",
            details_json={"collection_id": str(collection_id)},
        )


def _upsert_suggested_album(
    session: Session,
    *,
    owner: User,
    name: str,
    description: str,
    rule: SmartAlbumRule,
) -> SmartAlbum | None:
    runtime = get_smart_album_runtime_settings()
    rule_id = _rule_identity(rule)
    existing = session.execute(
        select(SmartAlbum).where(SmartAlbum.owner_id == owner.id)
    ).scalars().all()
    for album in existing:
        if _rule_identity(album.rule_json) == rule_id:
            album.name = name
            album.description = description
            album.enabled = True
            album.source = "suggested"
            synced = sync_album(session, album, owner=owner)
            return synced if synced.asset_count >= runtime.suggestion_min_assets else None
    album = SmartAlbum(
        name=name,
        description=description,
        owner_id=owner.id,
        enabled=True,
        rule_json=_rule_json(rule),
        source="suggested",
    )
    session.add(album)
    session.flush()
    synced = sync_album(session, album, owner=owner)
    if synced.asset_count < runtime.suggestion_min_assets:
        session.delete(synced)
        session.flush()
        return None
    return synced


def generate_smart_album_suggestions(session: Session) -> None:
    runtime = get_smart_album_runtime_settings()
    if not runtime.module_enabled:
        return
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=runtime.suggestion_lookback_days)
    users = session.execute(select(User)).scalars().all()

    for owner in users:
        event_items = session.execute(
            select(CurationEvent)
            .where(CurationEvent.user_id == owner.id, CurationEvent.created_at >= cutoff)
            .order_by(CurationEvent.created_at.desc())
        ).scalars().all()
        if len(event_items) < runtime.suggestion_min_events:
            continue

        positive_asset_ids = {item.asset_id for item in event_items}
        tag_counter: Counter[str] = Counter()
        for item in event_items:
            details = item.details_json if isinstance(item.details_json, dict) else {}
            if item.event_type == "tag.accept":
                tag = str(details.get("tag", "")).strip().lower()
                if tag:
                    tag_counter[tag] += 1

        person_counter: Counter[UUID] = Counter()
        combo_counter: Counter[tuple[str, UUID]] = Counter()
        if positive_asset_ids:
            person_rows = session.execute(
                select(FaceDetection.asset_id, FaceDetection.person_id)
                .join(FacePerson, FacePerson.id == FaceDetection.person_id)
                .where(
                    FaceDetection.asset_id.in_(positive_asset_ids),
                    FaceDetection.person_id.is_not(None),
                    FacePerson.name.is_not(None),
                )
            ).all()
            asset_people: dict[UUID, set[UUID]] = defaultdict(set)
            for asset_id, person_id in person_rows:
                if asset_id is None or person_id is None:
                    continue
                asset_people[asset_id].add(person_id)
                person_counter[person_id] += 1
            for item in event_items:
                if item.event_type != "tag.accept":
                    continue
                details = item.details_json if isinstance(item.details_json, dict) else {}
                tag = str(details.get("tag", "")).strip().lower()
                if not tag:
                    continue
                for person_id in asset_people.get(item.asset_id, set()):
                    combo_counter[(tag, person_id)] += 1

        created = 0
        if tag_counter:
            tag, support = tag_counter.most_common(1)[0]
            if support >= runtime.suggestion_min_events:
                album = _upsert_suggested_album(
                    session,
                    owner=owner,
                    name=f"Suggested: {tag}",
                    description=f"Suggested from repeated accepted tag activity for '{tag}'.",
                    rule=SmartAlbumRule(tags_any=[tag]),
                )
                if album is not None:
                    created += 1
        if person_counter and created < 5:
            person_id, support = person_counter.most_common(1)[0]
            if support >= runtime.suggestion_min_events:
                person = session.get(FacePerson, person_id)
                if person is not None:
                    album = _upsert_suggested_album(
                        session,
                        owner=owner,
                        name=f"Suggested: {person.name or 'Unnamed person'}",
                        description="Suggested from repeated positive curation around one person.",
                        rule=SmartAlbumRule(people_ids=[person_id]),
                    )
                    if album is not None:
                        created += 1
        if combo_counter and created < 5:
            (tag, person_id), support = combo_counter.most_common(1)[0]
            if support >= runtime.suggestion_min_events:
                person = session.get(FacePerson, person_id)
                if person is not None:
                    _upsert_suggested_album(
                        session,
                        owner=owner,
                        name=f"Suggested: {tag} + {person.name or 'Person'}",
                        description="Suggested from repeated tag and person curation overlap.",
                        rule=SmartAlbumRule(tags_any=[tag], people_ids=[person_id]),
                    )
        existing_suggested = session.execute(
            select(SmartAlbum)
            .where(SmartAlbum.owner_id == owner.id, SmartAlbum.source == "suggested")
            .order_by(desc(SmartAlbum.updated_at))
        ).scalars().all()
        for album in existing_suggested[5:]:
            session.delete(album)
        session.flush()
