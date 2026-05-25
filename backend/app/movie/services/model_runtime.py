from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
import tempfile
import time
from typing import Any
from urllib.parse import urlparse, urlunparse

import requests

from ..config import Settings

OPENAI_COMPATIBLE_PROVIDERS = {"openai", "openai_compatible", "openai-compatible"}
KOBOLDCPP_PROVIDERS = {"koboldcpp"}


class LocalModelRuntime:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def test_connection(self, runtime_config: dict) -> dict:
        started_at = time.perf_counter()
        config = self._normalize_runtime_config(runtime_config)
        capabilities = self._default_capabilities()
        vision_message = self._vision_skip_message(
            config,
            "Vision probing starts after the configured model is reachable for text generation.",
        )
        try:
            if config["provider"] == "ollama":
                available_models, resolved_base_url = self._fetch_ollama_models(config)
                resolved_model = config["model"]
            elif config["provider"] in OPENAI_COMPATIBLE_PROVIDERS:
                available_models, resolved_base_url = self._fetch_openai_compatible_models(config)
                resolved_model = config["model"]
            elif config["provider"] in KOBOLDCPP_PROVIDERS:
                available_models, resolved_base_url, resolved_model = self._fetch_koboldcpp_models(config)
            else:
                return self._connection_result(
                    config=config,
                    ok=False,
                    ready=False,
                    status="error",
                    message=f"Unsupported provider: {config['provider']}",
                    available_models=[],
                    resolved_base_url=config["base_url"],
                    resolved_model=config["model"],
                    started_at=started_at,
                    capabilities=capabilities,
                    vision_message=vision_message,
                )
        except Exception as exc:
            return self._connection_result(
                config=config,
                ok=False,
                ready=False,
                status="error",
                message=f"Connection test failed: {exc}",
                available_models=[],
                resolved_base_url=self._preferred_runtime_base_url(config),
                resolved_model=config["model"],
                started_at=started_at,
                capabilities=capabilities,
                vision_message=self._vision_skip_message(
                    config,
                    "Vision probing was skipped because the runtime connection test failed.",
                ),
            )

        if config["provider"] in KOBOLDCPP_PROVIDERS:
            if resolved_model:
                capabilities, vision_message = self._probe_runtime_capabilities(config, resolved_model)
                return self._connection_result(
                    config=config,
                    ok=True,
                    ready=True,
                    status="ready",
                    message=self._connection_message(
                        f"KoboldCpp is reachable and reports the active model `{resolved_model}`.",
                        configured_base_url=config["base_url"],
                        resolved_base_url=resolved_base_url,
                    ),
                    available_models=available_models,
                    resolved_base_url=resolved_base_url,
                    resolved_model=resolved_model,
                    started_at=started_at,
                    capabilities=capabilities,
                    vision_message=vision_message,
                )
            return self._connection_result(
                config=config,
                ok=True,
                ready=False,
                status="reachable",
                message=self._connection_message(
                    "KoboldCpp is reachable, but it did not report an active loaded model yet.",
                    configured_base_url=config["base_url"],
                    resolved_base_url=resolved_base_url,
                ),
                available_models=available_models,
                resolved_base_url=resolved_base_url,
                resolved_model=config["model"],
                started_at=started_at,
                capabilities=capabilities,
                vision_message=self._vision_skip_message(
                    config,
                    "KoboldCpp is reachable, but vision cannot be probed until an active model is loaded.",
                ),
            )

        model_available = resolved_model in available_models if available_models else False
        if model_available:
            capabilities, vision_message = self._probe_runtime_capabilities(config, resolved_model)
            return self._connection_result(
                config=config,
                ok=True,
                ready=True,
                status="ready",
                message=self._connection_message(
                    "Connection succeeded and the configured model is available.",
                    configured_base_url=config["base_url"],
                    resolved_base_url=resolved_base_url,
                ),
                available_models=available_models,
                resolved_base_url=resolved_base_url,
                resolved_model=resolved_model,
                started_at=started_at,
                capabilities=capabilities,
                vision_message=vision_message,
            )
        if available_models:
            return self._connection_result(
                config=config,
                ok=True,
                ready=False,
                status="reachable_model_missing",
                message=self._connection_message(
                    "Connection succeeded, but the configured model was not found on the runtime.",
                    configured_base_url=config["base_url"],
                    resolved_base_url=resolved_base_url,
                ),
                available_models=available_models,
                resolved_base_url=resolved_base_url,
                resolved_model=resolved_model,
                started_at=started_at,
                capabilities=capabilities,
                vision_message=vision_message,
            )
        return self._connection_result(
            config=config,
            ok=True,
            ready=False,
            status="reachable",
            message=self._connection_message(
                "Connection succeeded, but the runtime did not report any available models.",
                configured_base_url=config["base_url"],
                resolved_base_url=resolved_base_url,
            ),
            available_models=[],
            resolved_base_url=resolved_base_url,
            resolved_model=resolved_model,
            started_at=started_at,
            capabilities=capabilities,
            vision_message=vision_message,
        )

    def run_text(self, *, system_prompt: str, user_prompt: str, runtime_config: dict, parameters: dict) -> str | None:
        config = self._normalize_runtime_config(runtime_config)
        provider = config["provider"]
        if provider == "ollama":
            return self._run_ollama(system_prompt, user_prompt, config, parameters)
        if provider in OPENAI_COMPATIBLE_PROVIDERS:
            return self._run_openai_compatible(system_prompt, user_prompt, config, parameters, config["model"])
        if provider in KOBOLDCPP_PROVIDERS:
            model_name = self._resolve_koboldcpp_model(config)
            return self._run_openai_compatible(system_prompt, user_prompt, config, parameters, model_name)
        return None

    def run_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        runtime_config: dict,
        parameters: dict,
    ) -> object | None:
        retries = max(1, int(parameters.get("json_retries", 1)))
        for attempt in range(retries):
            attempt_parameters = dict(parameters)
            max_output_tokens = attempt_parameters.get("max_output_tokens")
            if attempt > 0 and max_output_tokens not in {None, ""}:
                attempt_parameters["max_output_tokens"] = min(8192, int(max_output_tokens) * (2 ** attempt))
            content = self.run_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                runtime_config=runtime_config,
                parameters=attempt_parameters,
            )
            parsed = self._parse_json_content(
                content or "",
                strip_markdown_fences=bool(attempt_parameters.get("strip_markdown_fences", True)),
            )
            if parsed is not None:
                return parsed
        return None

    def supports_vision(self, runtime_config: dict) -> bool:
        config = self._normalize_runtime_config(runtime_config)
        return config["provider"] == "ollama" or config["provider"] in OPENAI_COMPATIBLE_PROVIDERS or config["provider"] in KOBOLDCPP_PROVIDERS

    def run_vision_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        image_paths: list[Path],
        runtime_config: dict,
        parameters: dict,
    ) -> object | None:
        config = self._normalize_runtime_config(runtime_config)
        if config["provider"] == "ollama":
            content = self._run_ollama_vision(system_prompt, user_prompt, image_paths, config, parameters)
        elif config["provider"] in OPENAI_COMPATIBLE_PROVIDERS:
            content = self._run_openai_compatible_vision(
                system_prompt,
                user_prompt,
                image_paths,
                config,
                parameters,
                config["model"],
            )
        elif config["provider"] in KOBOLDCPP_PROVIDERS:
            content = self._run_openai_compatible_vision(
                system_prompt,
                user_prompt,
                image_paths,
                config,
                parameters,
                self._resolve_koboldcpp_model(config),
            )
        else:
            return None
        return self._parse_json_content(
            content or "",
            strip_markdown_fences=bool(parameters.get("strip_markdown_fences", True)),
        )

    def _run_ollama(self, system_prompt: str, user_prompt: str, runtime_config: dict, parameters: dict) -> str | None:
        payload = {
            "model": runtime_config["model"],
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False,
            "options": {
                "temperature": parameters.get("temperature"),
                "top_p": parameters.get("top_p"),
                "top_k": parameters.get("top_k"),
                "min_p": parameters.get("min_p"),
                "repeat_penalty": parameters.get("repeat_penalty"),
                "num_predict": parameters.get("max_output_tokens"),
                "seed": parameters.get("seed"),
                "stop": parameters.get("stop_sequences"),
            },
        }
        response, _resolved_base_url = self._request_from_candidates(
            "POST",
            self._base_url_candidates(runtime_config["base_url"]),
            "/api/generate",
            json_body=payload,
            timeout_s=runtime_config["timeout_s"],
        )
        response.raise_for_status()
        content = str(response.json().get("response", "")).strip()
        return content or None

    def _run_ollama_vision(
        self,
        system_prompt: str,
        user_prompt: str,
        image_paths: list[Path],
        runtime_config: dict,
        parameters: dict,
    ) -> str | None:
        payload = {
            "model": runtime_config["model"],
            "stream": False,
            "options": {
                "temperature": parameters.get("temperature"),
                "top_p": parameters.get("top_p"),
                "top_k": parameters.get("top_k"),
                "min_p": parameters.get("min_p"),
                "repeat_penalty": parameters.get("repeat_penalty"),
                "num_predict": parameters.get("max_output_tokens"),
                "seed": parameters.get("seed"),
                "stop": parameters.get("stop_sequences"),
            },
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt or "Respond to the user prompt directly.",
                },
                {
                    "role": "user",
                    "content": user_prompt,
                    "images": [self._encode_image_base64(path) for path in image_paths],
                },
            ],
        }
        response, _resolved_base_url = self._request_from_candidates(
            "POST",
            self._base_url_candidates(runtime_config["base_url"]),
            "/api/chat",
            json_body=payload,
            timeout_s=runtime_config["timeout_s"],
        )
        response.raise_for_status()
        message = response.json().get("message", {})
        content = str(message.get("content", "")).strip()
        return content or None

    def _run_openai_compatible(
        self,
        system_prompt: str,
        user_prompt: str,
        runtime_config: dict,
        parameters: dict,
        model_name: str,
    ) -> str | None:
        payload: dict[str, Any] = {
            "model": model_name,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt or "Respond to the user prompt directly.",
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            "temperature": parameters.get("temperature"),
            "top_p": parameters.get("top_p"),
            "max_tokens": parameters.get("max_output_tokens"),
        }
        if parameters.get("seed") is not None:
            payload["seed"] = parameters["seed"]
        if parameters.get("stop_sequences"):
            payload["stop"] = parameters["stop_sequences"]

        response, _resolved_base_url = self._request_from_candidates(
            "POST",
            self._openai_base_url_candidates(runtime_config),
            "/chat/completions",
            headers=self._openai_headers(runtime_config),
            json_body=payload,
            timeout_s=runtime_config["timeout_s"],
        )
        response.raise_for_status()
        payload = response.json()
        choices = payload.get("choices", [])
        if not choices:
            return None
        message = choices[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, list):
            content = "".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict)
            )
        normalized = str(content).strip()
        return normalized or None

    def _run_openai_compatible_vision(
        self,
        system_prompt: str,
        user_prompt: str,
        image_paths: list[Path],
        runtime_config: dict,
        parameters: dict,
        model_name: str | None = None,
    ) -> str | None:
        user_content: list[dict[str, Any]] = [{"type": "text", "text": user_prompt}]
        for path in image_paths:
            user_content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": self._image_data_url(path)},
                }
            )
        payload: dict[str, Any] = {
            "model": model_name or runtime_config["model"],
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt or "Respond to the user prompt directly.",
                },
                {
                    "role": "user",
                    "content": user_content,
                },
            ],
            "temperature": parameters.get("temperature"),
            "top_p": parameters.get("top_p"),
            "max_tokens": parameters.get("max_output_tokens"),
        }
        if parameters.get("seed") is not None:
            payload["seed"] = parameters["seed"]
        if parameters.get("stop_sequences"):
            payload["stop"] = parameters["stop_sequences"]

        response, _resolved_base_url = self._request_from_candidates(
            "POST",
            self._openai_base_url_candidates(runtime_config),
            "/chat/completions",
            headers=self._openai_headers(runtime_config),
            json_body=payload,
            timeout_s=runtime_config["timeout_s"],
        )
        response.raise_for_status()
        payload = response.json()
        choices = payload.get("choices", [])
        if not choices:
            return None
        message = choices[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, list):
            content = "".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict)
            )
        normalized = str(content).strip()
        return normalized or None

    def _parse_json_content(self, content: str, *, strip_markdown_fences: bool) -> object | None:
        normalized = content.strip()
        if not normalized:
            return None
        if strip_markdown_fences and normalized.startswith("```"):
            normalized = normalized.strip("`")
            if normalized.startswith("json\n"):
                normalized = normalized.replace("json\n", "", 1)
            normalized = normalized.strip()
        try:
            return json.loads(normalized)
        except Exception:
            candidate = self._extract_json_candidate(normalized)
            if candidate is None:
                return None
            try:
                return json.loads(candidate)
            except Exception:
                return None

    def _extract_json_candidate(self, content: str) -> str | None:
        start_index = None
        opening = ""
        for index, char in enumerate(content):
            if char in "{[":
                start_index = index
                opening = char
                break
        if start_index is None:
            return None

        closing = "}" if opening == "{" else "]"
        depth = 0
        in_string = False
        escape = False
        for index in range(start_index, len(content)):
            char = content[index]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == "\"":
                    in_string = False
                continue

            if char == "\"":
                in_string = True
            elif char == opening:
                depth += 1
            elif char == closing:
                depth -= 1
                if depth == 0:
                    return content[start_index : index + 1]
        return None

    def _fetch_ollama_models(self, runtime_config: dict) -> tuple[list[str], str]:
        response, resolved_base_url = self._request_from_candidates(
            "GET",
            self._base_url_candidates(runtime_config["base_url"]),
            "/api/tags",
            timeout_s=runtime_config["timeout_s"],
        )
        response.raise_for_status()
        payload = response.json()
        models = payload.get("models", [])
        return (
            sorted(
                {
                    str(model.get("name", "")).strip()
                    for model in models
                    if isinstance(model, dict) and str(model.get("name", "")).strip()
                }
            ),
            resolved_base_url,
        )

    def _fetch_openai_compatible_models(self, runtime_config: dict) -> tuple[list[str], str]:
        response, resolved_base_url = self._request_from_candidates(
            "GET",
            self._openai_base_url_candidates(runtime_config),
            "/models",
            headers=self._openai_headers(runtime_config),
            timeout_s=runtime_config["timeout_s"],
        )
        if response.status_code in {404, 405, 501}:
            return [], resolved_base_url
        response.raise_for_status()
        payload = response.json()
        models = payload.get("data", [])
        return (
            sorted(
                {
                    str(model.get("id", "")).strip()
                    for model in models
                    if isinstance(model, dict) and str(model.get("id", "")).strip()
                }
            ),
            resolved_base_url,
        )

    def _fetch_koboldcpp_models(self, runtime_config: dict) -> tuple[list[str], str, str]:
        openai_models, resolved_base_url = self._fetch_openai_compatible_models(runtime_config)
        active_model = self._fetch_koboldcpp_active_model(runtime_config)
        if active_model and active_model not in openai_models:
            openai_models = sorted([*openai_models, active_model])
        return openai_models, resolved_base_url, active_model or ""

    def _resolve_koboldcpp_model(self, runtime_config: dict) -> str:
        try:
            return self._fetch_koboldcpp_active_model(runtime_config) or runtime_config["model"]
        except Exception:
            return runtime_config["model"]

    def _fetch_koboldcpp_active_model(self, runtime_config: dict) -> str | None:
        response, _resolved_base_url = self._request_from_candidates(
            "GET",
            self._koboldcpp_root_base_url_candidates(runtime_config),
            "/api/v1/model",
            timeout_s=runtime_config["timeout_s"],
        )
        if response.status_code in {404, 405, 501}:
            return None
        response.raise_for_status()
        payload = response.json()
        return self._extract_koboldcpp_model_name(payload)

    def _extract_koboldcpp_model_name(self, payload: Any) -> str | None:
        if isinstance(payload, str):
            return payload.strip() or None
        if isinstance(payload, dict):
            for key in ("result", "model_name", "name", "value", "model"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return None

    def _request_from_candidates(
        self,
        method: str,
        base_urls: list[str],
        path: str,
        *,
        headers: dict[str, str] | None = None,
        json_body: dict | None = None,
        timeout_s: int,
    ) -> tuple[requests.Response, str]:
        last_error: Exception | None = None
        for base_url in base_urls:
            request_url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
            try:
                response = requests.request(
                    method,
                    request_url,
                    headers=headers,
                    json=json_body,
                    timeout=timeout_s,
                )
                return response, base_url
            except requests.RequestException as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise RuntimeError("No runtime URL candidates were available.")

    def _openai_headers(self, runtime_config: dict) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if runtime_config["api_key"]:
            headers["Authorization"] = f"Bearer {runtime_config['api_key']}"
        return headers

    def _openai_base_url_candidates(self, runtime_config: dict) -> list[str]:
        return self._base_url_candidates(self._normalized_openai_base_url(runtime_config))

    def _koboldcpp_root_base_url_candidates(self, runtime_config: dict) -> list[str]:
        return self._base_url_candidates(self._normalized_koboldcpp_root_url(runtime_config))

    def _base_url_candidates(self, base_url: str) -> list[str]:
        normalized = str(base_url).strip().rstrip("/")
        if not normalized:
            return []
        translated = self._translate_localhost_for_container(normalized)
        if translated != normalized:
            return [translated]
        return [normalized]

    def _normalized_openai_base_url(self, runtime_config: dict) -> str:
        base_url = str(runtime_config["base_url"]).strip().rstrip("/")
        provider = str(runtime_config["provider"]).strip().lower()
        if provider in KOBOLDCPP_PROVIDERS:
            parsed = urlparse(base_url)
            current_path = parsed.path.rstrip("/")
            if not current_path.endswith("/v1"):
                next_path = f"{current_path}/v1" if current_path else "/v1"
                base_url = urlunparse(parsed._replace(path=next_path))
        return base_url.rstrip("/")

    def _normalized_koboldcpp_root_url(self, runtime_config: dict) -> str:
        parsed = urlparse(self._normalized_openai_base_url(runtime_config))
        base_path = parsed.path.rstrip("/")
        if base_path.endswith("/v1"):
            base_path = base_path[:-3]
        return urlunparse(parsed._replace(path=base_path.rstrip("/"), params="", query="", fragment="")).rstrip("/")

    def _translate_localhost_for_container(self, base_url: str) -> str:
        if not self._is_running_in_container():
            return base_url
        parsed = urlparse(base_url)
        if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            return base_url
        auth_prefix = ""
        if parsed.username:
            auth_prefix = parsed.username
            if parsed.password:
                auth_prefix = f"{auth_prefix}:{parsed.password}"
            auth_prefix = f"{auth_prefix}@"
        port_suffix = f":{parsed.port}" if parsed.port else ""
        return urlunparse(parsed._replace(netloc=f"{auth_prefix}host.docker.internal{port_suffix}"))

    def _is_running_in_container(self) -> bool:
        runtime_flag = os.getenv("MOVIE_TOOL_DOCKERIZED")
        if runtime_flag is not None:
            return runtime_flag.strip().lower() in {"1", "true", "yes", "on"}
        return Path("/.dockerenv").exists()

    def _preferred_runtime_base_url(self, runtime_config: dict) -> str:
        provider = str(runtime_config["provider"]).strip().lower()
        if provider == "ollama":
            candidates = self._base_url_candidates(runtime_config["base_url"])
        else:
            candidates = self._openai_base_url_candidates(runtime_config)
        return candidates[0] if candidates else runtime_config["base_url"]

    def _connection_message(self, message: str, *, configured_base_url: str, resolved_base_url: str) -> str:
        if configured_base_url == resolved_base_url:
            return message
        return (
            f"{message} The Dockerized backend reached the runtime via `{resolved_base_url}` "
            f"instead of `{configured_base_url}`."
        )

    def _connection_result(
        self,
        *,
        config: dict,
        ok: bool,
        ready: bool,
        status: str,
        message: str,
        available_models: list[str],
        resolved_base_url: str,
        resolved_model: str,
        started_at: float,
        capabilities: dict[str, bool] | None = None,
        vision_message: str | None = None,
    ) -> dict:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        return {
            "ok": ok,
            "ready": ready,
            "status": status,
            "message": message,
            "provider": config["provider"],
            "base_url": config["base_url"],
            "resolved_base_url": resolved_base_url,
            "model": resolved_model,
            "available_models": available_models,
            "response_ms": elapsed_ms,
            "capabilities": capabilities or self._default_capabilities(),
            "vision_message": vision_message,
        }

    def _default_capabilities(self) -> dict[str, bool]:
        return {"text": False, "json": False, "vision": False}

    def _probe_runtime_capabilities(self, runtime_config: dict, model_name: str) -> tuple[dict[str, bool], str]:
        capabilities = {"text": True, "json": True, "vision": False}
        vision_ready, vision_message = self._probe_vision_capability(runtime_config, model_name)
        capabilities["vision"] = vision_ready
        return capabilities, vision_message

    def _probe_vision_capability(self, runtime_config: dict, model_name: str) -> tuple[bool, str]:
        config = self._normalize_runtime_config({**runtime_config, "model": model_name})
        if not self.supports_vision(config):
            return False, self._vision_skip_message(
                config,
                "The configured runtime does not expose a multimodal endpoint for continuity review.",
            )
        with tempfile.TemporaryDirectory(prefix="movie-scripting-vision-probe-") as temp_dir_name:
            probe_image_path = self._create_vision_probe_image(Path(temp_dir_name))
            parameters = {
                "temperature": 0.0,
                "top_p": 0.1,
                "max_output_tokens": 320,
                "json_retries": 1,
                "strip_markdown_fences": True,
                "stop_sequences": [],
            }
            try:
                if config["provider"] == "ollama":
                    content = self._run_ollama_vision(
                        "You are running a multimodal calibration check. Reply with JSON only.",
                        (
                            "Inspect the attached calibration image and reply with JSON only. "
                            "Use keys vision_ready, background_color, square_color, and explanation. "
                            "Set vision_ready to true only if you can actually inspect the image."
                        ),
                        [probe_image_path],
                        config,
                        parameters,
                    )
                else:
                    content = self._run_openai_compatible_vision(
                        "You are running a multimodal calibration check. Reply with JSON only.",
                        (
                            "Inspect the attached calibration image and reply with JSON only. "
                            "Use keys vision_ready, background_color, square_color, and explanation. "
                            "Set vision_ready to true only if you can actually inspect the image."
                        ),
                        [probe_image_path],
                        config,
                        parameters,
                        model_name,
                    )
            except Exception as exc:
                return False, self._vision_failure_message(config, str(exc))

        parsed = self._parse_json_content(content or "", strip_markdown_fences=True)
        if not isinstance(parsed, dict):
            if self._looks_like_successful_vision_probe_text(content or ""):
                return True, self._vision_success_message(config, natural_language_only=True)
            return False, self._vision_failure_message(
                config,
                "The runtime returned a non-JSON multimodal response to the calibration probe.",
            )

        background_color = str(parsed.get("background_color", "")).strip().lower()
        square_color = str(parsed.get("square_color", "")).strip().lower()
        vision_ready = bool(parsed.get("vision_ready"))
        if vision_ready and self._color_matches(background_color, ("magenta", "pink", "purple")) and self._color_matches(
            square_color,
            ("yellow", "gold"),
        ):
            return True, self._vision_success_message(config)

        explanation = str(parsed.get("explanation", "")).strip()
        if not explanation:
            explanation = (
                "The calibration probe did not confirm the expected magenta background and yellow square, "
                "so continuity review will stay on rules-only fallback."
            )
        return False, self._vision_failure_message(config, explanation)

    def _create_vision_probe_image(self, temp_dir: Path) -> Path:
        from PIL import Image, ImageDraw

        image_path = temp_dir / "vision-probe.png"
        image = Image.new("RGB", (128, 128), color=(255, 0, 170))
        draw = ImageDraw.Draw(image)
        draw.rectangle((36, 36, 92, 92), fill=(255, 220, 0))
        image.save(image_path, format="PNG")
        return image_path

    def _color_matches(self, value: str, expected_tokens: tuple[str, ...]) -> bool:
        normalized = value.lower()
        return any(token in normalized for token in expected_tokens)

    def _looks_like_successful_vision_probe_text(self, content: str) -> bool:
        normalized = " ".join(content.lower().split())
        background_ok = any(token in normalized for token in ("magenta", "pink", "purple"))
        square_ok = any(token in normalized for token in ("yellow", "gold"))
        structure_ok = "background" in normalized and "square" in normalized
        vision_claim_ok = any(
            token in normalized
            for token in (
                "i can clearly see",
                "i can see",
                "i can actually inspect",
                "i can inspect the image",
                "examine the image",
                "attached calibration image",
                "analyze the image",
            )
        )
        return background_ok and square_ok and structure_ok and vision_claim_ok

    def _vision_success_message(self, runtime_config: dict, *, natural_language_only: bool = False) -> str:
        suffix = ""
        if natural_language_only:
            suffix = (
                " The model described the calibration image correctly in natural language, but it did not stay in "
                "strict JSON. Multimodal transport is working, though some structured review tasks may still fall "
                "back to rules-only if the model ignores the JSON contract."
            )
        if runtime_config["provider"] in KOBOLDCPP_PROVIDERS:
            return (
                "Vision probe succeeded. KoboldCpp accepted a multimodal chat request and recognized the calibration "
                f"image, so continuity review can use local vision.{suffix}"
            )
        return (
            "Vision probe succeeded. The configured runtime recognized the calibration image, so continuity review can "
            f"use local vision.{suffix}"
        )

    def _vision_failure_message(self, runtime_config: dict, detail: str) -> str:
        detail_text = detail.strip()
        if runtime_config["provider"] in KOBOLDCPP_PROVIDERS:
            prefix = (
                "Vision probe did not succeed. KoboldCpp text chat is reachable, but multimodal review needs a "
                "matching `--mmproj` projector loaded for the active GGUF model."
            )
        else:
            prefix = (
                "Vision probe did not succeed. Continuity review will fall back to the explicit rules-only pass until "
                "a vision-capable model/runtime is configured."
            )
        return f"{prefix} {detail_text}".strip()

    def _vision_skip_message(self, runtime_config: dict, detail: str) -> str:
        if runtime_config["provider"] in KOBOLDCPP_PROVIDERS:
            return (
                f"{detail.strip()} When you enable KoboldCpp vision, load a matching `--mmproj` projector next to the "
                "active GGUF model."
            ).strip()
        return detail.strip()

    def _image_data_url(self, image_path: Path) -> str:
        mime_type = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
        encoded = self._encode_image_base64(image_path)
        return f"data:{mime_type};base64,{encoded}"

    def _encode_image_base64(self, image_path: Path) -> str:
        return base64.b64encode(image_path.read_bytes()).decode("ascii")

    def _normalize_runtime_config(self, runtime_config: dict) -> dict:
        provider = str(runtime_config.get("provider", self.settings.scenario_assistant_provider)).strip().lower()
        if provider in {"openai", "openai-compatible"}:
            provider = "openai_compatible"
        return {
            "provider": provider,
            "base_url": runtime_config.get("base_url", self.settings.scenario_assistant_base_url),
            "model": runtime_config.get("model", self.settings.scenario_assistant_model),
            "api_key": runtime_config.get("api_key", self.settings.scenario_assistant_api_key or ""),
            "timeout_s": int(runtime_config.get("timeout_s", self.settings.scenario_assistant_timeout_s)),
        }
