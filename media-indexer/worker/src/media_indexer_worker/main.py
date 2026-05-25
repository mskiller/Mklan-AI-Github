from __future__ import annotations

from datetime import datetime, timezone
import logging
import threading

from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
from sqlalchemy import func, select

from media_indexer_backend.db.session import SessionLocal
from media_indexer_backend.models.enums import ScanStatus, SourceStatus
from media_indexer_backend.models.tables import ScanJob, Source
from media_indexer_backend.services.image_enrichment import get_image_enrichment_service
from media_indexer_backend.core.logging import configure_logging
from media_indexer_backend.core.config import get_settings
from media_indexer_worker.services.scanner import ScanWorker
from media_indexer_backend.platform.bootstrap import bootstrap_platform


logger = logging.getLogger(__name__)


class TextEmbedRequest(BaseModel):
    text: str


def create_sidecar_app(worker: ScanWorker) -> FastAPI:
    app = FastAPI(title="media-indexer-worker-sidecar", version="0.1.0")

    @app.get("/status")
    def get_status() -> dict:
        with SessionLocal() as session:
            pending_jobs = session.execute(select(func.count(ScanJob.id)).where(ScanJob.status == ScanStatus.QUEUED)).scalar_one()
            running_jobs = session.execute(select(func.count(ScanJob.id)).where(ScanJob.status == ScanStatus.RUNNING)).scalar_one()
        enrichment = worker.image_enrichment
        provider_statuses = {item.key: item for item in enrichment.provider_statuses()}
        return {
            "clip_loaded": worker.similarity.embedder.is_loaded,
            "clip_model_id": worker.settings.clip_model_id,
            "wd_tagger_loaded": provider_statuses.get("wd_vit_v3") is not None and provider_statuses["wd_vit_v3"].warm,
            "caption_loaded": getattr(enrichment.captioning, "_model", None) is not None,
            "pending_jobs": int(pending_jobs or 0),
            "running_jobs": int(running_jobs or 0),
        }

    @app.post("/embed/text")
    def post_embed_text(payload: TextEmbedRequest) -> dict:
        embedding = worker.similarity.embedder.embed_text(payload.text) or []
        return {"embedding": embedding}

    return app


def start_sidecar(worker: ScanWorker) -> None:
    settings = get_settings()
    app = create_sidecar_app(worker)

    def run() -> None:
        uvicorn.run(app, host="0.0.0.0", port=settings.worker_status_port, log_level="warning")

    thread = threading.Thread(target=run, daemon=True)
    thread.start()


def recover_interrupted_scan_jobs() -> int:
    now = datetime.now(tz=timezone.utc)
    recovered = 0
    with SessionLocal() as session:
        jobs = session.execute(select(ScanJob).where(ScanJob.status == ScanStatus.RUNNING)).scalars().all()
        for job in jobs:
            job.status = ScanStatus.FAILED
            job.finished_at = now
            job.message = "Scan interrupted by worker restart. Queue a new scan to continue indexing."
            source = session.get(Source, job.source_id)
            if source is not None and source.status == SourceStatus.SCANNING:
                source.status = SourceStatus.READY
            recovered += 1
        if recovered:
            session.commit()
    return recovered


def main() -> None:
    configure_logging()
    with SessionLocal() as session:
        bootstrap_platform(session, runtime="worker")
        session.commit()
    recovered = recover_interrupted_scan_jobs()
    if recovered:
        logger.warning("recovered interrupted scan jobs", extra={"recovered_count": recovered})
    worker = ScanWorker()
    start_sidecar(worker)
    worker.run_forever()


if __name__ == "__main__":
    main()
