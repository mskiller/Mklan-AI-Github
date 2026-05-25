from __future__ import annotations

import uuid
import numpy as np
from typing import Any
from sklearn.cluster import KMeans
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from media_indexer_backend.models.tables import Asset, AssetSimilarity
from media_indexer_backend.schemas.clustering import ClusterProposal

def run_clustering(
    session: Session, 
    k: int = 20, 
    min_size: int = 5
) -> list[ClusterProposal]:
    # 1. Fetch all assets with embeddings
    query = (
        select(AssetSimilarity)
        .where(AssetSimilarity.embedding.is_not(None))
    )
    similarities = session.execute(query).scalars().all()
    
    if not similarities:
        return []
    
    asset_ids = [str(s.asset_id) for s in similarities]
    embeddings = np.array([s.embedding for s in similarities])
    
    # 2. Run k-means
    # If we have fewer samples than k, reduce k
    actual_k = min(k, len(embeddings))
    if actual_k < 1:
        return []
        
    kmeans = KMeans(n_clusters=actual_k, random_state=42, n_init="auto")
    labels = kmeans.fit_predict(embeddings)
    centroids = kmeans.cluster_centers_
    
    # 3. Organize clusters
    clusters: dict[int, list[str]] = {}
    for i, label in enumerate(labels):
        if label not in clusters:
            clusters[label] = []
        clusters[label].append(asset_ids[i])
        
    proposals = []
    for label, members in clusters.items():
        if len(members) < min_size:
            continue
            
        # Find asset closest to centroid as "centroid_id"
        cluster_indices = [i for i, l in enumerate(labels) if l == label]
        cluster_embeddings = embeddings[cluster_indices]
        centroid = centroids[label]
        
        # Calculate distances to centroid
        distances = np.linalg.norm(cluster_embeddings - centroid, axis=1)
        sort_idx = np.argsort(distances)
        
        centroid_asset_id = asset_ids[cluster_indices[sort_idx[0]]]
        cover_asset_ids = [asset_ids[cluster_indices[idx]] for idx in sort_idx[:4]]
        
        proposals.append(ClusterProposal(
            centroid_id=centroid_asset_id,
            cover_asset_ids=cover_asset_ids,
            asset_ids=members,
            size=len(members),
            suggested_label=f"Suggested Collection {label + 1}"
        ))
        
    # Sort by size descending
    proposals.sort(key=lambda x: x.size, reverse=True)
    return proposals
