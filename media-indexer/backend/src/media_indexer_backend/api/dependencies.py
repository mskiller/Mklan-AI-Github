from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from media_indexer_backend.core.auth import verify_session_token
from media_indexer_backend.core.config import get_settings
from media_indexer_backend.db.session import get_db_session
from media_indexer_backend.models.enums import UserRole, UserStatus
from media_indexer_backend.models.tables import User
from media_indexer_backend.platform.service import ensure_module_enabled as ensure_platform_module_enabled
from media_indexer_backend.schemas.auth import AuthCapabilities
from media_indexer_backend.services.api_token_service import authenticate_api_token
from media_indexer_backend.services.user_service import capabilities_for_user, enforce_user_status


def get_session(session: Session = Depends(get_db_session)) -> Session:
    return session


def get_current_user(
    request: Request,
    session: Session = Depends(get_session),
    authorization: str | None = Header(default=None),
) -> User:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:]
    
    # Studio Integration: Bypass Auth
    if not token:
        from sqlalchemy import select
        from media_indexer_backend.models.enums import UserRole
        admin_user = session.execute(select(User).where(User.role == UserRole.ADMIN)).scalar_one_or_none()
        if admin_user:
            return enforce_user_status(session, admin_user)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

    user_id = verify_session_token(token) if token else None
    if not user_id:
        from sqlalchemy import select
        from media_indexer_backend.models.enums import UserRole
        admin_user = session.execute(select(User).where(User.role == UserRole.ADMIN)).scalar_one_or_none()
        if admin_user:
            return enforce_user_status(session, admin_user)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    return enforce_user_status(session, user)


def get_current_capabilities(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> AuthCapabilities:
    return capabilities_for_user(session, current_user)


def require_authenticated(current_user: User = Depends(get_current_user)) -> User:
    return current_user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
    return current_user


def require_collection_manager(
    current_user: User = Depends(get_current_user),
    capabilities: AuthCapabilities = Depends(get_current_capabilities),
) -> User:
    if not capabilities.can_manage_collections:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Collection management access required.")
    return current_user


def require_upload_access(
    current_user: User = Depends(get_current_user),
    capabilities: AuthCapabilities = Depends(get_current_capabilities),
) -> User:
    if not capabilities.can_upload_assets:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Upload access required.")
    return current_user


def require_curator_or_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in {UserRole.CURATOR, UserRole.ADMIN}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Curator or admin access required.")
    return current_user


def require_enabled_module(module_id: str):
    def dependency(session: Session = Depends(get_session)) -> None:
        ensure_platform_module_enabled(session, module_id)

    return dependency


def require_api_token_user(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> User:
    raw_token = x_api_key
    if authorization and authorization.lower().startswith("bearer "):
        raw_token = authorization[7:]
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Valid API token required.")
    user = authenticate_api_token(session, raw_token)
    return enforce_user_status(session, user)


def user_can_access_source(capabilities: AuthCapabilities, source_id) -> bool:
    if capabilities.allowed_source_ids == "all":
        return True
    return str(source_id) in {str(value) for value in capabilities.allowed_source_ids}
