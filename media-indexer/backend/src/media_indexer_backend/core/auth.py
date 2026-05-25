from __future__ import annotations

from uuid import UUID

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from media_indexer_backend.core.config import get_settings


def _serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    return URLSafeTimedSerializer(settings.session_secret, salt="media-indexer-session")


def create_session_token(user_id: UUID) -> str:
    return _serializer().dumps({"user_id": str(user_id)})


def verify_session_token(token: str) -> UUID | None:
    settings = get_settings()
    try:
        payload = _serializer().loads(token, max_age=settings.access_token_ttl_seconds)
    except (BadSignature, SignatureExpired):
        return None
    user_id = payload.get("user_id")
    if not user_id:
        return None
    try:
        return UUID(str(user_id))
    except ValueError:
        return None
