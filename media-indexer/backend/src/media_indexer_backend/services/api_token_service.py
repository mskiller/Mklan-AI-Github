from __future__ import annotations

import secrets
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from media_indexer_backend.models.tables import ApiToken, User
from media_indexer_backend.schemas.integrations import ApiTokenCreateRequest, ApiTokenRead
from media_indexer_backend.services.user_service import hash_password, verify_password


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def api_token_read(item: ApiToken) -> ApiTokenRead:
    return ApiTokenRead(
        id=item.id,
        name=item.name,
        token_prefix=item.token_prefix,
        created_by=item.created_by,
        expires_at=item.expires_at,
        last_used_at=item.last_used_at,
        revoked_at=item.revoked_at,
        created_at=item.created_at,
    )


def list_api_tokens(session: Session) -> list[ApiTokenRead]:
    items = session.execute(select(ApiToken).order_by(ApiToken.created_at.desc())).scalars().all()
    return [api_token_read(item) for item in items]


def create_api_token(session: Session, payload: ApiTokenCreateRequest, current_user: User) -> tuple[ApiToken, str]:
    raw_token = f"mkl_{secrets.token_urlsafe(32)}"
    item = ApiToken(
        name=payload.name.strip(),
        token_prefix=raw_token[:12],
        token_hash=hash_password(raw_token),
        created_by=current_user.id,
        expires_at=payload.expires_at,
    )
    session.add(item)
    session.flush()
    return item, raw_token


def revoke_api_token(session: Session, token_id: UUID) -> ApiToken:
    item = session.get(ApiToken, token_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API token not found.")
    item.revoked_at = utcnow()
    session.flush()
    return item


def authenticate_api_token(session: Session, raw_token: str) -> User:
    items = session.execute(
        select(ApiToken)
        .where(ApiToken.revoked_at.is_(None))
        .order_by(ApiToken.created_at.desc())
    ).scalars().all()
    for item in items:
        if item.expires_at and item.expires_at <= utcnow():
            continue
        if not verify_password(item.token_hash, raw_token):
            continue
        item.last_used_at = utcnow()
        session.flush()
        user = session.get(User, item.created_by)
        if user is None:
            break
        return user
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Valid API token required.")
