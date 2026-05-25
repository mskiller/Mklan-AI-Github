from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MEDIA_INDEXER_SRC = REPO_ROOT / "media-indexer" / "backend" / "src"

if str(MEDIA_INDEXER_SRC) not in sys.path:
    sys.path.insert(0, str(MEDIA_INDEXER_SRC))

from media_indexer_backend.models.enums import MediaType
from media_indexer_backend.services.metadata import normalize_metadata, normalized_metadata_for_api


def test_comfyui_metadata_prefers_processed_wildcard_prompt_from_graph():
    prompt_graph = {
        "1": {
            "class_type": "CustomPromptProcessor",
            "inputs": {
                "prompt": "__artist__, __pose__, cinematic light",
                "populated_text": "sable fox mage, leaning on balcony, cinematic light",
            },
        },
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": ["1", 0]}},
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "positive": ["2", 0],
                "negative": "low quality, blurry",
                "steps": 24,
                "cfg": 6.5,
                "sampler_name": "dpmpp_2m",
                "scheduler": "karras",
            },
        },
    }

    normalized = normalize_metadata(
        media_type=MediaType.IMAGE,
        exif={"Prompt": json.dumps(prompt_graph), "Workflow": json.dumps({})},
        ffprobe={},
    )

    assert normalized["prompt"] == "sable fox mage, leaning on balcony, cinematic light"
    assert "__artist__" not in normalized["prompt"]
    assert normalized["negative_prompt"] == "low quality, blurry"


def test_comfyui_metadata_prefers_processed_wildcard_prompt_from_workflow_fallback():
    workflow = {
        "nodes": [
            {
                "type": "WildcardPrompt",
                "inputs": {
                    "prompt": "__character__, __style__, blue rim light",
                    "populated_text": "noir detective android, watercolor wash, blue rim light",
                },
            }
        ]
    }

    normalized = normalize_metadata(
        media_type=MediaType.IMAGE,
        exif={"Workflow": json.dumps(workflow)},
        ffprobe={},
    )

    assert normalized["prompt"] == "noir detective android, watercolor wash, blue rim light"
    assert "__character__" not in normalized["prompt"]


def test_comfyui_metadata_keeps_raw_and_processed_impact_wildcard_prompt():
    prompt_graph = {
        "1": {
            "class_type": "ImpactWildcardProcessor",
            "inputs": {
                "wildcard_text": "__ziggart/zig-quality__, __pose__, limited palette",
                "populated": "masterpiece, absurdres, leaning on balcony, limited palette",
            },
        },
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": ["1", 0]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "bad anatomy, low quality"}},
        "4": {
            "class_type": "KSampler",
            "inputs": {
                "positive": ["2", 0],
                "negative": ["3", 0],
                "steps": 18,
            },
        },
    }

    normalized = normalize_metadata(
        media_type=MediaType.IMAGE,
        exif={"Prompt": json.dumps(prompt_graph), "Workflow": json.dumps({})},
        ffprobe={},
    )

    assert normalized["prompt"] == "masterpiece, absurdres, leaning on balcony, limited palette"
    assert normalized["processed_prompt"] == normalized["prompt"]
    assert normalized["raw_prompt"] == "__ziggart/zig-quality__, __pose__, limited palette"
    assert normalized["negative_prompt"] == "bad anatomy, low quality"


def test_comfyui_metadata_uses_matching_show_text_output_for_wildcard_prompt():
    prompt_graph = {
        "1": {
            "class_type": "TextInput_",
            "inputs": {"text": "(Masterpiece, 1girl, toph_beifong (avatar_legends), {large breasts|small breasts}, __quality__)"},
        },
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": ["1", 0]}},
        "3": {"class_type": "KSampler", "inputs": {"positive": ["2", 0], "steps": 12}},
        "4": {
            "class_type": "ShowText|pysssss",
            "_meta": {"title": "Show Text"},
            "inputs": {
                "text_0": (
                    "(Masterpiece, 1girl, toph_beifong (avatar_legends), small breasts, "
                    "detailed, uhd, hires)"
                ),
                "text": ["1", 0],
            },
        },
        "5": {
            "class_type": "ShowText|pysssss",
            "_meta": {"title": "Show Text"},
            "inputs": {
                "text_0": "(Masterpiece, 1girl, asami_sato (avatar_legends), medium breasts, detailed, uhd, hires)"
            },
        },
    }

    normalized = normalize_metadata(
        media_type=MediaType.IMAGE,
        exif={"Prompt": json.dumps(prompt_graph), "Workflow": json.dumps({})},
        ffprobe={},
    )

    assert normalized["prompt"] == "(Masterpiece, 1girl, toph_beifong (avatar_legends), small breasts, detailed, uhd, hires)"
    assert normalized["raw_prompt"] == "(Masterpiece, 1girl, toph_beifong (avatar_legends), {large breasts|small breasts}, __quality__)"
    assert "asami_sato" not in normalized["prompt"]


def test_normalized_metadata_for_api_prefers_processed_prompt_for_display_and_tags():
    payload = normalized_metadata_for_api(
        {
            "prompt": "(1girl, toph_beifong (avatar_legends), {large breasts|small breasts}, __quality__)",
            "processed_prompt": "(1girl, toph_beifong (avatar_legends), small breasts, detailed, uhd, hires)",
            "raw_prompt": "(1girl, toph_beifong (avatar_legends), {large breasts|small breasts}, __quality__)",
        }
    )

    assert payload["prompt"] == "(1girl, toph_beifong (avatar_legends), small breasts, detailed, uhd, hires)"
    assert "small_breasts" in payload["prompt_tags"]
    assert not any("{" in tag or "__" in tag for tag in payload["prompt_tags"])
