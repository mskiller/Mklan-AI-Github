"""Wildcard parsing: category rules, regex patterns, and taxonomy helpers."""
from __future__ import annotations

import re
from collections import defaultdict
from functools import lru_cache

# Import path constants
from ..config import WILDCARD_DB

# Regex patterns
WILDCARD_REF_RE = re.compile(r"__([^_\n][^_\n]*?)__")
LORA_RE = re.compile(r"<lora:[^>]+>", re.IGNORECASE)
WEIGHTED_DYNAMIC_RE = re.compile(r"\{\s*\d+(?:\.\d+)?::")
MULTI_SELECT_RE = re.compile(r"\{\s*-?\d+(?:-\d+)?\$\$")
COMMENT_RE = re.compile(r"^\s*#")
NEGATIVE_PROMPT_RE = re.compile(
    r"\b(?:negative prompt|negative|neg prompt|negatives?)\s*:", re.IGNORECASE
)

CATEGORY_RULES: dict[str, tuple[str, ...]] = {
    "copyright": (
        "copyright", "series", "franchise", "source", "source material",
        "anime title", "game title", "manga", "comic title", "movie", "show",
        "universe", "pokemon", "genshin", "honkai", "fate", "touhou",
        "azur lane", "blue archive",
    ),
    "characters": (
        "character", "characters", "character specific", "characterspecific",
        "female", "females", "person", "people", "personmaker", "card",
        "actor", "actors", "actress", "celebrity", "celeb", "vtuber", "oc",
        "original character", "girl", "boy", "woman", "man", "pokemon",
    ),
    "pose": (
        "pose", "posing", "action", "gesture", "stance", "kneeling", "sitting",
        "standing", "lying", "laying", "reclining", "from behind", "from_below",
        "cowgirl", "missionary",
    ),
    "background": (
        "background", "location", "scenery", "scene", "environment",
        "landscape", "architecture", "interior", "outside", "forest",
        "city", "room", "beach", "street",
    ),
    "clothing": (
        "clothing", "clothes", "outfit", "attire", "dress", "shirt", "skirt",
        "pants", "uniform", "lingerie", "bikini", "costume", "headwear",
        "hat", "jewelry", "accessory",
    ),
    "quality": (
        "score_", "masterpiece", "best quality", "quality", "absurdres",
        "highres", "aesthetic", "intricate details",
    ),
    "style": (
        "style", "artist", "anime", "illustration", "photo", "realistic",
        "painting", "comic", "toon", "sketch", "lineart",
    ),
    "anatomy": (
        "body", "face", "hair", "eyes", "breast", "lips", "nose", "skin",
        "height", "build", "anatomy",
    ),
    "lighting": (
        "light", "lighting", "shadow", "hdr", "volumetric", "sunset",
        "neon", "ambient",
    ),
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