from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse, urlunparse

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
import requests

from app.studio_features import load_settings
from app.v2.workspaces import active_workspace_id


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class CopilotContextRequest(BaseModel):
    route: str = Field(default="/", max_length=240)
    module: str = Field(default="", max_length=80)
    selection: dict[str, Any] = Field(default_factory=dict)


class CopilotChatRequest(CopilotContextRequest):
    message: str = Field(min_length=1, max_length=8000)
    history: list[dict[str, str]] = Field(default_factory=list)


class CopilotChatResponse(BaseModel):
    ok: bool
    content: str
    mode: Literal["llm", "fallback"]
    model: str = ""
    endpoint: str = ""
    context: dict[str, Any]
    generated_at: str


router = APIRouter(prefix="/copilot", tags=["v2-copilot"])


def _normalize_openai_base_url(endpoint: str) -> str:
    parsed = urlparse((endpoint or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("LLM endpoint must be an http(s) URL.")
    hostname = (parsed.hostname or "").lower()
    netloc = parsed.netloc
    if Path("/.dockerenv").exists() and hostname in {"127.0.0.1", "localhost"}:
        netloc = parsed.netloc.replace(parsed.hostname or hostname, "host.docker.internal", 1)
    return urlunparse((parsed.scheme, netloc, parsed.path.rstrip("/"), "", "", "")).rstrip("/")


def _chat_endpoint(endpoint: str) -> str:
    base = _normalize_openai_base_url(endpoint)
    return base if base.endswith("/chat/completions") else f"{base}/chat/completions"


def _extract_chat_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message") if isinstance(first, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content.strip()
    text = first.get("text") if isinstance(first, dict) else None
    return str(text).strip() if text else ""


def _copilot_timeout_s(settings: dict[str, Any]) -> int:
    raw = os.getenv("STUDIO_COPILOT_TIMEOUT_S") or settings.get("copilot_timeout_s") or 8
    try:
        timeout = int(raw)
    except (TypeError, ValueError):
        timeout = 8
    return max(1, min(timeout, 30))


def _module_from_route(route: str) -> str:
    cleaned = (route or "/").strip() or "/"
    first = cleaned.strip("/").split("/", 1)[0]
    return first or "dashboard"


def build_context(payload: CopilotContextRequest, request: Request | None = None) -> dict[str, Any]:
    data_root = getattr(request.app.state, "data_root", None) if request is not None else None
    route = payload.route or "/"
    module = payload.module or _module_from_route(route)
    settings = load_settings()
    image = settings.get("image", {})
    llm = settings.get("llm", {})
    return {
        "route": route,
        "module": module,
        "workspace_id": active_workspace_id(Path(data_root) if data_root else None),
        "selection": payload.selection,
        "integrations": {
            "image_provider": image.get("provider"),
            "image_workflow": image.get("workflow"),
            "image_model": image.get("model"),
            "llm_provider": llm.get("provider"),
            "llm_model": llm.get("model"),
        },
    }


def _fallback_reply(message: str, context: dict[str, Any]) -> str:
    module = context.get("module") or "studio"
    workspace_id = context.get("workspace_id") or "default"
    if module == "training":
        return (
            f"Workspace `{workspace_id}` training context is active. "
            "For Phase 2, check the selected model family, caption style, dataset coverage, and the command preview before queueing a run. "
            f"Request noted: {message.strip()}"
        )
    if module == "generation":
        return (
            f"Workspace `{workspace_id}` generation context is active. "
            "Try a ComfyUI workflow preset, preview wildcard expansion, then queue the job so SSE can report node progress. "
            f"Request noted: {message.strip()}"
        )
    if module == "wildcards":
        return (
            f"Workspace `{workspace_id}` wildcard context is active. "
            "I can help reshape tokens into reusable prompt families, spot missing refs, or turn a strong result into a workflow preset. "
            f"Request noted: {message.strip()}"
        )
    if module == "movie":
        return (
            f"Workspace `{workspace_id}` movie context is active. "
            "Use scene beats, character anchors, and Wan prompts as structured context for image or video workflows. "
            f"Request noted: {message.strip()}"
        )
    return f"Workspace `{workspace_id}` is active. Tell me what to inspect or improve and I will use the current route context. Request noted: {message.strip()}"


@router.post("/context")
def get_copilot_context(payload: CopilotContextRequest, request: Request) -> dict[str, Any]:
    return {"context": build_context(payload, request), "generated_at": utc_now_iso()}


@router.post("/chat", response_model=CopilotChatResponse)
def chat_with_copilot(payload: CopilotChatRequest, request: Request) -> CopilotChatResponse:
    context = build_context(payload, request)
    settings = load_settings().get("llm", {})
    endpoint = str(settings.get("endpoint") or "").strip()
    model = str(settings.get("model") or "koboldcpp").strip()
    if endpoint:
        try:
            headers: dict[str, str] = {}
            if settings.get("api_key"):
                headers["Authorization"] = f"Bearer {settings['api_key']}"
            system = (
                "You are the Mklan Studio Copilot. Be concise, practical, and context-aware. "
                "Use the supplied route, module, workspace, current selection, and configured integrations. "
                "Prefer concrete next actions over generic advice."
            )
            messages = [{"role": "system", "content": system}]
            for item in payload.history[-8:]:
                role = item.get("role") if item.get("role") in {"user", "assistant"} else "user"
                content = str(item.get("content") or "").strip()
                if content:
                    messages.append({"role": role, "content": content})
            messages.append(
                {
                    "role": "user",
                    "content": f"Context:\n{context}\n\nUser request:\n{payload.message.strip()}",
                }
            )
            response = requests.post(
                _chat_endpoint(endpoint),
                headers=headers,
                json={"model": model, "messages": messages, "temperature": 0.35, "max_tokens": 700},
                timeout=_copilot_timeout_s(settings),
            )
            response.raise_for_status()
            content = _extract_chat_text(response.json())
            if content:
                return CopilotChatResponse(
                    ok=True,
                    content=content,
                    mode="llm",
                    model=model,
                    endpoint=endpoint,
                    context=context,
                    generated_at=utc_now_iso(),
                )
        except Exception:
            pass
    return CopilotChatResponse(
        ok=True,
        content=_fallback_reply(payload.message, context),
        mode="fallback",
        model=model,
        endpoint=endpoint,
        context=context,
        generated_at=utc_now_iso(),
    )
