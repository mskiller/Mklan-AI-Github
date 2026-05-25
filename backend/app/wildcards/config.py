"""Configuration for the Wildcards module."""
from __future__ import annotations

import os
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = APP_ROOT.parent

WILDCARD_SOURCE_ROOT = Path(os.environ.get(
    "WILDCARD_SOURCE_ROOT", str(PROJECT_ROOT / "data" / "wildcards")
))
WILDCARD_DATA_DIR = Path(os.environ.get(
    "WILDCARD_WORKSHOP_DATA_DIR", str(PROJECT_ROOT / "data" / "wildcards")
))
WILDCARD_DB = Path(os.environ.get(
    "WILDCARD_WORKSHOP_DB", str(WILDCARD_DATA_DIR / "wildcard_workshop.db")
))
EXPORT_ROOT = Path(os.environ.get(
    "WILDCARD_EXPORT_ROOT", str(PROJECT_ROOT / "data" / "exports")
))
