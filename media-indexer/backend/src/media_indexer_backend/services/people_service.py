from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from uuid import UUID

import numpy as np
from fastapi import HTTPException, status
from sklearn.cluster import DBSCAN
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from media_indexer_backend.core.config import get_settings
from media_indexer_backend.models.tables import Asset, FaceDetection, FacePerson, User
from media_indexer_backend.platform.runtime import get_people_runtime_settings
from media_indexer_backend.schemas.asset import AssetBrowseItem
from media_indexer_backend.schemas.people import (
    AssetFacePersonRead,
    AssetFaceRead,
    AssetFacesResponse,
    PersonDetail,
    PersonSummary,
    PersonUpdateRequest,
    ReclusterPeopleResponse,
)
from media_indexer_backend.services.asset_service import asset_browse_item, get_asset_or_404


def _crop_preview_url(face: FaceDetection) -> str | None:
    if not face.crop_preview_path:
        return None
    return f"/people/faces/{face.id}/crop"


def _face_read(face: FaceDetection) -> AssetFaceRead:
    person = None
    if face.person is not None:
        person = AssetFacePersonRead(id=face.person.id, name=face.person.name)
    return AssetFaceRead(
        id=face.id,
        asset_id=face.asset_id,
        bbox_x1=face.bbox_x1,
        bbox_y1=face.bbox_y1,
        bbox_x2=face.bbox_x2,
        bbox_y2=face.bbox_y2,
        det_score=face.det_score,
        crop_preview_url=_crop_preview_url(face),
        person=person,
    )


def _normalize_embedding(embedding: list[float] | None) -> np.ndarray | None:
    if embedding is None:
        return None
    vector = np.asarray(embedding, dtype=np.float32)
    norm = np.linalg.norm(vector)
    if norm == 0:
        return None
    return vector / norm


def _person_centroids(session: Session) -> dict[UUID, np.ndarray]:
    rows = session.execute(
        select(FaceDetection).where(FaceDetection.person_id.is_not(None), FaceDetection.embedding.is_not(None))
    ).scalars().all()
    grouped: dict[UUID, list[np.ndarray]] = defaultdict(list)
    for row in rows:
        normalized = _normalize_embedding(row.embedding)
        if normalized is None or row.person_id is None:
            continue
        grouped[row.person_id].append(normalized)
    centroids: dict[UUID, np.ndarray] = {}
    for person_id, vectors in grouped.items():
        centroid = np.mean(np.stack(vectors), axis=0)
        norm = np.linalg.norm(centroid)
        if norm == 0:
            continue
        centroids[person_id] = centroid / norm
    return centroids


def _assign_faces_to_existing_people(
    session: Session,
    detections: list[FaceDetection],
) -> int:
    if not detections:
        return 0
    settings = get_settings()
    centroids = _person_centroids(session)
    assigned = 0
    for detection in detections:
        if detection.person_id is not None:
            continue
        vector = _normalize_embedding(detection.embedding)
        if vector is None:
            continue
        best_person_id: UUID | None = None
        best_distance: float | None = None
        for person_id, centroid in centroids.items():
            distance = float(1.0 - float(np.dot(vector, centroid)))
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_person_id = person_id
        if best_person_id is not None and best_distance is not None and best_distance <= settings.face_recognition_threshold:
            detection.person_id = best_person_id
            assigned += 1
    if assigned:
        session.flush()
    return assigned


def _create_person_for_faces(session: Session, detections: list[FaceDetection]) -> FacePerson:
    person = FacePerson()
    session.add(person)
    session.flush()  # Needed to generate person.id before assigning FK
    for detection in detections:
        detection.person_id = person.id
    if detections:
        person.cover_face_id = detections[0].id
    session.flush()
    return person


def _cluster_unassigned_faces(session: Session, detections: list[FaceDetection]) -> tuple[int, int]:
    vectors: list[np.ndarray] = []
    with_vectors: list[FaceDetection] = []
    without_vectors: list[FaceDetection] = []
    for detection in detections:
        vector = _normalize_embedding(detection.embedding)
        if vector is None:
            without_vectors.append(detection)
            continue
        with_vectors.append(detection)
        vectors.append(vector)

    created_people = 0
    assigned_faces = 0

    if with_vectors:
        if len(with_vectors) == 1:
            _create_person_for_faces(session, with_vectors)
            created_people += 1
            assigned_faces += 1
        else:
            labels = DBSCAN(
                eps=get_settings().face_recognition_threshold,
                min_samples=2,
                metric="cosine",
            ).fit_predict(np.stack(vectors))
            grouped: dict[int, list[FaceDetection]] = defaultdict(list)
            for label, detection in zip(labels, with_vectors, strict=False):
                grouped[int(label)].append(detection)
            for label, cluster_faces in grouped.items():
                if label == -1:
                    for detection in cluster_faces:
                        _create_person_for_faces(session, [detection])
                        created_people += 1
                        assigned_faces += 1
                    continue
                _create_person_for_faces(session, cluster_faces)
                created_people += 1
                assigned_faces += len(cluster_faces)

    for detection in without_vectors:
        _create_person_for_faces(session, [detection])
        created_people += 1
        assigned_faces += 1

    return (assigned_faces, created_people)


def _delete_empty_people(session: Session) -> None:
    people = session.execute(
        select(FacePerson).options(selectinload(FacePerson.faces))
    ).scalars().all()
    for person in people:
        if not person.faces:
            session.delete(person)
    session.flush()


def assign_people_for_source(session: Session, source_id: UUID) -> tuple[int, int]:
    detections = session.execute(
        select(FaceDetection)
        .join(Asset, Asset.id == FaceDetection.asset_id)
        .where(Asset.source_id == source_id, FaceDetection.person_id.is_(None))
    ).scalars().all()
    if not detections:
        return (0, 0)
    assigned = _assign_faces_to_existing_people(session, detections)
    remaining = [item for item in detections if item.person_id is None]
    clustered_assigned, created_people = _cluster_unassigned_faces(session, remaining) if remaining else (0, 0)
    _delete_empty_people(session)
    return (assigned + clustered_assigned, created_people)


def recluster_people(session: Session) -> ReclusterPeopleResponse:
    unnamed_people = session.execute(
        select(FacePerson)
        .where(FacePerson.name.is_(None))
        .options(selectinload(FacePerson.faces))
    ).scalars().all()
    for person in unnamed_people:
        for face in person.faces:
            face.person_id = None
        session.delete(person)
    session.flush()
    detections = session.execute(
        select(FaceDetection).where(FaceDetection.person_id.is_(None))
    ).scalars().all()
    assigned = _assign_faces_to_existing_people(session, detections)
    remaining = [item for item in detections if item.person_id is None]
    clustered_assigned, created_people = _cluster_unassigned_faces(session, remaining) if remaining else (0, 0)
    _delete_empty_people(session)
    return ReclusterPeopleResponse(
        reassigned_faces=assigned + clustered_assigned,
        created_people=created_people,
    )


def get_face_crop_path_or_404(session: Session, face_id: UUID) -> Path:
    face = session.get(FaceDetection, face_id)
    if face is None or not face.crop_preview_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Face crop not found.")
    settings = get_settings()
    crop_path = (settings.preview_root_path / face.crop_preview_path).resolve(strict=False)
    if not crop_path.is_relative_to(settings.preview_root_path) or not crop_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Face crop not found.")
    return crop_path


def get_asset_faces(session: Session, asset_id: UUID, current_user: User | None = None) -> AssetFacesResponse:
    runtime = get_people_runtime_settings()
    asset = get_asset_or_404(session, asset_id, current_user=current_user)
    asset = session.execute(
        select(Asset)
        .where(Asset.id == asset.id)
        .options(selectinload(Asset.faces).selectinload(FaceDetection.person), selectinload(Asset.metadata_record))
    ).scalar_one()
    normalized = asset.metadata_record.normalized_json if asset.metadata_record else {}
    width = normalized.get("width") if isinstance(normalized.get("width"), int) else None
    height = normalized.get("height") if isinstance(normalized.get("height"), int) else None
    return AssetFacesResponse(
        enabled=runtime.face_detection_enabled,
        image_width=width,
        image_height=height,
        items=[_face_read(face) for face in sorted(asset.faces, key=lambda item: item.det_score, reverse=True)],
    )


def _person_summary(person: FacePerson, face_counts: dict[UUID, int], asset_counts: dict[UUID, int]) -> PersonSummary:
    cover_face = person.cover_face or (person.faces[0] if person.faces else None)
    return PersonSummary(
        id=person.id,
        name=person.name,
        cover_face_url=_crop_preview_url(cover_face) if cover_face else None,
        face_count=face_counts.get(person.id, 0),
        asset_count=asset_counts.get(person.id, 0),
        created_at=person.created_at,
    )


def list_people(
    session: Session,
    *,
    q: str | None = None,
    unnamed_only: bool = False,
) -> list[PersonSummary]:
    query = select(FacePerson).options(selectinload(FacePerson.faces), selectinload(FacePerson.cover_face))
    if unnamed_only:
        query = query.where(FacePerson.name.is_(None))
    elif q:
        query = query.where(func.lower(func.coalesce(FacePerson.name, "")).contains(q.strip().lower()))
    people = session.execute(query.order_by(FacePerson.created_at.desc())).scalars().unique().all()
    face_counts = dict(
        session.execute(
            select(FaceDetection.person_id, func.count(FaceDetection.id))
            .where(FaceDetection.person_id.is_not(None))
            .group_by(FaceDetection.person_id)
        ).all()
    )
    asset_counts = dict(
        session.execute(
            select(FaceDetection.person_id, func.count(func.distinct(FaceDetection.asset_id)))
            .where(FaceDetection.person_id.is_not(None))
            .group_by(FaceDetection.person_id)
        ).all()
    )
    summaries = [_person_summary(person, face_counts, asset_counts) for person in people]
    # Sort: named people first (name is None → False → sorts before True), then by face count desc, then name
    summaries.sort(key=lambda item: ((item.name is None), -(item.face_count), item.name or ""))
    return summaries


def get_person_or_404(session: Session, person_id: UUID) -> FacePerson:
    person = session.execute(
        select(FacePerson)
        .where(FacePerson.id == person_id)
        .options(
            selectinload(FacePerson.faces).selectinload(FaceDetection.person),
            selectinload(FacePerson.faces).selectinload(FaceDetection.asset).selectinload(Asset.metadata_record),
            selectinload(FacePerson.faces).selectinload(FaceDetection.asset).selectinload(Asset.tags),
            selectinload(FacePerson.faces).selectinload(FaceDetection.asset).selectinload(Asset.source),
            selectinload(FacePerson.faces).selectinload(FaceDetection.asset).selectinload(Asset.annotations),
            selectinload(FacePerson.cover_face),
        )
    ).scalar_one_or_none()
    if person is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found.")
    return person


def get_person_assets(session: Session, person_id: UUID) -> list[AssetBrowseItem]:
    person = get_person_or_404(session, person_id)
    seen: set[UUID] = set()
    items: list[AssetBrowseItem] = []
    for face in sorted(person.faces, key=lambda item: item.created_at, reverse=True):
        asset = face.asset
        if asset is None or asset.id in seen:
            continue
        seen.add(asset.id)
        items.append(asset_browse_item(asset))
    return items


def get_person_detail(session: Session, person_id: UUID) -> PersonDetail:
    person = get_person_or_404(session, person_id)
    face_count = len(person.faces)
    asset_ids = {face.asset_id for face in person.faces}
    summary = _person_summary(person, {person.id: face_count}, {person.id: len(asset_ids)})
    faces = [_face_read(face) for face in sorted(person.faces, key=lambda item: item.det_score, reverse=True)]
    # Reuse the already-loaded faces/assets instead of re-fetching via get_person_assets
    seen: set[UUID] = set()
    items: list[AssetBrowseItem] = []
    for face in sorted(person.faces, key=lambda item: item.created_at, reverse=True):
        asset = face.asset
        if asset is None or asset.id in seen:
            continue
        seen.add(asset.id)
        items.append(asset_browse_item(asset))
    return PersonDetail(
        **summary.model_dump(),
        faces=faces,
        items=items,
    )


def update_person(session: Session, person_id: UUID, payload: PersonUpdateRequest) -> FacePerson:
    person = get_person_or_404(session, person_id)
    if payload.name is not None:
        next_name = payload.name.strip() or None
        person.name = next_name
    if payload.cover_face_id is not None:
        matching = next((face for face in person.faces if face.id == payload.cover_face_id), None)
        if matching is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cover face must belong to this person.")
        person.cover_face_id = matching.id
    elif payload.cover_face_id is None and "cover_face_id" in payload.model_fields_set:
        person.cover_face_id = None
    session.flush()
    return person


def merge_people(session: Session, target_person_id: UUID, source_person_id: UUID) -> FacePerson:
    if target_person_id == source_person_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot merge a person into itself.")
    target = get_person_or_404(session, target_person_id)
    source = get_person_or_404(session, source_person_id)
    for face in source.faces:
        face.person_id = target.id
    if target.cover_face_id is None and source.cover_face_id is not None:
        target.cover_face_id = source.cover_face_id
    if target.name is None and source.name is not None:
        target.name = source.name
    session.delete(source)
    session.flush()
    return target
