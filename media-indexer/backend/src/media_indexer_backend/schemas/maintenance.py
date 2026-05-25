from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ResetRequest(BaseModel):
    mode: Literal["index", "all"] = "index"


class ResetResponse(BaseModel):
    deleted_assets: int
    deleted_scan_jobs: int
    deleted_sources: int
    deleted_audit_logs: int
