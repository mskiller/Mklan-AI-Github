from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ScheduledScanRead(BaseModel):
    id: UUID
    source_id: UUID
    source_name: str
    cron_expression: str
    enabled: bool
    last_triggered_at: datetime | None = None
    last_job_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class ScheduledScanCreateRequest(BaseModel):
    source_id: UUID
    cron_expression: str = Field(min_length=5, max_length=64)
    enabled: bool = True


class ScheduledScanUpdateRequest(BaseModel):
    cron_expression: str | None = Field(default=None, min_length=5, max_length=64)
    enabled: bool | None = None


class WebhookEndpointRead(BaseModel):
    id: UUID
    url: str
    events: list[str]
    enabled: bool
    created_at: datetime
    last_delivered_at: datetime | None = None
    last_status_code: int | None = None


class WebhookEndpointCreateRequest(BaseModel):
    url: str = Field(min_length=8)
    secret: str = Field(min_length=8)
    events: list[str] = Field(default_factory=list)
    enabled: bool = True


class WebhookEndpointUpdateRequest(BaseModel):
    url: str | None = None
    secret: str | None = Field(default=None, min_length=8)
    events: list[str] | None = None
    enabled: bool | None = None


class ApiTokenRead(BaseModel):
    id: UUID
    name: str
    token_prefix: str
    created_by: UUID
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime


class ApiTokenCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    expires_at: datetime | None = None


class ApiTokenCreateResponse(BaseModel):
    token: str
    item: ApiTokenRead
