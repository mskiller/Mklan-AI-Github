from __future__ import annotations

import argparse
from pathlib import Path
import shutil

from huggingface_hub import snapshot_download


REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = REPO_ROOT / "data" / "models" / "captioning"
TAG_VOCAB_ROOT = MODEL_ROOT / "tag_vocab"

DEFAULT_MODELS = {
    "blip-base": "Salesforce/blip-image-captioning-base",
    "blip-large": "Salesforce/blip-image-captioning-large",
    "danbooru-clip": "OysterQAQ/DanbooruCLIP",
    "laion-clip": "laion/CLIP-ViT-B-32-laion2B-s34B-b79K",
    "fashion-clip": "patrickjohncyh/fashion-clip",
    "openai-clip-large": "openai/clip-vit-large-patch14",
}
OPEN_CLIP_REPOS = {"laion/CLIP-ViT-B-32-laion2B-s34B-b79K"}


def safe_dir_name(repo_id: str) -> str:
    return repo_id.replace("/", "-")


def copy_default_tags() -> Path:
    TAG_VOCAB_ROOT.mkdir(parents=True, exist_ok=True)
    target = TAG_VOCAB_ROOT / "default_tags.txt"
    source = REPO_ROOT / "backend" / "app" / "resources" / "caption_tags_default.txt"
    if source.exists() and not target.exists():
        shutil.copyfile(source, target)
    return target


def download_model(repo_id: str, force: bool = False) -> Path:
    MODEL_ROOT.mkdir(parents=True, exist_ok=True)
    target = MODEL_ROOT / safe_dir_name(repo_id)
    if repo_id in OPEN_CLIP_REPOS:
        snapshot_download(
            repo_id=repo_id,
            cache_dir=str(MODEL_ROOT / "hf-cache"),
            resume_download=True,
        )
    if target.exists() and any(target.iterdir()) and not force:
        return target
    snapshot_download(
        repo_id=repo_id,
        local_dir=str(target),
        local_dir_use_symlinks=False,
        resume_download=True,
    )
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Download captioning models used by Mklan Studio Training Caption Scan.")
    parser.add_argument(
        "--models",
        nargs="+",
        default=["all"],
        help="Model keys or Hugging Face repo ids. Use 'all' for every supported BLIP/CLIP model.",
    )
    parser.add_argument("--force", action="store_true", help="Refresh existing local directories.")
    parser.add_argument("--skip-tags", action="store_true", help="Do not create data/models/captioning/tag_vocab/default_tags.txt.")
    args = parser.parse_args()

    selected: list[str] = []
    for item in args.models:
        if item in {"none", "tags-only"}:
            continue
        if item == "all":
            selected.extend(DEFAULT_MODELS.values())
        else:
            selected.append(DEFAULT_MODELS.get(item, item))

    if not args.skip_tags:
        tags_path = copy_default_tags()
        print(f"Tag vocabulary ready: {tags_path}")

    for repo_id in dict.fromkeys(selected):
        target = download_model(repo_id, force=args.force)
        print(f"{repo_id} -> {target}")


if __name__ == "__main__":
    main()
