"""Scanner/indexer boundary for incremental backend splitting."""

from pathlib import Path
from typing import Literal

from .main import ScanSummary, rebuild_aggregate_indexes, scan_library  # noqa: F401


def scan(source_root: Path, mode: Literal["incremental", "reset"] = "incremental") -> ScanSummary:
    return scan_library(source_root, mode == "reset", mode)
