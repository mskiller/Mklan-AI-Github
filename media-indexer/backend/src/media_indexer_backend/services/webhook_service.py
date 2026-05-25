from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import threading
from datetime import datetime, timezone

from sqlalchemy import select

from media_indexer_backend.db.session import SessionLocal
from media_indexer_backend.models.tables import WebhookEndpoint


logger = logging.getLogger(__name__)

WEBHOOK_EVENTS = [
    "asset.indexed",
    "asset.updated",
    "collection.updated",
    "scan.started",
    "scan.completed",
    "scan.failed",
    "inbox.item_ready",
    "smart_album.suggested",
]


def _utcnow_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


async def dispatch(event: str, payload: dict) -> None:
    try:
        import httpx
    except Exception as exc:  # noqa: BLE001
        logger.warning("webhook dispatch unavailable", extra={"error": str(exc)})
        return

    with SessionLocal() as session:
        endpoints = session.execute(
            select(WebhookEndpoint).where(WebhookEndpoint.enabled == True)  # noqa: E712
        ).scalars().all()

    targets = [endpoint for endpoint in endpoints if event in (endpoint.events or [])]
    if not targets:
        return

    await _deliver_to_targets(targets, event, payload)


async def _deliver_to_targets(targets: list[WebhookEndpoint], event: str, payload: dict) -> None:
    try:
        import httpx
    except Exception as exc:  # noqa: BLE001
        logger.warning("webhook dispatch unavailable", extra={"error": str(exc)})
        return

    body = json.dumps({"event": event, "timestamp": _utcnow_iso(), **payload})
    async with httpx.AsyncClient(timeout=10) as client:
        for endpoint in targets:
            status_code = 0
            try:
                signature = hmac.new(endpoint.secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
                response = await client.post(
                    endpoint.url,
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-MKLan-Signature": signature,
                    },
                )
                status_code = response.status_code
            except Exception as exc:  # noqa: BLE001
                logger.warning("webhook delivery failed", extra={"endpoint": endpoint.url, "event": event, "error": str(exc)})
            finally:
                with SessionLocal() as session:
                    managed = session.get(WebhookEndpoint, endpoint.id)
                    if managed is not None:
                        managed.last_delivered_at = datetime.now(tz=timezone.utc)
                        managed.last_status_code = status_code
                        session.commit()


def dispatch_webhook_event(event: str, payload: dict) -> None:
    thread = threading.Thread(target=lambda: asyncio.run(dispatch(event, payload)), daemon=True)
    thread.start()


async def dispatch_to_endpoint(endpoint_id, event: str, payload: dict) -> None:
    with SessionLocal() as session:
        endpoint = session.get(WebhookEndpoint, endpoint_id)
        if endpoint is None or not endpoint.enabled:
            return
        target = WebhookEndpoint(
            id=endpoint.id,
            url=endpoint.url,
            secret=endpoint.secret,
            events=list(endpoint.events or []),
            enabled=endpoint.enabled,
        )
    await _deliver_to_targets([target], event, payload)


def dispatch_webhook_test(endpoint_id, event: str, payload: dict) -> None:
    thread = threading.Thread(target=lambda: asyncio.run(dispatch_to_endpoint(endpoint_id, event, payload)), daemon=True)
    thread.start()
