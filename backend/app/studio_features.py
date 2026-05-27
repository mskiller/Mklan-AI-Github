from __future__ import annotations
import base64, json, os, uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
import requests
from app.comfyui_client import ComfyUIClient, build_workflow_from_generation
from app.semantic_search import SemanticSearchEngine
from app.v2.assets import AssetRegistry, GeneratedAssetIngestRequest
from app.v2.workspaces import active_workspace_id
from app.v2.upload_security import (
    IMAGE_EXTENSIONS,
    MODEL_EXTENSIONS,
    max_image_upload_bytes,
    max_model_upload_bytes,
    safe_upload_name,
    save_upload_with_limits,
)

router = APIRouter(prefix='/studio', tags=['studio'])
search_engine = SemanticSearchEngine()

def _default_data_root() -> Path:
    if os.environ.get("ENVIRONMENT") == "production" or Path("/.dockerenv").exists():
        return Path("/app/data")
    return Path(__file__).resolve().parents[2] / "data"


_env_data = os.environ.get("STUDIO_DATA_ROOT") or os.environ.get("MOVIE_TOOL_DATA_ROOT")
DATA = Path(_env_data) if _env_data else _default_data_root()
MODELS = DATA / 'models'
GENERATED = DATA / 'generated'
SETTINGS = DATA / 'studio_settings.json'
MODELS.mkdir(parents=True, exist_ok=True)
GENERATED.mkdir(parents=True, exist_ok=True)

DEFAULTS = {
 'llm': {
     'provider': 'koboldcpp',
     'endpoint': 'http://host.docker.internal:5001/v1',
     'model': 'koboldcpp',
     'api_key': '',
     'timeout_s': 120,
 },
 'image': {
     'provider': 'comfyui',
     'endpoint': 'http://host.docker.internal:8188',
     'workflow': 'sdxl',
     'workflow_json': '',
     'timeout_s': 300,
     'model': '',
     'defaults': {
         'width': 1024,
         'height': 1024,
         'steps': 30,
         'cfg_scale': 7.0,
         'sampler_name': 'LCM',
         'scheduler': 'KL-Optimal',
         'negative_prompt': 'worst quality, low quality, blurred, monochrome',
     },
 }
}


def _register_generated_asset(filename: str, metadata: dict) -> dict | None:
    try:
        registry = AssetRegistry(DATA)
        registry.initialize()
        return registry.ingest_generated(
            GeneratedAssetIngestRequest(
                file=filename,
                source_module=str(metadata.get("source_module") or metadata.get("provider") or "studio"),
                source_id=str(metadata.get("comfyui_prompt_id") or metadata.get("seed") or Path(filename).stem),
                metadata=metadata,
                provenance={"registered_by": "studio_features.generate_image"},
            )
        )
    except Exception:
        return None

class SettingsPayload(BaseModel):
    llm: dict
    image: dict

class PromptPayload(BaseModel):
    prompt: str
    negative_prompt: str = ''
    width: int = 1024
    height: int = 1024
    steps: int = 30
    cfg_scale: float = 7.0
    sampler_name: str = "Euler a"
    scheduler: str = "Automatic"
    seed: int | None = None
    provider: str | None = None
    model: str | None = None
    controlnet_type: str | None = None
    controlnet_image: str | None = None
    controlnet_strength: float | None = 0.8



class ComfyUITestPayload(BaseModel):
    endpoint: str


class LlmTestPayload(BaseModel):
    provider: str
    endpoint: str
    model: str = ""
    api_key: str = ""

class PreprocessControlnetPayload(BaseModel):
    image_base64: str
    preprocessor: str = ""
    api_key: str = ""


def _normalize_local_endpoint(endpoint: str) -> str:
    parsed = urlparse((endpoint or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Endpoint must be an http(s) URL.")
    hostname = (parsed.hostname or "").lower()
    netloc = parsed.netloc
    if Path("/.dockerenv").exists() and hostname in {"127.0.0.1", "localhost"}:
        netloc = parsed.netloc.replace(parsed.hostname or hostname, "host.docker.internal", 1)
    return urlunparse((parsed.scheme, netloc, parsed.path.rstrip("/"), "", "", "")).rstrip("/")


def _deep_merge(base: dict, overrides: dict | None) -> dict:
    if overrides is None:
        return json.loads(json.dumps(base))
    merged: dict = json.loads(json.dumps(base))
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_settings():
    if SETTINGS.exists():
        return _deep_merge(DEFAULTS, json.loads(SETTINGS.read_text()))
    SETTINGS.write_text(json.dumps(DEFAULTS, indent=2))
    return json.loads(json.dumps(DEFAULTS))


def _truthy_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _compact_error(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}".strip()
    return text[:240] + "..." if len(text) > 243 else text


def _http_probe(name: str, url: str, *, timeout_s: float = 2.0) -> dict:
    if not url:
        return {"id": name, "ready": False, "status": "missing", "error": "Endpoint is not configured."}
    try:
        response = requests.get(url, timeout=timeout_s)
        return {
            "id": name,
            "ready": response.status_code < 500,
            "status": "ready" if response.status_code < 500 else "error",
            "status_code": response.status_code,
            "url": url,
        }
    except Exception as exc:
        return {"id": name, "ready": False, "status": "error", "url": url, "error": _compact_error(exc)}


def _studio_modules() -> list[dict]:
    return [
        {"id": "dashboard", "label": "Dashboard", "path": "/", "category": "core", "status": "ready"},
        {"id": "training", "label": "Training", "path": "/training", "category": "sdxl", "status": "ready"},
        {"id": "generation", "label": "Generation", "path": "/generation", "category": "sdxl", "status": "ready"},
        {"id": "video", "label": "Video", "path": "/video", "category": "video", "status": "ready"},
        {"id": "gallery", "label": "Gallery", "path": "/gallery", "category": "library", "status": "ready"},
        {"id": "wildcards", "label": "Wildcards", "path": "/wildcards", "category": "prompting", "status": "ready"},
        {"id": "movie", "label": "Movie Script", "path": "/movie", "category": "story", "status": "ready"},
        {"id": "cards", "label": "SillyTavern Cards", "path": "/cards", "category": "characters", "status": "ready"},
        {"id": "settings", "label": "Settings", "path": "/settings", "category": "system", "status": "ready"},
    ]


@router.get('/manifest')
def get_manifest():
    settings = load_settings()
    image_settings = settings.get("image", {})
    llm_settings = settings.get("llm", {})
    return {
        "name": "Mklan Studio",
        "version": "2.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "data_root": str(DATA),
        "active_workspace_id": active_workspace_id(DATA),
        "modules": _studio_modules(),
        "integrations": {
            "comfyui": {
                "provider": image_settings.get("provider"),
                "endpoint": image_settings.get("endpoint"),
                "workflow": image_settings.get("workflow"),
                "model": image_settings.get("model"),
            },
            "llm": {
                "provider": llm_settings.get("provider"),
                "endpoint": llm_settings.get("endpoint"),
                "model": llm_settings.get("model"),
            },
            "media_indexer": {
                "internal_url": os.getenv("MEDIA_INDEXER_INTERNAL_URL", "http://media_indexer_backend:8000"),
                "auto_sync_generated": _truthy_env("MEDIA_INDEXER_AUTO_SYNC_GENERATED", True),
                "auto_scan_mode": os.getenv("MEDIA_INDEXER_AUTO_SCAN_MODE", "metadata"),
            },
            "sillytavern": {
                "enabled": _truthy_env("CARDS_SILLYTAVERN_ENABLED", True),
                "public_url": os.getenv("SILLYTAVERN_PUBLIC_URL", "http://localhost:8011"),
                "internal_url": os.getenv("SILLYTAVERN_INTERNAL_URL", "http://sillytavern:8000"),
            },
            "captioning": {
                "provider": os.getenv("STUDIO_CAPTION_PROVIDER", "auto"),
                "model": os.getenv("STUDIO_CAPTION_MODEL_ID", "Salesforce/blip-image-captioning-base"),
                "local_enabled": not _truthy_env("STUDIO_DISABLE_LOCAL_CAPTIONING", False),
                "download_allowed": _truthy_env("STUDIO_CAPTION_ALLOW_DOWNLOAD", False),
                "florence_url": os.getenv("STUDIO_FLORENCE_URL", ""),
                "florence_model": os.getenv("STUDIO_FLORENCE_MODEL_ID", "microsoft/Florence-2-base"),
                "florence_download_allowed": _truthy_env("STUDIO_FLORENCE_ALLOW_DOWNLOAD", False),
                "clip_model": os.getenv("STUDIO_CAPTION_CLIP_MODEL_ID", "OysterQAQ/DanbooruCLIP"),
                "clip_model_source": os.getenv("STUDIO_CAPTION_CLIP_MODEL_SOURCE", "auto"),
                "clip_download_allowed": _truthy_env("STUDIO_CAPTION_CLIP_ALLOW_DOWNLOAD", False),
                "clip_tags_path": os.getenv("STUDIO_CAPTION_CLIP_TAGS_PATH", "/app/data/models/captioning/tag_vocab/default_tags.txt"),
                "clip_top_k": int(os.getenv("STUDIO_CAPTION_CLIP_TOP_K", "24") or "24"),
                "vlm_endpoint": os.getenv("STUDIO_CAPTION_VLM_ENDPOINT", "") or llm_settings.get("endpoint"),
                "vlm_model": os.getenv("STUDIO_CAPTION_VLM_MODEL", "") or llm_settings.get("model"),
            },
        },
        "limits": {
            "image_upload_max_bytes": max_image_upload_bytes(),
            "model_upload_max_bytes": max_model_upload_bytes(),
            "dataset_zip_max_bytes": int(os.getenv("STUDIO_DATASET_ZIP_MAX_BYTES", str(1024 * 1024 * 1024))),
        },
        "capabilities": [
            "training.dataset_review",
            "training.caption_scan",
            "training.queue",
            "generation.queue",
            "gallery.sillytavern_card_scan",
            "studio.preflight",
            "workspaces.profiles",
            "workflows.template_library",
            "training.model_families",
            "copilot.alpha",
            "video.native",
            "video.movie_prefill",
            "captioning.florence2",
            "workspaces.zip_package",
            "workflows.node_inspector",
        ],
    }


@router.get('/preflight')
def get_preflight():
    settings = load_settings()
    image_settings = settings.get("image", {})
    llm_settings = settings.get("llm", {})
    checks: list[dict] = []
    warnings: list[dict] = []

    def add_warning(check_id: str, severity: str, title: str, detail: str, action: str = "") -> None:
        warnings.append({"id": check_id, "severity": severity, "title": title, "detail": detail, "action": action})

    if not os.getenv("STUDIO_API_KEY", "").strip():
        add_warning(
            "studio_api_key",
            "warning",
            "API key disabled",
            "Write endpoints are open to the local network while STUDIO_API_KEY is empty.",
            "Set STUDIO_API_KEY before exposing the studio outside a trusted LAN.",
        )

    cors = os.getenv("STUDIO_CORS_ORIGINS", "")
    if "*" in cors:
        add_warning("cors_origins", "warning", "Wide CORS policy", "STUDIO_CORS_ORIGINS contains '*'.")

    caption_provider = os.getenv("STUDIO_CAPTION_PROVIDER", "auto").strip().lower() or "auto"
    caption_vlm_endpoint = os.getenv("STUDIO_CAPTION_VLM_ENDPOINT", "").strip() or str(llm_settings.get("endpoint") or "").strip()
    caption_clip_tags_path = Path(os.getenv("STUDIO_CAPTION_CLIP_TAGS_PATH", str(DATA / "models" / "captioning" / "tag_vocab" / "default_tags.txt")))
    bundled_clip_tags_path = Path(__file__).resolve().parent / "resources" / "caption_tags_default.txt"
    if caption_provider in {"koboldcpp_vlm", "vlm", "koboldcpp"} and not caption_vlm_endpoint:
        add_warning(
            "captioning_vlm_endpoint",
            "warning",
            "Caption VLM endpoint missing",
            "STUDIO_CAPTION_PROVIDER selects KoboldCPP/vLLM captioning, but no caption or LLM endpoint is configured.",
            "Set STUDIO_CAPTION_VLM_ENDPOINT or configure the Studio LLM endpoint.",
        )

    if caption_provider in {"clip_tagger", "clip", "auto"} and not caption_clip_tags_path.exists() and not bundled_clip_tags_path.exists():
        add_warning(
            "captioning_clip_tags",
            "info",
            "CLIP tag vocabulary missing",
            "The CLIP tagger needs a candidate tag list before it can build useful captions.",
            "Run scripts/download_caption_models.py --models danbooru-clip or copy backend/app/resources/caption_tags_default.txt to the configured tag path.",
        )

    if _truthy_env("STUDIO_DISABLE_LOCAL_CAPTIONING", False):
        add_warning(
            "captioning_disabled",
            "info",
            "Local captioning disabled",
            "Local BLIP captioning is disabled. Caption scan can still use KoboldCPP/vLLM, CLIP tagger, or filename fallback.",
            "Unset STUDIO_DISABLE_LOCAL_CAPTIONING when a local caption model is available.",
        )
    elif not _truthy_env("STUDIO_CAPTION_ALLOW_DOWNLOAD", False):
        add_warning(
            "captioning_cache",
            "info",
            "Caption model must already be cached",
            "STUDIO_CAPTION_ALLOW_DOWNLOAD is false; caption scan falls back if the BLIP model is not cached locally.",
            "Set STUDIO_CAPTION_ALLOW_DOWNLOAD=true once if the host may download the model.",
        )

    if os.getenv("MEDIA_INDEXER_POSTGRES_PASSWORD", "") in {"", "change-me"}:
        add_warning("media_indexer_db_password", "warning", "Default media database password", "MEDIA_INDEXER_POSTGRES_PASSWORD is unset or still uses the docker-compose default.")

    if os.getenv("MEDIA_INDEXER_SESSION_SECRET", "") in {"", "change-me-in-production"}:
        add_warning("media_indexer_session_secret", "warning", "Default media session secret", "MEDIA_INDEXER_SESSION_SECRET is unset or still uses the docker-compose default.")

    if os.getenv("SILLYTAVERN_SECURITYOVERRIDE", "").lower() == "true":
        add_warning("sillytavern_security_override", "warning", "SillyTavern security override enabled", "SILLYTAVERN_SECURITYOVERRIDE=true is convenient locally but risky on an exposed host.")

    comfy_endpoint = str(image_settings.get("endpoint") or "").rstrip("/")
    if str(image_settings.get("provider") or "").lower() == "comfyui" and comfy_endpoint:
        try:
            comfy_url = f"{ComfyUIClient(comfy_endpoint, timeout_s=2).endpoint}/system_stats"
        except Exception:
            comfy_url = f"{comfy_endpoint}/system_stats"
        checks.append(_http_probe("comfyui", comfy_url, timeout_s=2))

    llm_endpoint = str(llm_settings.get("endpoint") or "").rstrip("/")
    if llm_endpoint:
        try:
            llm_endpoint = _normalize_local_endpoint(llm_endpoint)
        except Exception:
            pass
        checks.append(_http_probe("llm", f"{llm_endpoint}/models", timeout_s=2))

    media_url = os.getenv("MEDIA_INDEXER_INTERNAL_URL", "http://media_indexer_backend:8000").rstrip("/")
    checks.append(_http_probe("media_indexer", f"{media_url}/health", timeout_s=2))

    silly_url = os.getenv("SILLYTAVERN_INTERNAL_URL", "http://sillytavern:8000").rstrip("/")
    if _truthy_env("CARDS_SILLYTAVERN_ENABLED", True):
        checks.append(_http_probe("sillytavern", silly_url, timeout_s=2))

    error_checks = [check for check in checks if not check.get("ready")]
    return {
        "ok": not error_checks,
        "generated_at": datetime.now(UTC).isoformat(),
        "checks": checks,
        "warnings": warnings,
        "summary": {
            "ready": sum(1 for check in checks if check.get("ready")),
            "blocked": len(error_checks),
            "warnings": len(warnings),
        },
    }


@router.get('/settings')
def get_settings():
    return load_settings()

@router.post('/settings')
def save_settings(payload: SettingsPayload):
    merged = _deep_merge(DEFAULTS, payload.model_dump())
    SETTINGS.write_text(json.dumps(merged, indent=2))
    return {'saved': True}

@router.get('/models')
def list_models():
    files=[]
    seen: set[tuple[str, str]] = set()
    for ext in ['*.safetensors', '*.ckpt', '*.pt', '*.bin']:
        for f in MODELS.rglob(ext):
            if f.is_file():
                relative = str(f.relative_to(MODELS))
                seen.add((f.name, relative))
                files.append({
                    'name': f.name,
                    'size': f.stat().st_size,
                    'path': relative,
                    'provider': 'local',
                })

    settings = load_settings()
    image_settings = settings.get("image", {})
    if str(image_settings.get("provider") or "").strip().lower() == "comfyui":
        endpoint = str(image_settings.get("endpoint") or "").strip()
        if endpoint:
            try:
                checkpoints = ComfyUIClient(
                    endpoint,
                    timeout_s=int(image_settings.get("timeout_s") or 300),
                ).list_checkpoints()
                comfy_models = [
                        {
                            "name": checkpoint,
                            "size": 0,
                            "path": checkpoint,
                            "provider": "comfyui",
                        }
                        for checkpoint in checkpoints
                    if (checkpoint, checkpoint) not in seen
                ]
                files.extend(comfy_models)
            except Exception:
                # Keep local inventory visible even if the live ComfyUI endpoint is unreachable from the container.
                pass
    return {'models':files}


@router.post('/comfyui/test')
def test_comfyui(payload: ComfyUITestPayload):
    try:
        return ComfyUIClient(payload.endpoint, timeout_s=30).test_connection()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ComfyUI connection failed: {exc}")

@router.get('/comfyui/object_info')
def get_comfyui_object_info():
    settings = get_settings()
    image_settings = settings.get("image_generation", {})
    endpoint = image_settings.get("comfyui_endpoint")
    if not endpoint:
        raise HTTPException(status_code=400, detail="ComfyUI endpoint is not configured.")
    try:
        return ComfyUIClient(endpoint, timeout_s=15).object_info()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch ComfyUI object info: {exc}")

@router.post('/llm/test')
def test_llm(payload: LlmTestPayload):
    try:
        endpoint = _normalize_local_endpoint(payload.endpoint)
        headers = {}
        if payload.api_key:
            headers["Authorization"] = f"Bearer {payload.api_key}"
        response = requests.get(f"{endpoint}/models", headers=headers, timeout=10)
        response.raise_for_status()
        body = response.json()
        models = body.get("data") if isinstance(body, dict) else []
        model_names = [
            str(item.get("id") or item.get("name"))
            for item in models
            if isinstance(item, dict) and (item.get("id") or item.get("name"))
        ]
        configured_model = payload.model.strip()
        ready = not configured_model or not model_names or configured_model in model_names or payload.provider == "koboldcpp"
        return {
            "ok": True,
            "ready": ready,
            "endpoint": endpoint,
            "models": model_names,
            "message": "LLM endpoint is reachable.",
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM connection failed: {exc}")

@router.post('/preprocess-controlnet')
def preprocess_controlnet(payload: PreprocessControlnetPayload):
    settings = get_settings()
    image_settings = settings.get("image_generation", {})
    endpoint = image_settings.get("comfyui_endpoint")
    if not endpoint:
        raise HTTPException(status_code=400, detail="ComfyUI endpoint not configured.")
    
    try:
        client = ComfyUIClient(endpoint, timeout_s=120)
        # Decode base64
        header, encoded = payload.image_base64.split(',', 1) if ',' in payload.image_base64 else ('', payload.image_base64)
        img_data = base64.b64decode(encoded)
        
        # Upload
        upload_res = client.upload_image(img_data, f"prep_{uuid.uuid4().hex}.png")
        uploaded_name = upload_res["name"]
        
        # Map simple names to ComfyUI node classes (typically from ComfyUI-Controlnet-Aux)
        preprocessor_map = {
            "canny": "CannyEdgePreprocessor",
            "openpose": "OpenposePreprocessor",
            "depthanything": "DepthAnythingPreprocessor",
            "scribble": "ScribblePreprocessor",
            "lineart": "LineartPreprocessor"
        }
        
        node_class = preprocessor_map.get(payload.preprocessor.lower())
        if not node_class:
            node_class = payload.preprocessor # Fallback to literal class name if they pass one
            
        workflow = {
            "1": {
                "class_type": "LoadImage",
                "inputs": {"image": uploaded_name}
            },
            "2": {
                "class_type": node_class,
                "inputs": {"image": ["1", 0]}
            },
            "3": {
                "class_type": "SaveImage",
                "inputs": {"images": ["2", 0], "filename_prefix": "preproc"}
            }
        }
        
        image_b64, _, _ = client.render_base64(workflow)
        return {"image_base64": image_b64}
        
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Preprocessing failed: {exc}")

@router.post('/models/upload')
def upload_model(file: UploadFile = File(...)):
    safe_name = safe_upload_name(file.filename, allowed_extensions=MODEL_EXTENSIONS)
    target_dir = MODELS / 'images'
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / safe_name
    save_upload_with_limits(
        file,
        target,
        allowed_extensions=MODEL_EXTENSIONS,
        max_bytes=max_model_upload_bytes(),
    )
    return {'uploaded': True, 'filename': safe_name}

@router.post('/generate-image')
def generate_image(payload: PromptPayload):
    settings = load_settings()
    image_settings = settings.get('image', {})
    provider = payload.provider or str(image_settings.get('provider') or 'auto').strip().lower()
    model_name = payload.model or str(image_settings.get('model', '') or '').strip()

    if provider == "comfyui":
        endpoint = str(image_settings.get("endpoint", "") or "").strip()
        if not endpoint:
            raise HTTPException(status_code=400, detail="ComfyUI endpoint is not configured.")
        try:
            client = ComfyUIClient(endpoint, timeout_s=int(image_settings.get("timeout_s") or 300))
            if not model_name:
                checkpoints = client.list_checkpoints()
                model_name = checkpoints[0] if checkpoints else ""
            workflow, seed = build_workflow_from_generation(
                workflow_json=image_settings.get("workflow_json") or "",
                prompt=payload.prompt,
                negative_prompt=payload.negative_prompt,
                model=model_name,
                width=payload.width,
                height=payload.height,
                steps=payload.steps,
                cfg_scale=payload.cfg_scale,
                sampler_name=payload.sampler_name,
                scheduler=payload.scheduler,
                seed=payload.seed,
            )
            
            # ControlNet logic for ComfyUI
            if payload.controlnet_type and payload.controlnet_image:
                # 1. Decode base64 controlnet image
                header, encoded = payload.controlnet_image.split(',', 1)
                img_data = base64.b64decode(encoded)
                # 2. Upload image to ComfyUI
                upload_res = client.upload_image(img_data, f"controlnet_{uuid.uuid4().hex}.png")
                uploaded_filename = upload_res["name"]
                # 3. Find matched controlnet checkpoint
                controlnet_models = client.list_controlnets()
                controlnet_model_name = None
                target_type = payload.controlnet_type.lower()
                for m in controlnet_models:
                    if target_type in m.lower():
                        controlnet_model_name = m
                        break
                if not controlnet_model_name:
                    controlnet_model_name = controlnet_models[0] if controlnet_models else f"controlnet-{target_type}-sdxl.safetensors"
                # 4. Inject nodes to workflow
                workflow["10"] = {
                    "class_type": "LoadImage",
                    "inputs": {"image": uploaded_filename}
                }
                workflow["11"] = {
                    "class_type": "ControlNetLoader",
                    "inputs": {"control_net_name": controlnet_model_name}
                }
                ksampler_id = None
                for node_id, node in workflow.items():
                    if node.get("class_type") == "KSampler":
                        ksampler_id = node_id
                        break
                if ksampler_id:
                    ksampler = workflow[ksampler_id]
                    pos_link = ksampler.get("inputs", {}).get("positive")
                    if pos_link and isinstance(pos_link, list) and len(pos_link) >= 2:
                        workflow["12"] = {
                            "class_type": "ControlNetApply",
                            "inputs": {
                                "strength": payload.controlnet_strength if payload.controlnet_strength is not None else 0.8,
                                "conditioning": pos_link,
                                "control_net": ["11", 0],
                                "image": ["10", 0]
                            }
                        }
                        ksampler["inputs"]["positive"] = ["12", 0]

            image_b64, prompt_id, output = client.render_base64(workflow)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"ComfyUI generation failed: {exc}")

        image_bytes = base64.b64decode(image_b64)
        filename = f'{uuid.uuid4().hex}.png'
        path = GENERATED / filename
        path.write_bytes(image_bytes)
        metadata = {
            **payload.model_dump(),
            "provider": "comfyui",
            "model": model_name,
            "workflow": image_settings.get("workflow") or "comfyui",
            "seed": seed,
            "comfyui_prompt_id": prompt_id,
            "comfyui_output": output,
        }
        meta_path = GENERATED / f'{path.stem}.json'
        meta_path.write_text(json.dumps(metadata, indent=2))
        asset = _register_generated_asset(filename, metadata)
        return {'image_base64': image_b64, 'file': f'/generated/{filename}', 'metadata': metadata, 'asset': asset}

    # --- Find a local model file ---
    local_model_path: Path | None = None
    if provider not in {"sd_webui", "automatic1111"} and model_name:
        # Check if the saved model name matches a file we have
        for ext in ['*.safetensors', '*.ckpt', '*.pt']:
            for f in MODELS.rglob(ext):
                if f.name == model_name or f.stem == model_name:
                    local_model_path = f
                    break
    if provider not in {"sd_webui", "automatic1111"} and local_model_path is None:
        # Fall back to first available model
        for ext in ['*.safetensors', '*.ckpt', '*.pt']:
            candidates = list(MODELS.rglob(ext))
            if candidates:
                local_model_path = candidates[0]
                break
    if provider == "diffusers" and local_model_path is None:
        raise HTTPException(
            status_code=400,
            detail="Local Diffusers provider is selected, but no local checkpoint was found. Upload a model or switch the image provider.",
        )

    # --- Native diffusers inference ---
    if local_model_path is not None:
        try:
            import torch
            from diffusers import (
                StableDiffusionXLPipeline, 
                StableDiffusionXLControlNetPipeline, 
                ControlNetModel,
                EulerAncestralDiscreteScheduler, 
                LCMScheduler, 
                DPMSolverMultistepScheduler, 
                DPMSolverSinglestepScheduler
            )
            from PIL import Image as PILImage
            import io

            dtype = torch.float16 if torch.cuda.is_available() else torch.float32
            device = "cuda" if torch.cuda.is_available() else "cpu"

            # Check if ControlNet is enabled
            if payload.controlnet_type and payload.controlnet_image:
                repo_map = {
                    "canny": "diffusers/controlnet-canny-sdxl-1.0",
                    "openpose": "thibaud/controlnet-openpose-sdxl-1.0",
                    "depth": "diffusers/controlnet-depth-sdxl-1.0",
                    "depthanything": "diffusers/controlnet-depth-sdxl-1.0",
                    "scribble": "xinsir/controlnet-scribble-sdxl-1.0",
                    "lineart": "xinsir/controlnet-lineart-sdxl-1.0",
                }
                repo_id = repo_map.get(payload.controlnet_type.lower(), "diffusers/controlnet-canny-sdxl-1.0")
                
                # 1. Parse and preprocess image
                header, encoded = payload.controlnet_image.split(',', 1)
                img_data = base64.b64decode(encoded)
                control_image = PILImage.open(io.BytesIO(img_data)).convert("RGB")
                
                if payload.controlnet_type.lower() == "canny":
                    import numpy as np
                    try:
                        import cv2
                        np_img = np.array(control_image)
                        np_img = cv2.Canny(np_img, 100, 200)
                        np_img = np_img[:, :, None]
                        np_img = np.concatenate([np_img, np_img, np_img], axis=2)
                        control_image = PILImage.fromarray(np_img)
                    except ImportError:
                        from PIL import ImageFilter
                        control_image = control_image.filter(ImageFilter.FIND_EDGES)
                
                # 2. Load ControlNet
                controlnet = ControlNetModel.from_pretrained(repo_id, torch_dtype=dtype)
                
                # 3. Load Pipeline
                pipe = StableDiffusionXLControlNetPipeline.from_single_file(
                    str(local_model_path),
                    controlnet=controlnet,
                    torch_dtype=dtype,
                    use_safetensors=str(local_model_path).endswith('.safetensors'),
                ).to(device)
            else:
                pipe = StableDiffusionXLPipeline.from_single_file(
                    str(local_model_path),
                    torch_dtype=dtype,
                    use_safetensors=str(local_model_path).endswith('.safetensors'),
                ).to(device)

            # Apply sampler/scheduler selection
            sampler = payload.sampler_name.lower()
            if 'lcm' in sampler:
                pipe.scheduler = LCMScheduler.from_config(pipe.scheduler.config)
            elif 'dpm++ sde' in sampler or 'dpmpp_sde' in sampler:
                pipe.scheduler = DPMSolverSinglestepScheduler.from_config(pipe.scheduler.config, use_karras_sigmas='karras' in payload.scheduler.lower())
            elif 'dpm++ 2s' in sampler or 'dpmpp_2s' in sampler:
                pipe.scheduler = DPMSolverSinglestepScheduler.from_config(pipe.scheduler.config)
            elif 'dpm++ 2m' in sampler or 'dpmpp_2m' in sampler:
                pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config, use_karras_sigmas='karras' in payload.scheduler.lower())
            else:
                pipe.scheduler = EulerAncestralDiscreteScheduler.from_config(pipe.scheduler.config)

            pipe.enable_attention_slicing()

            if payload.controlnet_type and payload.controlnet_image:
                result = pipe(
                    prompt=payload.prompt,
                    negative_prompt=payload.negative_prompt or None,
                    image=control_image,
                    controlnet_conditioning_scale=payload.controlnet_strength if payload.controlnet_strength is not None else 0.8,
                    width=payload.width,
                    height=payload.height,
                    num_inference_steps=payload.steps,
                    guidance_scale=payload.cfg_scale,
                )
            else:
                result = pipe(
                    prompt=payload.prompt,
                    negative_prompt=payload.negative_prompt or None,
                    width=payload.width,
                    height=payload.height,
                    num_inference_steps=payload.steps,
                    guidance_scale=payload.cfg_scale,
                )
            img: PILImage.Image = result.images[0]

            # Save and return
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)
            filename = f'{uuid.uuid4().hex}.png'
            path = GENERATED / filename
            path.write_bytes(buf.read())
            
            # Save metadata
            meta_path = GENERATED / f'{path.stem}.json'
            metadata = payload.model_dump()
            meta_path.write_text(json.dumps(metadata, indent=2))
            asset = _register_generated_asset(filename, metadata)
            
            image_b64 = base64.b64encode(path.read_bytes()).decode()
            return {'image_base64': image_b64, 'file': f'/generated/{filename}', 'metadata': metadata, 'asset': asset}

        except Exception as exc:
            raise HTTPException(status_code=500, detail=f'Local inference failed: {exc}')

    # --- Fallback: external SD WebUI API ---
    endpoint = image_settings.get('endpoint', '').rstrip('/')
    if not endpoint:
        raise HTTPException(status_code=500, detail='No local model found and no image API endpoint configured. Upload a model via Settings → Models or set an endpoint.')
    body = {
      'prompt': payload.prompt,
      'negative_prompt': payload.negative_prompt,
      'steps': payload.steps,
      'width': payload.width,
      'height': payload.height,
      'cfg_scale': payload.cfg_scale,
      'sampler_name': payload.sampler_name,
      'scheduler': payload.scheduler,
    }
    try:
      response = requests.post(f'{endpoint}/sdapi/v1/txt2img', json=body, timeout=300)
      response.raise_for_status()
      data = response.json()
      image = data['images'][0]
    except Exception as exc:
      raise HTTPException(status_code=500, detail=f'External image API failed: {exc}')

    image_bytes = base64.b64decode(image.split(',', 1)[-1])
    filename = f'{uuid.uuid4().hex}.png'
    path = GENERATED / filename
    path.write_bytes(image_bytes)

    # Save metadata
    meta_path = GENERATED / f'{path.stem}.json'
    metadata = payload.model_dump()
    meta_path.write_text(json.dumps(metadata, indent=2))
    asset = _register_generated_asset(filename, metadata)

    return {'image_base64': image, 'file': f'/generated/{filename}', 'metadata': metadata, 'asset': asset}


@router.get('/generated')
def list_generated_images():
    files = []
    for f in GENERATED.glob('*.png'):
        if f.is_file():
            meta = {}
            meta_file = GENERATED / f'{f.stem}.json'
            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text())
                except:
                    pass
            files.append({
                'name': f.name,
                'size': f.stat().st_size,
                'created_at': f.stat().st_mtime,
                'url': f'/generated/{f.name}',
                'metadata': meta
            })
    # Sort by creation time, newest first
    files.sort(key=lambda x: x['created_at'], reverse=True)
    return {'images': files}

from typing import List
@router.post('/generated/upload')
def upload_generated_images(files: List[UploadFile] = File(...)):
    uploaded = []
    for file in files:
        if not file.filename:
            continue
        safe_name = safe_upload_name(file.filename, allowed_extensions=IMAGE_EXTENSIONS)
        # To avoid overwriting existing generated files
        if (GENERATED / safe_name).exists():
            safe_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
            
        target = GENERATED / safe_name
        save_upload_with_limits(
            file,
            target,
            allowed_extensions=IMAGE_EXTENSIONS,
            max_bytes=max_image_upload_bytes(),
            validate_image_magic=True,
        )
        _register_generated_asset(safe_name, {"source_module": "gallery_upload", "original_filename": file.filename})
        uploaded.append(safe_name)
    return {'uploaded': len(uploaded), 'filenames': uploaded}

@router.delete('/generated/{filename}')
def delete_generated_image(filename: str):
    target = GENERATED / filename
    # Sanity check to prevent directory traversal
    if target.parent != GENERATED:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    try:
        target.unlink()
        meta = GENERATED / f'{target.stem}.json'
        if meta.exists():
            meta.unlink()
        return {'deleted': True}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete image: {exc}")


@router.get('/templates/raw')
def list_raw_templates():
    template_dir = DATA / "characters" / "template"
    if not template_dir.exists():
        return {"images": []}
    
    images = []
    for f in template_dir.iterdir():
        if f.is_file() and f.suffix.lower() in ['.png', '.jpg', '.jpeg', '.webp']:
            # We will serve this via static files or a dedicated endpoint. 
            # But we can just use the static media route if we register it, or read it as base64 for now.
            images.append(f.name)
    return {"images": images}

@router.get('/templates/raw/{filename}')
def get_raw_template(filename: str):
    template_dir = DATA / "characters" / "template"
    file_path = template_dir / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Template not found")
    return FileResponse(file_path)

def _timestamp_ms(value: str | int | float | None) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            from datetime import datetime

            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000
        except ValueError:
            return 0
    return 0


def _media_indexer_item_to_gallery_image(item: dict) -> dict:
    asset_id = item.get("id")
    filename = item.get("filename") or str(item.get("relative_path") or asset_id or "asset").split("/")[-1]
    return {
        "id": asset_id,
        "name": filename,
        "size": item.get("size_bytes") or 0,
        "created_at": _timestamp_ms(item.get("modified_at") or item.get("created_at") or item.get("indexed_at")),
        "url": f"/api/media/assets/{asset_id}/image?w=1024" if asset_id else item.get("content_url"),
        "metadata": item.get("normalized_metadata") or {},
        "source": "media-indexer",
    }


def _registry_asset_to_gallery_image(asset: dict) -> dict:
    path = Path(asset.get("path") or "")
    size = path.stat().st_size if path.exists() else 0
    return {
        "id": asset.get("id"),
        "name": path.name or str(asset.get("source_id") or "asset"),
        "size": size,
        "created_at": _timestamp_ms(asset.get("updated_at") or asset.get("created_at")),
        "url": asset.get("url"),
        "metadata": asset.get("metadata") or {},
        "source": asset.get("source_module") or "studio-registry",
    }


@router.get('/semantic-search')
def semantic_search(q: str):
    query = q.strip()
    if not query:
        return {'images': []}

    media_result = search_engine.search(query, limit=80)
    media_items = media_result.get("items") or []
    if media_result.get("ok") and media_items:
        return {
            'images': [_media_indexer_item_to_gallery_image(item) for item in media_items if isinstance(item, dict)],
            'source': 'media-indexer',
            'media_indexer': {key: media_result.get(key) for key in ("status", "base_url", "total")},
        }

    registry = AssetRegistry(DATA)
    registry.initialize()
    local_assets = registry.search_local(query, limit=80)
    return {
        'images': [_registry_asset_to_gallery_image(asset) for asset in local_assets],
        'source': 'studio-registry-fallback',
        'media_indexer': {key: media_result.get(key) for key in ("status", "base_url", "error")},
    }


class RemoveBackgroundPayload(BaseModel):
    image_base64: str


@router.post('/remove-background')
def remove_background(payload: RemoveBackgroundPayload):
    try:
        import io
        from PIL import Image
        import rembg

        # Decode base64
        header, encoded = payload.image_base64.split(',', 1)
        img_data = base64.b64decode(encoded)
        img = Image.open(io.BytesIO(img_data))

        # Remove background using rembg
        output_img = rembg.remove(img)

        # Encode back to base64
        buf = io.BytesIO()
        output_img.save(buf, format='PNG')
        buf.seek(0)
        output_base64 = base64.b64encode(buf.read()).decode('utf-8')

        return {'image_base64': f"data:image/png;base64,{output_base64}"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Background removal failed: {exc}")
