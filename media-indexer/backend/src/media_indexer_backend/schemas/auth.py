from __future__ import annotations

from uuid import UUID
from typing import Literal

from pydantic import BaseModel, Field

from media_indexer_backend.models.enums import UserRole


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=4)
    confirm_password: str = Field(min_length=4)


class AuthCapabilities(BaseModel):
    can_manage_sources: bool
    can_run_scans: bool
    can_review_compare: bool
    can_reset: bool
    can_manage_users: bool
    can_manage_collections: bool
    can_upload_assets: bool
    can_view_admin: bool
    allowed_source_ids: list[UUID] | Literal["all"]


class AuthUserResponse(BaseModel):
    authenticated: bool = True
    id: UUID
    username: str
    role: UserRole
    capabilities: AuthCapabilities
