from __future__ import annotations

import argparse
import os
from pathlib import Path
import sqlite3
from typing import Any

from app.v2.core_db import connect_core_db, initialize_core_db


DEFAULT_TABLES = {
    "wildcards": ("WILDCARD_WORKSHOP_DB", "data/wildcards/wildcard_workshop.db", ["source_files", "entries", "prompt_recipes", "llm_jobs"]),
    "movie": ("MOVIE_DB", "data/movie/movie_tool.db", ["projects", "story_scenes", "scenes", "jobs"]),
    "cards": ("CARDS_DB", "data/cards/card_creator.db", ["projects", "characters", "scenarios", "lore_entries"]),
}


def _count_sqlite_tables(db_path: Path, tables: list[str]) -> dict[str, int | str]:
    if not db_path.exists():
        return {table: "missing-db" for table in tables}
    counts: dict[str, int | str] = {}
    with sqlite3.connect(db_path) as conn:
        existing = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        for table in tables:
            if table not in existing:
                counts[table] = "missing-table"
                continue
            counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    return counts


def _platform_counts() -> dict[str, int | str]:
    if not os.getenv("STUDIO_DATABASE_URL", "").strip():
        return {"platform_jobs": "no-STUDIO_DATABASE_URL", "platform_assets": "no-STUDIO_DATABASE_URL"}
    initialize_core_db()
    with connect_core_db() as conn:
        with conn.cursor() as cursor:
            result: dict[str, int | str] = {}
            for table in ("platform_jobs", "platform_job_events", "platform_assets", "platform_audit_events"):
                cursor.execute(f"SELECT COUNT(*) AS count FROM {table}")
                result[table] = int(cursor.fetchone()["count"])
            return result


def collect_plan(data_root: Path) -> dict[str, Any]:
    modules = {}
    for module, (env_name, relative_path, tables) in DEFAULT_TABLES.items():
        db_path = Path(os.getenv(env_name, str(data_root / relative_path)))
        modules[module] = {
            "source": str(db_path),
            "tables": _count_sqlite_tables(db_path, tables),
        }
    return {
        "mode": "dry-run",
        "message": "No source SQLite database is modified. Legacy module cutover remains disabled in Phase 1.",
        "modules": modules,
        "target_platform_counts": _platform_counts(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview V2 Phase 1 legacy SQLite to Studio Postgres migration readiness.")
    parser.add_argument("--data-root", default=os.getenv("STUDIO_DATA_ROOT", "data"), help="Studio data root containing wildcards/movie/cards folders.")
    args = parser.parse_args()
    plan = collect_plan(Path(args.data_root))
    for module, detail in plan["modules"].items():
        print(f"{module}: {detail['source']}")
        for table, count in detail["tables"].items():
            print(f"  {table}: {count}")
    print("target platform tables:")
    for table, count in plan["target_platform_counts"].items():
        print(f"  {table}: {count}")
    print(plan["message"])


if __name__ == "__main__":
    main()
