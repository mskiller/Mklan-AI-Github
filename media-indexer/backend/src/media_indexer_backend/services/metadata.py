from __future__ import annotations

import hashlib
import json
import mimetypes
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from media_indexer_backend.models.enums import MatchType, MediaType


SUPPORTED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".webp",
    ".tif",
    ".tiff",
    ".heic",
}
SUPPORTED_VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".m4v",
    ".wmv",
    ".webm",
}
METADATA_SCHEMA_VERSION = 9
_TEXT_INPUT_KEYS = (
    "populated_text",
    "populated",
    "populated_prompt",
    "processed_text",
    "processed_prompt",
    "processed",
    "resolved_text",
    "resolved_prompt",
    "resolved",
    "expanded_text",
    "expanded_prompt",
    "expanded",
    "final_text",
    "final_prompt",
    "final",
    "rendered_text",
    "rendered_prompt",
    "rendered",
    "output_text",
    "output_prompt",
    "prompt_output",
    "text_output",
    "result_text",
    "result_prompt",
    "positive_prompt",
    "negative_prompt",
    "prompt",
    "text",
    "text_1",
    "text_2",
    "text_3",
    "text_4",
    "text_5",
    "text1",
    "text2",
    "text3",
    "text4",
    "text5",
    "wildcard_text",
    "value",
    "strings",
    "posTextA",
    "posTextB",
    "negText",
)
_PROCESSED_TEXT_INPUT_KEYS = (
    "populated_text",
    "populated",
    "populated_prompt",
    "processed_text",
    "processed_prompt",
    "processed",
    "resolved_text",
    "resolved_prompt",
    "resolved",
    "expanded_text",
    "expanded_prompt",
    "expanded",
    "final_text",
    "final_prompt",
    "final",
    "rendered_text",
    "rendered_prompt",
    "rendered",
    "output_text",
    "output_prompt",
    "prompt_output",
    "text_output",
    "result_text",
    "result_prompt",
)
_POSITIVE_TEXT_INPUT_KEYS = (
    *_PROCESSED_TEXT_INPUT_KEYS,
    "positive_prompt",
    "posTextA",
    "posTextB",
    "prompt",
    "text",
)
_NEGATIVE_TEXT_INPUT_KEYS = (
    "negative_prompt",
    "negative_text",
    "negText",
    "neg_prompt",
    "negative",
    "populated_text",
    "processed_text",
    "processed_prompt",
    "resolved_text",
    "resolved_prompt",
    "expanded_text",
    "expanded_prompt",
    "final_text",
    "final_prompt",
    "rendered_text",
    "rendered_prompt",
    "prompt",
    "text",
)
_RAW_WILDCARD_TEXT_KEYS = {
    "wildcard_text",
    "wildcard",
    "raw_text",
    "raw_prompt",
    "template",
    "template_text",
    "unprocessed_text",
    "unprocessed_prompt",
}
_RAW_TEXT_INPUT_KEYS = (
    "wildcard_text",
    "wildcard",
    "raw_text",
    "raw_prompt",
    "template",
    "template_text",
    "unprocessed_text",
    "unprocessed_prompt",
    "prompt",
    "text",
)
_PROMPT_TAG_SPLIT_RE = re.compile(r"[\n,;|]+")
_PROMPT_WEIGHT_RE = re.compile(r"\s*:\s*-?\d+(?:\.\d+)?\s*(?:[\)\]\}>]+)?$")
_LORA_RE = re.compile(r"<lora:([^:>]+)(?::[^>]+)?>", re.IGNORECASE)
_TEXT_KEY_RE = re.compile(r"(?:^|_)(text|prompt|string|caption|label|value)(?:$|_)", re.IGNORECASE)
_NUMERIC_ONLY_RE = re.compile(r"^[\d\s.,:/\\-]+$")
_WILDCARD_MARKER_RE = re.compile(r"__(?P<name>[^_\n\r]{1,200})__|\{[^{}\n\r]{1,240}\|[^{}\n\r]{1,240}\}")
_TEXT_INPUT_KEY_SET = {value.lower() for value in _TEXT_INPUT_KEYS}
_DANBOORU_WHITESPACE_RE = re.compile(r"\s+")
_ATTENTION_WRAPPERS = {"(": ")", "[": "]", "{": "}", "<": ">"}
_ATTENTION_WRAPPER_REVERSE = {value: key for key, value in _ATTENTION_WRAPPERS.items()}


def guess_mime_type(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    return mime or "application/octet-stream"


def detect_media_type(path: Path, mime_type: str) -> MediaType:
    suffix = path.suffix.lower()
    if suffix in SUPPORTED_IMAGE_EXTENSIONS or mime_type.startswith("image/"):
        return MediaType.IMAGE
    if suffix in SUPPORTED_VIDEO_EXTENSIONS or mime_type.startswith("video/"):
        return MediaType.VIDEO
    return MediaType.UNKNOWN


def compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_datetime(value: Any) -> datetime | None:
    if value in (None, "", "0000:00:00 00:00:00"):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if isinstance(value, str):
        candidates = [value.replace("Z", "+00:00"), value]
        if value.count(":") >= 2:
            candidates.append(value.replace(":", "-", 2))
        for candidate in candidates:
            try:
                parsed = datetime.fromisoformat(candidate)
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def parse_float(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_int(value: Any) -> int | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def first_value(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def sanitize_json_value(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, list):
        return [sanitize_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key).replace("\x00", ""): sanitize_json_value(item) for key, item in value.items()}
    return value


def _parse_json_string(value: Any) -> dict[str, Any] | list[Any] | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, (dict, list)):
        return payload
    return None


def _normalize_fragment(value: str) -> str | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    if cleaned.lower() in {"true", "false", "none", "null"}:
        return None
    if _NUMERIC_ONLY_RE.fullmatch(cleaned):
        return None
    return cleaned


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = _normalize_fragment(value)
        if not cleaned:
            continue
        marker = cleaned.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        result.append(cleaned)
    return result


def _stringify_text(value: Any) -> list[str]:
    if value in (None, "") or isinstance(value, bool):
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, (list, tuple, set)):
        parts: list[str] = []
        for item in value:
            parts.extend(_stringify_text(item))
        return parts
    return []


def _meaningful_texts(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        fragment = _normalize_fragment(value)
        if fragment is None:
            continue
        if not any(character.isalpha() for character in fragment):
            continue
        cleaned.append(fragment)
    return _dedupe_strings(cleaned)


def _looks_like_unprocessed_wildcard_text(value: Any) -> bool:
    return any(_WILDCARD_MARKER_RE.search(text) for text in _stringify_text(value))


def _split_selector_strings(value: Any) -> list[str]:
    if not isinstance(value, str):
        return []
    return [line.strip() for line in value.replace("\r\n", "\n").split("\n") if line.strip()]


def _node_class_type(node: dict[str, Any]) -> str:
    return str(node.get("class_type", "")).strip().lower()


def _node_title(node: dict[str, Any]) -> str:
    meta = node.get("_meta")
    if isinstance(meta, dict) and isinstance(meta.get("title"), str):
        return meta["title"].strip().lower()
    title = node.get("title")
    if isinstance(title, str):
        return title.strip().lower()
    return ""


def _node_inputs(node: dict[str, Any]) -> dict[str, Any]:
    inputs = node.get("inputs", {})
    return inputs if isinstance(inputs, dict) else {}


def _looks_like_text_key(key: str) -> bool:
    lowered = key.strip().lower()
    return lowered in _TEXT_INPUT_KEY_SET or bool(_TEXT_KEY_RE.search(lowered))


def _extract_text_like_values(values: dict[str, Any]) -> list[tuple[str, Any]]:
    ordered: list[tuple[str, Any]] = []
    seen_keys: set[str] = set()
    for key in _TEXT_INPUT_KEYS:
        if key in values:
            ordered.append((key, values[key]))
            seen_keys.add(key)
    for key, value in values.items():
        if key in seen_keys:
            continue
        if _looks_like_text_key(key):
            ordered.append((key, value))
    return ordered


def _resolve_first_available_text_keys(
    inputs: dict[str, Any],
    keys: tuple[str, ...],
    prompt_graph: dict[str, dict[str, Any]],
    cache: dict[str, list[str]],
    stack: set[str],
    role: str,
) -> list[str]:
    for key in keys:
        if key not in inputs:
            continue
        resolved = _resolve_comfyui_text_value(inputs[key], prompt_graph, cache, stack, role)
        meaningful = _meaningful_texts(resolved)
        if meaningful:
            return meaningful
    return []


def _resolve_preferred_prompt_inputs(
    inputs: dict[str, Any],
    prompt_graph: dict[str, dict[str, Any]],
    cache: dict[str, list[str]],
    stack: set[str],
    role: str,
) -> list[str]:
    keys = _NEGATIVE_TEXT_INPUT_KEYS if role == "negative" else _POSITIVE_TEXT_INPUT_KEYS
    return _resolve_first_available_text_keys(inputs, keys, prompt_graph, cache, stack, role)


def _resolve_switch_value(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "on", "yes"}:
            return True
        if lowered in {"false", "0", "off", "no"}:
            return False
    return None


def _join_inline_fragments(values: list[str], separator: str = ", ") -> str | None:
    fragments = _meaningful_texts(values)
    if not fragments:
        return None
    return separator.join(fragment for fragment in fragments if fragment)


def _resolve_concat_node(
    inputs: dict[str, Any],
    prompt_graph: dict[str, dict[str, Any]],
    cache: dict[str, list[str]],
    stack: set[str],
    role: str,
) -> list[str]:
    fragments: list[str] = []
    for key, value in _extract_text_like_values(inputs):
        if key.lower().startswith("neg"):
            continue
        if key.lower() == "strings":
            continue
        resolved = _resolve_comfyui_text_value(value, prompt_graph, cache, stack, role)
        if joined := _join_inline_fragments(resolved):
            fragments.append(joined)
    return _meaningful_texts(fragments)


def _resolve_switch_node(
    inputs: dict[str, Any],
    prompt_graph: dict[str, dict[str, Any]],
    cache: dict[str, list[str]],
    stack: set[str],
    role: str,
) -> list[str]:
    switch_value = _resolve_switch_value(inputs.get("switch"))
    preferred_keys = []
    if switch_value is True:
        preferred_keys = ["on_true", "true", "input_true", "text_true"]
    elif switch_value is False:
        preferred_keys = ["on_false", "false", "input_false", "text_false"]
    for key in preferred_keys:
        if key in inputs:
            return _resolve_comfyui_text_value(inputs[key], prompt_graph, cache, stack, role)
    for key in ("on_true", "on_false", "true", "false"):
        if key in inputs:
            fragments = _resolve_comfyui_text_value(inputs[key], prompt_graph, cache, stack, role)
            if fragments:
                return fragments
    return []


def _resolve_selector_node(inputs: dict[str, Any]) -> list[str]:
    options = _split_selector_strings(inputs.get("strings"))
    if not options:
        return []

    selected_index = parse_int(inputs.get("select"))
    if selected_index is not None and 0 <= selected_index < len(options):
        return _meaningful_texts([options[selected_index]])

    if len(options) == 1:
        return _meaningful_texts(options)

    return []


def _resolve_wildcard_node(
    inputs: dict[str, Any],
    prompt_graph: dict[str, dict[str, Any]],
    cache: dict[str, list[str]],
    stack: set[str],
    role: str,
) -> list[str]:
    fragments = _resolve_preferred_prompt_inputs(inputs, prompt_graph, cache, stack, role)

    if role == "negative" and "wildcard_text" in inputs and not fragments:
        fragments.extend(_resolve_comfyui_text_value(inputs["wildcard_text"], prompt_graph, cache, stack, role))
    elif not fragments and "wildcard_text" in inputs:
        fragments.extend(_resolve_comfyui_text_value(inputs["wildcard_text"], prompt_graph, cache, stack, role))

    return _meaningful_texts(fragments)


def _resolve_comfyui_text_node(
    node_id: str,
    prompt_graph: dict[str, dict[str, Any]],
    cache: dict[str, list[str]],
    stack: set[str] | None = None,
    role: str = "positive",
) -> list[str]:
    cache_key = f"{role}:{node_id}"
    if cache_key in cache:
        return cache[cache_key]

    active_stack = set(stack or set())
    stack_key = cache_key
    if stack_key in active_stack:
        return []

    node = prompt_graph.get(str(node_id))
    if not node:
        return []

    active_stack.add(stack_key)
    class_type = _node_class_type(node)
    inputs = _node_inputs(node)
    if "switch" in class_type:
        parts = _resolve_switch_node(inputs, prompt_graph, cache, active_stack, role)
    elif "wildcard" in class_type:
        parts = _resolve_wildcard_node(inputs, prompt_graph, cache, active_stack, role)
    elif "concatenate" in class_type or "concat" in class_type:
        parts = _resolve_concat_node(inputs, prompt_graph, cache, active_stack, role)
    elif "cliptextencode" in class_type:
        parts = _resolve_preferred_prompt_inputs(inputs, prompt_graph, cache, active_stack, role)
        if not parts:
            parts = _resolve_comfyui_text_value(inputs.get("text"), prompt_graph, cache, active_stack, role)
    elif "selector" in class_type:
        parts = _resolve_selector_node(inputs)
    else:
        parts = _resolve_preferred_prompt_inputs(inputs, prompt_graph, cache, active_stack, role)
        if not parts:
            for key, value in _extract_text_like_values(inputs):
                lowered_key = key.lower()
                if lowered_key == "strings":
                    continue
                parts.extend(_resolve_comfyui_text_value(value, prompt_graph, cache, active_stack, role))
        if not parts:
            for key, value in inputs.items():
                if not _looks_like_text_key(str(key)):
                    continue
                if isinstance(value, list) and value and isinstance(value[0], (str, int)):
                    parts.extend(_resolve_comfyui_text_value(value, prompt_graph, cache, active_stack, role))
    active_stack.discard(stack_key)

    cache[cache_key] = _meaningful_texts(parts)
    return cache[cache_key]


def _resolve_comfyui_text_value(
    value: Any,
    prompt_graph: dict[str, dict[str, Any]],
    cache: dict[str, list[str]],
    stack: set[str] | None = None,
    role: str = "positive",
) -> list[str]:
    if isinstance(value, list) and value:
        reference = value[0]
        if isinstance(reference, (str, int)):
            return _resolve_comfyui_text_node(str(reference), prompt_graph, cache, stack, role)
    return _meaningful_texts(_stringify_text(value))


def _resolve_comfyui_raw_text_node(
    node_id: str,
    prompt_graph: dict[str, dict[str, Any]],
    cache: dict[str, list[str]],
    stack: set[str] | None = None,
    role: str = "positive",
) -> list[str]:
    cache_key = f"raw:{role}:{node_id}"
    if cache_key in cache:
        return cache[cache_key]

    active_stack = set(stack or set())
    if cache_key in active_stack:
        return []
    node = prompt_graph.get(str(node_id))
    if not node:
        return []

    active_stack.add(cache_key)
    inputs = _node_inputs(node)
    class_type = _node_class_type(node)

    if "cliptextencode" in class_type:
        parts = _resolve_comfyui_raw_text_value(inputs.get("text"), prompt_graph, cache, active_stack, role)
    elif "concat" in class_type or "concatenate" in class_type:
        parts = []
        for key, value in _extract_text_like_values(inputs):
            if key.lower() == "strings" or key.lower().startswith("neg"):
                continue
            parts.extend(_resolve_comfyui_raw_text_value(value, prompt_graph, cache, active_stack, role))
    elif "switch" in class_type:
        parts = _resolve_switch_node(inputs, prompt_graph, cache, active_stack, role)
    elif "selector" in class_type:
        parts = _resolve_selector_node(inputs)
    else:
        parts = []
        for key in _RAW_TEXT_INPUT_KEYS:
            if key in inputs:
                resolved = _resolve_comfyui_raw_text_value(inputs[key], prompt_graph, cache, active_stack, role)
                if resolved:
                    parts.extend(resolved)
                    if any(_looks_like_unprocessed_wildcard_text(item) for item in resolved):
                        break
        if not parts:
            for key, value in _extract_text_like_values(inputs):
                if key.lower() == "strings":
                    continue
                parts.extend(_resolve_comfyui_raw_text_value(value, prompt_graph, cache, active_stack, role))

    active_stack.discard(cache_key)
    cache[cache_key] = _meaningful_texts(parts)
    return cache[cache_key]


def _resolve_comfyui_raw_text_value(
    value: Any,
    prompt_graph: dict[str, dict[str, Any]],
    cache: dict[str, list[str]],
    stack: set[str] | None = None,
    role: str = "positive",
) -> list[str]:
    if isinstance(value, list) and value:
        reference = value[0]
        if isinstance(reference, (str, int)):
            return _resolve_comfyui_raw_text_node(str(reference), prompt_graph, cache, stack, role)
    return _meaningful_texts(_stringify_text(value))


def _extract_workflow_texts(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        parts: list[str] = []
        for key, value in payload.items():
            if _looks_like_text_key(key):
                parts.extend(_stringify_text(value))
            parts.extend(_extract_workflow_texts(value))
        return parts
    if isinstance(payload, list):
        parts: list[str] = []
        for item in payload:
            parts.extend(_extract_workflow_texts(item))
        return parts
    return []


def _infer_prompt_role_from_node(node: dict[str, Any]) -> str | None:
    hints = f"{_node_title(node)} {_node_class_type(node)}".strip()
    if "negative" in hints or " neg" in hints:
        return "negative"
    if "prompt" in hints or "positive" in hints:
        return "positive"
    return None


def _extract_workflow_prompt_candidates(payload: Any, role: str | None = None) -> tuple[list[str], list[str]]:
    positives: list[str] = []
    negatives: list[str] = []

    if isinstance(payload, dict):
        has_processed_text = any(key in payload for key in _PROCESSED_TEXT_INPUT_KEYS)
        hints = " ".join(
            str(payload.get(key, "")).strip().lower()
            for key in ("title", "type", "class_type", "name")
            if payload.get(key) not in (None, "")
        )
        local_role = role
        if "negative" in hints or " neg" in hints:
            local_role = "negative"
        elif "prompt" in hints or "positive" in hints:
            local_role = "positive"

        for key, value in payload.items():
            child_role = local_role
            lowered = key.strip().lower()
            if "negative" in lowered or lowered.startswith("neg"):
                child_role = "negative"
            elif lowered in {"populated_text", "positive_prompt", "prompt"}:
                child_role = "positive"

            if _looks_like_text_key(lowered):
                if (
                    has_processed_text
                    and lowered not in _PROCESSED_TEXT_INPUT_KEYS
                    and (lowered in _RAW_WILDCARD_TEXT_KEYS or _looks_like_unprocessed_wildcard_text(value))
                ):
                    child_positive, child_negative = _extract_workflow_prompt_candidates(value, child_role)
                    positives.extend(child_positive)
                    negatives.extend(child_negative)
                    continue
                text_values = _stringify_text(value)
                if child_role == "negative":
                    negatives.extend(text_values)
                elif child_role == "positive" or lowered == "populated_text":
                    positives.extend(text_values)

            child_positive, child_negative = _extract_workflow_prompt_candidates(value, child_role)
            positives.extend(child_positive)
            negatives.extend(child_negative)
    elif isinstance(payload, list):
        for item in payload:
            child_positive, child_negative = _extract_workflow_prompt_candidates(item, role)
            positives.extend(child_positive)
            negatives.extend(child_negative)

    return _dedupe_strings(positives), _dedupe_strings(negatives)


def _join_fragments(values: list[str], limit: int = 12000) -> str | None:
    fragments = _dedupe_strings(values)
    if not fragments:
        return None

    joined: list[str] = []
    total_length = 0
    for fragment in fragments:
        next_length = total_length + len(fragment) + 2
        if next_length > limit:
            break
        joined.append(fragment)
        total_length = next_length
    return "\n".join(joined) if joined else None


def _select_prompt_candidate(values: list[str], limit: int = 12000) -> str | None:
    fragments = _dedupe_strings(values)
    if not fragments:
        return None

    processed_fragments = [fragment for fragment in fragments if not _looks_like_unprocessed_wildcard_text(fragment)]
    if processed_fragments:
        return _join_fragments(processed_fragments, limit=limit)
    return _join_fragments(fragments, limit=limit)


def _select_raw_prompt_candidate(values: list[str], limit: int = 12000) -> str | None:
    fragments = _dedupe_strings(values)
    if not fragments:
        return None
    wildcard_fragments = [fragment for fragment in fragments if _looks_like_unprocessed_wildcard_text(fragment)]
    if wildcard_fragments:
        return _join_fragments(wildcard_fragments, limit=limit)
    return _join_fragments(fragments, limit=limit)


def _extract_processed_prompt_outputs(payload: Any) -> list[str]:
    candidates: list[str] = []
    if isinstance(payload, dict):
        hints = " ".join(
            str(payload.get(key, "")).strip().lower()
            for key in ("title", "type", "class_type", "name")
            if payload.get(key) not in (None, "")
        )
        output_node = any(token in hints for token in ("show text", "showtext", "save image", "image saver", "prompt"))
        for key, value in payload.items():
            lowered = str(key).strip().lower()
            if lowered in {"text_0", "output_text", "result_text", "final_text", "processed_text", "populated_text"} or (
                output_node and lowered.startswith("text")
            ):
                for text in _meaningful_texts(_stringify_text(value)):
                    if len(text) >= 40 and not _looks_like_unprocessed_wildcard_text(text):
                        candidates.append(text)
            candidates.extend(_extract_processed_prompt_outputs(value))
    elif isinstance(payload, list):
        for item in payload:
            candidates.extend(_extract_processed_prompt_outputs(item))
    return _dedupe_strings(candidates)


def _identity_prompt_tags(prompt: str | None) -> set[str]:
    generic = {
        "1girl",
        "1boy",
        "absurdres",
        "highres",
        "looking_at_viewer",
        "masterpiece",
        "posing",
        "solo",
    }
    return {
        tag
        for tag in extract_prompt_tags(prompt, limit=160)
        if tag not in generic and ("(" in tag or ")" in tag)
    }


def _select_matching_processed_prompt(candidates: list[str], raw_prompt: str | None) -> str | None:
    if not candidates:
        return None
    raw_tags = set(extract_prompt_tags(raw_prompt, limit=180))
    raw_identity_tags = _identity_prompt_tags(raw_prompt)
    best_score = 0.0
    best_candidate: str | None = None
    for candidate in candidates:
        candidate_tags = set(extract_prompt_tags(candidate, limit=120))
        if not candidate_tags:
            continue
        candidate_identity_tags = _identity_prompt_tags(candidate)
        if candidate_identity_tags and raw_identity_tags and not (candidate_identity_tags & raw_identity_tags):
            continue
        shared = candidate_tags & raw_tags
        overlap = len(shared) / max(1, len(candidate_tags))
        identity_bonus = 0.18 if candidate_identity_tags and (candidate_identity_tags & raw_identity_tags) else 0.0
        score = overlap + identity_bonus + min(_text_quality_score(candidate) / 10000, 0.08)
        if score > best_score:
            best_score = score
            best_candidate = candidate
    return best_candidate if best_score >= 0.55 else None


def _parse_a1111_parameters(parameters: str) -> tuple[str | None, str | None]:
    text = parameters.replace("\r\n", "\n").strip()
    if not text:
        return None, None

    metadata_match = re.search(r"\nSteps:\s", text)
    prompt_block = text[: metadata_match.start()].strip() if metadata_match else text

    negative_match = re.search(r"(?:^|\n)Negative prompt:\s*", prompt_block)
    if not negative_match:
        return prompt_block or None, None

    prompt = prompt_block[: negative_match.start()].strip()
    negative_prompt = prompt_block[negative_match.end() :].strip()
    return prompt or None, negative_prompt or None


def _parse_a1111_option_map(parameters: str) -> dict[str, str]:
    text = parameters.replace("\r\n", "\n").strip()
    metadata_match = re.search(r"(?:^|\n)(Steps:\s.*)$", text, flags=re.DOTALL)
    if not metadata_match:
        return {}
    option_block = metadata_match.group(1).strip()
    tokens = option_block.split(",")
    pairs: list[tuple[str, str]] = []
    current_key: str | None = None
    current_value = ""

    for token in tokens:
        part = token.strip()
        if not part:
            continue
        if ":" in part:
            if current_key is not None:
                pairs.append((current_key, current_value.strip()))
            current_key, current_value = part.split(":", 1)
            current_key = current_key.strip().lower()
            current_value = current_value.strip()
        elif current_key is not None:
            current_value = f"{current_value}, {part}".strip()

    if current_key is not None:
        pairs.append((current_key, current_value.strip()))
    return {key: value for key, value in pairs}


def _parse_prompt_loras(prompt: str | None) -> list[str]:
    if not prompt:
        return []
    return _dedupe_strings(match.group(1).strip() for match in _LORA_RE.finditer(prompt))


def _clean_loader_name(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _collect_comfyui_generation_settings(
    prompt_graph: dict[str, dict[str, Any]],
    workflow_payload: dict[str, Any] | list[Any] | None,
    prompt: str | None,
) -> dict[str, Any]:
    settings: dict[str, Any] = {
        "seed": None,
        "steps": None,
        "cfg_scale": None,
        "sampler_name": None,
        "scheduler": None,
        "checkpoint": None,
        "vae": None,
        "loras": [],
    }

    loras = list(_parse_prompt_loras(prompt))
    for node in prompt_graph.values():
        class_type = _node_class_type(node)
        inputs = _node_inputs(node)

        if "sampler" in class_type:
            settings["seed"] = first_value(settings["seed"], parse_int(inputs.get("seed")))
            settings["steps"] = first_value(settings["steps"], parse_int(inputs.get("steps")))
            settings["cfg_scale"] = first_value(settings["cfg_scale"], parse_float(inputs.get("cfg")))
            settings["sampler_name"] = first_value(settings["sampler_name"], _clean_loader_name(inputs.get("sampler_name")))
            settings["scheduler"] = first_value(settings["scheduler"], _clean_loader_name(inputs.get("scheduler")))

        if "checkpoint" in class_type:
            settings["checkpoint"] = first_value(
                settings["checkpoint"],
                _clean_loader_name(first_value(inputs.get("ckpt_name"), inputs.get("checkpoint"))),
            )

        if "vae" in class_type:
            settings["vae"] = first_value(
                settings["vae"],
                _clean_loader_name(first_value(inputs.get("vae_name"), inputs.get("vae"))),
            )

        if "lora" in class_type:
            if lora_name := _clean_loader_name(first_value(inputs.get("lora_name"), inputs.get("lora"))):
                loras.append(lora_name)

    if workflow_payload is not None and settings["checkpoint"] is None:
        for item in _extract_workflow_texts(workflow_payload):
            lowered = item.lower()
            if lowered.endswith(".ckpt") or lowered.endswith(".safetensors"):
                settings["checkpoint"] = item
                break

    settings["loras"] = _dedupe_strings(loras)
    return settings


def _sampler_title_penalty(node: dict[str, Any]) -> int:
    hints = f"{_node_title(node)} {_node_class_type(node)}".strip().lower()
    penalty = 0
    if any(token in hints for token in ("detail", "upscale", "refiner", "hires", "preview")):
        penalty += 120
    return penalty


def _text_quality_score(text: str | None) -> int:
    if not text:
        return 0
    alpha_count = sum(character.isalpha() for character in text)
    digit_count = sum(character.isdigit() for character in text)
    wildcard_noise = text.count("__") * 20
    return min(len(text), 800) + (alpha_count * 2) - (digit_count * 3) - wildcard_noise


def _select_comfyui_prompt_pair(prompt_graph: dict[str, dict[str, Any]], *, raw: bool = False) -> tuple[str | None, str | None]:
    cache: dict[str, list[str]] = {}
    best_score: int | None = None
    best_prompt: str | None = None
    best_negative: str | None = None

    for node in prompt_graph.values():
        if "sampler" not in _node_class_type(node):
            continue
        inputs = _node_inputs(node)
        resolve_value = _resolve_comfyui_raw_text_value if raw else _resolve_comfyui_text_value
        join_value = _select_raw_prompt_candidate if raw else _join_fragments
        positive_text = join_value(resolve_value(inputs.get("positive"), prompt_graph, cache, role="positive"))
        negative_text = join_value(resolve_value(inputs.get("negative"), prompt_graph, cache, role="negative"))
        if not positive_text and not negative_text:
            continue

        score = _text_quality_score(positive_text) + (_text_quality_score(negative_text) // 2) - _sampler_title_penalty(node)
        if positive_text and negative_text:
            score += 100
        if best_score is None or score > best_score:
            best_score = score
            best_prompt = positive_text
            best_negative = negative_text

    return best_prompt, best_negative


def _extract_generation_metadata(exif: dict[str, Any]) -> dict[str, Any]:
    parameters = first_value(exif.get("Parameters"), exif.get("parameters"))
    if isinstance(parameters, str) and parameters.strip():
        prompt, negative_prompt = _parse_a1111_parameters(parameters)
        option_map = _parse_a1111_option_map(parameters)
        return {
            "generator": "automatic1111",
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "workflow_text": parameters.strip(),
            "workflow_format": "automatic1111_parameters",
            "seed": parse_int(option_map.get("seed")),
            "steps": parse_int(option_map.get("steps")),
            "cfg_scale": parse_float(option_map.get("cfg scale")),
            "sampler_name": first_value(option_map.get("sampler"), option_map.get("sampler name")),
            "scheduler": option_map.get("schedule type"),
            "checkpoint": first_value(option_map.get("model"), option_map.get("model hash")),
            "vae": option_map.get("vae"),
            "loras": _parse_prompt_loras(prompt),
        }

    prompt_graph_raw = _parse_json_string(first_value(exif.get("Prompt"), exif.get("prompt")))
    workflow_raw = _parse_json_string(first_value(exif.get("Workflow"), exif.get("workflow")))
    prompt_graph = prompt_graph_raw if isinstance(prompt_graph_raw, dict) else {}
    workflow_payload = workflow_raw if isinstance(workflow_raw, (dict, list)) else None

    if not prompt_graph and workflow_payload is None:
        return {
            "generator": None,
            "prompt": None,
            "negative_prompt": None,
            "workflow_text": None,
            "workflow_format": None,
            "seed": None,
            "steps": None,
            "cfg_scale": None,
            "sampler_name": None,
            "scheduler": None,
            "checkpoint": None,
            "vae": None,
            "loras": [],
        }

    prompt, negative_prompt = _select_comfyui_prompt_pair(prompt_graph)
    raw_prompt, raw_negative_prompt = _select_comfyui_prompt_pair(prompt_graph, raw=True)
    fallback_positive, fallback_negative = _extract_workflow_prompt_candidates(workflow_payload)
    fallback_prompt = _select_prompt_candidate(fallback_positive)
    fallback_negative_prompt = _select_prompt_candidate(fallback_negative)
    fallback_raw_prompt = _select_raw_prompt_candidate(fallback_positive)
    fallback_raw_negative_prompt = _select_raw_prompt_candidate(fallback_negative)
    processed_output_prompt = _select_matching_processed_prompt(
        [
            *_extract_processed_prompt_outputs(prompt_graph),
            *(_extract_processed_prompt_outputs(workflow_payload) if workflow_payload is not None else []),
        ],
        prompt or fallback_raw_prompt or raw_prompt,
    )
    if not prompt:
        prompt = fallback_prompt
    elif (
        fallback_prompt
        and _looks_like_unprocessed_wildcard_text(prompt)
        and not _looks_like_unprocessed_wildcard_text(fallback_prompt)
    ):
        prompt = fallback_prompt
    if not negative_prompt:
        negative_prompt = fallback_negative_prompt
    elif (
        fallback_negative_prompt
        and _looks_like_unprocessed_wildcard_text(negative_prompt)
        and not _looks_like_unprocessed_wildcard_text(fallback_negative_prompt)
    ):
        negative_prompt = fallback_negative_prompt
    if processed_output_prompt and (not prompt or _looks_like_unprocessed_wildcard_text(prompt)):
        raw_prompt = raw_prompt or prompt
        prompt = processed_output_prompt
    if not raw_prompt:
        raw_prompt = fallback_raw_prompt
    if not raw_negative_prompt:
        raw_negative_prompt = fallback_raw_negative_prompt

    generation_settings = _collect_comfyui_generation_settings(prompt_graph, workflow_payload, prompt)
    workflow_text = _join_fragments(
        [
            value
            for value in [
                prompt,
                negative_prompt,
                generation_settings.get("checkpoint"),
                generation_settings.get("vae"),
                generation_settings.get("sampler_name"),
                generation_settings.get("scheduler"),
                *generation_settings.get("loras", []),
            ]
            if isinstance(value, str)
        ],
        limit=20000,
    )

    return {
        "generator": "comfyui",
        "prompt": prompt,
        "processed_prompt": prompt,
        "raw_prompt": raw_prompt if raw_prompt != prompt else None,
        "negative_prompt": negative_prompt,
        "processed_negative_prompt": negative_prompt,
        "raw_negative_prompt": raw_negative_prompt if raw_negative_prompt != negative_prompt else None,
        "workflow_text": workflow_text,
        "workflow_format": "comfyui_prompt_and_workflow",
        **generation_settings,
    }


def _clean_prompt_tag(value: str) -> str | None:
    tag = value.strip().lower()
    if not tag:
        return None
    tag = tag.strip("\"'")
    tag = tag.replace("\\(", "(").replace("\\)", ")")
    tag = tag.strip(",.; ")
    while len(tag) > 2 and tag[0] in _ATTENTION_WRAPPERS and tag[-1] == _ATTENTION_WRAPPERS[tag[0]]:
        tag = tag[1:-1].strip()
    tag = _PROMPT_WEIGHT_RE.sub("", tag)
    tag = tag.strip(",.; ")
    while tag and tag[0] in _ATTENTION_WRAPPERS and tag.count(tag[0]) > tag.count(_ATTENTION_WRAPPERS[tag[0]]):
        tag = tag[1:].strip()
    while tag and tag[-1] in _ATTENTION_WRAPPER_REVERSE and tag.count(tag[-1]) > tag.count(_ATTENTION_WRAPPER_REVERSE[tag[-1]]):
        tag = tag[:-1].strip()
    tag = _DANBOORU_WHITESPACE_RE.sub(" ", tag)
    tag = tag.strip(".,:_- ")
    tag = tag.replace(" ", "_")
    if len(tag) < 2 or len(tag) > 512:
        return None
    if tag in {"and", "or", "none", "n/a"}:
        return None
    return tag


def canonicalize_tag(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = _clean_prompt_tag(value)
    if cleaned:
        return cleaned
    fallback = value.strip().lower().replace(" ", "_")
    fallback = re.sub(r"_+", "_", fallback).strip("._-")
    if not fallback:
        return None
    return fallback[:1024]


def extract_prompt_tags(prompt: str | None, limit: int = 48) -> list[str]:
    if not prompt:
        return []

    tags: list[str] = []
    seen: set[str] = set()
    for fragment in _PROMPT_TAG_SPLIT_RE.split(prompt):
        tag = canonicalize_tag(fragment)
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
        if len(tags) >= limit:
            break
    return tags


def prompt_tag_string(prompt_tags: list[str] | None) -> str | None:
    if not prompt_tags:
        return None
    values = [tag.strip() for tag in prompt_tags if isinstance(tag, str) and tag.strip()]
    return ", ".join(values) if values else None


def prompt_excerpt(prompt: str | None, limit: int = 240) -> str | None:
    if not prompt:
        return None
    cleaned = " ".join(part.strip() for part in prompt.replace("\r\n", "\n").splitlines() if part.strip())
    if not cleaned:
        return None
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 1].rstrip()}…"


def display_prompt_from_normalized(normalized: dict[str, Any] | None) -> str | None:
    if not normalized:
        return None
    for key in ("processed_prompt", "prompt"):
        value = normalized.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def display_negative_prompt_from_normalized(normalized: dict[str, Any] | None) -> str | None:
    if not normalized:
        return None
    for key in ("processed_negative_prompt", "negative_prompt"):
        value = normalized.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def metadata_version(normalized_json: dict[str, Any] | None) -> int:
    if not normalized_json:
        return 0
    return parse_int(normalized_json.get("metadata_version")) or 0


def should_reextract_metadata(
    *,
    existing_size_bytes: int | None,
    existing_modified_at: datetime | None,
    existing_normalized_json: dict[str, Any] | None,
    file_size_bytes: int,
    file_modified_at: datetime,
) -> bool:
    if existing_size_bytes is None or existing_modified_at is None:
        return True
    if existing_size_bytes != file_size_bytes or existing_modified_at != file_modified_at:
        return True
    return metadata_version(existing_normalized_json) < METADATA_SCHEMA_VERSION


def prompt_tags_from_normalized(normalized: dict[str, Any] | None) -> list[str]:
    if not normalized:
        return []
    stored_prompt_tags = normalized.get("prompt_tags")
    cleaned_stored_tags = []
    if isinstance(stored_prompt_tags, list):
        cleaned_stored_tags = [
            tag for value in stored_prompt_tags if isinstance(value, str) if (tag := canonicalize_tag(value))
        ]

    prompt = display_prompt_from_normalized(normalized)
    extracted_from_prompt = extract_prompt_tags(prompt)
    if extracted_from_prompt:
        return extracted_from_prompt
    return _dedupe_strings(cleaned_stored_tags)


def normalized_metadata_for_api(normalized: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(normalized or {})
    display_prompt = display_prompt_from_normalized(payload)
    display_negative_prompt = display_negative_prompt_from_normalized(payload)
    if display_prompt:
        payload["prompt"] = display_prompt
        payload.setdefault("processed_prompt", display_prompt)
    if display_negative_prompt:
        payload["negative_prompt"] = display_negative_prompt
        payload.setdefault("processed_negative_prompt", display_negative_prompt)
    prompt_tags = prompt_tags_from_normalized(payload)
    payload["prompt_tags"] = prompt_tags
    payload["prompt_tag_string"] = prompt_tag_string(prompt_tags)
    payload["gps_latitude"] = payload.get("gps_lat")
    payload["gps_longitude"] = payload.get("gps_lon")
    return payload


def compute_prompt_tag_similarity(
    left_normalized: dict[str, Any] | None,
    right_normalized: dict[str, Any] | None,
) -> tuple[float, list[str], list[str], list[str]]:
    left_tags = prompt_tags_from_normalized(left_normalized)
    right_tags = prompt_tags_from_normalized(right_normalized)
    left_set = set(left_tags)
    right_set = set(right_tags)
    shared = sorted(left_set & right_set)
    union = left_set | right_set
    left_only = [tag for tag in left_tags if tag not in right_set]
    right_only = [tag for tag in right_tags if tag not in left_set]
    score = float(len(shared) / len(union)) if union else 0.0
    return score, shared, left_only, right_only


def compute_prompt_tag_overlap(
    left_normalized: dict[str, Any] | None,
    right_normalized: dict[str, Any] | None,
) -> tuple[int, list[str], list[str], list[str]]:
    score, shared, left_only, right_only = compute_prompt_tag_similarity(left_normalized, right_normalized)
    return len(shared), shared, left_only, right_only


def normalize_metadata(
    *,
    media_type: MediaType,
    exif: dict[str, Any] | None,
    ffprobe: dict[str, Any] | None,
) -> dict[str, Any]:
    exif = exif or {}
    ffprobe = ffprobe or {}
    format_data = ffprobe.get("format", {})
    streams = ffprobe.get("streams", [])
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), {})

    created = first_value(
        parse_datetime(exif.get("DateTimeOriginal")),
        parse_datetime(exif.get("CreateDate")),
        parse_datetime(exif.get("MediaCreateDate")),
        parse_datetime(format_data.get("tags", {}).get("creation_time")),
    )

    normalized = {
        "metadata_version": METADATA_SCHEMA_VERSION,
        "media_type": media_type.value,
        "width": first_value(parse_int(exif.get("ImageWidth")), parse_int(video_stream.get("width"))),
        "height": first_value(parse_int(exif.get("ImageHeight")), parse_int(video_stream.get("height"))),
        "orientation": first_value(exif.get("Orientation"), "unknown"),
        "created_at": created.isoformat() if created else None,
        "camera_make": first_value(exif.get("Make"), exif.get("CameraMake")),
        "camera_model": first_value(exif.get("Model"), exif.get("CameraModelName")),
        "lens": first_value(exif.get("LensModel"), exif.get("LensInfo")),
        "gps_lat": first_value(parse_float(exif.get("GPSLatitude")), parse_float(exif.get("GPSLatitudeRef"))),
        "gps_lon": first_value(parse_float(exif.get("GPSLongitude")), parse_float(exif.get("GPSLongitudeRef"))),
        "codec": first_value(video_stream.get("codec_name"), exif.get("CompressorName")),
        "duration_seconds": first_value(parse_float(format_data.get("duration")), parse_float(exif.get("Duration"))),
        "fps": None,
        "bitrate": first_value(parse_int(format_data.get("bit_rate")), parse_int(video_stream.get("bit_rate"))),
        "color_profile": first_value(exif.get("ProfileDescription"), video_stream.get("color_space")),
    }
    normalized.update(_extract_generation_metadata(exif))
    normalized["prompt_tags"] = extract_prompt_tags(display_prompt_from_normalized(normalized))
    normalized["prompt_tag_string"] = prompt_tag_string(normalized["prompt_tags"])

    avg_frame_rate = video_stream.get("avg_frame_rate")
    if isinstance(avg_frame_rate, str) and "/" in avg_frame_rate:
        numerator, denominator = avg_frame_rate.split("/", 1)
        try:
            normalized["fps"] = round(float(numerator) / float(denominator), 3) if float(denominator) else None
        except (TypeError, ValueError, ZeroDivisionError):
            normalized["fps"] = None
    else:
        normalized["fps"] = first_value(parse_float(video_stream.get("r_frame_rate")), parse_float(video_stream.get("FrameRate")))

    return normalized


def _keywords_from_raw(exif: dict[str, Any] | None) -> list[str]:
    exif = exif or {}
    raw_keywords = first_value(exif.get("Keywords"), exif.get("Subject"), exif.get("HierarchicalSubject"))
    if isinstance(raw_keywords, str):
        return [raw_keywords]
    if isinstance(raw_keywords, list):
        return [str(item) for item in raw_keywords if item]
    return []


def build_tags(normalized: dict[str, Any], exif: dict[str, Any] | None = None) -> list[str]:
    tags: set[str] = set()
    for keyword in _keywords_from_raw(exif):
        if canonical := canonicalize_tag(keyword):
            tags.add(canonical)

    if make := normalized.get("camera_make"):
        tags.add(f"camera:{str(make).strip().lower()}")
    if model := normalized.get("camera_model"):
        tags.add(f"model:{str(model).strip().lower()}")
    if lens := normalized.get("lens"):
        tags.add(f"lens:{str(lens).strip().lower()}")
    if created_at := normalized.get("created_at"):
        tags.add(f"year:{created_at[:4]}")
    if media_type := normalized.get("media_type"):
        tags.add(f"media:{media_type}")
    if generator := normalized.get("generator"):
        tags.add(f"generator:{str(generator).strip().lower()}")
    if checkpoint := normalized.get("checkpoint"):
        tags.add(f"checkpoint:{str(checkpoint).strip().lower()}")
    if sampler_name := normalized.get("sampler_name"):
        tags.add(f"sampler:{str(sampler_name).strip().lower()}")
    if vae := normalized.get("vae"):
        tags.add(f"vae:{str(vae).strip().lower()}")
    for lora in normalized.get("loras", []) or []:
        if isinstance(lora, str) and lora.strip():
            tags.add(f"lora:{lora.strip().lower()}")
    if width := normalized.get("width"):
        tags.add(f"width:{width}")
    if height := normalized.get("height"):
        tags.add(f"height:{height}")
    for prompt_tag in prompt_tags_from_normalized(normalized):
        tags.add(prompt_tag)
    return sorted(tag for tag in tags if tag)


def build_search_text(filename: str, relative_path: str, normalized: dict[str, Any], tags: list[str]) -> str:
    parts = [filename, relative_path]

    def append_search_value(value: Any) -> None:
        if value is None or isinstance(value, bool):
            return
        if isinstance(value, (str, int, float)):
            parts.append(str(value))
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                append_search_value(item)

    for value in normalized.values():
        append_search_value(value)
    parts.extend(tags)
    return " ".join(parts)


def canonical_pair(asset_id_a: Any, asset_id_b: Any) -> tuple[Any, Any]:
    return (asset_id_a, asset_id_b) if str(asset_id_a) < str(asset_id_b) else (asset_id_b, asset_id_a)


def hamming_distance(left: str | None, right: str | None) -> int | None:
    if not left or not right:
        return None
    try:
        left_bits = bin(int(left, 16))[2:].zfill(len(left) * 4)
        right_bits = bin(int(right, 16))[2:].zfill(len(right) * 4)
    except ValueError:
        return None
    return sum(1 for bit_left, bit_right in zip(left_bits, right_bits, strict=False) if bit_left != bit_right)


def score_from_distance(match_type: MatchType, distance: float) -> float:
    if match_type == MatchType.DUPLICATE:
        return max(0.0, 1.0 - (distance / 64.0))
    if match_type == MatchType.TAG:
        return max(0.0, 1.0 - distance)
    return max(0.0, 1.0 - distance)
