from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from app.v2.core_db import connect_core_db, core_db_enabled, initialize_core_db
from app.v2.workspaces import active_workspace_id


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class AuditLog:
    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root
        self.path = data_root / "audit" / "studio-audit.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, action: str, *, actor: str = "local", target: str = "", payload: dict[str, Any] | None = None) -> None:
        entry = {
            "timestamp": utc_now_iso(),
            "actor": actor,
            "action": action,
            "target": target,
            "payload": payload or {},
            "workspace_id": active_workspace_id(self.data_root),
        }
        if core_db_enabled():
            try:
                initialize_core_db()
                with connect_core_db() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            """
                            INSERT INTO platform_audit_events (timestamp, actor, action, target, payload_json, workspace_id)
                            VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                            """,
                            (
                                entry["timestamp"],
                                entry["actor"],
                                entry["action"],
                                entry["target"],
                                json.dumps(entry["payload"], ensure_ascii=False, sort_keys=True),
                                entry["workspace_id"],
                            ),
                        )
                    conn.commit()
                return
            except Exception:
                pass
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
