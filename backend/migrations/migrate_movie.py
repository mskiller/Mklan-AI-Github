#!/usr/bin/env python3
"""
Migrate Movie tool database to Mklan Studio structure.

Usage: python migrate_movie.py [--source PATH] [--dry-run]
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import os
from pathlib import Path


def find_movie_db() -> Path | None:
    """Search common locations for movie_tool.db."""
    candidates = [
        Path(os.environ.get("MOVIE_DB", "")),
        Path(__file__).parents[2] / "data" / "movie_tool.db",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def migrate(source: Path | None, target_dir: Path, dry_run: bool = False):
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / "movie_tool.db"
    
    if source is None:
        print("No source database found — will create new at target location")
        if not dry_run:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(target_path)
            conn.close()
        return
    
    print(f"Source: {source}")
    print(f"Target: {target_path}")
    
    if dry_run:
        print("[DRY RUN] Would copy database")
        return
    
    if target_path.exists():
        backup = target_path.with_name(f"movie_tool.backup.db")
        shutil.copy2(target_path, backup)
        print(f"  Backed up existing DB to {backup}")
    
    shutil.copy2(source, target_path)
    print(f"  Copied {source.stat().st_size / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    import os
    parser = argparse.ArgumentParser(description="Migrate Movie Tool DB")
    parser.add_argument("--source", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--target", type=Path, default=None)
    args = parser.parse_args()
    
    source = args.source or find_movie_db()
    target = args.target or (Path(__file__).parents[2] / "data" / "movie")
    
    print(f"=== Movie DB Migration ===")
    migrate(source, target, args.dry_run)
    print("Done")
