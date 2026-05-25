from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from media_indexer_backend.models.tables import CurationEvent


def log_curation_event(
    session: Session,
    *,
    user_id: UUID,
    asset_id: UUID,
    event_type: str,
    details_json: dict | None = None,
) -> CurationEvent:
    event = CurationEvent(
        user_id=user_id,
        asset_id=asset_id,
        event_type=event_type,
        details_json=details_json,
    )
    session.add(event)
    session.flush()
    return event
