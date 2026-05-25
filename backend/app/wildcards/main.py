from __future__ import annotations

import hashlib
import fnmatch
import asyncio
import json
import os
import re
import shutil
import sqlite3
import threading
from collections import Counter, defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Literal
from urllib.parse import urlparse, urlunparse

import httpx
import yaml
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

# Import Pydantic models from schemas module
from .schemas.wildcards import (
    ScanRequest, ScanSummary, ScanStatus,
    WildcardListItem, EntryItem, WildcardDetail, EntryPatch,
    TagsResponse, CategoriesResponse,
    PromptComposeRequest, PromptComposeResponse,
    LlmSuggestRequest, LlmSuggestResponse, LlmJobRequest, LlmJobItem,
    CleanupPreviewRequest, CleanupPreviewResponse,
    PromptRecipeSaveRequest, TagOverrideRequest, TaxonomyPatchRequest,
    ExportRequest, ExportPlan,
    utc_now,
)

# Removed redundant imports of parser constants

# Removed redundant database imports

# Path constants imported from config module
from .config import WILDCARD_SOURCE_ROOT as DEFAULT_SOURCE_ROOT
from .config import WILDCARD_DATA_DIR as DATA_DIR
from .config import WILDCARD_DB as DB_PATH
from .config import EXPORT_ROOT

WILDCARD_REF_RE = re.compile(r"__([^_\n][^_\n]*?)__")
LORA_RE = re.compile(r"<lora:[^>]+>", re.IGNORECASE)
WEIGHTED_DYNAMIC_RE = re.compile(r"\{\s*\d+(?:\.\d+)?::")
MULTI_SELECT_RE = re.compile(r"\{\s*-?\d+(?:-\d+)?\$\$")
COMMENT_RE = re.compile(r"^\s*#")
NEGATIVE_PROMPT_RE = re.compile(r"\b(?:negative prompt|negative|neg prompt|negatives?)\s*:", re.IGNORECASE)

CATEGORY_RULES: dict[str, tuple[str, ...]] = {
    "copyright": (
        "copyright",
        "series",
        "franchise",
        "source",
        "source material",
        "anime title",
        "game title",
        "manga",
        "comic title",
        "movie",
        "show",
        "universe",
        "pokemon",
        "genshin",
        "honkai",
        "fate",
        "touhou",
        "azur lane",
        "blue archive",
    ),
    "characters": (
        "character",
        "characters",
        "character specific",
        "characterspecific",
        "female",
        "females",
        "person",
        "people",
        "personmaker",
        "card",
        "actor",
        "actors",
        "actress",
        "celebrity",
        "celeb",
        "vtuber",
        "oc",
        "original character",
        "girl",
        "boy",
        "woman",
        "man",
        "pokemon",
    ),
    "pose": (
        "pose",
        "posing",
        "action",
        "gesture",
        "stance",
        "kneeling",
        "sitting",
        "standing",
        "lying",
        "laying",
        "reclining",
        "from behind",
        "from_below",
        "cowgirl",
        "missionary",
    ),
    "background": (
        "background",
        "location",
        "scenery",
        "scene",
        "environment",
        "landscape",
        "architecture",
        "interior",
        "outside",
        "forest",
        "city",
        "room",
        "beach",
        "street",
    ),
    "clothing": (
        "clothing",
        "clothes",
        "outfit",
        "attire",
        "dress",
        "shirt",
        "skirt",
        "pants",
        "uniform",
        "lingerie",
        "bikini",
        "costume",
        "headwear",
        "hat",
        "jewelry",
        "accessory",
    ),
    "quality": (
        "score_",
        "masterpiece",
        "best quality",
        "quality",
        "absurdres",
        "highres",
        "aesthetic",
        "intricate details",
    ),
    "style": (
        "style",
        "artist",
        "anime",
        "illustration",
        "photo",
        "realistic",
        "painting",
        "comic",
        "toon",
        "sketch",
        "lineart",
    ),
    "anatomy": (
        "body",
        "face",
        "hair",
        "eyes",
        "breast",
        "lips",
        "nose",
        "skin",
        "height",
        "build",
        "anatomy",
    ),
    "lighting": (
        "light",
        "lighting",
        "shadow",
        "hdr",
        "volumetric",
        "sunset",
        "neon",
        "ambient",
    ),
}

SCAN_LOCK = threading.Lock()
SCAN_STATE: dict[str, Any] = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "summary": None,
    "error": None,
}

PROMPT_MODES = ("danbooru_tags", "sdxl_natural", "mixed", "unknown")

SDXL_PROMPT_CONTEXT = """
You are helping organize and rewrite SDXL natural-language prompts.
Use descriptive photographic or illustrative prose rather than Danbooru tag salad.
Start with the image type or medium, then describe the central subject/action/location, detailed imagery, environment,
mood/atmosphere, style, and style execution. Prefer concrete camera, lens, depth of field, lighting, composition,
materials, fabric, texture, foreground/background, and spatial relationships. Avoid contradictions such as "photo, anime style".
Return reviewable text only; do not mutate wildcard syntax, LoRA syntax, BREAK, or dynamic prompt expressions.
""".strip()

DANBOORU_PROMPT_CONTEXT = """
You are helping organize prompts for NoobAI XL and Illustrious XL style models.
Favor Danbooru/e621-style tag prompting over natural-language sentences. Preserve useful wildcard refs, dynamic prompt syntax,
weights, LoRA syntax, BREAK, score/rating/source tags, character names, series/copyright tags, artist/style tags, poses,
clothing, background, lighting, and quality tags. Order positive prompts roughly as: character count, character,
series/copyright, artist/style, anatomy/details, clothing, pose/action/expression, background/camera/lighting, quality.
Use concise comma-separated tags unless the task explicitly asks for JSON. Keep all output reviewable; never silently apply edits.
""".strip()



def seed_taxonomy_defaults(conn: sqlite3.Connection) -> None:
    existing = conn.execute("SELECT COUNT(*) AS count FROM taxonomy_rules").fetchone()["count"]
    if existing:
        return
    now = utc_now()
    conn.executemany(
        "INSERT OR IGNORE INTO taxonomy_rules(category, keyword, enabled, updated_at) VALUES (?, ?, 1, ?)",
        [(category, keyword, now) for category, keywords in CATEGORY_RULES.items() for keyword in keywords],
    )
    conn.execute(
        "INSERT OR REPLACE INTO taxonomy_meta(key, value, updated_at) VALUES ('version', ?, ?)",
        (now, now),
    )


@lru_cache(maxsize=1)
def taxonomy_rules_cached() -> dict[str, tuple[str, ...]]:
    if not DB_PATH.exists():
        return CATEGORY_RULES
    try:
        with connect() as conn:
            rows = conn.execute(
                "SELECT category, keyword FROM taxonomy_rules WHERE enabled = 1 ORDER BY category, keyword"
            ).fetchall()
    except sqlite3.Error:
        return CATEGORY_RULES
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        grouped[row["category"]].append(row["keyword"])
    return {category: tuple(keywords) for category, keywords in grouped.items()} or CATEGORY_RULES


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS source_files (
                id INTEGER PRIMARY KEY,
                original_path TEXT NOT NULL UNIQUE,
                relative_path TEXT NOT NULL,
                extension TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                last_modified TEXT NOT NULL,
                wildcard_path TEXT NOT NULL,
                import_status TEXT NOT NULL,
                warning_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY,
                source_file_id INTEGER NOT NULL REFERENCES source_files(id) ON DELETE CASCADE,
                wildcard_path TEXT NOT NULL,
                item_index INTEGER NOT NULL,
                raw_text TEXT NOT NULL,
                staged_text TEXT,
                normalized_text TEXT NOT NULL,
                kind TEXT NOT NULL,
                prompt_mode TEXT NOT NULL DEFAULT 'unknown',
                tags_json TEXT NOT NULL,
                positive_tags_json TEXT NOT NULL DEFAULT '[]',
                negative_tags_json TEXT NOT NULL DEFAULT '[]',
                all_extracted_tags_json TEXT NOT NULL DEFAULT '[]',
                prompt_parts_json TEXT NOT NULL DEFAULT '{}',
                tag_categories_json TEXT NOT NULL DEFAULT '[]',
                refs_json TEXT NOT NULL,
                warnings_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS entry_history (
                id INTEGER PRIMARY KEY,
                entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
                previous_text TEXT,
                next_text TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS scan_runs (
                id INTEGER PRIMARY KEY,
                source_root TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tag_index (
                tag TEXT NOT NULL,
                category TEXT NOT NULL,
                usage_count INTEGER NOT NULL,
                PRIMARY KEY (tag, category)
            );

            CREATE TABLE IF NOT EXISTS category_index (
                category TEXT PRIMARY KEY,
                usage_count INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS category_stats (
                category TEXT PRIMARY KEY,
                entry_count INTEGER NOT NULL,
                file_count INTEGER NOT NULL,
                tag_count INTEGER NOT NULL,
                wildcard_count INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS prompt_mode_index (
                prompt_mode TEXT PRIMARY KEY,
                entry_count INTEGER NOT NULL,
                file_count INTEGER NOT NULL,
                wildcard_count INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS prompt_recipes (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                preset TEXT NOT NULL,
                slots_json TEXT NOT NULL,
                negative_tags_json TEXT NOT NULL,
                wildcard_refs_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tag_overrides (
                tag TEXT PRIMARY KEY,
                canonical_tag TEXT,
                category TEXT,
                is_ignored INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS taxonomy_rules (
                category TEXT NOT NULL,
                keyword TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (category, keyword)
            );

            CREATE TABLE IF NOT EXISTS taxonomy_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS source_file_stats (
                source_file_id INTEGER PRIMARY KEY REFERENCES source_files(id) ON DELETE CASCADE,
                entry_count INTEGER NOT NULL DEFAULT 0,
                prompt_count INTEGER NOT NULL DEFAULT 0,
                duplicate_count INTEGER NOT NULL DEFAULT 0,
                unresolved_refs INTEGER NOT NULL DEFAULT 0,
                categories_json TEXT NOT NULL DEFAULT '[]',
                prompt_modes_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS llm_jobs (
                id INTEGER PRIMARY KEY,
                task TEXT NOT NULL,
                prompt_mode TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                model TEXT NOT NULL,
                input_text TEXT NOT NULL,
                status TEXT NOT NULL,
                suggestion TEXT NOT NULL DEFAULT '',
                error TEXT,
                endpoint_used TEXT,
                raw_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                accepted_at TEXT,
                rejected_at TEXT,
                cancelled_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_entries_source_file ON entries(source_file_id);
            CREATE INDEX IF NOT EXISTS idx_entries_wildcard_path ON entries(wildcard_path);
            CREATE INDEX IF NOT EXISTS idx_entries_normalized ON entries(normalized_text);
            CREATE INDEX IF NOT EXISTS idx_source_files_wildcard_path ON source_files(wildcard_path);
            """
        )
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(entries)").fetchall()}
        if "tag_categories_json" not in columns:
            conn.execute("ALTER TABLE entries ADD COLUMN tag_categories_json TEXT NOT NULL DEFAULT '[]'")
        if "prompt_mode" not in columns:
            conn.execute("ALTER TABLE entries ADD COLUMN prompt_mode TEXT NOT NULL DEFAULT 'unknown'")
        if "positive_tags_json" not in columns:
            conn.execute("ALTER TABLE entries ADD COLUMN positive_tags_json TEXT NOT NULL DEFAULT '[]'")
        if "negative_tags_json" not in columns:
            conn.execute("ALTER TABLE entries ADD COLUMN negative_tags_json TEXT NOT NULL DEFAULT '[]'")
        if "all_extracted_tags_json" not in columns:
            conn.execute("ALTER TABLE entries ADD COLUMN all_extracted_tags_json TEXT NOT NULL DEFAULT '[]'")
        if "prompt_parts_json" not in columns:
            conn.execute("ALTER TABLE entries ADD COLUMN prompt_parts_json TEXT NOT NULL DEFAULT '{}'")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entries_prompt_mode ON entries(prompt_mode)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tag_polarity_index (
                tag TEXT NOT NULL,
                category TEXT NOT NULL,
                polarity TEXT NOT NULL,
                usage_count INTEGER NOT NULL,
                PRIMARY KEY (tag, category, polarity)
            )
            """
        )
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS entry_fts USING fts5(effective_text, wildcard_path, tags)")
        seed_taxonomy_defaults(conn)


def reset_library(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS entry_fts;
        DELETE FROM entry_history;
        DELETE FROM entries;
        DELETE FROM source_files;
        DELETE FROM tag_index;
        DELETE FROM tag_polarity_index;
        DELETE FROM category_index;
        DELETE FROM category_stats;
        DELETE FROM prompt_mode_index;
        DELETE FROM source_file_stats;
        CREATE VIRTUAL TABLE entry_fts USING fts5(effective_text, wildcard_path, tags);
        """
    )


def clear_aggregate_indexes(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DELETE FROM tag_index;
        DELETE FROM tag_polarity_index;
        DELETE FROM category_index;
        DELETE FROM category_stats;
        DELETE FROM prompt_mode_index;
        DELETE FROM source_file_stats;
        """
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_text(text: str) -> str:
    value = text.strip().lower()
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"\s*,\s*", ", ", value)
    return value


def path_to_wildcard(relative_path: Path) -> str:
    without_suffix = relative_path.with_suffix("")
    return "/".join(without_suffix.parts)


def split_prompt_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    depth = 0
    for char in text:
        if char in "({[":
            depth += 1
        elif char in ")}]" and depth > 0:
            depth -= 1
        if char == "," and depth == 0:
            token = "".join(current).strip()
            if token:
                tokens.append(clean_tag(token))
            current = []
        else:
            current.append(char)
    token = "".join(current).strip()
    if token:
        tokens.append(clean_tag(token))
    return [token for token in tokens if token and len(token) <= 80]


def clean_tag(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^\(+|\)+$", "", value)
    value = re.sub(r":[0-9.]+\)?$", "", value)
    value = value.strip("{}[]() ")
    value = value.replace("\\(", "(").replace("\\)", ")")
    return value


def stable_unique(values: Iterable[str], limit: int = 160) -> list[str]:
    stable: list[str] = []
    seen = set()
    ignored = {"", "break", "and", "or", "|", "negative prompt", "negative"}
    for value in values:
        cleaned = clean_tag(value)
        lowered = cleaned.lower().strip().replace("_", " ")
        if lowered in ignored or lowered.startswith("#"):
            continue
        if lowered not in seen:
            seen.add(lowered)
            stable.append(cleaned)
        if len(stable) >= limit:
            break
    return stable


def strip_dynamic_weight(value: str) -> str:
    value = re.sub(r"^\s*-?\d+(?:-\d+)?\$\$", "", value)
    value = re.sub(r"^\s*\d+(?:\.\d+)?::", "", value)
    return value.strip()


def dynamic_options(text: str) -> list[str]:
    options: list[str] = []
    for match in re.finditer(r"\{([^{}]+)\}", text):
        content = match.group(1)
        if "|" not in content and "$$" not in content and "::" not in content:
            continue
        if "$$" in content:
            content = content.split("$$", 1)[1]
        for option in content.split("|"):
            cleaned = strip_dynamic_weight(option)
            if cleaned:
                options.append(cleaned)
    return options


def prompt_sections(text: str) -> tuple[str, str, list[str]]:
    warnings: list[str] = []
    matches = list(NEGATIVE_PROMPT_RE.finditer(text))
    if not matches:
        return text, "", warnings
    if len(matches) > 1:
        warnings.append("Multiple negative prompt markers; using the first marker")
    first = matches[0]
    positive = text[: first.start()].strip(" \n\r,")
    negative = text[first.end() :].strip(" \n\r,")
    if not positive:
        warnings.append("Negative prompt marker found without a positive section")
    if not negative:
        warnings.append("Negative prompt marker found without negative tags")
    return positive, negative, warnings


def prose_phrase_candidates(text: str) -> list[str]:
    lowered = text.lower()
    phrases = []
    known_phrases = (
        "depth of field",
        "shallow depth of field",
        "golden hour",
        "studio lighting",
        "cinematic lighting",
        "volumetric lighting",
        "soft lighting",
        "wide shot",
        "close-up",
        "full body",
        "realistic texture",
        "realistic textures",
        "wet pavement",
        "rainy street",
        "foreground",
        "background",
        "middle ground",
        "portrait",
        "photo",
        "photograph",
        "illustration",
        "oil painting",
        "watercolor painting",
    )
    for phrase in known_phrases:
        if phrase in lowered:
            phrases.append(phrase)
    for pattern in (
        r"\bwearing\s+(?:a|an|the)?\s*([a-z0-9 _-]{3,48})",
        r"\bholding\s+(?:a|an|the)?\s*([a-z0-9 _-]{3,48})",
        r"\b(?:standing|sitting|walking)\s+(?:in|on|through|near)\s+(?:a|an|the)?\s*([a-z0-9 _-]{3,48})",
        r"\bshot on\s+(?:a|an|the)?\s*([a-z0-9 _-]{3,48})",
    ):
        for match in re.finditer(pattern, lowered):
            phrase = re.split(r"\b(?:with|while|during|and|,|\.|;)\b", match.group(1), maxsplit=1)[0].strip()
            words = phrase.split()
            if 1 <= len(words) <= 6:
                phrases.append(phrase)
    return stable_unique(phrases, 24)


def prompt_tag_candidates(section_text: str, include_refs: bool = True) -> list[str]:
    refs = [ref.replace("/", " ") for ref in detect_refs(section_text)] if include_refs else []
    text = WILDCARD_REF_RE.sub(" ", section_text)
    text = LORA_RE.sub(" ", text)
    options = dynamic_options(text)
    text = re.sub(r"\bBREAK\b", ",", text, flags=re.IGNORECASE)
    for option in options:
        text += f", {option}"
    text = re.sub(r"[{}|]", ",", text)
    text = re.sub(r"\b\d+(?:\.\d+)?::", "", text)
    has_commas = "," in text
    chunks = split_prompt_tokens(text) if has_commas else re.split(r"[;\n]+", text)
    tags: list[str] = []
    for chunk in chunks:
        cleaned = clean_tag(chunk)
        if not cleaned:
            continue
        if is_builder_tag(cleaned) or (has_commas and len(cleaned) <= 80 and not cleaned.lower().startswith(("a ", "an ", "the "))):
            tags.append(cleaned)
        else:
            tags.extend(prose_phrase_candidates(cleaned))
    tags.extend(split_prompt_tokens(ref.replace("_", " ")) for ref in refs)
    flattened: list[str] = []
    for item in tags:
        if isinstance(item, list):
            flattened.extend(item)
        else:
            flattened.append(item)
    return stable_unique(flattened)


def parse_prompt_text(text: str) -> dict[str, Any]:
    positive_text, negative_text, section_warnings = prompt_sections(text)
    positive_tags = prompt_tag_candidates(positive_text or text, include_refs=True)
    negative_tags = prompt_tag_candidates(negative_text, include_refs=False) if negative_text else []
    refs = detect_refs(text)
    loras = LORA_RE.findall(text)
    dynamic = dynamic_options(text)
    all_tags = stable_unique([*positive_tags, *negative_tags, *[ref.replace("/", " ") for ref in refs]])
    return {
        "positive_text": positive_text or text,
        "negative_text": negative_text,
        "positive_tags": positive_tags,
        "negative_tags": negative_tags,
        "all_extracted_tags": all_tags,
        "refs": refs,
        "loras": loras,
        "dynamic_options": stable_unique(dynamic, 120),
        "break_count": len(re.findall(r"\bBREAK\b", text, flags=re.IGNORECASE)),
        "warnings": section_warnings,
    }


def detect_tags(text: str) -> list[str]:
    parsed = parse_prompt_text(text)
    return stable_unique([*parsed["positive_tags"], *[ref.replace("/", " ") for ref in parsed["refs"]]], 80)


def detect_categories(text: str, wildcard_path: str, source_name: str = "", tags: list[str] | None = None) -> list[str]:
    haystack_parts = [text, wildcard_path, source_name, *(tags if tags is not None else detect_tags(text))]
    haystack = " ".join(haystack_parts).replace("_", " ").replace("-", " ").lower()
    padded = f" {haystack} "
    categories = []
    for category, needles in taxonomy_rules_cached().items():
        matched = False
        for needle in needles:
            normalized_needle = needle.replace("_", " ").replace("-", " ").lower()
            if normalized_needle.endswith("_") or normalized_needle.endswith(" "):
                matched = normalized_needle.rstrip() in haystack
            elif " " in normalized_needle:
                matched = f" {normalized_needle} " in padded
            else:
                matched = re.search(rf"(?<![a-z0-9]){re.escape(normalized_needle)}(?![a-z0-9])", haystack) is not None
            if matched:
                break
        if matched:
            categories.append(category)
    return categories or ["general"]


def is_builder_tag(tag: str) -> bool:
    value = tag.strip()
    lowered = value.lower()
    if not value or len(value) > 64:
        return False
    words = re.findall(r"[a-zA-Z0-9_()'-]+", value)
    if len(words) > 5:
        return False
    prose_markers = (" with ", " and ", " while ", " that ", " at the ", " in the ", " of a ", " of the ")
    if any(marker in lowered for marker in prose_markers) and "_" not in value:
        return False
    if lowered.startswith(("a ", "an ", "the ")):
        return False
    return True


def copyright_path_terms(wildcard_path: str) -> list[str]:
    ignored = {
        "copyright",
        "series",
        "franchise",
        "source",
        "characters",
        "character",
        "chars",
        "random",
        "prompt",
        "prompts",
        "card",
        "cards",
        "female",
        "male",
        "any",
        "anything",
    }
    terms = []
    for part in re.split(r"[\\/]+", wildcard_path):
        cleaned = part.replace("_", " ").replace("-", " ").strip()
        if cleaned and cleaned.lower() not in ignored and is_builder_tag(cleaned):
            terms.append(cleaned)
    return terms[:8]


@lru_cache(maxsize=200_000)
def cached_builder_tag_categories(tag: str) -> tuple[str, ...]:
    return tuple(detect_categories(tag, ""))


def detect_refs(text: str) -> list[str]:
    refs = []
    seen = set()
    for match in WILDCARD_REF_RE.finditer(text):
        ref = match.group(1).strip()
        if not is_valid_wildcard_ref(ref):
            continue
        lowered = ref.lower()
        if ref and lowered not in seen:
            refs.append(ref)
            seen.add(lowered)
    return refs


def is_valid_wildcard_ref(ref: str) -> bool:
    if not ref or len(ref) > 180:
        return False
    if any(char in ref for char in "\n\r,{}|\"'():"):
        return False
    if re.search(r"\s{2,}", ref):
        return False
    lowered = ref.strip().lower()
    if lowered in {"a", "an", "and", "or", "the", "with", "from", "of", "on", "in"}:
        return False
    parts = [part.strip() for part in re.split(r"[\\/]", ref) if part.strip()]
    if not parts:
        return False
    word_count = len(" ".join(parts).split())
    if word_count > 10:
        return False
    if len(parts) == 1 and word_count > 4:
        return False
    if len(parts) == 1 and re.search(r"\b(?:the|of|with|while|from|amidst|through)\b", lowered):
        return False
    return all(re.fullmatch(r"[A-Za-z0-9 _.*+\-]+", part) for part in parts)


def ref_is_resolved(ref: str, known: set[str]) -> bool:
    normalized = ref.replace("\\", "/").rstrip("/").lower()
    if "*" in normalized:
        if normalized.endswith("/*"):
            prefix = normalized[:-2]
            return any(path == prefix or path.startswith(f"{prefix}/") for path in known)
        return any(fnmatch.fnmatch(path, normalized) for path in known)
    return normalized.rstrip("/*") in known


def detect_warnings(text: str) -> list[str]:
    warnings: list[str] = []
    if text.count("{") != text.count("}"):
        warnings.append("Unbalanced dynamic prompt braces")
    if text.count("__") % 2 != 0:
        warnings.append("Unbalanced wildcard markers")
    if "$$" in text and not MULTI_SELECT_RE.search(text):
        warnings.append("Possible malformed multi-select syntax")
    if re.search(r"\{\s*\d+:[^:]", text):
        warnings.append("Legacy single-colon weight syntax; Impact expects n::option")
    if LORA_RE.search(text):
        warnings.append("Contains LoRA loader syntax")
    if "BREAK" in text:
        warnings.append("Contains BREAK conditioning separator")
    if WEIGHTED_DYNAMIC_RE.search(text):
        warnings.append("Contains weighted dynamic prompt")
    return warnings


def detect_kind(text: str, source_name: str) -> str:
    lowered = f"{source_name} {text}".lower()
    if "__" in text or ("{" in text and "|" in text) or any(word in lowered for word in ("prompt", "scene", "card", "fullprompt")):
        return "prompt"
    if "," in text and len(detect_tags(text)) > 1:
        return "tag_list"
    return "wildcard_item"


def detect_prompt_mode(text: str, wildcard_path: str = "", source_name: str = "", kind: str | None = None) -> str:
    value = text.strip()
    if not value:
        return "unknown"
    lowered = f"{source_name} {wildcard_path} {value}".lower()
    tokens = detect_tags(value)
    comma_count = value.count(",")
    sentence_count = len(re.findall(r"[.!?](?:\s|$)", value))
    word_count = len(re.findall(r"\b[a-zA-Z]{2,}\b", value))
    tag_like = sum(
        1
        for token in tokens
        if re.fullmatch(r"[a-z0-9_:'()\\\-/ ]{1,48}", token.lower())
        and not token.lower().startswith(("a ", "an ", "the "))
    )
    danbooru_markers = (
        "1girl",
        "1boy",
        "solo",
        "looking_at_viewer",
        "score_",
        "source_anime",
        "rating_",
        "masterpiece",
        "best quality",
        "very aesthetic",
        "absurdres",
        "highres",
        "danbooru",
        "illustrious",
        "noobai",
    )
    sdxl_markers = (
        "photo",
        "photograph",
        "shot on",
        "captured with",
        "camera",
        "lens",
        "depth of field",
        "bokeh",
        "foreground",
        "middle ground",
        "background",
        "atmosphere",
        "cinematic",
        "studio lighting",
        "golden hour",
        "portrait of",
        "wearing a",
        "standing in",
        "sitting in",
    )
    danbooru_score = 0
    if comma_count >= 3 and tag_like >= 4:
        danbooru_score += 3
    if any(marker in lowered for marker in danbooru_markers):
        danbooru_score += 2
    if "_" in value or "__" in value or LORA_RE.search(value):
        danbooru_score += 1
    if kind == "tag_list":
        danbooru_score += 1

    sdxl_score = 0
    if word_count >= 18 and (sentence_count >= 1 or comma_count <= 2):
        sdxl_score += 3
    if any(marker in lowered for marker in sdxl_markers):
        sdxl_score += 2
    if re.search(r"\b(a|an|the)\s+[a-z]+", lowered) and any(marker in lowered for marker in (" with ", " while ", " during ", " in a ", " on a ")):
        sdxl_score += 1
    if len(tokens) <= 3 and word_count >= 12:
        sdxl_score += 1

    if sdxl_score >= 3 and danbooru_score >= 3:
        return "mixed"
    if sdxl_score > danbooru_score and sdxl_score >= 3:
        return "sdxl_natural"
    if danbooru_score >= 2:
        return "danbooru_tags"
    return "unknown"


def flatten_yaml(node: Any, prefix: list[str] | None = None, warnings: list[str] | None = None) -> Iterable[tuple[str, str]]:
    prefix = prefix or []
    warnings = warnings if warnings is not None else []
    if isinstance(node, dict):
        for key, value in node.items():
            yield from flatten_yaml(value, [*prefix, str(key)], warnings)
    elif isinstance(node, list):
        wildcard_path = "/".join(prefix)
        if not node:
            warnings.append(f"Empty YAML array ignored at {wildcard_path or '<root>'}")
        for item in node:
            if isinstance(item, dict):
                warnings.append(f"Unsupported YAML object inside array at {wildcard_path or '<root>'}")
            elif isinstance(item, list):
                warnings.append(f"Unsupported nested YAML array at {wildcard_path or '<root>'}")
            elif item is not None:
                yield wildcard_path, str(item)
    elif node is not None:
        warnings.append(f"Scalar YAML leaf ignored at {'/'.join(prefix) or '<root>'}")


def parse_txt(path: Path) -> list[tuple[str, list[str]]]:
    entries: list[tuple[str, list[str]]] = []
    with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
        for line in handle:
            raw = line.rstrip("\r\n")
            if not raw.strip() or COMMENT_RE.match(raw):
                continue
            entries.append((raw, []))
    return entries


def parse_yaml_file(path: Path) -> tuple[list[tuple[str, str, list[str]]], list[str]]:
    warnings: list[str] = []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8-sig", errors="replace"))
    except Exception as exc:  # noqa: BLE001
        return [], [f"YAML parse failed: {exc}"]
    if data is None:
        return [], [f"Empty YAML file: {path.name}"]
    if not isinstance(data, dict):
        return [], [f"YAML root must be a mapping for wildcard hierarchy: {path.name}"]
    entries: list[tuple[str, str, list[str]]] = []
    for wildcard_path, text in flatten_yaml(data, warnings=warnings):
        if not wildcard_path:
            warnings.append(f"Skipped YAML value without path in {path.name}")
            continue
        if text.strip():
            entries.append((wildcard_path, text, []))
    return entries, warnings


def insert_entry(
    conn: sqlite3.Connection,
    source_file_id: int,
    wildcard_path: str,
    item_index: int,
    text: str,
    source_name: str,
    extra_warnings: list[str] | None = None,
) -> tuple[int, list[str], list[str], str, list[str], list[str], list[str]]:
    parsed = parse_prompt_text(text)
    positive_tags = parsed["positive_tags"]
    negative_tags = parsed["negative_tags"]
    all_extracted_tags = parsed["all_extracted_tags"]
    warnings = [*(extra_warnings or []), *detect_warnings(text), *parsed["warnings"]]
    tags = stable_unique([*positive_tags, *[ref.replace("/", " ") for ref in parsed["refs"]]], 80)
    categories = detect_categories(text, wildcard_path, source_name, all_extracted_tags or tags)
    refs = parsed["refs"]
    kind = detect_kind(text, source_name)
    prompt_mode = detect_prompt_mode(text, wildcard_path, source_name, kind)
    now = utc_now()
    cur = conn.execute(
        """
        INSERT INTO entries (
            source_file_id, wildcard_path, item_index, raw_text, staged_text,
            normalized_text, kind, prompt_mode, tags_json, positive_tags_json, negative_tags_json,
            all_extracted_tags_json, prompt_parts_json, tag_categories_json, refs_json, warnings_json,
            created_at, updated_at
        )
        VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_file_id,
            wildcard_path,
            item_index,
            text,
            normalize_text(text),
            kind,
            prompt_mode,
            json.dumps(tags, ensure_ascii=False),
            json.dumps(positive_tags, ensure_ascii=False),
            json.dumps(negative_tags, ensure_ascii=False),
            json.dumps(all_extracted_tags, ensure_ascii=False),
            json.dumps(
                {
                    "positive_text": parsed["positive_text"],
                    "negative_text": parsed["negative_text"],
                    "loras": parsed["loras"],
                    "dynamic_options": parsed["dynamic_options"],
                    "break_count": parsed["break_count"],
                },
                ensure_ascii=False,
            ),
            json.dumps(categories, ensure_ascii=False),
            json.dumps(refs, ensure_ascii=False),
            json.dumps(warnings, ensure_ascii=False),
            now,
            now,
        ),
    )
    entry_id = int(cur.lastrowid)
    conn.execute(
        "INSERT INTO entry_fts(rowid, effective_text, wildcard_path, tags) VALUES (?, ?, ?, ?)",
        (entry_id, text, wildcard_path, " ".join(all_extracted_tags or tags)),
    )
    return entry_id, tags, categories, prompt_mode, positive_tags, negative_tags, all_extracted_tags


def rebuild_source_file_stats(conn: sqlite3.Connection) -> None:
    duplicate_norms = {
        row["normalized_text"]
        for row in conn.execute(
            """
            SELECT normalized_text
            FROM entries
            WHERE normalized_text != ''
            GROUP BY normalized_text
            HAVING COUNT(*) > 1
            """
        ).fetchall()
    }
    known_paths = {row["wildcard_path"].lower() for row in conn.execute("SELECT DISTINCT wildcard_path FROM entries")}
    rows = conn.execute("SELECT id FROM source_files").fetchall()
    conn.execute("DELETE FROM source_file_stats")
    stat_rows = []
    now = utc_now()
    for source_row in rows:
        entry_rows = conn.execute(
            """
            SELECT kind, normalized_text, refs_json, tag_categories_json, prompt_mode
            FROM entries
            WHERE source_file_id = ?
            """,
            (source_row["id"],),
        ).fetchall()
        categories: set[str] = set()
        prompt_modes: Counter[str] = Counter()
        unresolved = 0
        duplicate_count = 0
        prompt_count = 0
        for entry in entry_rows:
            categories.update(json.loads(entry["tag_categories_json"] or "[]"))
            prompt_modes[entry["prompt_mode"]] += 1
            if entry["kind"] == "prompt":
                prompt_count += 1
            if entry["normalized_text"] in duplicate_norms:
                duplicate_count += 1
            for ref in json.loads(entry["refs_json"] or "[]"):
                if ref and not ref_is_resolved(ref, known_paths):
                    unresolved += 1
        stat_rows.append(
            (
                source_row["id"],
                len(entry_rows),
                prompt_count,
                duplicate_count,
                unresolved,
                json.dumps(sorted(categories, key=str.lower)),
                json.dumps(dict(prompt_modes)),
                now,
            )
        )
    conn.executemany(
        """
        INSERT INTO source_file_stats(
            source_file_id, entry_count, prompt_count, duplicate_count, unresolved_refs,
            categories_json, prompt_modes_json, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        stat_rows,
    )


def rebuild_aggregate_indexes(conn: sqlite3.Connection) -> None:
    clear_aggregate_indexes(conn)
    tag_totals: Counter[str] = Counter()
    tag_category_totals: Counter[tuple[str, str]] = Counter()
    tag_polarity_totals: Counter[tuple[str, str, str]] = Counter()
    category_totals: Counter[str] = Counter()
    category_files: dict[str, set[str]] = defaultdict(set)
    category_wildcards: dict[str, set[str]] = defaultdict(set)
    prompt_mode_totals: Counter[str] = Counter()
    prompt_mode_files: dict[str, set[str]] = defaultdict(set)
    prompt_mode_wildcards: dict[str, set[str]] = defaultdict(set)
    rows = conn.execute(
        """
        SELECT e.*, sf.relative_path
        FROM entries e
        JOIN source_files sf ON sf.id = e.source_file_id
        """
    ).fetchall()
    for row in rows:
        categories = json.loads(row["tag_categories_json"] or "[]")
        positive_tags = json.loads(row["positive_tags_json"] or "[]")
        negative_tags = json.loads(row["negative_tags_json"] or "[]")
        all_extracted_tags = json.loads(row["all_extracted_tags_json"] or "[]")
        wildcard_path = row["wildcard_path"]
        relative = row["relative_path"]
        prompt_mode = row["prompt_mode"]
        prompt_mode_totals[prompt_mode] += 1
        prompt_mode_files[prompt_mode].add(relative)
        prompt_mode_wildcards[prompt_mode].add(wildcard_path)
        category_totals.update(categories)
        for category in categories:
            category_files[category].add(relative)
            category_wildcards[category].add(wildcard_path)
        for tag in all_extracted_tags:
            tag_totals[tag] += 1
            if not is_builder_tag(tag):
                continue
            direct_categories = set(cached_builder_tag_categories(tag))
            if "characters" in categories:
                direct_categories.add("characters")
            for category in direct_categories:
                tag_category_totals[(tag, category)] += 1
        for polarity, polarity_tags in (("positive", positive_tags), ("negative", negative_tags), ("all", all_extracted_tags)):
            for tag in polarity_tags:
                if not is_builder_tag(tag):
                    continue
                direct_categories = set(cached_builder_tag_categories(tag))
                for category in direct_categories:
                    tag_polarity_totals[(tag, category, polarity)] += 1
                tag_polarity_totals[(tag, "__all__", polarity)] += 1
        if "copyright" in categories:
            for term in copyright_path_terms(wildcard_path):
                tag_category_totals[(term, "copyright")] += 1

    conn.executemany(
        "INSERT INTO tag_index(tag, category, usage_count) VALUES (?, ?, ?)",
        [(tag, "__all__", count) for tag, count in tag_totals.items()],
    )
    conn.executemany(
        "INSERT INTO tag_index(tag, category, usage_count) VALUES (?, ?, ?)",
        [(tag, category, count) for (tag, category), count in tag_category_totals.items()],
    )
    conn.executemany(
        "INSERT INTO tag_polarity_index(tag, category, polarity, usage_count) VALUES (?, ?, ?, ?)",
        [(tag, category, polarity, count) for (tag, category, polarity), count in tag_polarity_totals.items()],
    )
    conn.executemany("INSERT INTO category_index(category, usage_count) VALUES (?, ?)", list(category_totals.items()))
    conn.executemany(
        "INSERT INTO category_stats(category, entry_count, file_count, tag_count, wildcard_count) VALUES (?, ?, ?, ?, ?)",
        [
            (
                category,
                entry_count,
                len(category_files[category]),
                sum(1 for (_, tag_category), _count in tag_category_totals.items() if tag_category == category),
                len(category_wildcards[category]),
            )
            for category, entry_count in category_totals.items()
        ],
    )
    conn.executemany(
        "INSERT INTO prompt_mode_index(prompt_mode, entry_count, file_count, wildcard_count) VALUES (?, ?, ?, ?)",
        [
            (
                mode,
                prompt_mode_totals.get(mode, 0),
                len(prompt_mode_files.get(mode, set())),
                len(prompt_mode_wildcards.get(mode, set())),
            )
            for mode in PROMPT_MODES
            if prompt_mode_totals.get(mode, 0)
        ],
    )
    rebuild_source_file_stats(conn)


def scan_library(source_root: Path, reset: bool, mode: Literal["incremental", "reset"] | None = None) -> ScanSummary:
    if not source_root.exists():
        raise HTTPException(status_code=404, detail=f"Source root does not exist: {source_root}")
    scan_mode: Literal["incremental", "reset"] = "reset" if reset or mode == "reset" else "incremental"
    reset = scan_mode == "reset"

    files = [
        path
        for path in source_root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".txt", ".yaml", ".yml"}
    ]
    summary_warnings: list[str] = []
    total_bytes = sum(path.stat().st_size for path in files)
    indexed_files = 0
    skipped_files = 0
    indexed_entries = 0
    txt_files = 0
    yaml_files = 0
    tag_totals: Counter[str] = Counter()
    tag_category_totals: Counter[tuple[str, str]] = Counter()
    tag_polarity_totals: Counter[tuple[str, str, str]] = Counter()
    category_totals: Counter[str] = Counter()
    category_files: dict[str, set[str]] = defaultdict(set)
    category_wildcards: dict[str, set[str]] = defaultdict(set)
    prompt_mode_totals: Counter[str] = Counter()
    prompt_mode_files: dict[str, set[str]] = defaultdict(set)
    prompt_mode_wildcards: dict[str, set[str]] = defaultdict(set)

    with connect() as conn:
        if reset:
            reset_library(conn)
        else:
            current_paths = {str(path) for path in files}
            for row in conn.execute("SELECT id, original_path FROM source_files").fetchall():
                if row["original_path"] not in current_paths:
                    conn.execute("DELETE FROM source_files WHERE id = ?", (row["id"],))
        for path in files:
            relative = path.relative_to(source_root)
            extension = path.suffix.lower()
            wildcard_path = path_to_wildcard(relative)
            stat = path.stat()
            file_warnings: list[str] = []
            now = utc_now()
            last_modified = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
            if not reset:
                existing = conn.execute(
                    """
                    SELECT id, size_bytes, last_modified, import_status
                    FROM source_files
                    WHERE original_path = ?
                    """,
                    (str(path),),
                ).fetchone()
                if (
                    existing
                    and existing["size_bytes"] == stat.st_size
                    and existing["last_modified"] == last_modified
                    and existing["import_status"] == "indexed"
                ):
                    skipped_files += 1
                    continue
            file_hash = sha256_file(path)
            cur = conn.execute(
                """
                INSERT OR REPLACE INTO source_files (
                    id, original_path, relative_path, extension, size_bytes, sha256,
                    last_modified, wildcard_path, import_status, warning_count, created_at, updated_at
                )
                VALUES (
                    (SELECT id FROM source_files WHERE original_path = ?), ?, ?, ?, ?, ?, ?, ?, ?, 0,
                    COALESCE((SELECT created_at FROM source_files WHERE original_path = ?), ?), ?
                )
                """,
                (
                    str(path),
                    str(path),
                    relative.as_posix(),
                    extension,
                    stat.st_size,
                    file_hash,
                    last_modified,
                    wildcard_path,
                    "indexed",
                    str(path),
                    now,
                    now,
                ),
            )
            source_file_id = int(cur.lastrowid or conn.execute("SELECT id FROM source_files WHERE original_path = ?", (str(path),)).fetchone()["id"])
            conn.execute("DELETE FROM entries WHERE source_file_id = ?", (source_file_id,))

            try:
                if extension == ".txt":
                    txt_files += 1
                    entries = parse_txt(path)
                    for index, (text, warnings) in enumerate(entries):
                        _, tags, categories, prompt_mode, positive_tags, negative_tags, all_extracted_tags = insert_entry(conn, source_file_id, wildcard_path, index, text, path.name, warnings)
                        prompt_mode_totals[prompt_mode] += 1
                        prompt_mode_files[prompt_mode].add(str(relative))
                        prompt_mode_wildcards[prompt_mode].add(wildcard_path)
                        category_totals.update(categories)
                        for category in categories:
                            category_files[category].add(str(relative))
                            category_wildcards[category].add(wildcard_path)
                        for tag in all_extracted_tags:
                            tag_totals[tag] += 1
                            if not is_builder_tag(tag):
                                continue
                            direct_categories = set(cached_builder_tag_categories(tag))
                            if "characters" in categories and is_builder_tag(tag):
                                direct_categories.add("characters")
                            for category in direct_categories:
                                tag_category_totals[(tag, category)] += 1
                        for polarity, polarity_tags in (("positive", positive_tags), ("negative", negative_tags), ("all", all_extracted_tags)):
                            for tag in polarity_tags:
                                if not is_builder_tag(tag):
                                    continue
                                direct_categories = set(cached_builder_tag_categories(tag))
                                for category in direct_categories:
                                    tag_polarity_totals[(tag, category, polarity)] += 1
                                tag_polarity_totals[(tag, "__all__", polarity)] += 1
                        if "copyright" in categories:
                            for term in copyright_path_terms(wildcard_path):
                                tag_category_totals[(term, "copyright")] += 1
                    indexed_entries += len(entries)
                else:
                    yaml_files += 1
                    yaml_entries, file_warnings = parse_yaml_file(path)
                    for index, (yaml_path, text, warnings) in enumerate(yaml_entries):
                        _, tags, categories, prompt_mode, positive_tags, negative_tags, all_extracted_tags = insert_entry(conn, source_file_id, yaml_path, index, text, path.name, warnings)
                        prompt_mode_totals[prompt_mode] += 1
                        prompt_mode_files[prompt_mode].add(str(relative))
                        prompt_mode_wildcards[prompt_mode].add(yaml_path)
                        category_totals.update(categories)
                        for category in categories:
                            category_files[category].add(str(relative))
                            category_wildcards[category].add(yaml_path)
                        for tag in all_extracted_tags:
                            tag_totals[tag] += 1
                            if not is_builder_tag(tag):
                                continue
                            direct_categories = set(cached_builder_tag_categories(tag))
                            if "characters" in categories and is_builder_tag(tag):
                                direct_categories.add("characters")
                            for category in direct_categories:
                                tag_category_totals[(tag, category)] += 1
                        for polarity, polarity_tags in (("positive", positive_tags), ("negative", negative_tags), ("all", all_extracted_tags)):
                            for tag in polarity_tags:
                                if not is_builder_tag(tag):
                                    continue
                                direct_categories = set(cached_builder_tag_categories(tag))
                                for category in direct_categories:
                                    tag_polarity_totals[(tag, category, polarity)] += 1
                                tag_polarity_totals[(tag, "__all__", polarity)] += 1
                        if "copyright" in categories:
                            for term in copyright_path_terms(yaml_path):
                                tag_category_totals[(term, "copyright")] += 1
                    indexed_entries += len(yaml_entries)
            except Exception as exc:  # noqa: BLE001
                file_warnings.append(f"Import failed: {exc}")
                conn.execute("UPDATE source_files SET import_status = ? WHERE id = ?", ("failed", source_file_id))

            if file_warnings:
                conn.execute(
                    "UPDATE source_files SET warning_count = ? WHERE id = ?",
                    (len(file_warnings), source_file_id),
                )
                summary_warnings.extend([f"{relative.as_posix()}: {warning}" for warning in file_warnings[:3]])
            indexed_files += 1

        if not reset:
            indexed_entries = conn.execute("SELECT COUNT(*) AS count FROM entries").fetchone()["count"]
            rebuild_aggregate_indexes(conn)
            summary = ScanSummary(
                source_root=str(source_root),
                scan_mode=scan_mode,
                files_seen=len(files),
                files_indexed=indexed_files + skipped_files,
                files_skipped=skipped_files,
                files_changed=indexed_files,
                entries_indexed=indexed_entries,
                txt_files=conn.execute("SELECT COUNT(*) AS count FROM source_files WHERE extension = '.txt'").fetchone()["count"],
                yaml_files=conn.execute("SELECT COUNT(*) AS count FROM source_files WHERE extension IN ('.yaml', '.yml')").fetchone()["count"],
                total_mb=round(total_bytes / (1024 * 1024), 2),
                warnings=summary_warnings[:200],
            )
            conn.execute(
                "INSERT INTO scan_runs(source_root, summary_json, created_at) VALUES (?, ?, ?)",
                (str(source_root), summary.model_dump_json(), utc_now()),
            )
            return summary

        conn.executemany(
            "INSERT INTO tag_index(tag, category, usage_count) VALUES (?, ?, ?)",
            [(tag, "__all__", count) for tag, count in tag_totals.items()],
        )
        conn.executemany(
            "INSERT INTO tag_index(tag, category, usage_count) VALUES (?, ?, ?)",
            [(tag, category, count) for (tag, category), count in tag_category_totals.items()],
        )
        conn.executemany(
            "INSERT INTO tag_polarity_index(tag, category, polarity, usage_count) VALUES (?, ?, ?, ?)",
            [(tag, category, polarity, count) for (tag, category, polarity), count in tag_polarity_totals.items()],
        )
        conn.executemany(
            "INSERT INTO category_index(category, usage_count) VALUES (?, ?)",
            list(category_totals.items()),
        )
        stat_rows = []
        for category, entry_count in category_totals.items():
            tag_count = sum(1 for (_, tag_category), _count in tag_category_totals.items() if tag_category == category)
            stat_rows.append(
                (
                    category,
                    entry_count,
                    len(category_files[category]),
                    tag_count,
                    len(category_wildcards[category]),
                )
            )
        conn.executemany(
            "INSERT INTO category_stats(category, entry_count, file_count, tag_count, wildcard_count) VALUES (?, ?, ?, ?, ?)",
            stat_rows,
        )
        conn.executemany(
            "INSERT INTO prompt_mode_index(prompt_mode, entry_count, file_count, wildcard_count) VALUES (?, ?, ?, ?)",
            [
                (
                    mode,
                    prompt_mode_totals.get(mode, 0),
                    len(prompt_mode_files.get(mode, set())),
                    len(prompt_mode_wildcards.get(mode, set())),
                )
                for mode in PROMPT_MODES
                if prompt_mode_totals.get(mode, 0)
            ],
        )
        rebuild_source_file_stats(conn)

        summary = ScanSummary(
            source_root=str(source_root),
            scan_mode=scan_mode,
            files_seen=len(files),
            files_indexed=indexed_files,
            files_skipped=skipped_files,
            files_changed=indexed_files,
            entries_indexed=indexed_entries,
            txt_files=txt_files,
            yaml_files=yaml_files,
            total_mb=round(total_bytes / (1024 * 1024), 2),
            warnings=summary_warnings[:200],
        )
        conn.execute(
            "INSERT INTO scan_runs(source_root, summary_json, created_at) VALUES (?, ?, ?)",
            (str(source_root), summary.model_dump_json(), utc_now()),
        )
        return summary


def run_background_scan(source: Path, reset: bool, mode: Literal["incremental", "reset"] | None = None) -> None:
    try:
        summary = scan_library(source, reset, mode)
        with SCAN_LOCK:
            SCAN_STATE.update(
                {
                    "running": False,
                    "finished_at": utc_now(),
                    "summary": summary.model_dump(),
                    "error": None,
                }
            )
    except Exception as exc:  # noqa: BLE001
        with SCAN_LOCK:
            SCAN_STATE.update(
                {
                    "running": False,
                    "finished_at": utc_now(),
                    "summary": None,
                    "error": str(exc),
                }
            )


def entry_from_row(row: sqlite3.Row) -> EntryItem:
    staged = row["staged_text"]
    raw = row["raw_text"]
    effective = staged if staged is not None else raw
    return EntryItem(
        id=row["id"],
        source_file_id=row["source_file_id"],
        wildcard_path=row["wildcard_path"],
        item_index=row["item_index"],
        raw_text=raw,
        staged_text=staged,
        effective_text=effective,
        normalized_text=row["normalized_text"],
        kind=row["kind"],
        prompt_mode=row["prompt_mode"],
        tags=json.loads(row["tags_json"] or "[]"),
        positive_tags=json.loads(row["positive_tags_json"] or "[]"),
        negative_tags=json.loads(row["negative_tags_json"] or "[]"),
        all_extracted_tags=json.loads(row["all_extracted_tags_json"] or "[]"),
        prompt_parts=json.loads(row["prompt_parts_json"] or "{}"),
        tag_categories=json.loads(row["tag_categories_json"] or "[]"),
        refs=json.loads(row["refs_json"] or "[]"),
        warnings=json.loads(row["warnings_json"] or "[]"),
        is_dirty=staged is not None and staged != raw,
    )


def wildcard_paths(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT DISTINCT wildcard_path FROM entries").fetchall()
    return {row["wildcard_path"].lower() for row in rows}


def list_wildcards(
    search: str = "",
    tag: str = "",
    tag_polarity: str = "all",
    kind: str = "",
    category: str = "",
    prompt_mode: str = "",
    limit: int = 250,
    offset: int = 0,
) -> list[WildcardListItem]:
    conditions = []
    params: list[Any] = []
    if search:
        conditions.append("(sf.relative_path LIKE ? OR sf.wildcard_path LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    if kind:
        conditions.append("EXISTS (SELECT 1 FROM entries ek WHERE ek.source_file_id = sf.id AND ek.kind = ?)")
        params.append(kind)
    if tag:
        polarity_column = {
            "positive": "positive_tags_json",
            "negative": "negative_tags_json",
            "all": "all_extracted_tags_json",
        }.get(tag_polarity, "all_extracted_tags_json")
        conditions.append(f"EXISTS (SELECT 1 FROM entries et WHERE et.source_file_id = sf.id AND et.{polarity_column} LIKE ?)")
        params.append(f"%{tag}%")
    if category:
        conditions.append("EXISTS (SELECT 1 FROM entries ec WHERE ec.source_file_id = sf.id AND ec.tag_categories_json LIKE ?)")
        params.append(f"%{category}%")
    if prompt_mode:
        conditions.append("EXISTS (SELECT 1 FROM entries epm WHERE epm.source_file_id = sf.id AND epm.prompt_mode = ?)")
        params.append(prompt_mode)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""
        SELECT
            sf.id,
            sf.wildcard_path,
            sf.relative_path,
            sf.extension,
            sf.size_bytes,
            sf.updated_at,
            COALESCE(sfs.entry_count, 0) AS entry_count,
            COALESCE(sfs.prompt_count, 0) AS prompt_count,
            COALESCE(sfs.duplicate_count, 0) AS duplicate_count,
            COALESCE(sfs.unresolved_refs, 0) AS unresolved_refs,
            COALESCE(sfs.categories_json, '[]') AS categories_json,
            COALESCE(sfs.prompt_modes_json, '{{}}') AS prompt_modes_json
        FROM source_files sf
        LEFT JOIN source_file_stats sfs ON sfs.source_file_id = sf.id
        {where}
        ORDER BY sf.relative_path COLLATE NOCASE
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    with connect() as conn:
        rows = conn.execute(query, params).fetchall()
        items: list[WildcardListItem] = []
        for row in rows:
            categories = json.loads(row["categories_json"] or "[]")
            prompt_modes = json.loads(row["prompt_modes_json"] or "{}")
            items.append(
                WildcardListItem(
                    id=row["id"],
                    wildcard_path=row["wildcard_path"],
                    relative_path=row["relative_path"],
                    extension=row["extension"],
                    size_bytes=row["size_bytes"],
                    entry_count=row["entry_count"] or 0,
                    prompt_count=row["prompt_count"] or 0,
                    duplicate_count=row["duplicate_count"] or 0,
                    unresolved_refs=row["unresolved_refs"] or 0,
                    categories=sorted(categories, key=str.lower)[:12],
                    prompt_modes=prompt_modes,
                    updated_at=row["updated_at"],
                )
            )
        return items


def build_duplicate_groups(limit: int = 200) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    with connect() as conn:
        file_rows = conn.execute(
            """
            SELECT sha256, COUNT(*) AS count, json_group_array(relative_path) AS paths
            FROM source_files
            GROUP BY sha256
            HAVING COUNT(*) > 1
            ORDER BY count DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        for row in file_rows:
            groups.append({"type": "exact_file", "key": row["sha256"], "count": row["count"], "items": json.loads(row["paths"])})

        line_rows = conn.execute(
            """
            SELECT normalized_text, COUNT(*) AS count,
                   json_group_array(wildcard_path || '#' || item_index) AS items
            FROM entries
            WHERE normalized_text != ''
            GROUP BY normalized_text
            HAVING COUNT(*) > 1
            ORDER BY count DESC, length(normalized_text) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        for row in line_rows:
            groups.append({"type": "normalized_entry", "key": row["normalized_text"], "count": row["count"], "items": json.loads(row["items"])})

        path_rows = conn.execute(
            """
            SELECT lower(wildcard_path) AS key, COUNT(*) AS count, json_group_array(relative_path) AS paths
            FROM source_files
            GROUP BY lower(wildcard_path)
            HAVING COUNT(*) > 1
            ORDER BY count DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        for row in path_rows:
            groups.append({"type": "path_collision", "key": row["key"], "count": row["count"], "items": json.loads(row["paths"])})
    return groups


def compute_unresolved_refs(conn: sqlite3.Connection, rows: list[sqlite3.Row] | None = None) -> list[str]:
    known = wildcard_paths(conn)
    unresolved = set()
    if rows is None:
        rows = conn.execute("SELECT refs_json FROM entries WHERE refs_json != '[]'").fetchall()
    for row in rows:
        for ref in json.loads(row["refs_json"] or "[]"):
            if ref and not ref_is_resolved(ref, known):
                unresolved.add(ref)
    return sorted(unresolved, key=str.lower)


def export_entry_rows(ids: list[int] | None = None, prompt_mode: str = "all") -> list[sqlite3.Row]:
    with connect() as conn:
        conditions = []
        params: list[Any] = []
        if ids:
            placeholders = ",".join("?" for _ in ids)
            conditions.append(f"source_file_id IN ({placeholders})")
            params.extend(ids)
        if prompt_mode != "all":
            conditions.append("prompt_mode = ?")
            params.append(prompt_mode)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = conn.execute(
            f"SELECT * FROM entries {where} ORDER BY wildcard_path, item_index",
            params,
        ).fetchall()
    return rows


def export_entries(ids: list[int] | None = None, prompt_mode: str = "all") -> dict[str, list[str]]:
    rows = export_entry_rows(ids, prompt_mode)
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        text = row["staged_text"] if row["staged_text"] is not None else row["raw_text"]
        grouped[row["wildcard_path"]].append(text)
    return dict(grouped)


def build_yaml_tree(grouped: dict[str, list[str]]) -> dict[str, Any]:
    tree: dict[str, Any] = {}
    for wildcard_path, entries in grouped.items():
        cursor = tree
        parts = [part for part in wildcard_path.split("/") if part]
        if not parts:
            continue
        for part in parts[:-1]:
            existing = cursor.setdefault(part, {})
            if not isinstance(existing, dict):
                cursor[part] = {}
            cursor = cursor[part]
        cursor[parts[-1]] = entries
    return tree


def export_metadata_summary(rows: list[sqlite3.Row]) -> dict[str, Any]:
    prompt_modes: Counter[str] = Counter()
    positive_tags: Counter[str] = Counter()
    negative_tags: Counter[str] = Counter()
    warning_count = 0
    refs: set[str] = set()
    for row in rows:
        prompt_modes[row["prompt_mode"]] += 1
        positive_tags.update(json.loads(row["positive_tags_json"] or "[]"))
        negative_tags.update(json.loads(row["negative_tags_json"] or "[]"))
        warnings = json.loads(row["warnings_json"] or "[]")
        warning_count += len(warnings)
        refs.update(json.loads(row["refs_json"] or "[]"))
    return {
        "entry_count": len(rows),
        "wildcard_count": len({row["wildcard_path"] for row in rows}),
        "prompt_modes": dict(prompt_modes),
        "positive_tag_count": sum(positive_tags.values()),
        "negative_tag_count": sum(negative_tags.values()),
        "top_positive_tags": positive_tags.most_common(50),
        "top_negative_tags": negative_tags.most_common(50),
        "ref_count": len(refs),
        "warning_count": warning_count,
    }


def write_export_file(path: Path, content: str, overwrite: bool, created: list[str], changed: list[str], skipped: list[str], conflicts: list[str], write: bool) -> None:
    output_rel = str(path)
    if path.exists():
        existing = path.read_text(encoding="utf-8", errors="replace")
        if existing == content:
            skipped.append(output_rel)
            return
        if not overwrite:
            conflicts.append(output_rel)
            return
        changed.append(output_rel)
    else:
        created.append(output_rel)
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def build_export_plan(request: ExportRequest, write: bool) -> ExportPlan:
    target_root = Path(request.target_root) if request.target_root else EXPORT_ROOT / f"wildcards-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    target_root = target_root.resolve()
    source_root = DEFAULT_SOURCE_ROOT.resolve()
    if source_root == target_root or source_root in target_root.parents:
        raise HTTPException(status_code=400, detail="Refusing to export inside the source Wildcards folder")

    selected_rows = export_entry_rows(request.wildcard_ids, request.prompt_mode)
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in selected_rows:
        text = row["staged_text"] if row["staged_text"] is not None else row["raw_text"]
        grouped[row["wildcard_path"]].append(text)
    created: list[str] = []
    changed: list[str] = []
    skipped: list[str] = []
    conflicts: list[str] = []

    if request.format in {"txt_tree", "both"}:
        for wildcard_path, entries in grouped.items():
            relative = Path(*wildcard_path.split("/")).with_suffix(".txt")
            output_path = target_root / relative
            content = "\n".join(entries).rstrip() + "\n"
            write_export_file(output_path, content, request.overwrite, created, changed, skipped, conflicts, write)
    if request.format in {"yaml", "sd_yaml", "both"}:
        output_name = "wildcards.yaml" if request.format != "both" else "wildcards.sd-dynamic-prompts.yaml"
        output_path = target_root / output_name
        tree = build_yaml_tree(grouped)
        content = yaml.safe_dump(tree, allow_unicode=True, sort_keys=True, width=120)
        write_export_file(output_path, content, request.overwrite, created, changed, skipped, conflicts, write)

    manifest_path = str(target_root / "wildcard-workshop-manifest.json") if request.include_manifest else None
    with connect() as conn:
        unresolved = compute_unresolved_refs(conn, selected_rows)
        last_scan = conn.execute("SELECT summary_json FROM scan_runs ORDER BY id DESC LIMIT 1").fetchone()
        taxonomy = conn.execute("SELECT value FROM taxonomy_meta WHERE key = 'version'").fetchone()
        llm_counts = conn.execute("SELECT status, COUNT(*) AS count FROM llm_jobs GROUP BY status").fetchall()
    plan = ExportPlan(
        target_root=str(target_root),
        format=request.format,
        created=created,
        changed=changed,
        skipped=skipped,
        conflicts=conflicts,
        manifest_path=manifest_path,
        unresolved_refs=unresolved,
    )
    if write and request.include_manifest and not conflicts:
        target_root.mkdir(parents=True, exist_ok=True)
        Path(manifest_path).write_text(
            json.dumps(
                {
                    "created_at": utc_now(),
                    "format": request.format,
                    "prompt_mode": request.prompt_mode,
                    "source_root": str(DEFAULT_SOURCE_ROOT),
                    "scan_mode": json.loads(last_scan["summary_json"]).get("scan_mode") if last_scan else None,
                    "parser_version": "prompt-aware-v2",
                    "taxonomy_version": taxonomy["value"] if taxonomy else None,
                    "llm_suggestion_counts": {row["status"]: row["count"] for row in llm_counts},
                    "parsed_prompt_metadata": export_metadata_summary(selected_rows),
                    "summary": plan.model_dump(),
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    return plan


def prompt_instruction(task: str, prompt_mode: str = "danbooru_tags") -> str:
    context = SDXL_PROMPT_CONTEXT if prompt_mode == "sdxl_natural" else DANBOORU_PROMPT_CONTEXT
    instructions = {
        "normalize_tags": "Normalize these image prompt tokens as concise Danbooru-style tags. Keep useful underscores, remove prose, and return comma-separated tags only.",
        "split_prose_to_tags": "Convert this prompt/prose into Danbooru-style tags for NoobAI or Illustrious. Return comma-separated tags only.",
        "suggest_category": "Suggest a short wildcard category path for this content. Return only one slash-separated path.",
        "detect_duplicates": "Identify likely duplicate or near-duplicate prompt tags. Return compact JSON with duplicate_groups.",
        "improve_prompt_order": "Improve the order of this Danbooru-style image prompt for NoobAI or Illustrious. Preserve meaning and return only the improved prompt.",
        "improve_sdxl_prompt": "Rewrite this as an SDXL natural-language prompt. Use a coherent paragraph, photographic/medium language, clear subject, environment, mood, style, and execution. Return only the improved positive prompt.",
        "convert_tags_to_sdxl": "Convert these image tags into an SDXL natural-language prompt. Preserve the visual intent, expand terse tags into concrete descriptions, and return one polished paragraph.",
        "convert_sdxl_to_tags": "Convert this SDXL natural-language prompt into NoobAI/Illustrious Danbooru-style tags. Return comma-separated tags only.",
    }
    return f"{context}\n\nTask: {instructions[task]}"


def llm_endpoint_candidates(raw_endpoint: str) -> list[str]:
    endpoint = (raw_endpoint or "http://host.docker.internal:5001/v1").rstrip("/")
    parsed = urlparse(endpoint)
    if not parsed.scheme or not parsed.netloc:
        endpoint = f"http://{endpoint.lstrip('/')}"
        parsed = urlparse(endpoint)

    base_path = parsed.path.rstrip("/")
    paths: list[str]
    if base_path.endswith("/v1/chat/completions"):
        paths = [base_path]
    elif base_path.endswith("/api/v1/generate"):
        paths = [base_path]
    elif base_path.endswith("/v1"):
        paths = [f"{base_path}/chat/completions", "/api/v1/generate"]
    elif base_path in {"", "/"}:
        paths = ["/v1/chat/completions", "/api/v1/generate"]
    else:
        paths = [base_path, f"{base_path}/v1/chat/completions", "/api/v1/generate"]

    hosts = [parsed.netloc]
    hostname = (parsed.hostname or "").lower()
    if hostname in {"127.0.0.1", "localhost", "::1"}:
        port = f":{parsed.port}" if parsed.port else ""
        hosts.append(f"host.docker.internal{port}")

    candidates: list[str] = []
    for host in hosts:
        for path in paths:
            candidate = urlunparse((parsed.scheme or "http", host, path, "", "", ""))
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates


async def call_kobold(request: LlmSuggestRequest) -> LlmSuggestResponse:
    messages = [
        {"role": "system", "content": prompt_instruction(request.task, request.prompt_mode)},
        {"role": "user", "content": request.text[:12000]},
    ]
    endpoints = llm_endpoint_candidates(request.endpoint)
    errors: list[str] = []
    async with httpx.AsyncClient(timeout=60.0) as client:
        for endpoint in endpoints:
            try:
                if endpoint.endswith("/v1/chat/completions"):
                    response = await client.post(
                        endpoint,
                        json={"model": request.model, "messages": messages, "temperature": 0.2, "max_tokens": 800},
                    )
                    response.raise_for_status()
                    payload = response.json()
                    suggestion = payload["choices"][0]["message"]["content"].strip()
                    return LlmSuggestResponse(ok=True, endpoint_used=endpoint, suggestion=suggestion, raw=payload)
                prompt = f"{prompt_instruction(request.task, request.prompt_mode)}\n\n{request.text[:12000]}"
                response = await client.post(
                    endpoint,
                    json={"prompt": prompt, "max_length": 800, "max_context_length": 4096, "temperature": 0.2},
                )
                response.raise_for_status()
                payload = response.json()
                suggestion = (payload.get("results", [{}])[0].get("text") or payload.get("text") or "").strip()
                return LlmSuggestResponse(ok=True, endpoint_used=endpoint, suggestion=suggestion, raw=payload)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{endpoint}: {exc}")
    return LlmSuggestResponse(
        ok=False,
        endpoint_used=", ".join(endpoints),
        suggestion="",
        error="All connection attempts failed. Tried: " + " | ".join(errors),
    )


def llm_job_from_row(row: sqlite3.Row) -> LlmJobItem:
    return LlmJobItem(
        id=row["id"],
        task=row["task"],
        prompt_mode=row["prompt_mode"],
        endpoint=row["endpoint"],
        model=row["model"],
        input_text=row["input_text"],
        status=row["status"],
        suggestion=row["suggestion"] or "",
        error=row["error"],
        endpoint_used=row["endpoint_used"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        accepted_at=row["accepted_at"],
        rejected_at=row["rejected_at"],
        cancelled_at=row["cancelled_at"],
    )


def run_llm_job(job_id: int) -> None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM llm_jobs WHERE id = ?", (job_id,)).fetchone()
        if not row or row["status"] == "cancelled":
            return
        conn.execute("UPDATE llm_jobs SET status = 'running', updated_at = ? WHERE id = ?", (utc_now(), job_id))
        request = LlmSuggestRequest(
            task=row["task"],
            text=row["input_text"],
            endpoint=row["endpoint"],
            model=row["model"],
            prompt_mode=row["prompt_mode"],
        )
    try:
        result = asyncio.run(call_kobold(request))
        with connect() as conn:
            current = conn.execute("SELECT status FROM llm_jobs WHERE id = ?", (job_id,)).fetchone()
            if current and current["status"] == "cancelled":
                return
            conn.execute(
                """
                UPDATE llm_jobs
                SET status = ?, suggestion = ?, error = ?, endpoint_used = ?, raw_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    "completed" if result.ok else "failed",
                    result.suggestion,
                    result.error,
                    result.endpoint_used,
                    json.dumps(result.raw, ensure_ascii=False) if result.raw is not None else None,
                    utc_now(),
                    job_id,
                ),
            )
    except Exception as exc:  # noqa: BLE001
        with connect() as conn:
            conn.execute(
                "UPDATE llm_jobs SET status = 'failed', error = ?, updated_at = ? WHERE id = ?",
                (str(exc), utc_now(), job_id),
            )


# APIRouter for all wildcard routes (prefix="" so mounting app provides /wildcards prefix)
router = APIRouter(prefix="", tags=["wildcards"])


@router.get("/health")
def health() -> dict[str, Any]:
    init_db()
    with connect() as conn:
        files = conn.execute("SELECT COUNT(*) AS count FROM source_files").fetchone()["count"]
        entries = conn.execute("SELECT COUNT(*) AS count FROM entries").fetchone()["count"]
        last_scan = conn.execute("SELECT summary_json, created_at FROM scan_runs ORDER BY id DESC LIMIT 1").fetchone()
    return {
        "ok": True,
        "db_path": str(DB_PATH),
        "source_root_exists": DEFAULT_SOURCE_ROOT.exists(),
        "files": files,
        "entries": entries,
        "last_scan": dict(last_scan) if last_scan else None,
    }


@router.post("/import/scan")
def import_scan(request: ScanRequest) -> dict[str, Any] | ScanSummary:
    source = Path(request.source_root).resolve() if request.source_root else DEFAULT_SOURCE_ROOT.resolve()
    scan_mode: Literal["incremental", "reset"] = request.mode or ("reset" if request.reset else "incremental")
    reset = scan_mode == "reset"
    if request.background:
        with SCAN_LOCK:
            if SCAN_STATE["running"]:
                return {"running": True, "message": "Scan already running", "status": SCAN_STATE}
            SCAN_STATE.update(
                {
                    "running": True,
                    "started_at": utc_now(),
                    "finished_at": None,
                    "summary": None,
                    "error": None,
                }
            )
        thread = threading.Thread(target=run_background_scan, args=(source, reset, scan_mode), daemon=True)
        thread.start()
        return {"running": True, "message": "Scan started"}
    return scan_library(source, reset, scan_mode)


@router.get("/import/status", response_model=ScanStatus)
def import_status() -> ScanStatus:
    with SCAN_LOCK:
        state = dict(SCAN_STATE)
    summary_data = state.get("summary")
    return ScanStatus(
        running=state["running"],
        started_at=state.get("started_at"),
        finished_at=state.get("finished_at"),
        summary=ScanSummary(**summary_data) if summary_data else None,
        error=state.get("error"),
    )


@router.get("/wildcards", response_model=list[WildcardListItem])
def get_wildcards(
    search: str = "",
    tag: str = "",
    tag_polarity: Literal["positive", "negative", "all"] = "all",
    kind: str = "",
    category: str = "",
    prompt_mode: str = "",
    limit: int = Query(default=250, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[WildcardListItem]:
    return list_wildcards(search, tag, tag_polarity, kind, category, prompt_mode, limit, offset)


@router.get("/prompt-modes")
def get_prompt_modes() -> dict[str, Any]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM prompt_mode_index ORDER BY entry_count DESC").fetchall()
    return {"modes": [dict(row) for row in rows]}


@router.get("/wildcards/{source_file_id}", response_model=WildcardDetail)
def get_wildcard(source_file_id: int, limit: int = Query(default=500, ge=1, le=5000), offset: int = Query(default=0, ge=0)) -> WildcardDetail:
    with connect() as conn:
        file_row = conn.execute("SELECT * FROM source_files WHERE id = ?", (source_file_id,)).fetchone()
        if not file_row:
            raise HTTPException(status_code=404, detail="Wildcard file not found")
        entry_rows = conn.execute(
            "SELECT * FROM entries WHERE source_file_id = ? ORDER BY item_index LIMIT ? OFFSET ?",
            (source_file_id, limit, offset),
        ).fetchall()
        entries = [entry_from_row(row) for row in entry_rows]
        refs = sorted({ref for entry in entries for ref in entry.refs}, key=str.lower)
        unresolved = compute_unresolved_refs(conn, entry_rows)
        warnings = sorted({warning for entry in entries for warning in entry.warnings})
        return WildcardDetail(file=dict(file_row), entries=entries, refs=refs, unresolved_refs=unresolved, warnings=warnings)


@router.patch("/entries/{entry_id}", response_model=EntryItem)
def patch_entry(entry_id: int, request: EntryPatch) -> EntryItem:
    with connect() as conn:
        row = conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Entry not found")
        previous = row["staged_text"] if row["staged_text"] is not None else row["raw_text"]
        parsed = parse_prompt_text(request.staged_text)
        tags = stable_unique([*parsed["positive_tags"], *[ref.replace("/", " ") for ref in parsed["refs"]]], 80)
        categories = detect_categories(request.staged_text, row["wildcard_path"], row["wildcard_path"], parsed["all_extracted_tags"] or tags)
        refs = parsed["refs"]
        warnings = [*detect_warnings(request.staged_text), *parsed["warnings"]]
        kind = detect_kind(request.staged_text, row["wildcard_path"])
        prompt_mode = detect_prompt_mode(request.staged_text, row["wildcard_path"], row["wildcard_path"], kind)
        conn.execute(
            """
            UPDATE entries
            SET staged_text = ?, normalized_text = ?, tags_json = ?, positive_tags_json = ?,
                negative_tags_json = ?, all_extracted_tags_json = ?, prompt_parts_json = ?,
                refs_json = ?, tag_categories_json = ?, warnings_json = ?, kind = ?, prompt_mode = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                request.staged_text,
                normalize_text(request.staged_text),
                json.dumps(tags, ensure_ascii=False),
                json.dumps(parsed["positive_tags"], ensure_ascii=False),
                json.dumps(parsed["negative_tags"], ensure_ascii=False),
                json.dumps(parsed["all_extracted_tags"], ensure_ascii=False),
                json.dumps(
                    {
                        "positive_text": parsed["positive_text"],
                        "negative_text": parsed["negative_text"],
                        "loras": parsed["loras"],
                        "dynamic_options": parsed["dynamic_options"],
                        "break_count": parsed["break_count"],
                    },
                    ensure_ascii=False,
                ),
                json.dumps(refs, ensure_ascii=False),
                json.dumps(categories, ensure_ascii=False),
                json.dumps(warnings, ensure_ascii=False),
                kind,
                prompt_mode,
                utc_now(),
                entry_id,
            ),
        )
        conn.execute("DELETE FROM entry_fts WHERE rowid = ?", (entry_id,))
        conn.execute(
            "INSERT INTO entry_fts(rowid, effective_text, wildcard_path, tags) VALUES (?, ?, ?, ?)",
            (entry_id, request.staged_text, row["wildcard_path"], " ".join(parsed["all_extracted_tags"] or tags)),
        )
        conn.execute(
            "INSERT INTO entry_history(entry_id, previous_text, next_text, created_at) VALUES (?, ?, ?, ?)",
            (entry_id, previous, request.staged_text, utc_now()),
        )
        updated = conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
        return entry_from_row(updated)


@router.get("/tags", response_model=TagsResponse)
def get_tags(
    search: str = "",
    category: str = "",
    tag_polarity: Literal["positive", "negative", "all"] = "all",
    limit: int = Query(default=250, ge=1, le=1000),
) -> TagsResponse:
    index_category = category or "__all__"
    with connect() as conn:
        table = "tag_polarity_index" if tag_polarity in {"positive", "negative", "all"} else "tag_index"
        if search:
            rows = conn.execute(
                f"""
                SELECT tag, usage_count FROM {table}
                WHERE category = ? AND polarity = ? AND tag LIKE ?
                ORDER BY usage_count DESC, tag COLLATE NOCASE
                LIMIT ?
                """,
                (index_category, tag_polarity, f"%{search}%", limit),
            ).fetchall()
        else:
            rows = conn.execute(
                f"""
                SELECT tag, usage_count FROM {table}
                WHERE category = ? AND polarity = ?
                ORDER BY usage_count DESC, tag COLLATE NOCASE
                LIMIT ?
                """,
                (index_category, tag_polarity, limit),
            ).fetchall()
    tags = [{"tag": row["tag"], "usage_count": row["usage_count"]} for row in rows]
    return TagsResponse(tags=tags)


@router.get("/categories", response_model=CategoriesResponse)
def get_categories() -> CategoriesResponse:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT ci.category, ci.usage_count, COALESCE(cs.file_count, 0) AS file_count,
                   COALESCE(cs.tag_count, 0) AS tag_count,
                   COALESCE(cs.wildcard_count, 0) AS wildcard_count
            FROM category_index ci
            LEFT JOIN category_stats cs ON cs.category = ci.category
            ORDER BY ci.usage_count DESC, ci.category
            """
        ).fetchall()
    return CategoriesResponse(
        categories=[
            {
                "category": row["category"],
                "usage_count": row["usage_count"],
                "file_count": row["file_count"],
                "tag_count": row["tag_count"],
                "wildcard_count": row["wildcard_count"],
            }
            for row in rows
        ]
    )


@router.get("/duplicates")
def get_duplicates(limit: int = Query(default=200, ge=1, le=1000)) -> dict[str, Any]:
    return {"groups": build_duplicate_groups(limit)}


@router.post("/prompts/compose", response_model=PromptComposeResponse)
def compose_prompt(request: PromptComposeRequest) -> PromptComposeResponse:
    if request.prompt_mode == "sdxl_natural":
        fields = request.sdxl or {}
        image_type = (fields.get("image_type") or "photo").strip()
        subject = (fields.get("subject") or "a clear central subject").strip()
        details = (fields.get("details") or "").strip()
        environment = (fields.get("environment") or "").strip()
        mood = (fields.get("mood") or "").strip()
        style = (fields.get("style") or "").strip()
        slot_phrases = [tag for slot in ["characters", "clothing", "pose", "background", "lighting", "style"] for tag in request.slots.get(slot, [])]
        refs = [f"__{ref.strip('_')}__" for ref in request.wildcard_refs if ref.strip()]
        sentence_parts = [f"{image_type} of {subject}"]
        if details or slot_phrases:
            sentence_parts.append(", ".join([details, *slot_phrases]).strip(", "))
        if environment:
            sentence_parts.append(environment)
        if mood:
            sentence_parts.append(mood)
        if style:
            sentence_parts.append(style)
        if refs:
            sentence_parts.append("Reusable wildcard details: " + ", ".join(refs))
        positive = ". ".join(part.rstrip(".") for part in sentence_parts if part) + "."
        negative_parts = request.negative_tags or ["cartoon", "anime", "illustration", "cgi", "3d render", "low quality", "extra fingers"]
        negative = ", ".join(dict.fromkeys(part.strip() for part in negative_parts if part.strip()))
        with connect() as conn:
            known = wildcard_paths(conn)
        unresolved = [ref.strip("_") for ref in request.wildcard_refs if ref.strip("_").lower().rstrip("/*") not in known]
        return PromptComposeResponse(
            positive=positive,
            negative=negative,
            wildcard_prompt=f"{positive}\nNegative prompt: {negative}",
            model_profile="SDXL Natural Language",
            preset=request.preset,
            prompt_mode=request.prompt_mode,
            slot_order=["image_type", "subject", "details", "environment", "mood", "style", "wildcard_refs"],
            unresolved_refs=unresolved,
        )

    preset_profile = "NoobAI" if request.preset == "NoobAI tag-heavy" else request.model_profile
    profile_prefix = {
        "NoobAI": ["score_9", "score_8_up", "score_7_up", "source_anime"],
        "Illustrious": ["masterpiece", "best quality", "very aesthetic", "absurdres"],
        "Generic Danbooru": ["masterpiece", "best quality"],
    }[preset_profile]
    if request.quality_preset == "minimal":
        profile_prefix = profile_prefix[:2]
    elif request.quality_preset == "high":
        profile_prefix = [*profile_prefix, "intricate details", "highres"]
    refs = [f"__{ref.strip('_')}__" for ref in request.wildcard_refs if ref.strip()]
    slot_order = ["quality", "copyright", "characters", "anatomy", "clothing", "pose", "background", "lighting", "style", "general"]
    slot_tags = []
    for slot in slot_order:
        slot_tags.extend(request.slots.get(slot, []))
    all_positive_tags = [*slot_tags, *request.positive_tags]
    buckets: dict[str, list[str]] = {category: [] for category in slot_order}
    for tag in all_positive_tags:
        categories = detect_categories(tag, "")
        bucket = next((category for category in slot_order if category in categories), "general")
        buckets[bucket].append(tag)
    ordered_tags = [tag for category in slot_order for tag in buckets[category]]
    if request.preset == "Wildcard-heavy randomizer":
        ref_parts = [f"{{1-2$$__{ref.strip('_')}__}}" for ref in request.wildcard_refs if ref.strip()]
    else:
        ref_parts = refs
    positive_parts = [*profile_prefix, *ordered_tags, *ref_parts]
    negative_parts = request.negative_tags or ["worst quality", "low quality", "bad anatomy"]
    positive = ", ".join(dict.fromkeys(part.strip() for part in positive_parts if part.strip()))
    negative = ", ".join(dict.fromkeys(part.strip() for part in negative_parts if part.strip()))
    with connect() as conn:
        known = wildcard_paths(conn)
    unresolved = [ref.strip("_") for ref in request.wildcard_refs if ref.strip("_").lower().rstrip("/*") not in known]
    return PromptComposeResponse(
        positive=positive,
        negative=negative,
        wildcard_prompt=f"{positive}\nNegative prompt: {negative}",
        model_profile=preset_profile,
        preset=request.preset,
        prompt_mode=request.prompt_mode,
        slot_order=slot_order,
        unresolved_refs=unresolved,
    )


@router.post("/llm/suggest", response_model=LlmSuggestResponse)
async def llm_suggest(request: LlmSuggestRequest) -> LlmSuggestResponse:
    return await call_kobold(request)


@router.post("/llm/test", response_model=LlmSuggestResponse)
async def llm_test(request: LlmSuggestRequest) -> LlmSuggestResponse:
    probe = request.model_copy(
        update={
            "task": "normalize_tags",
            "text": "Reply with: ok",
        }
    )
    return await call_kobold(probe)


@router.post("/llm/jobs", response_model=LlmJobItem)
def create_llm_job(request: LlmJobRequest) -> LlmJobItem:
    init_db()
    now = utc_now()
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO llm_jobs(task, prompt_mode, endpoint, model, input_text, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (request.task, request.prompt_mode, request.endpoint, request.model, request.text, now, now),
        )
        job_id = int(cur.lastrowid)
        row = conn.execute("SELECT * FROM llm_jobs WHERE id = ?", (job_id,)).fetchone()
    thread = threading.Thread(target=run_llm_job, args=(job_id,), daemon=True)
    thread.start()
    return llm_job_from_row(row)


@router.get("/llm/jobs", response_model=list[LlmJobItem])
def list_llm_jobs(limit: int = Query(default=50, ge=1, le=200)) -> list[LlmJobItem]:
    init_db()
    with connect() as conn:
        rows = conn.execute("SELECT * FROM llm_jobs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [llm_job_from_row(row) for row in rows]


@router.get("/llm/jobs/{job_id}", response_model=LlmJobItem)
def get_llm_job(job_id: int) -> LlmJobItem:
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT * FROM llm_jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="LLM job not found")
    return llm_job_from_row(row)


@router.post("/llm/jobs/{job_id}/cancel", response_model=LlmJobItem)
def cancel_llm_job(job_id: int) -> LlmJobItem:
    init_db()
    now = utc_now()
    with connect() as conn:
        row = conn.execute("SELECT * FROM llm_jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="LLM job not found")
        if row["status"] in {"pending", "running"}:
            conn.execute(
                "UPDATE llm_jobs SET status = 'cancelled', cancelled_at = ?, updated_at = ? WHERE id = ?",
                (now, now, job_id),
            )
        updated = conn.execute("SELECT * FROM llm_jobs WHERE id = ?", (job_id,)).fetchone()
    return llm_job_from_row(updated)


@router.post("/cleanup/preview", response_model=CleanupPreviewResponse)
def cleanup_preview(request: CleanupPreviewRequest) -> CleanupPreviewResponse:
    raw_lines = [line.strip() for line in request.text.splitlines()]
    normalized = [normalize_text(line) for line in raw_lines if line]
    counts = Counter(normalized)
    duplicates = [line for line, count in counts.items() if count > 1]
    by_lower: dict[str, set[str]] = defaultdict(set)
    for line in raw_lines:
        if line:
            by_lower[line.lower()].add(line)
    case_conflicts = [sorted(values) for values in by_lower.values() if len(values) > 1]
    prose = [line for line in raw_lines if line and not is_builder_tag(line)]
    return CleanupPreviewResponse(
        normalized_lines=normalized,
        duplicate_lines=duplicates,
        case_conflicts=case_conflicts,
        prose_candidates=prose[:200],
    )


@router.get("/prompt-recipes")
def list_prompt_recipes() -> dict[str, Any]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM prompt_recipes ORDER BY updated_at DESC, name COLLATE NOCASE").fetchall()
    return {
        "recipes": [
            {
                "id": row["id"],
                "name": row["name"],
                "preset": row["preset"],
                "slots": json.loads(row["slots_json"]),
                "negative_tags": json.loads(row["negative_tags_json"]),
                "wildcard_refs": json.loads(row["wildcard_refs_json"]),
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]
    }


@router.post("/prompt-recipes")
def save_prompt_recipe(request: PromptRecipeSaveRequest) -> dict[str, Any]:
    now = utc_now()
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO prompt_recipes(name, preset, slots_json, negative_tags_json, wildcard_refs_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request.name,
                request.preset,
                json.dumps(request.slots, ensure_ascii=False),
                json.dumps(request.negative_tags, ensure_ascii=False),
                json.dumps(request.wildcard_refs, ensure_ascii=False),
                now,
                now,
            ),
        )
        return {"id": cur.lastrowid, "updated_at": now}


@router.get("/tag-overrides")
def list_tag_overrides() -> dict[str, Any]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM tag_overrides ORDER BY updated_at DESC, tag COLLATE NOCASE").fetchall()
    return {"overrides": [dict(row) for row in rows]}


@router.post("/tag-overrides")
def save_tag_override(request: TagOverrideRequest) -> dict[str, Any]:
    now = utc_now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO tag_overrides(tag, canonical_tag, category, is_ignored, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(tag) DO UPDATE SET
                canonical_tag = excluded.canonical_tag,
                category = excluded.category,
                is_ignored = excluded.is_ignored,
                updated_at = excluded.updated_at
            """,
            (request.tag, request.canonical_tag, request.category, int(request.is_ignored), now),
        )
    return {"tag": request.tag, "updated_at": now}


@router.get("/taxonomy")
def get_taxonomy() -> dict[str, Any]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            "SELECT category, keyword, enabled, updated_at FROM taxonomy_rules ORDER BY category, keyword"
        ).fetchall()
        meta = conn.execute("SELECT value, updated_at FROM taxonomy_meta WHERE key = 'version'").fetchone()
    rules: dict[str, list[str]] = defaultdict(list)
    disabled: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        target = rules if row["enabled"] else disabled
        target[row["category"]].append(row["keyword"])
    return {
        "rules": dict(rules),
        "disabled": dict(disabled),
        "version": meta["value"] if meta else None,
        "updated_at": meta["updated_at"] if meta else None,
        "fallback_categories": list(CATEGORY_RULES.keys()),
    }


@router.patch("/taxonomy")
def update_taxonomy(request: TaxonomyPatchRequest) -> dict[str, Any]:
    if request.rules is None and not (request.category and request.keywords is not None):
        raise HTTPException(status_code=400, detail="Provide either rules or category plus keywords")
    now = utc_now()
    with connect() as conn:
        if request.rules is not None:
            conn.execute("DELETE FROM taxonomy_rules")
            rows = [
                (category.strip(), keyword.strip(), now)
                for category, keywords in request.rules.items()
                for keyword in keywords
                if category.strip() and keyword.strip()
            ]
        else:
            category = (request.category or "").strip()
            if not category:
                raise HTTPException(status_code=400, detail="Category is required")
            conn.execute("DELETE FROM taxonomy_rules WHERE category = ?", (category,))
            rows = [(category, keyword.strip(), now) for keyword in request.keywords or [] if keyword.strip()]
        conn.executemany(
            "INSERT OR REPLACE INTO taxonomy_rules(category, keyword, enabled, updated_at) VALUES (?, ?, 1, ?)",
            rows,
        )
        conn.execute(
            "INSERT OR REPLACE INTO taxonomy_meta(key, value, updated_at) VALUES ('version', ?, ?)",
            (now, now),
        )
    taxonomy_rules_cached.cache_clear()
    cached_builder_tag_categories.cache_clear()
    return {"updated_at": now, "keyword_count": len(rows)}


@router.post("/taxonomy/reindex")
def reindex_taxonomy(background: bool = True) -> dict[str, Any] | ScanSummary:
    source = DEFAULT_SOURCE_ROOT.resolve()
    if background:
        with SCAN_LOCK:
            if SCAN_STATE["running"]:
                return {"running": True, "message": "Scan already running", "status": SCAN_STATE}
            SCAN_STATE.update(
                {
                    "running": True,
                    "started_at": utc_now(),
                    "finished_at": None,
                    "summary": None,
                    "error": None,
                }
            )
        thread = threading.Thread(target=run_background_scan, args=(source, True, "reset"), daemon=True)
        thread.start()
        return {"running": True, "message": "Taxonomy reindex started"}
    return scan_library(source, True, "reset")


@router.post("/export/dry-run", response_model=ExportPlan)
def export_dry_run(request: ExportRequest) -> ExportPlan:
    return build_export_plan(request, write=False)


@router.post("/export/run", response_model=ExportPlan)
def export_run(request: ExportRequest) -> ExportPlan:
    plan = build_export_plan(request, write=True)
    if plan.conflicts:
        raise HTTPException(status_code=409, detail=plan.model_dump())
    return plan


@router.post("/library/backup")
def backup_library() -> dict[str, str]:
    if not DB_PATH.exists():
        raise HTTPException(status_code=404, detail="No library database exists yet")
    backup_path = DATA_DIR / f"wildcard_workshop-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
    shutil.copy2(DB_PATH, backup_path)
    return {"backup_path": str(backup_path)}
