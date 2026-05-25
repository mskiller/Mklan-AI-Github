from __future__ import annotations

from pydantic import BaseModel
from uuid import UUID

class ClusterProposal(BaseModel):
    centroid_id: UUID
    cover_asset_ids: list[UUID]
    asset_ids: list[UUID]
    size: int
    suggested_label: str

class ClusteringRequest(BaseModel):
    k: int = 20
    min_size: int = 5

class ClusterAcceptRequest(BaseModel):
    label: str
    asset_ids: list[UUID]

class ClusteringAcceptAllRequest(BaseModel):
    proposals: list[ClusterAcceptRequest]
