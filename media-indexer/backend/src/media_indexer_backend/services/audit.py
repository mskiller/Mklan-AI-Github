from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from media_indexer_backend.models.tables import AuditLog


def _normalize_resource_id(resource_id: UUID | str | None) -> tuple[UUID | None, str | None]:
    if resource_id is None:
        return None, None
    if isinstance(resource_id, UUID):
        return resource_id, None

    candidate = str(resource_id).strip()
    if not candidate:
        return None, None
    try:
        return UUID(candidate), None
    except ValueError:
        return None, candidate


def record_audit_event(
    session: Session,
    *,
    actor: str,
    action: str,
    resource_type: str,
    resource_id: UUID | str | None = None,
    details: dict | None = None,
) -> None:
    normalized_resource_id, resource_ref = _normalize_resource_id(resource_id)
    payload = dict(details or {})
    if resource_ref and "resource_ref" not in payload:
        payload["resource_ref"] = resource_ref

    session.add(
        AuditLog(
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=normalized_resource_id,
            details=payload,
        )
    )
