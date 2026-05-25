"""Mklan Studio — Backend Configuration."""
from __future__ import annotations

import os
from pathlib import Path

# Project root (backend/app/ → project root)
APP_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = APP_ROOT / "data"

# ── Wildcard Module ──────────────────────────────────────────
WILDCARD_SOURCE_ROOT = Path(os.getenv("WILDCARD_SOURCE_ROOT", str(DATA_ROOT / "wildcards")))
WILDCARD_WORKSHOP_DATA_DIR = Path(os.getenv("WILDCARD_WORKSHOP_DATA_DIR", str(DATA_ROOT / "wildcards")))
WILDCARD_WORKSHOP_DB = Path(os.getenv("WILDCARD_WORKSHOP_DB", str(DATA_ROOT / "wildcards" / "wildcard_workshop.db")))
WILDCARD_EXPORT_ROOT = Path(os.getenv("WILDCARD_EXPORT_ROOT", str(DATA_ROOT / "exports")))

# Aliases for wildcard module compatibility
WILDCARD_DATA_DIR = WILDCARD_WORKSHOP_DATA_DIR
WILDCARD_DB = WILDCARD_WORKSHOP_DB

# ── Movie Module ──────────────────────────────────────────────
MOVIE_DATA_DIR = Path(os.getenv("MOVIE_DATA_DIR", str(DATA_ROOT / "movie")))
MOVIE_DB = Path(os.getenv("MOVIE_DB", str(DATA_ROOT / "movie" / "movie_tool.db")))

# ── Shared ───────────────────────────────────────────────────
COMFYUI_CUSTOM_NODES_DIR = Path(os.getenv("COMFYUI_CUSTOM_NODES_DIR", str(DATA_ROOT / "integrations" / "comfyui")))
