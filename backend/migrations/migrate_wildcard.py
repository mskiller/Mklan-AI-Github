#!/usr/bin/env python3
"""
Migrate Wildcard Workshop database to Mklan Studio structure.

Usage: python migrate_wildcard.py [--source PATH] [--dry-run]

This script:
1. Finds the existing wildcard_workshop.db
2. Copies it to the new location (data/wildcards/)
3. Verifies the schema is compatible
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path


def find_wildcard_db() -> Path | None:
    """Search common locations for wildcard_workshop.db."""
    candidates = [
        # Original locations
        Path(os.environ.get("WILDCARD_WORKSHOP_DB", "")),
        Path(r"C:\tmp\WildcardWorkshop\wildcard_workshop.db"),
        # Docker default in source project
        Path(__file__).parents[2] / "Wildcards" / "wildcard_workshop.db",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def verify_schema(db_path: Path) -> bool:
    """Verify the wildcard DB has expected tables."""
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {r[0] for r in cur.fetchall()}
        conn.close()
        required = {"source_files", "entries", "tag_overrides", "taxonomy_rules", "llm_jobs"}
        missing = required - tables
        if missing:
            print(f"  WARNING: Missing tables: {missing}")
            return False
        print(f"  Schema verified: {len(tables)} tables found")
        return True
    except Exception as e:
        print(f"  ERROR verifying schema: {e}")
        return False


def migrate(source: Path | None, target_dir: Path, dry_run: bool = False):
    import os
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / "wildcard_workshop.db"
    
    if source is None:
        print("No source database found — will create new at target location")
        if not dry_run:
            # Touch the target to create placeholder
            target_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(target_path)
            conn.close()
        return
    
    print(f"Source: {source}")
    print(f"Target: {target_path}")
    
    if dry_run:
        print("[DRY RUN] Would copy database")
        return
    
    # Backup target if exists
    if target_path.exists():
        backup = target_path.with_name(f"wildcard_workshop.backup.db")
        shutil.copy2(target_path, backup)
        print(f"  Backed up existing DB to {backup}")
    
    # Copy source to target
    shutil.copy2(source, target_path)
    print(f"  Copied {source.stat().st_size / 1024 / 1024:.1f} MB")
    
    # Verify
    verify_schema(target_path)


if __name__ == "__main__":
    import os
    parser = argparse.ArgumentParser(description="Migrate Wildcard Workshop DB")
    parser.add_argument("--source", type=Path, default=None, help="Source DB path")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually copy")
    parser.add_argument("--target", type=Path, default=None, help="Target directory")
    args = parser.parse_args()
    
    source = args.source or find_wildcard_db()
    target = args.target or (Path(__file__).parents[2] / "data" / "wildcards")
    
    print(f"=== Wildcard DB Migration ===")
    migrate(source, target, args.dry_run)
    print("Done")
