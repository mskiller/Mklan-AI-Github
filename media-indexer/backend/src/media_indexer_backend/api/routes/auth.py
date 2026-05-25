from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from media_indexer_backend.api.dependencies import get_session, require_authenticated
from media_indexer_backend.core.auth import create_session_token
from media_indexer_backend.core.config import get_settings
from media_indexer_backend.core.rate_limit import enforce_rate_limit
from media_indexer_backend.models.tables import User
from media_indexer_backend.schemas.auth import AuthUserResponse, ChangePasswordRequest, LoginRequest
from media_indexer_backend.services.user_service import auth_user_response, authenticate_user, change_password


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=AuthUserResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> AuthUserResponse:
    settings = get_settings()
    client_host = request.client.host if request.client else "unknown"
    enforce_rate_limit(f"login:{client_host}", limit=10, window_seconds=60, detail="Too many login attempts.")
    user = authenticate_user(session, payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")

    token = create_session_token(user.id)
    response.set_cookie(
        settings.session_cookie_name,
        token,
        httponly=True,
        max_age=settings.access_token_ttl_seconds,
        samesite="lax",
        secure=settings.cookie_secure,
    )
    return auth_user_response(session, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout() -> Response:
    settings = get_settings()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(settings.session_cookie_name)
    return response


@router.get("/me", response_model=AuthUserResponse)
def me(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> AuthUserResponse:
    return auth_user_response(session, current_user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def post_change_password(
    payload: ChangePasswordRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_authenticated),
) -> Response:
    change_password(session, current_user, payload.current_password, payload.new_password, payload.confirm_password)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
