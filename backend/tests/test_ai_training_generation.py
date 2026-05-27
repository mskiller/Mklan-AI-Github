from __future__ import annotations

import importlib
import io
import sys
import zipfile

import pytest
from fastapi import UploadFile
from PIL import Image


def fresh_training(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_DATA_ROOT", str(tmp_path))
    for name in ["app.training", "app.studio_features"]:
        sys.modules.pop(name, None)
    return importlib.import_module("app.training")


def fresh_generation(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("WILDCARD_SOURCE_ROOT", str(tmp_path / "wildcards"))
    for name in ["app.generation", "app.studio_features"]:
        sys.modules.pop(name, None)
    return importlib.import_module("app.generation")


def tiny_png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), color=(220, 40, 80)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_training_dataset_config_and_command_preview(monkeypatch, tmp_path):
    training = fresh_training(monkeypatch, tmp_path)
    base_model = tmp_path / "models" / "images" / "Base" / "base.safetensors"
    base_model.parent.mkdir(parents=True, exist_ok=True)
    base_model.write_bytes(b"base")
    dataset = training.create_dataset(
        training.DatasetCreateRequest(
            name="Hero SDXL",
            trigger_token="herohero",
            class_tokens="person",
        )
    )

    config = training.build_dataset_config(dataset.id)
    assert "[[datasets]]" in config.toml
    assert "resolution = 1024" in config.toml
    assert "herohero person" in config.toml

    command = training.build_training_command(
        training.TrainingRunRequest(
            dataset_id=dataset.id,
            preset="sdxl_lora",
            output_name="Hero LoRA",
            base_model=str(base_model),
            epochs=10,
            num_repeats=7,
            max_train_steps=543,
            lora_type="lora",
            shuffle_caption=False,
            keep_tokens=0,
            clip_skip=1,
            unet_lr=0.0005,
            text_encoder_lr=0.00005,
            lr_scheduler="cosine",
            lr_scheduler_num_cycles=3,
            min_snr_gamma=5,
            network_dim=32,
            network_alpha=32,
            noise_offset=0.1,
            optimizer_type="Adafactor",
            dry_run=True,
        )
    )

    assert command.command[0] == "accelerate"
    assert "sdxl_train_network.py" in command.script
    assert "--network_module" in command.command
    assert "networks.lora" in command.command
    assert "--dataset_config" in command.command
    assert "--optimizer_type" in command.command
    assert "Adafactor" in command.command
    assert "--unet_lr" in command.command
    assert "0.0005" in command.command
    assert "--text_encoder_lr" in command.command
    assert "--cache_text_encoder_outputs" not in command.command
    assert "--clip_skip" in command.command
    assert "--min_snr_gamma" in command.command
    assert "--noise_offset" in command.command
    assert command.output_dir.endswith("hero-lora")

    rebuilt = training.build_dataset_config(dataset.id, overrides=training.TrainingRunRequest(dataset_id=dataset.id, base_model=str(base_model)).model_dump())
    assert "shuffle_caption = false" in rebuilt.toml
    assert "keep_tokens = 0" in rebuilt.toml


def test_sdxl_lora_unet_only_caches_text_encoder_outputs(monkeypatch, tmp_path):
    training = fresh_training(monkeypatch, tmp_path)
    base_model = tmp_path / "models" / "images" / "Base" / "base.safetensors"
    base_model.parent.mkdir(parents=True, exist_ok=True)
    base_model.write_bytes(b"base")
    dataset = training.create_dataset(training.DatasetCreateRequest(name="UNet Only", trigger_token="unetonly"))

    command = training.build_training_command(
        training.TrainingRunRequest(
            dataset_id=dataset.id,
            output_name="UNet Only LoRA",
            base_model=str(base_model),
            text_encoder_lr=0,
            dry_run=True,
        )
    )

    assert "--text_encoder_lr" not in command.command
    assert "--network_train_unet_only" in command.command
    assert "--cache_text_encoder_outputs" in command.command


def test_sdxl_lora_rejects_text_encoder_cache_while_training_encoder(monkeypatch, tmp_path):
    training = fresh_training(monkeypatch, tmp_path)
    base_model = tmp_path / "models" / "images" / "Base" / "base.safetensors"
    base_model.parent.mkdir(parents=True, exist_ok=True)
    base_model.write_bytes(b"base")
    dataset = training.create_dataset(training.DatasetCreateRequest(name="Bad Cache", trigger_token="badcache"))

    with pytest.raises(RuntimeError, match="cannot cache text encoder outputs"):
        training.build_training_command(
            training.TrainingRunRequest(
                dataset_id=dataset.id,
                output_name="Bad Cache LoRA",
                base_model=str(base_model),
                text_encoder_lr=0.00005,
                extra_args={"cache_text_encoder_outputs": True},
                dry_run=True,
            )
        )


def test_training_model_files_and_path_resolution(monkeypatch, tmp_path):
    training = fresh_training(monkeypatch, tmp_path)
    base_model = tmp_path / "models" / "images" / "Base" / "Illustrious-XL-v2.0.safetensors"
    vae_model = tmp_path / "models" / "images" / "VAE" / "sdxl_vae.safetensors"
    base_model.parent.mkdir(parents=True, exist_ok=True)
    vae_model.parent.mkdir(parents=True, exist_ok=True)
    base_model.write_bytes(b"base")
    vae_model.write_bytes(b"vae")
    dataset = training.create_dataset(training.DatasetCreateRequest(name="Path Resolve", trigger_token="pathhero"))

    inventory = training.list_training_model_files()
    assert {family["id"] for family in inventory.families} >= {"sd15", "sdxl", "sdxl_pony", "flux"}
    assert [item.name for item in inventory.base_models] == ["Illustrious-XL-v2.0.safetensors"]
    assert inventory.base_models[0].family == "sdxl"
    assert [item.name for item in inventory.vae_models] == ["sdxl_vae.safetensors"]

    command = training.build_training_command(
        training.TrainingRunRequest(
            dataset_id=dataset.id,
            base_model="data\\models\\images\\Illustrious-XL-v2.0.safetensors",
            vae="\\data\\models\\images\\sdxl_vae.safetensors",
            dry_run=True,
        )
    )
    assert str(base_model) in command.command
    assert str(vae_model) in command.command


def test_flux_lora_command_preview_uses_simpletuner_profile(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_SIMPLETUNER_ROOT", str(tmp_path / "trainers" / "SimpleTuner"))
    training = fresh_training(monkeypatch, tmp_path)
    flux_model = tmp_path / "models" / "images" / "Flux" / "flux-dev.safetensors"
    flux_model.parent.mkdir(parents=True, exist_ok=True)
    flux_model.write_bytes(b"flux")
    dataset = training.create_dataset(training.DatasetCreateRequest(name="Flux Dataset", trigger_token="fluxhero"))

    command = training.build_training_command(
        training.TrainingRunRequest(
            dataset_id=dataset.id,
            model_family="flux",
            preset="flux_lora",
            output_name="Flux Hero",
            base_model=str(flux_model),
            dry_run=True,
        )
    )

    assert command.preset == "flux_lora"
    assert "train.py" in command.script
    assert "--model_family" in command.command
    assert "flux" in command.command
    assert "--pretrained_model_name_or_path" in command.command
    assert str(flux_model) in command.command


def test_training_dataset_can_import_media_collection(monkeypatch, tmp_path):
    training = fresh_training(monkeypatch, tmp_path)
    monkeypatch.setenv("MEDIA_INDEXER_INTERNAL_URL", "http://media-indexer.test")

    class FakeResponse:
        def __init__(self, *, payload=None, content=b""):
            self._payload = payload
            self.content = content

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def fake_get(url, params=None, timeout=None):
        if url == "http://media-indexer.test/collections/collection-1":
            return FakeResponse(
                payload={
                    "id": "collection-1",
                    "name": "Hero Collection",
                    "total": 1,
                    "items": [
                        {
                            "id": "asset-1",
                            "filename": "hero.png",
                            "media_type": "image",
                            "content_url": "/assets/asset-1/content",
                            "caption": "herohero cinematic portrait",
                            "prompt_tags": ["herohero", "portrait"],
                        }
                    ],
                }
            )
        if url == "http://media-indexer.test/assets/asset-1/content":
            return FakeResponse(content=b"\x89PNG\r\n\x1a\nfake")
        raise AssertionError(url)

    monkeypatch.setattr(training.requests, "get", fake_get)

    result = training.import_collection_dataset(
        training.CollectionDatasetImportRequest(
            collection_id="collection-1",
            trigger_token="herohero",
            class_tokens="person",
        )
    )

    assert result.imported == 1
    assert result.skipped == 0
    assert result.dataset.image_count == 1
    assert result.dataset.caption_count == 1
    image_dir = tmp_path / "training" / "datasets" / result.dataset.id / "images"
    assert (image_dir / "hero.png").exists()
    assert (image_dir / "hero.txt").read_text(encoding="utf-8") == "herohero cinematic portrait"


def test_training_dataset_items_and_trigger_prepend(monkeypatch, tmp_path):
    training = fresh_training(monkeypatch, tmp_path)
    dataset = training.create_dataset(
        training.DatasetCreateRequest(
            name="Caption Review",
            trigger_token="herohero",
            class_tokens="person",
        )
    )
    image_dir = tmp_path / "training" / "datasets" / dataset.id / "images"
    (image_dir / "first.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    (image_dir / "first.txt").write_text("cinematic portrait", encoding="utf-8")
    (image_dir / "second.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")

    items = training.list_dataset_items(dataset.id)

    assert [item.filename for item in items] == ["first.png", "second.png"]
    assert items[0].caption == "cinematic portrait"
    assert items[0].image_url.endswith(f"/{dataset.id}/images/first.png")

    result = training.apply_caption_trigger(
        dataset.id,
        training.TriggerCaptionApplyRequest(trigger_word="herohero"),
    )

    assert result.updated == 2
    assert result.dataset.caption_count == 2
    assert (image_dir / "first.txt").read_text(encoding="utf-8") == "herohero, cinematic portrait"
    assert (image_dir / "second.txt").read_text(encoding="utf-8") == "herohero"

    repeat = training.apply_caption_trigger(
        dataset.id,
        training.TriggerCaptionApplyRequest(trigger_word="herohero"),
    )
    assert repeat.updated == 0
    assert repeat.unchanged == 2


def test_training_dataset_zip_import_and_export(monkeypatch, tmp_path):
    training = fresh_training(monkeypatch, tmp_path)
    dataset = training.create_dataset(training.DatasetCreateRequest(name="Zip Dataset", trigger_token="ziphero"))
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as archive:
        archive.writestr("ready/hero.png", tiny_png_bytes())
        archive.writestr("ready/hero.txt", "ziphero portrait lighting")

    upload = UploadFile(filename="ready-dataset.zip", file=io.BytesIO(zip_buffer.getvalue()))
    result = training.upload_dataset_zip(dataset.id, upload)

    assert result.imported == 1
    assert result.captions == 1
    assert result.dataset.image_count == 1
    assert result.items[0].caption == "ziphero portrait lighting"

    exported, filename = training._dataset_zip_bytes(dataset.id)
    assert filename.endswith("-training-dataset.zip")
    with zipfile.ZipFile(io.BytesIO(exported)) as archive:
        assert sorted(archive.namelist()) == ["001.png", "001.txt"]
        assert archive.read("001.txt").decode("utf-8") == "ziphero portrait lighting"
        with Image.open(io.BytesIO(archive.read("001.png"))) as image:
            assert image.format == "PNG"


def test_training_caption_models_discovers_local_blip(monkeypatch, tmp_path):
    training = fresh_training(monkeypatch, tmp_path)
    model_dir = tmp_path / "models" / "captioning" / "blip-custom"
    model_dir.mkdir(parents=True)
    (model_dir / "config.json").write_text('{"model_type":"blip","architectures":["BlipForConditionalGeneration"]}', encoding="utf-8")

    models = training.list_caption_models()

    assert any(model["id"] == "blip-custom" and model["provider"] == "local_blip" and model["local"] for model in models)
    assert any(model["id"] == "OysterQAQ/DanbooruCLIP" and model["provider"] == "clip_tagger" for model in models)


def test_training_caption_models_exposes_florence_sidecar(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_FLORENCE_URL", "http://florence.test")
    training = fresh_training(monkeypatch, tmp_path)

    models = training.list_caption_models()

    assert any(model["provider"] == "florence2" and model["path"] == "http://florence.test" for model in models)


def test_training_caption_scan_can_use_florence_sidecar(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_FLORENCE_URL", "http://florence.test")
    training = fresh_training(monkeypatch, tmp_path)
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(tiny_png_bytes())

    class FakeResponse:
        def __init__(self, payload, status_code=200):
            self._payload = payload
            self.status_code = status_code

        def json(self):
            return self._payload

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"HTTP {self.status_code}")

    def fake_get(url, timeout=None):
        assert url == "http://florence.test/health"
        return FakeResponse({"ok": True, "ready": True})

    def fake_post(url, json=None, timeout=None):
        assert url == "http://florence.test/caption"
        assert json["max_words"] == 12
        return FakeResponse({"caption": "dramatic portrait, soft light, studio framing"})

    monkeypatch.setattr(training.requests, "get", fake_get)
    monkeypatch.setattr(training.requests, "post", fake_post)

    caption, source = training._caption_image_with_source(image_path, 12, provider="florence2")

    assert caption == "dramatic portrait, soft light, studio framing"
    assert source["source"] == "florence2"


def test_training_caption_scan_explicit_florence_fails_actionably(monkeypatch, tmp_path):
    monkeypatch.delenv("STUDIO_FLORENCE_URL", raising=False)
    training = fresh_training(monkeypatch, tmp_path)
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(tiny_png_bytes())

    with pytest.raises(RuntimeError, match="STUDIO_FLORENCE_URL"):
        training._caption_image_with_source(image_path, 12, provider="florence2")


@pytest.mark.asyncio
async def test_training_caption_scan_reports_fallback_and_preserves_trigger_limit(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_DISABLE_LOCAL_CAPTIONING", "true")
    training = fresh_training(monkeypatch, tmp_path)
    dataset = training.create_dataset(training.DatasetCreateRequest(name="Caption Scan", trigger_token="scanhero"))
    image_dir = tmp_path / "training" / "datasets" / dataset.id / "images"
    (image_dir / "red-blue-42.png").write_bytes(tiny_png_bytes())

    class FakeManager:
        def __init__(self):
            self.progress_payloads = []

        async def update_progress(self, job_id, progress, message, *, payload=None):
            self.progress_payloads.append(payload or {})

        async def raise_if_canceled(self, job_id):
            return None

    manager = FakeManager()
    result = await training.run_caption_scan_job(
        {
            "id": "caption-job",
            "payload": {
                "dataset_id": dataset.id,
                "max_words": 2,
                "overwrite": False,
                "prepend_trigger": True,
                "trigger_word": "scanhero",
                "provider": "filename_fallback",
            },
        },
        manager,
    )

    assert result["updated"] == 1
    assert result["fallback_count"] == 1
    assert result["caption_sources"]["filename_fallback"] == 1
    assert result["trigger_applied_count"] == 1
    assert (image_dir / "red-blue-42.txt").read_text(encoding="utf-8") == "scanhero, red blue"
    assert any(payload.get("last_source") == "filename_fallback" for payload in manager.progress_payloads)


@pytest.mark.asyncio
async def test_training_caption_scan_can_emit_natural_language(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_DISABLE_LOCAL_CAPTIONING", "true")
    training = fresh_training(monkeypatch, tmp_path)
    dataset = training.create_dataset(training.DatasetCreateRequest(name="Natural Captions", trigger_token=""))
    image_dir = tmp_path / "training" / "datasets" / dataset.id / "images"
    (image_dir / "red-blue.png").write_bytes(tiny_png_bytes())

    class FakeManager:
        async def update_progress(self, job_id, progress, message, *, payload=None):
            return None

        async def raise_if_canceled(self, job_id):
            return None

    result = await training.run_caption_scan_job(
        {
            "id": "caption-natural-job",
            "payload": {
                "dataset_id": dataset.id,
                "max_words": 10,
                "overwrite": True,
                "prepend_trigger": False,
                "provider": "filename_fallback",
                "caption_style": "natural_language",
            },
        },
        FakeManager(),
    )

    assert result["caption_style"] == "natural_language"
    assert (image_dir / "red-blue.txt").read_text(encoding="utf-8") == "A training image showing Natural Captions, red blue."


@pytest.mark.asyncio
async def test_training_caption_scan_can_use_koboldcpp_vlm(monkeypatch, tmp_path):
    training = fresh_training(monkeypatch, tmp_path)
    monkeypatch.setenv("STUDIO_CAPTION_VLM_ENDPOINT", "http://vlm.test/v1")
    monkeypatch.setenv("STUDIO_CAPTION_VLM_MODEL", "vision-model")
    dataset = training.create_dataset(training.DatasetCreateRequest(name="VLM Caption Scan", trigger_token="vlmhero"))
    image_dir = tmp_path / "training" / "datasets" / dataset.id / "images"
    (image_dir / "openart-image_abc123_raw.png").write_bytes(tiny_png_bytes())

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": "magical girl idol, subway car, pink neon lighting",
                        }
                    }
                ]
            }

    def fake_post(url, json=None, headers=None, timeout=None):
        assert url == "http://vlm.test/v1/chat/completions"
        content = json["messages"][0]["content"]
        assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
        return FakeResponse()

    monkeypatch.setattr(training.requests, "post", fake_post)

    class FakeManager:
        async def update_progress(self, job_id, progress, message, *, payload=None):
            return None

        async def raise_if_canceled(self, job_id):
            return None

    result = await training.run_caption_scan_job(
        {
            "id": "caption-vlm-job",
            "payload": {
                "dataset_id": dataset.id,
                "max_words": 20,
                "overwrite": True,
                "prepend_trigger": True,
                "trigger_word": "vlmhero",
                "provider": "koboldcpp_vlm",
            },
        },
        FakeManager(),
    )

    assert result["updated"] == 1
    assert result["fallback_count"] == 0
    assert result["vlm_count"] == 1
    assert result["caption_sources"]["koboldcpp_vlm"] == 1
    assert (image_dir / "openart-image_abc123_raw.txt").read_text(encoding="utf-8") == "vlmhero, magical girl idol, subway car, pink neon lighting"


@pytest.mark.asyncio
async def test_training_caption_scan_uses_selected_local_blip(monkeypatch, tmp_path):
    training = fresh_training(monkeypatch, tmp_path)
    dataset = training.create_dataset(training.DatasetCreateRequest(name="Local BLIP Caption Scan", trigger_token="bliphero"))
    image_dir = tmp_path / "training" / "datasets" / dataset.id / "images"
    (image_dir / "sample.png").write_bytes(tiny_png_bytes())

    def fake_local_caption(path, max_words, model_id=None):
        assert model_id == "blip-image-captioning-large"
        return "soft portrait lighting", {"source": "local_blip", "model_id": model_id}

    monkeypatch.setattr(training, "_caption_image_with_local_model_result", fake_local_caption)

    class FakeManager:
        async def update_progress(self, job_id, progress, message, *, payload=None):
            return None

        async def raise_if_canceled(self, job_id):
            return None

    result = await training.run_caption_scan_job(
        {
            "id": "caption-local-job",
            "payload": {
                "dataset_id": dataset.id,
                "max_words": 20,
                "overwrite": True,
                "prepend_trigger": True,
                "trigger_word": "bliphero",
                "provider": "local_blip",
                "local_model_id": "blip-image-captioning-large",
            },
        },
        FakeManager(),
    )

    assert result["updated"] == 1
    assert result["caption_sources"]["local_blip"] == 1
    assert result["model_used"] == "blip-image-captioning-large"
    assert (image_dir / "sample.txt").read_text(encoding="utf-8") == "bliphero, soft portrait lighting"


@pytest.mark.asyncio
async def test_training_caption_scan_uses_clip_tagger(monkeypatch, tmp_path):
    training = fresh_training(monkeypatch, tmp_path)
    dataset = training.create_dataset(training.DatasetCreateRequest(name="CLIP Caption Scan", trigger_token="cliphero"))
    image_dir = tmp_path / "training" / "datasets" / dataset.id / "images"
    (image_dir / "sample.png").write_bytes(tiny_png_bytes())

    def fake_clip_caption(path, max_words, model_id=None):
        assert model_id == "OysterQAQ/DanbooruCLIP"
        return "anime style, subway car, neon lighting", {"source": "clip_tagger", "model_id": model_id}

    monkeypatch.setattr(training, "_caption_image_with_clip_result", fake_clip_caption)

    class FakeManager:
        async def update_progress(self, job_id, progress, message, *, payload=None):
            return None

        async def raise_if_canceled(self, job_id):
            return None

    result = await training.run_caption_scan_job(
        {
            "id": "caption-clip-job",
            "payload": {
                "dataset_id": dataset.id,
                "max_words": 20,
                "overwrite": True,
                "prepend_trigger": True,
                "trigger_word": "cliphero",
                "provider": "clip_tagger",
                "clip_model_id": "OysterQAQ/DanbooruCLIP",
            },
        },
        FakeManager(),
    )

    assert result["updated"] == 1
    assert result["caption_sources"]["clip_tagger"] == 1
    assert result["clip_count"] == 1
    assert result["model_used"] == "OysterQAQ/DanbooruCLIP"
    assert (image_dir / "sample.txt").read_text(encoding="utf-8") == "cliphero, anime style, subway car, neon lighting"


@pytest.mark.asyncio
async def test_training_dry_run_job_writes_artifact(monkeypatch, tmp_path):
    training = fresh_training(monkeypatch, tmp_path)
    base_model = tmp_path / "models" / "images" / "Base" / "base.safetensors"
    base_model.parent.mkdir(parents=True, exist_ok=True)
    base_model.write_bytes(b"base")
    dataset = training.create_dataset(training.DatasetCreateRequest(name="Dry Run", trigger_token="dryrun"))

    from app.v2.jobs import JobManager

    manager = JobManager(tmp_path)
    training.register_training_jobs(manager)
    await manager.start()
    try:
        created = await manager.create_job(
            "training.sdxl_lora",
            training.TrainingRunRequest(
                dataset_id=dataset.id,
                output_name="Dry Run LoRA",
                base_model=str(base_model),
                dry_run=True,
            ).model_dump(),
        )
        for _ in range(50):
            job = manager.get_job(created["id"])
            if job["status"] in {"succeeded", "failed", "canceled"}:
                break
            await manager.wait_for_event(created["id"], timeout_s=0.1)
        job = manager.get_job(created["id"])
    finally:
        await manager.stop()

    assert job["status"] == "succeeded"
    assert job["result"]["dry_run"] is True
    assert job["result"]["artifacts"]


def test_generation_wildcard_expansion_is_seeded(monkeypatch, tmp_path):
    generation = fresh_generation(monkeypatch, tmp_path)
    wildcard_root = tmp_path / "wildcards"
    wildcard_root.mkdir()
    (wildcard_root / "colors.txt").write_text("red\nblue\n# ignored\n", encoding="utf-8")

    first = generation.expand_wildcards("portrait with __colors__ light", seed=123)
    second = generation.expand_wildcards("portrait with __colors__ light", seed=123)

    assert first.expanded_prompt == second.expanded_prompt
    assert first.refs[0]["name"] == "colors"
    assert first.missing == []


def test_generation_wildcard_missing_refs_are_preserved(monkeypatch, tmp_path):
    generation = fresh_generation(monkeypatch, tmp_path)
    preview = generation.expand_wildcards("portrait __missing_ref__", seed=1)

    assert preview.expanded_prompt == "portrait __missing_ref__"
    assert preview.missing == ["missing_ref"]


def test_generation_clear_jobs_removes_only_requested_terminal_status(monkeypatch, tmp_path):
    generation = fresh_generation(monkeypatch, tmp_path)

    from app.v2.jobs import JobManager, utc_now_iso

    manager = JobManager(tmp_path)
    manager.initialize()
    now = utc_now_iso()
    with manager._connect() as conn:
        conn.executemany(
            """
            INSERT INTO jobs (
                id, job_type, status, progress, payload_json, result_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, 1, '{}', '{}', ?, ?)
            """,
            [
                ("failed-job", "generation.image", "failed", now, now),
                ("succeeded-job", "generation.image", "succeeded", now, now),
                ("training-job", "training.sdxl_lora", "failed", now, now),
            ],
        )
        conn.executemany(
            "INSERT INTO job_events (job_id, event_type, message, progress, payload_json, created_at) VALUES (?, 'done', '', 1, '{}', ?)",
            [("failed-job", now), ("succeeded-job", now), ("training-job", now)],
        )
        conn.commit()

    assert generation.clear_generation_jobs(manager, "failed") == 1

    with manager._connect() as conn:
        remaining = {row["id"] for row in conn.execute("SELECT id FROM jobs").fetchall()}
        remaining_events = {row["job_id"] for row in conn.execute("SELECT job_id FROM job_events").fetchall()}

    assert remaining == {"succeeded-job", "training-job"}
    assert remaining_events == {"succeeded-job", "training-job"}


def test_comfyui_client_upload_and_controlnet(monkeypatch):
    from app.comfyui_client import ComfyUIClient
    client = ComfyUIClient("http://localhost:8188")
    
    class FakeResponse:
        def __init__(self, json_data, status_code=200):
            self._json = json_data
            self.status_code = status_code
        def json(self):
            return self._json
        def raise_for_status(self):
            pass

    def fake_post(session, url, *args, **kwargs):
        if "/upload/image" in url:
            return FakeResponse({"name": "test_image.png", "subfolder": "", "type": "input"})
        return FakeResponse({})

    def fake_get(session, url, *args, **kwargs):
        if "/models/controlnets" in url:
            return FakeResponse(["controlnet-canny-sdxl.safetensors"])
        return FakeResponse({})

    import requests
    monkeypatch.setattr(requests.Session, "post", fake_post)
    monkeypatch.setattr(requests.Session, "get", fake_get)
    
    res = client.upload_image(b"fake-bytes", "test_image.png")
    assert res["name"] == "test_image.png"
    
    nets = client.list_controlnets()
    assert len(nets) == 1
    assert nets[0] == "controlnet-canny-sdxl.safetensors"


def test_prompt_payload_overrides():
    from app.studio_features import PromptPayload
    payload = PromptPayload(
        prompt="cyberpunk character",
        provider="comfyui",
        model="sdxl_check.safetensors",
        controlnet_type="canny",
        controlnet_image="data:image/png;base64,iVBORw0KGgoAAAANS",
        controlnet_strength=0.8
    )
    assert payload.provider == "comfyui"
    assert payload.model == "sdxl_check.safetensors"
    assert payload.controlnet_type == "canny"
    assert payload.controlnet_image.startswith("data:image/")
    assert payload.controlnet_strength == 0.8


def test_generate_image_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_DATA_ROOT", str(tmp_path))
    
    class FakeResponse:
        def __init__(self, json_data, status_code=200, content=b""):
            self._json = json_data
            self.status_code = status_code
            self.content = content
        def json(self):
            return self._json
        def raise_for_status(self):
            pass

    uploaded = False
    workflow_has_controlnet = False

    def fake_post(session, url, *args, **kwargs):
        nonlocal uploaded, workflow_has_controlnet
        if "/upload/image" in url:
            uploaded = True
            return FakeResponse({"name": "input_image.png", "subfolder": "", "type": "input"})
        elif "/prompt" in url:
            prompt_data = kwargs.get("json", {}).get("prompt", {})
            if "10" in prompt_data and "11" in prompt_data and "12" in prompt_data:
                workflow_has_controlnet = True
            return FakeResponse({"prompt_id": "test_prompt"})
        return FakeResponse({})

    def fake_get(session, url, *args, **kwargs):
        if "/models/checkpoints" in url:
            return FakeResponse(["checkpoint.safetensors"])
        elif "/models/controlnets" in url:
            return FakeResponse(["controlnet-canny-sdxl.safetensors"])
        elif "/history/" in url:
            return FakeResponse({
                "test_prompt": {
                    "outputs": {
                        "7": {
                            "images": [{"filename": "out.png", "subfolder": "", "type": "output"}]
                        }
                    }
                }
            })
        elif "/view" in url:
            import base64
            # return a valid 1x1 transparent png representation in bytes
            png_bytes = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
            return FakeResponse({}, content=png_bytes)
        return FakeResponse({})

    import requests
    monkeypatch.setattr(requests.Session, "post", fake_post)
    monkeypatch.setattr(requests.Session, "get", fake_get)
    
    import json
    settings_file = tmp_path / "studio_settings.json"
    settings_file.write_text(json.dumps({
        "image": {
            "provider": "comfyui",
            "endpoint": "http://host.docker.internal:8188",
            "workflow": "sdxl"
        }
    }))

    from fastapi import FastAPI
    from app.studio_features import router as studio_router
    from fastapi.testclient import TestClient
    
    app = FastAPI()
    app.include_router(studio_router, prefix="/api")
    client = TestClient(app)

    payload = {
        "prompt": "cyberpunk character",
        "provider": "comfyui",
        "model": "checkpoint.safetensors",
        "controlnet_type": "canny",
        "controlnet_image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
        "controlnet_strength": 0.8
    }
    # Note: prefix is /api/studio, and router suffix is /generate-image
    res = client.post("/api/studio/generate-image", json=payload)
    assert res.status_code == 200
    assert "image_base64" in res.json()
    assert uploaded
    assert workflow_has_controlnet
