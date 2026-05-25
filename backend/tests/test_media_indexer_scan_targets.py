from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError


REPO_ROOT = Path(__file__).resolve().parents[2]
MEDIA_INDEXER_SRC = REPO_ROOT / "media-indexer" / "backend" / "src"
MEDIA_WORKER_SCANNER = REPO_ROOT / "media-indexer" / "worker" / "src" / "media_indexer_worker" / "services" / "scanner.py"

if str(MEDIA_INDEXER_SRC) not in sys.path:
    sys.path.insert(0, str(MEDIA_INDEXER_SRC))

from media_indexer_backend.schemas.scan_job import ScanJobCreate, ScanJobTarget


def test_scan_target_validates_required_identifier_by_type():
    with pytest.raises(ValidationError):
        ScanJobTarget(type="source")
    with pytest.raises(ValidationError):
        ScanJobTarget(type="collection")
    with pytest.raises(ValidationError):
        ScanJobTarget(type="assets", asset_ids=[])

    assert ScanJobTarget(type="source", source_id=uuid4()).type == "source"
    assert ScanJobTarget(type="collection", collection_id=uuid4()).type == "collection"
    assert ScanJobTarget(type="assets", asset_ids=[uuid4()]).type == "assets"


def test_new_scan_modes_are_accepted_by_create_schema():
    for mode in [
        "workflow",
        "preview",
        "similarity",
        "caption",
        "ocr",
        "tags",
        "safety_quality",
        "faces",
        "video_intel",
        "vision_llm",
        "sillytavern_card",
    ]:
        payload = ScanJobCreate(scan_mode=mode, target=ScanJobTarget(type="assets", asset_ids=[uuid4()]))
        assert payload.scan_mode == mode


def test_worker_scanner_no_longer_uses_hot_loop_expire_all():
    scanner_source = MEDIA_WORKER_SCANNER.read_text(encoding="utf-8")
    assert "expire_all(" not in scanner_source


def test_worker_scanner_treats_asset_tag_scalar_query_as_strings():
    scanner_source = MEDIA_WORKER_SCANNER.read_text(encoding="utf-8")
    assert "old_tags = list(session.execute(select(AssetTag.tag)" in scanner_source
    assert "old_tags = [tag.tag" not in scanner_source


def test_worker_scanner_contains_sillytavern_card_parser():
    scanner_source = MEDIA_WORKER_SCANNER.read_text(encoding="utf-8")
    assert '"sillytavern_card"' in scanner_source
    assert "def _extract_sillytavern_card" in scanner_source
