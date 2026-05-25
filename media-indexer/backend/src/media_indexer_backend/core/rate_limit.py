from __future__ import annotations

import threading
import time

from fastapi import HTTPException, status


_LOCK = threading.Lock()
_BUCKETS: dict[str, list[float]] = {}


def enforce_rate_limit(key: str, limit: int, window_seconds: int, detail: str) -> None:
    now = time.time()
    cutoff = now - window_seconds
    with _LOCK:
        entries = [value for value in _BUCKETS.get(key, []) if value >= cutoff]
        if len(entries) >= limit:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail)
        entries.append(now)
        _BUCKETS[key] = entries
