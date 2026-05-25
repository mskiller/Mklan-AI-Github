from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class AuditLog:
    def __init__(self, data_root: Path) -> None:
        self.path = data_root / "audit" / "studio-audit.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, action: str, *, actor: str = "local", target: str = "", payload: dict[str, Any] | None = None) -> None:
        entry = {
            "timestamp": utc_now_iso(),
            "actor": actor,
            "action": action,
            "target": target,
            "payload": payload or {},
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")

