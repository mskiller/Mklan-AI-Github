from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from media_indexer_backend.core.config import get_settings
from media_indexer_backend.models.enums import UserRole, UserStatus
from media_indexer_backend.models.tables import AuditLog, Group, User, UserGroup
from media_indexer_backend.schemas.admin import (
    AuditLogRead,
    GroupCreateRequest,
    GroupRead,
    GroupUpdateRequest,
    UserCreateRequest,
    UserRead,
    UserUpdateRequest,
)
from media_indexer_backend.schemas.auth import AuthCapabilities, AuthUserResponse


_password_hasher = PasswordHasher()


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


ROLE_BASE = {
    UserRole.GUEST: {
        "can_manage_sources": False,
        "can_run_scans": False,
        "can_review_compare": False,
        "can_reset": False,
        "can_manage_users": False,
        "can_manage_collections": False,
        "can_upload_assets": False,
        "can_view_admin": False,
    },
    UserRole.CURATOR: {
        "can_manage_sources": False,
        "can_run_scans": False,
        "can_review_compare": True,
        "can_reset": False,
        "can_manage_users": False,
        "can_manage_collections": True,
        "can_upload_assets": True,
        "can_view_admin": False,
    },
    UserRole.ADMIN: {
        "can_manage_sources": True,
        "can_run_scans": True,
        "can_review_compare": True,
        "can_reset": True,
        "can_manage_users": True,
        "can_manage_collections": True,
        "can_upload_assets": True,
        "can_view_admin": True,
    },
}


def get_user_groups(session: Session, user: User) -> list[Group]:
    refreshed = session.execute(
        select(User)
        .where(User.id == user.id)
        .options(selectinload(User.group_memberships).selectinload(UserGroup.group))
    ).scalar_one()
    return [membership.group for membership in refreshed.group_memberships if membership.group is not None]


def resolve_capabilities(user: User, groups: list[Group]) -> AuthCapabilities:
    caps: dict[str, bool | list[str] | str] = {**ROLE_BASE[user.role], "allowed_source_ids": "all"}
    explicit_source_lists: list[str] = []
    source_scope_configured = False

    for group in groups:
        permissions = group.permissions if isinstance(group.permissions, dict) else {}
        for key, value in permissions.items():
            if isinstance(value, bool) and key in caps:
                caps[key] = bool(caps.get(key, False) or value)
            elif key == "allowed_source_ids":
                source_scope_configured = True
                if value == "all":
                    explicit_source_lists = []
                    caps["allowed_source_ids"] = "all"
                elif isinstance(value, list) and caps.get("allowed_source_ids") != "all":
                    explicit_source_lists.extend(str(item) for item in value)
                elif isinstance(value, list):
                    caps["allowed_source_ids"] = []
                    explicit_source_lists.extend(str(item) for item in value)

    if source_scope_configured and caps.get("allowed_source_ids") != "all":
        caps["allowed_source_ids"] = sorted(set(explicit_source_lists))

    return AuthCapabilities(**caps)


def capabilities_for_user(session: Session, user: User) -> AuthCapabilities:
    return resolve_capabilities(user, get_user_groups(session, user))


def auth_user_response(session: Session, user: User) -> AuthUserResponse:
    return AuthUserResponse(
        id=user.id,
        username=user.username,
        role=user.role,
        capabilities=capabilities_for_user(session, user),
    )


def get_user_or_404(session: Session, user_id: UUID) -> User:
    user = session.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.group_memberships))
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


def get_user_by_username(session: Session, username: str) -> User | None:
    return session.execute(select(User).where(User.username == username.strip())).scalar_one_or_none()


def list_users(session: Session) -> list[User]:
    return (
        session.execute(
            select(User)
            .order_by(User.role, User.username)
            .options(selectinload(User.group_memberships))
        )
        .scalars()
        .all()
    )


def list_groups(session: Session) -> list[Group]:
    return session.execute(select(Group).order_by(Group.name)).scalars().all()


def list_audit_logs(session: Session, limit: int = 50) -> list[AuditLogRead]:
    logs = session.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)).scalars().all()
    return [AuditLogRead.model_validate(log) for log in logs]


def authenticate_user(session: Session, username: str, password: str) -> User | None:
    user = get_user_by_username(session, username)
    if not user:
        return None
    if not verify_password(user.password_hash, password):
        return None
    # Raises 403 with the specific reason for locked/banned accounts
    enforce_user_status(session, user)
    return user


def enforce_user_status(session: Session, user: User) -> User:
    if user.status == UserStatus.LOCKED:
        if user.locked_until and user.locked_until <= utcnow():
            user.status = UserStatus.ACTIVE
            user.locked_until = None
            session.flush()
            return user
        remaining = "unknown"
        if user.locked_until:
            delta = max(0, int((user.locked_until - utcnow()).total_seconds() // 60))
            remaining = f"{delta} more minutes"
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Account locked for {remaining}.")
    if user.status == UserStatus.BANNED:
        detail = user.ban_reason or "contact an administrator"
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Account banned: {detail}.")
    if user.status != UserStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    return user


def ensure_seed_users(session: Session) -> None:
    settings = get_settings()
    defaults: Iterable[tuple[str, str, UserRole]] = [
        (settings.admin_username, settings.admin_password, UserRole.ADMIN),
        (settings.curator_username, settings.curator_password, UserRole.CURATOR),
        (settings.guest_username, settings.guest_password, UserRole.GUEST),
    ]
    for username, password, role in defaults:
        if not username.strip():
            continue
        existing = get_user_by_username(session, username)
        if existing:
            existing.role = role
            if existing.status in {UserStatus.DISABLED, UserStatus.ACTIVE}:
                existing.status = UserStatus.ACTIVE
            continue
        session.add(
            User(
                username=username.strip(),
                password_hash=hash_password(password),
                role=role,
                status=UserStatus.ACTIVE,
            )
        )
    session.flush()


def _assert_username_available(session: Session, username: str, *, exclude_user_id: UUID | None = None) -> None:
    existing = get_user_by_username(session, username)
    if existing and existing.id != exclude_user_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists.")


def _active_admin_count(session: Session) -> int:
    return session.execute(
        select(func.count(User.id)).where(User.role == UserRole.ADMIN, User.status == UserStatus.ACTIVE)
    ).scalar_one()


def _assert_not_last_active_admin(
    session: Session,
    user: User,
    *,
    next_role: UserRole | None = None,
    next_status: UserStatus | None = None,
) -> None:
    resolved_role = next_role or user.role
    resolved_status = next_status or user.status
    if user.role != UserRole.ADMIN or user.status != UserStatus.ACTIVE:
        return
    if resolved_role == UserRole.ADMIN and resolved_status == UserStatus.ACTIVE:
        return
    if _active_admin_count(session) <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot disable or demote the last active admin.",
        )


def create_user(session: Session, payload: UserCreateRequest) -> User:
    username = payload.username.strip()
    _assert_username_available(session, username)
    user = User(
        username=username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        status=UserStatus.ACTIVE,
    )
    session.add(user)
    session.flush()
    return user


def update_user(session: Session, user_id: UUID, payload: UserUpdateRequest) -> User:
    user = get_user_or_404(session, user_id)
    if payload.username is not None:
        username = payload.username.strip()
        _assert_username_available(session, username, exclude_user_id=user.id)
        user.username = username
    if payload.role is not None or payload.status is not None:
        _assert_not_last_active_admin(session, user, next_role=payload.role, next_status=payload.status)
    if payload.role is not None:
        user.role = payload.role
    if payload.status is not None:
        user.status = payload.status
        if payload.status != UserStatus.LOCKED:
            user.locked_until = None
        if payload.status != UserStatus.BANNED:
            user.ban_reason = None
    if payload.locked_until is not None:
        user.locked_until = payload.locked_until
        if payload.locked_until:
            user.status = UserStatus.LOCKED
    if payload.ban_reason is not None:
        user.ban_reason = payload.ban_reason
        if payload.ban_reason:
            user.status = UserStatus.BANNED
    if payload.group_ids is not None:
        groups = session.execute(select(Group).where(Group.id.in_(payload.group_ids))).scalars().all()
        if len(groups) != len(payload.group_ids):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more groups were not found.")
        user.group_memberships.clear()
        for group_id in payload.group_ids:
            user.group_memberships.append(UserGroup(user_id=user.id, group_id=group_id))
    session.flush()
    return user


def set_user_password(session: Session, user_id: UUID, new_password: str) -> User:
    user = get_user_or_404(session, user_id)
    user.password_hash = hash_password(new_password)
    session.flush()
    return user


def change_password(session: Session, user: User, current_password: str, new_password: str, confirm_password: str) -> User:
    if new_password != confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password confirmation does not match.")
    if not verify_password(user.password_hash, current_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect.")
    user.password_hash = hash_password(new_password)
    session.flush()
    return user


def create_group(session: Session, payload: GroupCreateRequest) -> Group:
    existing = session.execute(select(Group).where(Group.name == payload.name.strip())).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Group name already exists.")
    group = Group(
        name=payload.name.strip(),
        description=payload.description,
        permissions=payload.permissions,
    )
    session.add(group)
    session.flush()
    return group


def update_group(session: Session, group_id: UUID, payload: GroupUpdateRequest) -> Group:
    group = session.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found.")
    if payload.name is not None:
        existing = session.execute(select(Group).where(Group.name == payload.name.strip(), Group.id != group_id)).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Group name already exists.")
        group.name = payload.name.strip()
    if payload.description is not None:
        group.description = payload.description
    if payload.permissions is not None:
        group.permissions = payload.permissions
    session.flush()
    return group


def delete_group(session: Session, group_id: UUID) -> Group:
    group = session.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found.")
    session.delete(group)
    return group


def group_reads(groups: list[Group]) -> list[GroupRead]:
    return [GroupRead.model_validate(group) for group in groups]


def user_reads(users: list[User]) -> list[UserRead]:
    return [
        UserRead(
            id=user.id,
            username=user.username,
            role=user.role,
            status=user.status,
            locked_until=user.locked_until,
            ban_reason=user.ban_reason,
            group_ids=[membership.group_id for membership in user.group_memberships],
            created_at=user.created_at,
            updated_at=user.updated_at,
        )
        for user in users
    ]
