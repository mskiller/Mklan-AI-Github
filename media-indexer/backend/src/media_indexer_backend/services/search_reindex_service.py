from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from media_indexer_backend.models.tables import Asset, AssetSearch
from media_indexer_backend.services.metadata import build_search_text


def reindex_search_documents(session: Session) -> int:
    assets = session.execute(
        select(Asset).options(selectinload(Asset.metadata_record), selectinload(Asset.tags))
    ).scalars().all()

    for asset in assets:
        normalized = asset.metadata_record.normalized_json if asset.metadata_record else {}
        tags = [tag.tag for tag in asset.tags]
        search_text = build_search_text(asset.filename, asset.relative_path, normalized, tags)
        session.execute(
            insert(AssetSearch)
            .values(asset_id=asset.id, document=func.to_tsvector("simple", search_text))
            .on_conflict_do_update(
                index_elements=[AssetSearch.asset_id],
                set_={"document": func.to_tsvector("simple", search_text)},
            )
        )
    session.flush()
    return len(assets)
