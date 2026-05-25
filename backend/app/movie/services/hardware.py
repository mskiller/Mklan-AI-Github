from __future__ import annotations

import os
import subprocess

from ..config import Settings


def _detect_ram_gb() -> float | None:
    try:
        import psutil  # type: ignore

        return round(psutil.virtual_memory().total / (1024**3), 1)
    except Exception:
        return None


def _detect_cuda_with_torch() -> tuple[bool, float | None]:
    try:
        import torch

        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            total_memory_gb = round(props.total_memory / (1024**3), 1)
            return True, total_memory_gb
    except Exception:
        return False, None
    return False, None


def detect_hardware_profile(settings: Settings) -> dict:
    cpu_cores = os.cpu_count() or 1
    gpu_vendor = None
    gpu_name = None
    vram_gb = None
    cuda_available, torch_vram = _detect_cuda_with_torch()

    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            check=True,
            text=True,
            timeout=5,
        )
        first_line = result.stdout.strip().splitlines()[0]
        gpu_name, memory_mib = [part.strip() for part in first_line.split(",", maxsplit=1)]
        gpu_vendor = "nvidia"
        vram_gb = round(float(memory_mib) / 1024, 1)
        cuda_available = True
    except Exception:
        if torch_vram is not None:
            vram_gb = torch_vram
            gpu_vendor = "nvidia"
            gpu_name = "CUDA device"

    ram_gb = _detect_ram_gb()
    supported = bool(cuda_available and gpu_vendor == "nvidia" and (vram_gb or 0) >= settings.supported_min_vram_gb)
    support_tier = "supported" if supported else "degraded"
    recommended_renderer = "cogvideox" if supported else "placeholder"
    notes = []
    if supported:
        notes.append("This machine meets the v1 CUDA + 16 GB VRAM target.")
    else:
        notes.append("Official v1 support is NVIDIA CUDA with at least 16 GB VRAM.")
        if settings.allow_placeholder_renderer:
            notes.append("Placeholder rendering remains available for local smoke tests and UI validation.")

    return {
        "gpu_vendor": gpu_vendor,
        "gpu_name": gpu_name,
        "vram_gb": vram_gb,
        "ram_gb": ram_gb,
        "cpu_cores": cpu_cores,
        "cuda_available": cuda_available,
        "support_tier": support_tier,
        "supported_for_v1": supported,
        "recommended_renderer": recommended_renderer,
        "notes": notes,
    }

