from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ModuleSettingField(BaseModel):
    key: str
    label: str
    type: Literal["boolean", "string", "integer", "number"]
    description: str | None = None
    default: Any = None


class ModuleManifest(BaseModel):
    id: str
    name: str
    version: str
    description: str | None = None
    platform_api_version: str = "1"
    kind: Literal["builtin", "addon"] = "addon"
    source_ref: str | None = None
    enabled_by_default: bool = True
    permissions: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    backend_entrypoint: str | None = None
    worker_entrypoint: str | None = None
    frontend_entrypoint: str | None = None
    backend_migrations: str | None = None
    backend_router: str | None = None
    api_mount: str | None = None
    user_mount: str | None = None
    admin_mount: str | None = None
    nav_label: str | None = None
    nav_href: str | None = None
    nav_order: int = 100
    admin_nav_label: str | None = None
    admin_nav_href: str | None = None
    admin_nav_order: int = 100
    user_visible: bool = False
    admin_visible: bool = False
    settings_fields: list[ModuleSettingField] = Field(default_factory=list)
    manifest_path: str | None = None
    error: str | None = None
