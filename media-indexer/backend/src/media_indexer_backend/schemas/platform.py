from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class ModuleSettingFieldRead(BaseModel):
    key: str
    label: str
    type: Literal["boolean", "string", "integer", "number"]
    description: str | None = None
    default: Any = None


class PlatformModuleRead(BaseModel):
    module_id: str
    name: str
    kind: str
    version: str
    description: str | None = None
    platform_api_version: str
    source_ref: str | None = None
    enabled: bool
    status: str
    error: str | None = None
    permissions: list[str]
    dependencies: list[str]
    backend_entrypoint: str | None = None
    worker_entrypoint: str | None = None
    frontend_entrypoint: str | None = None
    backend_migrations: str | None = None
    api_mount: str | None = None
    user_mount: str | None = None
    admin_mount: str | None = None
    nav_label: str | None = None
    nav_href: str | None = None
    nav_order: int
    admin_nav_label: str | None = None
    admin_nav_href: str | None = None
    admin_nav_order: int
    user_visible: bool
    admin_visible: bool
    settings_schema: list[ModuleSettingFieldRead]
    settings_json: dict[str, Any]
    manifest_path: str | None = None
    installed_at: datetime
    updated_at: datetime


class PlatformModuleUpdateRequest(BaseModel):
    enabled: bool | None = None
    settings_json: dict[str, Any] | None = None
