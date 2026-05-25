from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime, timezone

# Project paths
APP_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = APP_ROOT.parent

# Unified database
DATA_DIR = Path(os.environ.get("MKLANG_STUDIO_DATA_DIR", str(APP_ROOT / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.environ.get("MKLANG_STUDIO_DB", str(DATA_DIR / "mklan_studio.db")))

# Wildcard-specific paths
DEFAULT_SOURCE_ROOT = Path(os.environ.get("WILDCARD_SOURCE_ROOT", str(PROJECT_ROOT.parent / "Wildcards")))
EXPORT_ROOT = Path(os.environ.get("WILDCARD_EXPORT_ROOT", str(APP_ROOT / "exports")))

# Movie-specific paths
MEDIA_ROOT = Path(os.environ.get("MKLANG_STUDIO_MEDIA_ROOT", str(DATA_DIR / "media")))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()