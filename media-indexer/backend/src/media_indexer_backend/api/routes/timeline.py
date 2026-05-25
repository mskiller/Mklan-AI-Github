from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, desc
from sqlalchemy.orm import Session, selectinload

from media_indexer_backend.api.dependencies import get_session, require_authenticated
from media_indexer_backend.models.tables import Asset, User
from media_indexer_backend.schemas.asset import AssetListResponse
from media_indexer_backend.services.asset_service import _allowed_source_ids, _apply_source_scope, _asset_summary

router = APIRouter(prefix="/timeline", tags=["timeline"])


def _timeline_date_expression():
    return func.coalesce(Asset.created_at, Asset.modified_at)


@router.get("/years")
def get_timeline_years(
    source_id: UUID | None = Query(default=None),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> list[dict[str, Any]]:
    allowed_sources = _allowed_source_ids(session, current_user)
    date_val = _timeline_date_expression()
    year_expr = func.extract("year", date_val)
    query = select(
        year_expr.label("year"),
        func.count(Asset.id).label("count"),
    )
    if source_id is not None:
        query = query.where(Asset.source_id == source_id)
    query = _apply_source_scope(query, allowed_sources)
    query = query.where(date_val.is_not(None))
    query = query.group_by(year_expr).order_by(desc(year_expr))
    results = session.execute(query).fetchall()
    return [{"year": int(r.year), "count": r.count} for r in results if r.year is not None]

@router.get("/months")
def get_timeline_months(
    year: int = Query(...),
    source_id: UUID | None = Query(default=None),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> list[dict[str, Any]]:
    allowed_sources = _allowed_source_ids(session, current_user)
    date_val = _timeline_date_expression()
    month_expr = func.extract("month", date_val)
    query = select(
        month_expr.label("month"),
        func.count(Asset.id).label("count"),
    ).where(
        func.extract("year", date_val) == year,
        date_val.is_not(None),
    )
    if source_id is not None:
        query = query.where(Asset.source_id == source_id)
    query = _apply_source_scope(query, allowed_sources)
    query = query.group_by(month_expr).order_by(month_expr)
    results = session.execute(query).fetchall()
    return [{"month": int(r.month), "count": r.count} for r in results if r.month is not None]

@router.get("/days")
def get_timeline_days(
    year: int = Query(...),
    month: int = Query(...),
    source_id: UUID | None = Query(default=None),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> list[dict[str, Any]]:
    allowed_sources = _allowed_source_ids(session, current_user)
    date_val = _timeline_date_expression()
    day_expr = func.extract("day", date_val)
    query = select(
        day_expr.label("day"),
        func.count(Asset.id).label("count"),
    ).where(
        func.extract("year", date_val) == year,
        func.extract("month", date_val) == month,
        date_val.is_not(None),
    )
    if source_id is not None:
        query = query.where(Asset.source_id == source_id)
    query = _apply_source_scope(query, allowed_sources)
    query = query.group_by(day_expr).order_by(day_expr)
    results = session.execute(query).fetchall()
    return [{"day": int(r.day), "count": r.count} for r in results if r.day is not None]


@router.get("/assets", response_model=AssetListResponse)
def get_timeline_assets(
    year: int = Query(...),
    month: int | None = Query(default=None),
    day: int | None = Query(default=None),
    source_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> AssetListResponse:
    allowed_sources = _allowed_source_ids(session, current_user)
    date_val = _timeline_date_expression()
    query = (
        select(Asset)
        .options(
            selectinload(Asset.metadata_record),
            selectinload(Asset.tags),
            selectinload(Asset.annotations),
        )
        .where(
            func.extract("year", date_val) == year,
            date_val.is_not(None),
        )
    )
    count_query = select(func.count(Asset.id)).where(
        func.extract("year", date_val) == year,
        date_val.is_not(None),
    )
    if month is not None:
        query = query.where(func.extract("month", date_val) == month)
        count_query = count_query.where(func.extract("month", date_val) == month)
    if day is not None:
        query = query.where(func.extract("day", date_val) == day)
        count_query = count_query.where(func.extract("day", date_val) == day)
    if source_id is not None:
        query = query.where(Asset.source_id == source_id)
        count_query = count_query.where(Asset.source_id == source_id)
    query = _apply_source_scope(query, allowed_sources)
    count_query = _apply_source_scope(count_query, allowed_sources)
    total = session.scalar(count_query) or 0
    query = query.order_by(desc(date_val)).limit(limit).offset(offset)
    assets = session.execute(query).scalars().unique().all()
    user_id = current_user.id if current_user else None
    return AssetListResponse(
        items=[_asset_summary(asset, user_id=user_id) for asset in assets],
        total=total,
        page=(offset // limit) + 1,
        page_size=limit,
    )
