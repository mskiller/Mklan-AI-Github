from __future__ import annotations

import base64
from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
import random
import re
import time
from typing import Any, Callable
from urllib.parse import urlparse, urlunparse
import uuid

import requests

try:
    from websockets.sync.client import connect as connect_websocket
except Exception:  # pragma: no cover - optional runtime dependency in some CPU-only installs
    connect_websocket = None


DEFAULT_COMFYUI_WORKFLOW: dict[str, Any] = {
    "1": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "%model%"},
    },
    "2": {
        "class_type": "CLIPTextEncode",
        "inputs": {"clip": ["1", 1], "text": "%prompt%"},
    },
    "3": {
        "class_type": "CLIPTextEncode",
        "inputs": {"clip": ["1", 1], "text": "%negative_prompt%"},
    },
    "4": {
        "class_type": "EmptyLatentImage",
        "inputs": {"width": "%width%", "height": "%height%", "batch_size": 1},
    },
    "5": {
        "class_type": "KSampler",
        "inputs": {
            "model": ["1", 0],
            "positive": ["2", 0],
            "negative": ["3", 0],
            "latent_image": ["4", 0],
            "seed": "%seed%",
            "steps": "%steps%",
            "cfg": "%scale%",
            "sampler_name": "%sampler%",
            "scheduler": "%scheduler%",
            "denoise": "%denoise%",
        },
    },
    "6": {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
    },
    "7": {
        "class_type": "SaveImage",
        "inputs": {"images": ["6", 0], "filename_prefix": "MklanStudio"},
    },
}


COMFY_SAMPLER_ALIASES = {
    "euler_a": "euler_ancestral",
    "euler_ancestral": "euler_ancestral",
    "euler": "euler",
    "lcm": "lcm",
    "res_multistep": "res_multistep",
    "res_multistep_cfgpp": "res_multistep_cfgpp",
    "dpm_2s_a": "dpmpp_2s_ancestral",
    "dpm_2s_ancestral": "dpmpp_2s_ancestral",
    "dpmpp_2s_a": "dpmpp_2s_ancestral",
    "dpmpp_2s_ancestral": "dpmpp_2s_ancestral",
    "dpm_sde": "dpmpp_sde",
    "dpmpp_sde": "dpmpp_sde",
    "dpm_2m": "dpmpp_2m",
    "dpmpp_2m": "dpmpp_2m",
    "dpm_2m_sde": "dpmpp_2m_sde",
    "dpmpp_2m_sde": "dpmpp_2m_sde",
    "ddim": "ddim",
}

COMFY_SCHEDULER_ALIASES = {
    "automatic": "normal",
    "auto": "normal",
    "normal": "normal",
    "simple": "simple",
    "karras": "karras",
    "kl_optimal": "kl_optimal",
    "kloptimal": "kl_optimal",
    "gits": "gits",
    "beta": "beta",
    "exponential": "exponential",
    "sgm_uniform": "sgm_uniform",
}


@dataclass(frozen=True)
class ComfyUIRenderResult:
    image_bytes: bytes
    prompt_id: str
    output: dict[str, Any]


ComfyUIProgressCallback = Callable[[dict[str, Any]], None]


def normalize_comfyui_endpoint(endpoint: str) -> str:
    cleaned = str(endpoint or "").strip().rstrip("/")
    if not cleaned:
        raise ValueError("ComfyUI endpoint is required.")
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("ComfyUI endpoint must be an http(s) URL, for example http://127.0.0.1:8188.")
    if Path("/.dockerenv").exists() and parsed.hostname in {"127.0.0.1", "localhost"}:
        netloc = "host.docker.internal"
        if parsed.port:
            netloc = f"{netloc}:{parsed.port}"
        cleaned = urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)).rstrip("/")
    return cleaned


def parse_workflow_template(workflow_json: str | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(workflow_json, dict):
        return deepcopy(workflow_json)
    raw = str(workflow_json or "").strip()
    if not raw:
        return deepcopy(DEFAULT_COMFYUI_WORKFLOW)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"ComfyUI workflow JSON is invalid: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("ComfyUI workflow JSON must be an API-format object keyed by node id.")
    return parsed


def render_workflow_template(workflow: dict[str, Any], replacements: dict[str, Any]) -> dict[str, Any]:
    placeholders = {f"%{key}%": value for key, value in replacements.items()}

    def replace_value(value: Any) -> Any:
        if isinstance(value, str):
            if value in placeholders:
                return placeholders[value]
            output = value
            for placeholder, replacement in placeholders.items():
                if placeholder in output:
                    output = output.replace(placeholder, str(replacement))
            return output
        if isinstance(value, list):
            return [replace_value(item) for item in value]
        if isinstance(value, dict):
            return {key: replace_value(item) for key, item in value.items()}
        return value

    return replace_value(deepcopy(workflow))


def _comfy_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def normalize_comfy_sampler_name(sampler_name: str) -> str:
    key = _comfy_key(sampler_name)
    return COMFY_SAMPLER_ALIASES.get(key, key or "euler")


def normalize_comfy_scheduler_name(scheduler: str) -> str:
    key = _comfy_key(scheduler)
    return COMFY_SCHEDULER_ALIASES.get(key, key or "normal")


def build_workflow_from_generation(
    *,
    workflow_json: str | dict[str, Any] | None,
    prompt: str,
    negative_prompt: str,
    model: str,
    width: int,
    height: int,
    steps: int,
    cfg_scale: float,
    sampler_name: str,
    scheduler: str,
    seed: int | None = None,
    denoise: float = 1.0,
) -> tuple[dict[str, Any], int]:
    resolved_seed = int(seed if seed is not None and seed >= 0 else random.randint(1, 2**31 - 1))
    workflow = parse_workflow_template(workflow_json)
    comfy_sampler = normalize_comfy_sampler_name(sampler_name)
    comfy_scheduler = normalize_comfy_scheduler_name(scheduler)
    return (
        render_workflow_template(
            workflow,
            {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "model": model,
                "width": int(width),
                "height": int(height),
                "steps": int(steps),
                "scale": float(cfg_scale),
                "cfg_scale": float(cfg_scale),
                "cfg": float(cfg_scale),
                "sampler": comfy_sampler,
                "sampler_name": comfy_sampler,
                "scheduler": comfy_scheduler,
                "seed": resolved_seed,
                "denoise": float(denoise),
            },
        ),
        resolved_seed,
    )


class ComfyUIClient:
    def __init__(self, endpoint: str, *, timeout_s: int = 300) -> None:
        self.endpoint = normalize_comfyui_endpoint(endpoint)
        self.timeout_s = timeout_s
        self.session = requests.Session()

    def test_connection(self) -> dict[str, Any]:
        started = time.perf_counter()
        stats = self._get_json("/system_stats", timeout=10)
        models: list[str] = []
        try:
            payload = self._get_json("/models/checkpoints", timeout=10)
            if isinstance(payload, list):
                models = [str(item) for item in payload]
        except Exception:
            models = []
        return {
            "ok": True,
            "ready": True,
            "status": "ready",
            "message": "Connected to ComfyUI.",
            "endpoint": self.endpoint,
            "response_ms": round((time.perf_counter() - started) * 1000),
            "system": stats,
            "models": models,
        }

    def list_checkpoints(self) -> list[str]:
        payload = self._get_json("/models/checkpoints", timeout=10)
        if not isinstance(payload, list):
            return []
        return [str(item) for item in payload]

    def upload_image(self, image_bytes: bytes, filename: str) -> dict[str, Any]:
        files = {"image": (filename, image_bytes, "image/png")}
        data = {"overwrite": "true"}
        response = self.session.post(f"{self.endpoint}/upload/image", files=files, data=data, timeout=30)
        response.raise_for_status()
        return response.json()

    def list_controlnets(self) -> list[str]:
        try:
            payload = self._get_json("/models/controlnets", timeout=10)
            if isinstance(payload, list):
                return [str(item) for item in payload]
        except Exception:
            pass
        return []

    def list_models(self, model_type: str) -> list[str]:
        safe_type = _comfy_key(model_type)
        if not safe_type:
            return []
        payload = self._get_json(f"/models/{safe_type}", timeout=10)
        if not isinstance(payload, list):
            return []
        return [str(item) for item in payload]

    def object_info(self) -> dict[str, Any]:
        payload = self._get_json("/object_info", timeout=15)
        return payload if isinstance(payload, dict) else {}

    def render(self, workflow: dict[str, Any], *, progress_callback: ComfyUIProgressCallback | None = None) -> ComfyUIRenderResult:
        client_id = str(uuid.uuid4())
        websocket = self._open_progress_socket(client_id, progress_callback)
        queued = self._post_json("/prompt", {"prompt": workflow, "client_id": client_id}, timeout=30)
        prompt_id = str(queued.get("prompt_id") or "")
        if not prompt_id:
            error = queued.get("error") or queued.get("node_errors") or queued
            raise RuntimeError(f"ComfyUI rejected workflow: {error}")

        if websocket is not None:
            try:
                history = self._wait_for_websocket_completion(prompt_id, websocket, progress_callback)
            except Exception as exc:
                self._emit_progress(
                    progress_callback,
                    {
                        "type": "comfyui.websocket_fallback",
                        "prompt_id": prompt_id,
                        "message": f"Falling back to history polling: {exc}",
                    },
                )
                history = self._wait_for_history(prompt_id, progress_callback=progress_callback)
            finally:
                try:
                    websocket.close()
                except Exception:
                    pass
        else:
            history = self._wait_for_history(prompt_id, progress_callback=progress_callback)
        output = self._first_image_output(history)
        params = {
            "filename": output["filename"],
            "subfolder": output.get("subfolder", ""),
            "type": output.get("type", "output"),
        }
        image_response = self.session.get(f"{self.endpoint}/view", params=params, timeout=60)
        image_response.raise_for_status()
        return ComfyUIRenderResult(image_bytes=image_response.content, prompt_id=prompt_id, output=output)

    def render_base64(self, workflow: dict[str, Any], *, progress_callback: ComfyUIProgressCallback | None = None) -> tuple[str, str, dict[str, Any]]:
        result = self.render(workflow, progress_callback=progress_callback)
        return base64.b64encode(result.image_bytes).decode("ascii"), result.prompt_id, result.output

    def _wait_for_history(self, prompt_id: str, *, progress_callback: ComfyUIProgressCallback | None = None) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout_s
        last_payload: dict[str, Any] = {}
        while time.monotonic() < deadline:
            payload = self._get_json(f"/history/{prompt_id}", timeout=15)
            if isinstance(payload, dict):
                last_payload = payload
                entry = payload.get(prompt_id)
                if isinstance(entry, dict):
                    if entry.get("status", {}).get("status_str") == "error":
                        raise RuntimeError(f"ComfyUI workflow failed: {entry.get('status')}")
                    if self._history_has_image(entry):
                        return entry
            self._emit_progress(progress_callback, {"type": "comfyui.history_poll", "prompt_id": prompt_id})
            time.sleep(1.0)
        raise TimeoutError(f"Timed out waiting for ComfyUI prompt {prompt_id}. Last response: {last_payload}")

    def _wait_for_websocket_completion(
        self,
        prompt_id: str,
        websocket: Any,
        progress_callback: ComfyUIProgressCallback | None,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout_s
        last_history_check = 0.0
        while time.monotonic() < deadline:
            try:
                raw = websocket.recv(timeout=2)
                event = self._parse_websocket_event(raw)
                self._handle_websocket_event(prompt_id, event, progress_callback)
                event_type = str(event.get("type") or "")
                data = event.get("data") if isinstance(event.get("data"), dict) else {}
                if event_type == "execution_error" and (not data.get("prompt_id") or data.get("prompt_id") == prompt_id):
                    raise RuntimeError(f"ComfyUI workflow failed: {data}")
                if event_type == "executing" and data.get("prompt_id") == prompt_id and data.get("node") is None:
                    entry = self._history_entry_if_ready(prompt_id)
                    if entry is not None:
                        return entry
            except TimeoutError:
                pass

            now = time.monotonic()
            if now - last_history_check >= 2.0:
                entry = self._history_entry_if_ready(prompt_id)
                if entry is not None:
                    return entry
                last_history_check = now

        raise TimeoutError(f"Timed out waiting for ComfyUI websocket completion for prompt {prompt_id}.")

    def _history_entry_if_ready(self, prompt_id: str) -> dict[str, Any] | None:
        payload = self._get_json(f"/history/{prompt_id}", timeout=15)
        if not isinstance(payload, dict):
            return None
        entry = payload.get(prompt_id)
        if not isinstance(entry, dict):
            return None
        if entry.get("status", {}).get("status_str") == "error":
            raise RuntimeError(f"ComfyUI workflow failed: {entry.get('status')}")
        return entry if self._history_has_image(entry) else None

    def _open_progress_socket(self, client_id: str, progress_callback: ComfyUIProgressCallback | None) -> Any | None:
        if connect_websocket is None:
            self._emit_progress(progress_callback, {"type": "comfyui.websocket_unavailable", "message": "websockets package is not installed."})
            return None
        parsed = urlparse(self.endpoint)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        path = f"{parsed.path.rstrip('/')}/ws" if parsed.path else "/ws"
        url = urlunparse((scheme, parsed.netloc, path, "", f"clientId={client_id}", ""))
        try:
            websocket = connect_websocket(url, open_timeout=5, close_timeout=1)
            self._emit_progress(progress_callback, {"type": "comfyui.websocket_connected", "client_id": client_id})
            return websocket
        except Exception as exc:
            self._emit_progress(progress_callback, {"type": "comfyui.websocket_unavailable", "message": str(exc)})
            return None

    def _parse_websocket_event(self, raw: Any) -> dict[str, Any]:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                return {"type": "comfyui.websocket_message", "raw": raw}
            return parsed if isinstance(parsed, dict) else {"type": "comfyui.websocket_message", "raw": parsed}
        return {"type": "comfyui.websocket_message", "raw": repr(raw)}

    def _handle_websocket_event(self, prompt_id: str, event: dict[str, Any], progress_callback: ComfyUIProgressCallback | None) -> None:
        event_type = str(event.get("type") or "")
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        payload: dict[str, Any] = {"type": f"comfyui.{event_type or 'event'}", "prompt_id": data.get("prompt_id") or prompt_id}
        if event_type == "progress":
            value = data.get("value")
            maximum = data.get("max")
            payload.update({"value": value, "max": maximum, "node": data.get("node")})
            try:
                payload["fraction"] = max(0.0, min(1.0, float(value) / float(maximum))) if maximum else None
            except (TypeError, ValueError, ZeroDivisionError):
                payload["fraction"] = None
        elif event_type in {"executing", "executed"}:
            payload.update({"node": data.get("node")})
        elif event_type in {"execution_error", "execution_interrupted"}:
            payload.update({"message": data})
        else:
            payload.update({"data": data})
        self._emit_progress(progress_callback, payload)

    def _emit_progress(self, progress_callback: ComfyUIProgressCallback | None, event: dict[str, Any]) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(event)
        except Exception:
            pass

    def _history_has_image(self, entry: dict[str, Any]) -> bool:
        try:
            self._first_image_output(entry)
            return True
        except RuntimeError:
            return False

    def _first_image_output(self, entry: dict[str, Any]) -> dict[str, Any]:
        outputs = entry.get("outputs") or {}
        if not isinstance(outputs, dict):
            raise RuntimeError("ComfyUI history response did not contain outputs.")
        for node_output in outputs.values():
            if not isinstance(node_output, dict):
                continue
            for image in node_output.get("images") or []:
                if isinstance(image, dict) and image.get("filename"):
                    return image
        raise RuntimeError("ComfyUI completed the workflow but did not return an image output.")

    def _get_json(self, path: str, *, timeout: int) -> Any:
        response = self.session.get(f"{self.endpoint}{path}", timeout=timeout)
        response.raise_for_status()
        return response.json()

    def _post_json(self, path: str, payload: dict[str, Any], *, timeout: int) -> dict[str, Any]:
        response = self.session.post(f"{self.endpoint}{path}", json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError(f"Unexpected ComfyUI response for {path}: {data!r}")
        return data
