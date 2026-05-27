from __future__ import annotations

import importlib
from pathlib import Path
import sys

import pytest
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.testclient import TestClient


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
        "/api/workspaces",
        "/api/workspaces/{workspace_id}/export.zip",
        "/api/workspaces/import",
        "/api/copilot/chat",
        "/api/training/model-families",
        "/api/video/models",
        "/api/video/generate",
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


@pytest.mark.asyncio
async def test_v2_job_manager_cancels_queued_job(tmp_path):
    from app.v2.jobs import JobManager

    manager = JobManager(tmp_path)

    async def handler(job, manager):
        return {"done": True}

    manager.register_handler("test.cancel", handler)
    manager.initialize()
    created = await manager.create_job("test.cancel", {}, enqueue=False)

    canceled = await manager.cancel_job(created["id"])

    assert canceled["status"] == "canceled"
    assert canceled["cancel_requested"] is True
    assert any(event["event_type"] == "canceled" for event in manager.list_events(created["id"]))


@pytest.mark.asyncio
async def test_v2_job_manager_arq_enqueue_uses_redis_queue(monkeypatch, tmp_path):
    from app.v2 import jobs
    from app.v2.jobs import JobManager

    enqueued = []

    class FakePool:
        async def enqueue_job(self, name, job_id):
            enqueued.append((name, job_id))

        async def close(self):
            return None

    async def fake_create_pool(settings):
        return FakePool()

    class FakeRedisSettings:
        @classmethod
        def from_dsn(cls, url):
            return {"url": url}

    monkeypatch.setattr(jobs, "create_pool", fake_create_pool)
    monkeypatch.setattr(jobs, "RedisSettings", FakeRedisSettings)
    monkeypatch.setattr(jobs, "redis_async", None)

    manager = JobManager(tmp_path, queue_backend="arq", redis_url="redis://example:6379/0")

    async def handler(job, manager):
        return {"done": True}

    manager.register_handler("test.arq", handler)
    await manager.start()
    try:
        created = await manager.create_job("test.arq", {"value": 1})
    finally:
        await manager.stop()

    assert enqueued == [("run_studio_job", created["id"])]
    assert manager.get_job(created["id"])["status"] == "queued"


def test_v2_job_sse_stream_returns_snapshot_and_events(tmp_path):
    from app.v2.jobs import JobManager, router

    app = FastAPI()
    manager = JobManager(tmp_path)

    async def handler(job, manager):
        return {"done": True}

    manager.register_handler("test.stream", handler)
    manager.initialize()
    app.state.v2_jobs = manager
    app.include_router(router, prefix="/api")

    async def create_completed_job():
        created = await manager.create_job("test.stream", {}, enqueue=False)
        await manager.complete_job(created["id"], {"done": True})
        return created["id"]

    import asyncio

    job_id = asyncio.run(create_completed_job())
    client = TestClient(app)
    response = client.get(f"/api/jobs/{job_id}/events/stream")

    assert response.status_code == 200
    assert "event: snapshot" in response.text
    assert "event: job_event" in response.text
    assert "Job succeeded." in response.text


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


def test_v2_asset_registry_ingests_nested_video_file(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDIA_INDEXER_AUTO_SYNC_GENERATED", "false")
    from app.v2.assets import AssetRegistry, GeneratedAssetIngestRequest

    video_dir = tmp_path / "generated" / "video"
    video_dir.mkdir(parents=True)
    video = video_dir / "sample.mp4"
    video.write_bytes(b"video")
    video.with_suffix(".json").write_text('{"prompt": "slow pan"}', encoding="utf-8")

    registry = AssetRegistry(tmp_path)
    registry.initialize()
    asset = registry.ingest_generated(
        GeneratedAssetIngestRequest(file="video/sample.mp4", source_module="test", kind="video")
    )

    assert asset["url"] == "/generated/video/sample.mp4"
    assert asset["kind"] == "video"
    assert registry.search_local("slow pan")[0]["url"] == "/generated/video/sample.mp4"


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


def test_workflow_validation_extracts_comfyui_edges():
    from app.v2.workflows import WorkflowValidationRequest, validate_workflow

    response = validate_workflow(
        WorkflowValidationRequest(
            workflow_json={
                "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "%model%"}},
                "2": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "seed": "%seed%"}},
            }
        )
    )

    assert response["ok"] is True
    assert response["workflow"]["edges"] == [{"from": "1", "to": "2", "input": "model", "output": 0}]


def test_workflow_template_library_saves_and_loads(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_DATA_ROOT", str(tmp_path))
    sys.modules.pop("app.studio_features", None)
    sys.modules.pop("app.v2.workflows", None)

    from app.v2.workflows import WorkflowTemplateSaveRequest, get_workflow_template, load_workflow_templates, save_workflow_template

    template = save_workflow_template(
        WorkflowTemplateSaveRequest(
            id="phase2_test_template",
            label="Phase 2 Test Template",
            task="generation",
            description="Template library smoke test.",
            fields=["prompt", "seed"],
            workflow_json={
                "1": {"class_type": "KSampler", "inputs": {"seed": "%seed%", "cfg": "%scale%"}},
                "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "%prompt%"}},
            },
        )
    )

    assert template["id"] == "phase2_test_template"
    assert template["summary"]["node_count"] == 2
    assert get_workflow_template("phase2_test_template")["label"] == "Phase 2 Test Template"
    assert any(item["id"] == "phase2_test_template" for item in load_workflow_templates())


def test_workspace_store_json_fallback_create_activate(monkeypatch, tmp_path):
    monkeypatch.delenv("STUDIO_DATABASE_URL", raising=False)
    from app.v2.workspaces import DEFAULT_WORKSPACE_ID, WorkspaceCreateRequest, WorkspaceStore

    store = WorkspaceStore(tmp_path)
    assert store.active_workspace_id() == DEFAULT_WORKSPACE_ID

    created = store.create_workspace(WorkspaceCreateRequest(name="Phase 2 Project", description="Local work", activate=True))

    assert created["active"] is True
    assert store.active_workspace_id() == created["id"]
    assert store.get_workspace(created["id"])["name"] == "Phase 2 Project"
    assert store.activate_workspace(DEFAULT_WORKSPACE_ID)["active"] is True
    assert store.active_workspace_id() == DEFAULT_WORKSPACE_ID


def test_workspace_zip_export_import_roundtrip(monkeypatch, tmp_path):
    monkeypatch.delenv("STUDIO_DATABASE_URL", raising=False)
    monkeypatch.setenv("MEDIA_INDEXER_AUTO_SYNC_GENERATED", "false")
    from app.v2.assets import AssetRegistry, GeneratedAssetIngestRequest
    from app.v2.workspaces import router

    generated = tmp_path / "generated" / "video"
    generated.mkdir(parents=True)
    (generated / "clip.mp4").write_bytes(b"clip")
    registry = AssetRegistry(tmp_path)
    registry.initialize()
    registry.ingest_generated(GeneratedAssetIngestRequest(file="video/clip.mp4", kind="video", source_module="test"))

    app = FastAPI()
    app.state.data_root = tmp_path
    app.include_router(router, prefix="/api")
    client = TestClient(app)

    exported = client.get("/api/workspaces/default/export.zip")
    assert exported.status_code == 200
    assert exported.content.startswith(b"PK")

    imported = client.post(
        "/api/workspaces/import",
        files={"file": ("workspace.zip", exported.content, "application/zip")},
        data={"mode": "create_new"},
    )

    assert imported.status_code == 201
    payload = imported.json()
    assert payload["workspace"]["id"] != "default"
    assert payload["imported_assets"] == 1
    assert payload["copied_files"] == 1


@pytest.mark.asyncio
async def test_jobs_are_scoped_to_active_workspace(monkeypatch, tmp_path):
    monkeypatch.delenv("STUDIO_DATABASE_URL", raising=False)
    from app.v2.jobs import JobManager
    from app.v2.workspaces import DEFAULT_WORKSPACE_ID, WorkspaceCreateRequest, WorkspaceStore

    store = WorkspaceStore(tmp_path)
    phase_workspace = store.create_workspace(WorkspaceCreateRequest(name="Scoped Jobs", activate=True))
    manager = JobManager(tmp_path)

    async def handler(job, manager):
        return {"ok": True}

    manager.register_handler("test.scoped", handler)
    manager.initialize()
    phase_job = await manager.create_job("test.scoped", {"name": "phase"}, enqueue=False)
    store.activate_workspace(DEFAULT_WORKSPACE_ID)
    default_job = await manager.create_job("test.scoped", {"name": "default"}, enqueue=False)

    visible = manager.list_jobs(limit=20)
    all_jobs = manager.list_jobs(limit=20, workspace_id="__all__")

    assert [job["id"] for job in visible] == [default_job["id"]]
    assert {job["id"] for job in all_jobs} == {phase_job["id"], default_job["id"]}
    assert phase_job["workspace_id"] == phase_workspace["id"]
    assert default_job["workspace_id"] == DEFAULT_WORKSPACE_ID


@pytest.mark.asyncio
async def test_video_mock_job_writes_sidecar_and_registers_asset(monkeypatch, tmp_path):
    monkeypatch.delenv("STUDIO_DATABASE_URL", raising=False)
    monkeypatch.setenv("MEDIA_INDEXER_AUTO_SYNC_GENERATED", "false")
    from app.video import VIDEO_JOB_TYPE, register_video_jobs
    from app.v2.assets import AssetRegistry
    from app.v2.jobs import JobManager

    registry = AssetRegistry(tmp_path)
    registry.initialize()
    manager = JobManager(tmp_path)
    manager.asset_registry = registry
    register_video_jobs(manager)
    manager.initialize()

    created = await manager.create_job(VIDEO_JOB_TYPE, {"prompt": "phase three smoke clip", "provider": "mock"}, enqueue=False)
    await manager.process_one(created["id"])
    job = manager.get_job(created["id"])

    assert job["status"] == "succeeded"
    video = Path(job["result"]["video"]["path"])
    assert video.exists()
    assert video.with_suffix(".json").exists()
    assets = registry.list_assets()
    assert assets[0]["kind"] == "video"
    assert assets[0]["source_id"] == created["id"]


def test_copilot_fallback_uses_workspace_context(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_DATA_ROOT", str(tmp_path))
    monkeypatch.delenv("STUDIO_DATABASE_URL", raising=False)
    sys.modules.pop("app.studio_features", None)
    sys.modules.pop("app.v2.copilot", None)

    import requests
    def mock_post(*args, **kwargs):
        raise requests.RequestException("Mocked network error for testing fallback")
    monkeypatch.setattr("requests.post", mock_post)

    from app.v2.copilot import router

    app = FastAPI()
    app.state.data_root = tmp_path
    app.include_router(router, prefix="/api")
    client = TestClient(app)

    response = client.post(
        "/api/copilot/chat",
        json={"route": "/training", "module": "training", "message": "What should I check before training?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "fallback"
    assert payload["context"]["workspace_id"] == "default"
    assert "training context" in payload["content"]


def test_upload_security_rejects_path_and_extension():
    from app.v2.upload_security import IMAGE_EXTENSIONS, safe_upload_name

    with pytest.raises(HTTPException):
        safe_upload_name("../bad.png", allowed_extensions=IMAGE_EXTENSIONS)
    with pytest.raises(HTTPException):
        safe_upload_name("model.exe", allowed_extensions=IMAGE_EXTENSIONS)


def test_core_postgres_dry_run_counts_sqlite_without_modifying(monkeypatch, tmp_path):
    from migrations.dry_run_core_postgres import collect_plan

    wildcard_db = tmp_path / "wildcards" / "wildcard_workshop.db"
    wildcard_db.parent.mkdir(parents=True)
    import sqlite3

    with sqlite3.connect(wildcard_db) as conn:
        conn.execute("CREATE TABLE source_files(id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE entries(id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO source_files DEFAULT VALUES")
        conn.execute("INSERT INTO entries DEFAULT VALUES")
        conn.commit()

    monkeypatch.setenv("WILDCARD_WORKSHOP_DB", str(wildcard_db))
    monkeypatch.delenv("STUDIO_DATABASE_URL", raising=False)

    plan = collect_plan(tmp_path)

    assert plan["mode"] == "dry-run"
    assert plan["modules"]["wildcards"]["tables"]["source_files"] == 1
    assert plan["modules"]["wildcards"]["tables"]["entries"] == 1
    assert plan["target_platform_counts"]["platform_jobs"] == "no-STUDIO_DATABASE_URL"
