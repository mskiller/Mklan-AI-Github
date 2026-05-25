from __future__ import annotations

import json
import logging
import subprocess
import zlib
from pathlib import Path

from PIL import Image
import numpy as np


logger = logging.getLogger(__name__)


def _run_json_command(command: list[str]) -> dict | list | None:
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        logger.warning("metadata command failed", extra={"command": command, "error": str(exc)})
        return None

    if not result.stdout.strip():
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        logger.warning("metadata command returned invalid json", extra={"command": command})
        return None


def extract_exiftool(path: Path) -> dict:
    payload = _run_json_command(["exiftool", "-j", "-n", str(path)])
    if isinstance(payload, list) and payload:
        return payload[0]
    return {}


def extract_ffprobe(path: Path) -> dict:
    payload = _run_json_command(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
    )
    if isinstance(payload, dict):
        return payload
    return {}


def extract_png_metadata_from_file(path: Path) -> dict:
    """
    Read PNG tEXt / iTXt chunks and decode stealth_pngcomp alpha-channel data.
    Returns a flat dict of key -> value strings, same shape as exiftool output.
    Silently returns {} for non-PNG files or read errors.
    """
    result: dict = {}

    # 1. Standard tEXt / iTXt chunks via Pillow
    try:
        with Image.open(path) as img:
            for key, value in img.info.items():
                if isinstance(value, (str, bytes)):
                    result[key] = (
                        value.decode("utf-8", errors="replace")
                        if isinstance(value, bytes)
                        else value
                    )
    except Exception:
        pass

    # 2. Stealth PNG (alpha-channel LSB encoding)
    try:
        with Image.open(path) as img:
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            
            alpha = np.array(img)[:, :, 3].flatten()
            
            if len(alpha) < 64:
                return result

            # Read magic (first 32 alpha pixels, bit 0)
            magic_bits = alpha[:32] & 1
            magic_val = int("".join(str(b) for b in magic_bits), 2)
            
            MAGIC_UNCOMPRESSED = 0x53746c73  # "Stls"
            MAGIC_COMPRESSED   = 0x53746c63  # "Stlc"
            
            if magic_val in (MAGIC_UNCOMPRESSED, MAGIC_COMPRESSED):
                # Read 32-bit length
                len_bits = alpha[32:64] & 1
                payload_len = int("".join(str(b) for b in len_bits), 2)
                
                if payload_len > 0 and (64 + payload_len) <= len(alpha):
                    # Read payload bits
                    bit_stream = alpha[64:64 + payload_len] & 1
                    byte_count = payload_len // 8
                    
                    if byte_count > 0:
                        raw_bytes = bytes(
                            int("".join(str(b) for b in bit_stream[i*8:(i+1)*8]), 2)
                            for i in range(byte_count)
                        )
                        
                        if magic_val == MAGIC_COMPRESSED:
                            raw_bytes = zlib.decompress(raw_bytes)
                        
                        payload = json.loads(raw_bytes.decode("utf-8"))
                        if isinstance(payload, dict):
                            # Stealth payload typically has "workflow" and/or "prompt" keys
                            for k, v in payload.items():
                                result.setdefault(
                                    k.capitalize(), 
                                    json.dumps(v) if not isinstance(v, str) else v
                                )
    except Exception:
        pass
    
    return result
