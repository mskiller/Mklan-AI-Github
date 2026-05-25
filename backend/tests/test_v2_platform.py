from __future__ import annotations

import importlib
from pathlib import Path
import sys

import pytest
from fastapi import HTTPException


def test_v2_routes_mount_without_eager_model_loading(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("STUDIO_SEMANTIC_SEARCH_ENABLED", "false")
    sys.modules.pop("app.studio_features", None)
    sys.modules.pop("app.main", None)

    main = importlib.import_module("app.main")
    paths = {route.path for route in main.app.routes}

    assert {
        "/api/jobs/{job_id}",
        "/api/jobs/overview",
        "/api/studio/manifest",
        "/api/studio/preflight",
        "/api/assets/search",
        "/api/assets/{asset_id}/provenance",
        "/api/workflows/presets",
        "/api/workflows/render",
        "/api/workflows/validate",
        "/api/canon/entities",
        "/api/canon/export-pack",
    } <= paths


@pytest.mark.asyncio
async def test_v2_job_manager_runs_registered_handler(tmp_path):
    from app.v2.jobs import JobManager

    manager = JobManager(tmp_path)

    async def handler(job, manager):
        await manager.update_progress(job["id"], 0.5, "Halfway.")
        return {"done": True}

    manager.register_handler("test.echo", handler)
    await manager.start()
    try:
        created = await manager.create_job("test.echo", {"hello": "world"})
        for _ in range(50):
            current = manager.get_job(created["id"])
            if current["status"] in {"succeeded", "failed", "canceled"}:
                break
            await manager.wait_for_event(created["id"], timeout_s=0.1)
        job = manager.get_job(created["id"])
    finally:
        await manager.stop()

    assert job["status"] == "succeeded"
    assert job["result"] == {"done": True}
    assert any(event["event_type"] == "progress" for event in manager.list_events(created["id"]))


def test_v2_asset_registry_ingests_generated_file(tmp_path):
    from app.v2.assets import AssetRegistry, GeneratedAssetIngestRequest

    generated = tmp_path / "generated"
    generated.mkdir()
    image = generated / "sample.png"
    image.write_bytes(b"not-a-real-png-but-registered")
    image.with_suffix(".json").write_text('{"prompt": "blue comet"}', encoding="utf-8")

    registry = AssetRegistry(tmp_path)
    registry.initialize()
    asset = registry.ingest_generated(
        GeneratedAssetIngestRequest(file="sample.png", source_module="test", metadata={"seed": 123})
    )

    assert asset["url"] == "/generated/sample.png"
    assert asset["metadata"]["prompt"] == "blue comet"
    assert asset["metadata"]["seed"] == 123
    assert registry.search_local("comet")[0]["id"] == asset["id"]


def test_v2_asset_registry_syncs_generated_source(monkeypatch, tmp_path):
    from app.v2.assets import AssetRegistry

    calls = []

    class FakeResponse:
        def __init__(self, payload, status_code=200):
            self._payload = payload
            self.status_code = status_code

        def json(self):
            return self._payload

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"HTTP {self.status_code}")

    def fake_get(url, **kwargs):
        calls.append(("GET", url, kwargs))
        return FakeResponse(
            [
                {
                    "id": "source-1",
                    "name": "Mklan Studio Generated",
                    "root_path": "/data/sources/generated",
                }
            ]
        )

    def fake_post(url, json=None, **kwargs):
        calls.append(("POST", url, json, kwargs))
        return FakeResponse({"id": "job-1", "scan_mode": json["scan_mode"], "path_filter": json.get("path_filter")})

    monkeypatch.setenv("MEDIA_INDEXER_INTERNAL_URL", "http://media-indexer.test")
    monkeypatch.setattr("app.v2.assets.requests.get", fake_get)
    monkeypatch.setattr("app.v2.assets.requests.post", fake_post)

    registry = AssetRegistry(tmp_path)
    result = registry.sync_generated_source(scan_mode="metadata", path_filter="sample.png")

    assert result["ok"] is True
    assert result["status"] == "scan_queued"
    assert result["source"]["id"] == "source-1"
    assert result["scan_job"]["path_filter"] == "sample.png"
    assert calls[0][0] == "GET"
    assert calls[1][0] == "POST"


def test_semantic_search_delegates_to_media_indexer(monkeypatch):
    from app.semantic_search import SemanticSearchEngine

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"items": [{"id": "asset-1", "filename": "sample.png"}], "total": 1}

    def fake_get(url, params=None, timeout=None):
        assert url == "http://media-indexer.test/search/nl"
        assert params == {"q": "blue comet", "limit": 10}
        assert timeout == 3
        return FakeResponse()

    monkeypatch.setenv("MEDIA_INDEXER_INTERNAL_URL", "http://media-indexer.test")
    monkeypatch.setenv("STUDIO_SEMANTIC_SEARCH_ENABLED", "true")
    monkeypatch.setattr("app.semantic_search.requests.get", fake_get)

    result = SemanticSearchEngine().search("blue comet", limit=10)

    assert result["ok"] is True
    assert result["items"][0]["filename"] == "sample.png"


def test_workflow_validation_summarizes_placeholders():
    from app.v2.workflows import WorkflowValidationRequest, validate_workflow

    response = validate_workflow(
        WorkflowValidationRequest(
            workflow_json={
                "1": {"class_type": "KSampler", "inputs": {"seed": "%seed%", "cfg": "%scale%"}},
                "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "prefix %prompt%"}},
            }
        )
    )

    assert response["ok"] is True
    assert response["workflow"]["node_count"] == 2
    assert "%prompt%" in response["workflow"]["placeholders"]
    assert "%seed%" in response["workflow"]["placeholders"]


def test_upload_security_rejects_path_and_extension():
    from app.v2.upload_security import IMAGE_EXTENSIONS, safe_upload_name

    with pytest.raises(HTTPException):
        safe_upload_name("../bad.png", allowed_extensions=IMAGE_EXTENSIONS)
    with pytest.raises(HTTPException):
        safe_upload_name("model.exe", allowed_extensions=IMAGE_EXTENSIONS)
