from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[2] / "sample_media" / "generated"


def make_image(path: Path, base: str, accent: str, label: str) -> None:
    image = Image.new("RGB", (1600, 900), base)
    draw = ImageDraw.Draw(image)
    draw.rectangle((140, 140, 1460, 760), outline=accent, width=16)
    draw.ellipse((220, 220, 540, 540), outline=accent, width=14)
    draw.rectangle((640, 250, 1280, 620), fill=accent)
    draw.text((180, 780), label, fill="white")
    image.save(path, quality=92)


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    make_image(ROOT / "studio-a.jpg", "#17313E", "#E8A87C", "Studio A")
    make_image(ROOT / "studio-a-copy.jpg", "#16303D", "#E8A87C", "Studio A Copy")
    make_image(ROOT / "coastline.png", "#214037", "#F0C05A", "Coastline")
    print(f"Generated demo images in {ROOT}")


if __name__ == "__main__":
    main()

