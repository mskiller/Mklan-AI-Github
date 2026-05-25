from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from media_indexer_backend.models.enums import UserRole, UserStatus


class UserRead(BaseModel):
    id: UUID
    username: str
    role: UserRole
    status: UserStatus
    locked_until: datetime | None = None
    ban_reason: str | None = None
    group_ids: list[UUID] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=4)
    role: UserRole = UserRole.GUEST


class UserUpdateRequest(BaseModel):
    username: str | None = Field(default=None, min_length=1)
    role: UserRole | None = None
    status: UserStatus | None = None
    locked_until: datetime | None = None
    ban_reason: str | None = None
    group_ids: list[UUID] | None = None


class UserPasswordResetRequest(BaseModel):
    new_password: str = Field(min_length=4)


class GroupRead(BaseModel):
    id: UUID
    name: str
    description: str
    permissions: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class GroupCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    permissions: dict = {}


class GroupUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    permissions: dict | None = None


class AuditLogRead(BaseModel):
    id: UUID
    actor: str
    action: str
    resource_type: str
    resource_id: UUID | None
    details: dict
    created_at: datetime

    model_config = {"from_attributes": True}
