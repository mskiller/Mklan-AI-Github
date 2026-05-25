from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from media_indexer_backend.api.dependencies import get_session, require_admin, require_authenticated
from media_indexer_backend.models.tables import User
from media_indexer_backend.schemas.asset import CompareResponse, CompareReviewRequest
from media_indexer_backend.services.audit import record_audit_event
from media_indexer_backend.services.compare_service import compare_assets


router = APIRouter(tags=["compare"])


@router.get("/compare", response_model=CompareResponse)
def get_compare(
    a: UUID,
    b: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> CompareResponse:
    return compare_assets(session, a, b, current_user=current_user)


@router.post("/compare/review", status_code=status.HTTP_204_NO_CONTENT)
def post_compare_review(
    payload: CompareReviewRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> None:
    record_audit_event(
        session,
        actor=current_user.username,
        action=f"compare.{payload.action}",
        resource_type="compare_review",
        details={
            "asset_id_a": str(payload.asset_id_a),
            "asset_id_b": str(payload.asset_id_b),
        },
    )
    session.commit()
