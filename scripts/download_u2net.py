from __future__ import annotations

import os
import shutil
import urllib.request
from pathlib import Path


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    u2net_dir = repo_root / "data" / "models" / "u2net"
    u2net_dot_dir = u2net_dir / ".u2net"

    u2net_dir.mkdir(parents=True, exist_ok=True)
    u2net_dot_dir.mkdir(parents=True, exist_ok=True)

    url = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx"
    target1 = u2net_dir / "u2net.onnx"
    target2 = u2net_dot_dir / "u2net.onnx"

    if target1.exists() and target2.exists():
        print(f"u2net.onnx already exists at:\n  - {target1}\n  - {target2}")
        return

    print(f"Downloading {url}...")
    print(f"Saving to {target1}...")
    
    # Custom progress reporter
    def report_progress(block_num: int, block_size: int, total_size: int) -> None:
        read_so_far = block_num * block_size
        if total_size > 0:
            percent = min(100, int(read_so_far * 100 / total_size))
            print(f"Download Progress: {percent}% ({read_so_far} / {total_size} bytes)", end="\r")
        else:
            print(f"Downloaded {read_so_far} bytes", end="\r")

    urllib.request.urlretrieve(url, target1, reporthook=report_progress)
    print("\nDownload completed successfully!")

    print(f"Copying to {target2}...")
    shutil.copyfile(target1, target2)
    print("All model files are now in place!")


if __name__ == "__main__":
    main()
