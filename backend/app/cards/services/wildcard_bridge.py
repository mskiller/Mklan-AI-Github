from __future__ import annotations

import os
from pathlib import Path
from typing import Any


class WildcardBridgeService:
    def __init__(self, wildcard_root: Path | None = None) -> None:
        self.wildcard_root = wildcard_root or Path(
            os.getenv("WILDCARD_SOURCE_ROOT", Path(__file__).resolve().parents[4] / "data" / "wildcards")
        )

    def suggestions(self, query: str = "", limit: int = 30) -> dict[str, Any]:
        query_text = query.strip().lower()
        matches: list[dict[str, str]] = []
        if not self.wildcard_root.exists():
            return {"root": str(self.wildcard_root), "suggestions": [], "recipes": []}

        for path in self.wildcard_root.rglob("*"):
            if len(matches) >= limit:
                break
            if path.suffix.lower() not in {".txt", ".yaml", ".yml"} or not path.is_file():
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            for line in lines:
                candidate = line.strip().lstrip("-").strip().strip("'\"")
                if not candidate or candidate.startswith("#") or len(candidate) > 160:
                    continue
                if query_text and query_text not in candidate.lower() and query_text not in path.stem.lower():
                    continue
                matches.append(
                    {
                        "tag": candidate,
                        "source": str(path.relative_to(self.wildcard_root)),
                        "style_anchor": path.stem,
                    }
                )
                if len(matches) >= limit:
                    break
        return {
            "root": str(self.wildcard_root),
            "suggestions": matches,
            "recipes": [
                {
                    "id": item["source"],
                    "label": item["style_anchor"],
                    "tags": [item["tag"]],
                }
                for item in matches[:10]
            ],
        }
