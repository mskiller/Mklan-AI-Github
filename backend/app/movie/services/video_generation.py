"""Video generation service.

Supported providers
-------------------
mock       – FFmpeg looped-still, used for smoke tests / CI.
lightx2v   – Full-precision / bfloat16 WAN model via the LightX2V Python API.
wan_gguf   – GGUF-quantised WAN transformer (e.g. garrychan/Wan-2.2-Remix-I2V-GGUF-Q4)
             loaded through LightX2V's built-in GGUF back-end, optionally combined
             with a distill LoRA (lightx2v/Wan2.2-Distill-Models or its GGUF variant
             jayn7/WAN2.2-I2V_A14B-DISTILL-LIGHTX2V-4STEP-GGUF) and a custom fp8-scaled
             text encoder (Osrivers/nsfw_wan_umt5-xxl_fp8_scaled.safetensors).

Drop-folder workflow (wan_gguf)
-------------------------------
Place any combination of the following into the video-models folder
(default: .movie-tool-smoke/video-models  or  /models/video in Docker):

  • A .gguf file whose name does NOT contain "lora" or "distill"
      → used as the quantised transformer
      → e.g.  Wan-2.2-Remix-I2V-Q4_K_M.gguf
                (garrychan/Wan-2.2-Remix-I2V-GGUF-Q4)

  • A directory that contains config.json
      → used as model_root (config, tokeniser, …)
      → e.g.  wan2.2-Remix/  (FX-FeiHou/wan2.2-Remix on HF)

  • A .safetensors file whose name contains "t5", "umt5", or "encoder"
      → used as the text encoder
      → e.g.  nsfw_wan_umt5-xxl_fp8_scaled.safetensors
                (Osrivers/nsfw_wan_umt5-xxl_fp8_scaled.safetensors)

  • A .safetensors file whose name contains "vae"
      → used as the VAE
      → e.g.  wan_vae.safetensors  (standard WAN VAE)

  • A .gguf OR .safetensors file whose name contains "lora" or "distill"
      → used as the distill LoRA accelerator
      → e.g.  Wan2.2-I2V-A14B-Distill-lightx2v-lora.safetensors
                (lightx2v/Wan2.2-Distill-Models)
           OR  WAN2.2-distill-4step.gguf
                (jayn7/WAN2.2-I2V_A14B-DISTILL-LIGHTX2V-4STEP-GGUF)

When any of gguf_model_path / encoder_root / vae_root / lora_path are left empty
in the settings, the service scans the video-models folder at runtime and fills in
the first matching file for each component automatically.
"""
from __future__ import annotations

from datetime import UTC, datetime
import random
from pathlib import Path
import shutil
import subprocess
from typing import Any

from ..config import Settings


# ---------------------------------------------------------------------------
# File-name matching helpers for folder scanning
# ---------------------------------------------------------------------------

_GGUF_SUFFIX = ".gguf"
_SAFE_SUFFIX = ".safetensors"
_MODEL_SUFFIXES = {_GGUF_SUFFIX, _SAFE_SUFFIX, ".ckpt", ".pt", ".pth", ".bin"}

# Names containing any of these are LoRA / distill adapters, not transformers.
_LORA_KEYWORDS = {"lora", "distill", "adapter"}

# Names containing any of these are text-encoder files.
_ENCODER_KEYWORDS = {"t5", "umt5", "encoder", "clip"}

# Names containing any of these are VAE files.
_VAE_KEYWORDS = {"vae"}


def _name_contains_any(name: str, keywords: set[str]) -> bool:
    lower = name.lower()
    return any(kw in lower for kw in keywords)


def _utc_now_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class VideoGenerationService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    # ------------------------------------------------------------------
    # Folder scanning
    # ------------------------------------------------------------------

    def list_available_video_models(self, media_settings: dict) -> dict[str, Any]:
        """Scan the video-models folder and group files by detected component type.

        Returns a dict matching VideoModelInventoryRead, including an
        ``auto_config`` sub-dict with the best-guess path for each component.
        """
        config = media_settings["video"]
        root = self._resolve_video_models_root(config)

        transformer_gguf: list[dict] = []
        model_dirs: list[dict] = []
        encoders: list[dict] = []
        vaes: list[dict] = []
        loras: list[dict] = []
        other: list[dict] = []

        if root.exists():
            for child in sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
                if child.name.startswith("."):
                    continue
                entry = self._video_model_entry(root, child)

                if child.is_dir():
                    if (child / "config.json").exists() or (child / "model_index.json").exists():
                        model_dirs.append(entry)
                    else:
                        other.append(entry)
                    continue

                suffix = child.suffix.lower()
                name = child.name

                if suffix == _GGUF_SUFFIX:
                    if _name_contains_any(name, _LORA_KEYWORDS):
                        loras.append(entry)
                    else:
                        transformer_gguf.append(entry)
                    continue

                if suffix == _SAFE_SUFFIX:
                    if _name_contains_any(name, _LORA_KEYWORDS):
                        loras.append(entry)
                    elif _name_contains_any(name, _VAE_KEYWORDS):
                        vaes.append(entry)
                    elif _name_contains_any(name, _ENCODER_KEYWORDS):
                        encoders.append(entry)
                    else:
                        other.append(entry)
                    continue

                if suffix in _MODEL_SUFFIXES:
                    other.append(entry)

        auto_config: dict[str, str] = {
            "gguf_model_path": transformer_gguf[0]["absolute_path"] if transformer_gguf else "",
            "model_root": model_dirs[0]["absolute_path"] if model_dirs else "",
            "encoder_root": encoders[0]["absolute_path"] if encoders else "",
            "vae_root": vaes[0]["absolute_path"] if vaes else "",
            "lora_path": loras[0]["absolute_path"] if loras else "",
        }

        return {
            "root_path": root.as_posix(),
            "transformer_gguf": transformer_gguf,
            "model_dirs": model_dirs,
            "encoders": encoders,
            "vaes": vaes,
            "loras": loras,
            "other": other,
            "auto_config": auto_config,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def test_settings(self, media_settings: dict, hardware_profile: dict) -> dict:
        config = media_settings["video"]
        provider = config["provider"]
        warnings: list[str] = []

        if not config.get("enabled", True):
            return self._result(
                ok=True, ready=False, status="disabled",
                message="Video generation is disabled in settings.",
                provider=provider, resolved_paths={}, warnings=warnings,
            )

        if provider == "mock":
            return self._result(
                ok=True, ready=True, status="ready",
                message="Mock video generation is ready for Docker smoke tests.",
                provider=provider,
                resolved_paths={"model_root": config.get("model_root", "")},
                warnings=warnings,
            )

        if provider in ("lightx2v", "wan_gguf"):
            try:
                import lightx2v  # noqa: F401
            except Exception as exc:
                return self._result(
                    ok=False, ready=False, status="missing_dependency",
                    message=f"LightX2V is not installed: {exc}",
                    provider=provider, resolved_paths={}, warnings=warnings,
                )

            # For wan_gguf auto-fill empty paths from the folder scan.
            if provider == "wan_gguf":
                config = self._auto_fill_gguf_config(config, media_settings, warnings)

            resolved: dict[str, str] = {}
            missing: list[str] = []

            if provider == "wan_gguf":
                gguf_path = Path(config.get("gguf_model_path") or "")
                if not gguf_path.is_file():
                    missing.append(
                        f"No .gguf transformer found (gguf_model_path='{gguf_path}'). "
                        "Drop a .gguf file into the video-models folder or set gguf_model_path."
                    )
                else:
                    resolved["gguf_model_path"] = str(gguf_path)
                raw_root = config.get("model_root") or ""
                if raw_root:
                    resolved["model_root"] = raw_root
                else:
                    warnings.append(
                        "model_root is not set – will use the video-models folder for config files."
                    )
            else:
                model_root = self._resolve_model_root(config)
                if not model_root.exists():
                    missing.append(f"Video model root does not exist: {model_root}")
                else:
                    resolved["model_root"] = model_root.as_posix()

            for field, label, hint in [
                ("encoder_root", "text encoder",
                 "Add a safetensors whose name contains 't5', 'umt5', or 'encoder'."),
                ("vae_root", "VAE",
                 "Add a safetensors whose name contains 'vae'."),
                ("lora_path", "distill LoRA",
                 "Add a safetensors/gguf whose name contains 'lora' or 'distill'. "
                 "Without it the full diffusion schedule runs (slower)."),
            ]:
                val = config.get(field) or ""
                if val:
                    resolved[field] = val
                else:
                    warnings.append(f"{label} not found – {hint}")

            if not hardware_profile.get("cuda_available"):
                warnings.append(
                    "CUDA is not available. Real Wan video generation will likely not be practical."
                )

            if missing:
                return self._result(
                    ok=False, ready=False, status="missing_model",
                    message="; ".join(missing),
                    provider=provider, resolved_paths=resolved, warnings=warnings,
                )

            return self._result(
                ok=True, ready=True, status="ready",
                message=f"LightX2V ({provider}) is installed and all configured paths exist.",
                provider=provider, resolved_paths=resolved, warnings=warnings,
            )

        return self._result(
            ok=False, ready=False, status="unsupported_provider",
            message=f"Unsupported video generation provider: {provider}",
            provider=provider, resolved_paths={}, warnings=warnings,
        )

    def generate_sequence_video(
        self,
        *,
        project: dict,
        scene: dict,
        sequence: dict,
        input_asset: dict,
        media_settings: dict,
        request: dict,
    ) -> dict[str, Any]:
        config = media_settings["video"]
        provider = config["provider"]
        model_name = request.get("model_name") or config.get("model_class") or "wan2.2_i2v"
        seed = self._resolve_seed(
            seed_mode=request.get("seed_mode") or config.get("seed_mode") or "random",
            seed=request.get("seed", config.get("seed")),
        )
        project_root = self.settings.projects_root / project["id"]
        output_dir = project_root / "sequence-videos" / "generated"
        frame_dir = project_root / "sequence-frames"
        output_dir.mkdir(parents=True, exist_ok=True)
        frame_dir.mkdir(parents=True, exist_ok=True)
        input_path = project_root / input_asset["relative_path"]
        if not input_path.exists():
            raise RuntimeError(f"Input frame is missing for sequence {sequence['order']:02d}.")

        stamp = _utc_now_stamp()
        native_output = output_dir / f"sequence-{sequence['absolute_order']:03d}-{stamp}-native.mp4"
        final_output = output_dir / f"sequence-{sequence['absolute_order']:03d}-{stamp}.mp4"

        if provider == "mock":
            self._generate_mock_video(input_path, native_output, project, config)
        elif provider == "lightx2v":
            self._generate_lightx2v_video(
                input_path, native_output, sequence["wan_prompt_text"], config, model_name, seed
            )
        elif provider == "wan_gguf":
            _dummy_warnings: list[str] = []
            config = self._auto_fill_gguf_config(config, media_settings, _dummy_warnings)
            self._generate_wan_gguf_video(
                input_path, native_output, sequence["wan_prompt_text"], config, model_name, seed
            )
        else:
            raise RuntimeError(f"Unsupported video generation provider: {provider}")

        native_duration = self._probe_duration(native_output)
        output_duration = native_duration
        if config.get("retime_mode") != "none":
            output_duration = float(sequence["target_duration_s"])
            self._retime_video(
                source_path=native_output,
                output_path=final_output,
                target_duration_s=output_duration,
                target_fps=int(config.get("target_output_fps") or project["output_fps"]),
                mode=str(config.get("retime_mode", "fit_duration")),
            )
            native_output.unlink(missing_ok=True)
        else:
            shutil.move(str(native_output), str(final_output))

        last_frame_path = frame_dir / f"sequence-{sequence['absolute_order']:03d}-{stamp}-last.png"
        self.extract_last_frame(final_output, last_frame_path)
        return {
            "relative_path": str(final_output.relative_to(project_root)).replace("\\", "/"),
            "original_filename": final_output.name,
            "mime_type": "video/mp4",
            "size_bytes": final_output.stat().st_size,
            "provider": provider,
            "model_name": model_name,
            "seed": seed,
            "prompt_text": sequence["wan_prompt_text"],
            "native_duration_s": native_duration,
            "output_duration_s": self._probe_duration(final_output),
            "input_frame": input_asset,
            "last_frame": {
                "relative_path": str(last_frame_path.relative_to(project_root)).replace("\\", "/"),
                "original_filename": last_frame_path.name,
                "mime_type": "image/png",
                "size_bytes": last_frame_path.stat().st_size,
                "created_at": datetime.now(UTC).isoformat(),
            },
        }

    def extract_last_frame(self, video_path: Path, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [
                self.settings.ffmpeg_binary,
                "-y",
                "-sseof",
                "-0.1",
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                str(output_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or not output_path.exists():
            raise RuntimeError(result.stderr.strip() or "Failed to extract the last frame from the generated video.")

    # ------------------------------------------------------------------
    # Provider implementations
    # ------------------------------------------------------------------

    def _generate_mock_video(
        self, input_path: Path, output_path: Path, project: dict, config: dict
    ) -> None:
        fps = int(config.get("target_output_fps") or project["output_fps"])
        native_duration_s = max(1.0, int(config.get("native_frame_count", 49)) / max(fps, 1))
        result = subprocess.run(
            [
                self.settings.ffmpeg_binary,
                "-y",
                "-loop",
                "1",
                "-i",
                str(input_path),
                "-t",
                f"{native_duration_s:.2f}",
                "-vf",
                (
                    f"fps={fps},"
                    f"scale={int(config.get('native_width', 832))}:{int(config.get('native_height', 480))}:"
                    "force_original_aspect_ratio=decrease,"
                    f"pad={int(config.get('native_width', 832))}:{int(config.get('native_height', 480))}:(ow-iw)/2:(oh-ih)/2,"
                    "format=yuv420p"
                ),
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(output_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Mock video generation failed.")

    def _generate_lightx2v_video(
        self,
        input_path: Path,
        output_path: Path,
        prompt_text: str,
        config: dict,
        model_name: str,
        seed: int,
    ) -> None:
        """Full-precision / bfloat16 WAN I2V via LightX2V.

        Wires up encoder_root, vae_root, lora_path, and quantization_preset
        in addition to the core model_root.
        """
        from lightx2v import LightX2VPipeline

        model_root = self._resolve_model_root(config, model_name)
        encoder_root: str | None = config.get("encoder_root") or None
        vae_root: str | None = config.get("vae_root") or None
        lora_path: str | None = config.get("lora_path") or None
        lora_scale = float(config.get("lora_scale", 1.0))
        quant_preset = config.get("quantization_preset") or "auto"

        pipeline_kwargs: dict[str, Any] = {
            "model_path": str(model_root),
            "model_cls": str(config.get("model_class", "wan2.2_i2v")),
            "task": "i2v",
        }
        if encoder_root:
            pipeline_kwargs["text_encoder_path"] = encoder_root
        if vae_root:
            pipeline_kwargs["vae_path"] = vae_root
        if quant_preset not in ("auto", "", None):
            pipeline_kwargs["quant_config"] = {"transformer": {"quant_type": quant_preset}}

        pipe = LightX2VPipeline(**pipeline_kwargs)
        if lora_path:
            pipe.load_lora(lora_path, scale=lora_scale)

        pipe.enable_offload(
            cpu_offload=bool(config.get("cpu_offload", True)),
            offload_granularity="block",
            text_encoder_offload=bool(config.get("text_encoder_offload", True)),
            image_encoder_offload=bool(config.get("image_encoder_offload", False)),
            vae_offload=bool(config.get("vae_offload", False)),
        )
        guidance = [float(config.get("guidance_scale", 3.5)), float(config.get("guidance_scale", 3.5))]
        pipe.create_generator(
            attn_mode=str(config.get("attention_mode", "sage_attn2")),
            infer_steps=int(config.get("infer_steps", 4)),
            height=int(config.get("native_height", 480)),
            width=int(config.get("native_width", 832)),
            num_frames=int(config.get("native_frame_count", 49)),
            guidance_scale=guidance,
            sample_shift=float(config.get("sample_shift", 5.0)),
        )
        pipe.generate(
            seed=seed,
            image_path=str(input_path),
            prompt=prompt_text,
            negative_prompt="",
            save_result_path=str(output_path),
        )
        if not output_path.exists():
            raise RuntimeError("LightX2V (lightx2v) did not write the generated video to disk.")

    def _generate_wan_gguf_video(
        self,
        input_path: Path,
        output_path: Path,
        prompt_text: str,
        config: dict,
        model_name: str,
        seed: int,
    ) -> None:
        """GGUF-quantised WAN I2V via LightX2V's GGUF back-end.

        All paths are expected to be pre-filled by _auto_fill_gguf_config().

        Required config
        ---------------
        gguf_model_path
            Absolute path to the quantised transformer .gguf file.
            Download from: garrychan/Wan-2.2-Remix-I2V-GGUF-Q4

        Optional config
        ---------------
        model_root      – directory with config.json / tokeniser for the base model.
                          Falls back to the parent of gguf_model_path when empty.
                          Point at FX-FeiHou/wan2.2-Remix for local clone.
        encoder_root    – nsfw_wan_umt5-xxl_fp8_scaled.safetensors
                          (Osrivers/nsfw_wan_umt5-xxl_fp8_scaled.safetensors)
        vae_root        – standard WAN VAE safetensors file or directory
        lora_path       – lightx2v/Wan2.2-Distill-Models  (full precision)
                          OR  jayn7/WAN2.2-I2V_A14B-DISTILL-LIGHTX2V-4STEP-GGUF
        lora_scale      – adapter strength, default 1.0
        """
        from lightx2v import LightX2VPipeline

        gguf_path = Path(config.get("gguf_model_path") or "")
        if not gguf_path.is_file():
            raise RuntimeError(
                f"gguf_model_path is not a valid file: '{gguf_path}'. "
                "Drop a .gguf transformer file into the video-models folder or set gguf_model_path."
            )

        raw_model_root = config.get("model_root") or ""
        model_root = Path(raw_model_root) if raw_model_root else gguf_path.parent

        encoder_root: str | None = config.get("encoder_root") or None
        vae_root: str | None = config.get("vae_root") or None
        lora_path: str | None = config.get("lora_path") or None
        lora_scale = float(config.get("lora_scale", 1.0))

        quant_config: dict[str, Any] = {
            "transformer": {
                "quant_type": "gguf",
                "quant_path": str(gguf_path),
            }
        }

        pipeline_kwargs: dict[str, Any] = {
            "model_path": str(model_root),
            "model_cls": str(config.get("model_class", "wan2.2_i2v")),
            "task": "i2v",
            "quant_config": quant_config,
        }
        if encoder_root:
            pipeline_kwargs["text_encoder_path"] = encoder_root
        if vae_root:
            pipeline_kwargs["vae_path"] = vae_root

        pipe = LightX2VPipeline(**pipeline_kwargs)
        if lora_path:
            pipe.load_lora(lora_path, scale=lora_scale)

        pipe.enable_offload(
            cpu_offload=bool(config.get("cpu_offload", True)),
            offload_granularity="block",
            text_encoder_offload=bool(config.get("text_encoder_offload", True)),
            image_encoder_offload=bool(config.get("image_encoder_offload", False)),
            vae_offload=bool(config.get("vae_offload", False)),
        )
        # With the 4-step distill LoRA: infer_steps=4, guidance_scale ~1.0.
        guidance = [float(config.get("guidance_scale", 3.5)), float(config.get("guidance_scale", 3.5))]
        pipe.create_generator(
            attn_mode=str(config.get("attention_mode", "sage_attn2")),
            infer_steps=int(config.get("infer_steps", 4)),
            height=int(config.get("native_height", 480)),
            width=int(config.get("native_width", 832)),
            num_frames=int(config.get("native_frame_count", 49)),
            guidance_scale=guidance,
            sample_shift=float(config.get("sample_shift", 5.0)),
        )
        pipe.generate(
            seed=seed,
            image_path=str(input_path),
            prompt=prompt_text,
            negative_prompt="",
            save_result_path=str(output_path),
        )
        if not output_path.exists():
            raise RuntimeError("LightX2V (wan_gguf) did not write the generated video to disk.")

    # ------------------------------------------------------------------
    # Auto-fill helpers
    # ------------------------------------------------------------------

    def _auto_fill_gguf_config(
        self,
        config: dict,
        media_settings: dict,
        warnings: list[str],
    ) -> dict:
        """Return a copy of config with empty path fields filled from folder scan.

        Only fills a field when it is empty/None; explicit values are preserved.
        """
        needs_fill = not all([
            config.get("gguf_model_path"),
            config.get("encoder_root"),
            config.get("vae_root"),
            config.get("lora_path"),
        ])
        if not needs_fill:
            return config

        inventory = self.list_available_video_models(media_settings)
        auto = inventory["auto_config"]
        filled = dict(config)

        for field in ("gguf_model_path", "model_root", "encoder_root", "vae_root", "lora_path"):
            if not filled.get(field) and auto.get(field):
                filled[field] = auto[field]
                warnings.append(f"Auto-detected {field}: {auto[field]}")

        return filled

    def _resolve_video_models_root(self, config: dict) -> Path:
        """Return the directory that should be scanned for video model files."""
        raw = config.get("model_root") or ""
        if raw:
            candidate = Path(raw)
            if candidate.is_dir():
                return candidate
            if candidate.exists():
                return candidate.parent
        return Path(self.settings.default_video_model_root)

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _video_model_entry(self, root: Path, model_path: Path) -> dict[str, Any]:
        try:
            value = model_path.relative_to(root).as_posix()
        except ValueError:
            value = model_path.as_posix()
        return {
            "label": model_path.name,
            "value": value,
            "kind": "directory" if model_path.is_dir() else "file",
            "absolute_path": model_path.as_posix(),
            "size_bytes": model_path.stat().st_size if model_path.is_file() else None,
        }

    def _retime_video(
        self,
        *,
        source_path: Path,
        output_path: Path,
        target_duration_s: float,
        target_fps: int,
        mode: str,
    ) -> None:
        source_duration = self._probe_duration(source_path)
        if source_duration <= 0:
            shutil.move(str(source_path), str(output_path))
            return
        factor = max(target_duration_s, 0.1) / max(source_duration, 0.1)
        if abs(factor - 1.0) < 0.02 and target_fps <= 0:
            shutil.move(str(source_path), str(output_path))
            return
        if mode == "frame_interpolate_fit":
            filter_chain = f"setpts={factor:.6f}*PTS,minterpolate=fps={target_fps},format=yuv420p"
        else:
            filter_chain = f"setpts={factor:.6f}*PTS,fps={target_fps},format=yuv420p"
        result = subprocess.run(
            [
                self.settings.ffmpeg_binary,
                "-y",
                "-i",
                str(source_path),
                "-vf",
                filter_chain,
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(output_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Failed to retime the generated video.")

    def _probe_duration(self, video_path: Path) -> float:
        ffprobe = shutil.which("ffprobe")
        if ffprobe is None:
            return 0.0
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            return round(float(result.stdout.strip()), 2)
        except Exception:
            return 0.0

    def _resolve_model_root(self, config: dict, model_name: str | None = None) -> Path:
        configured_root = Path(config.get("model_root") or self.settings.default_video_model_root)
        candidate_name = model_name or ""
        candidate = Path(candidate_name)
        if candidate_name and candidate.is_absolute():
            return candidate
        if candidate_name:
            joined = configured_root / candidate_name
            if joined.exists():
                return joined
        return configured_root

    def _resolve_seed(self, *, seed_mode: str, seed: int | None) -> int:
        if seed_mode == "fixed" and seed is not None:
            return int(seed)
        return random.randint(1, 2**31 - 1)

    def _result(
        self,
        *,
        ok: bool,
        ready: bool,
        status: str,
        message: str,
        provider: str,
        resolved_paths: dict[str, str],
        warnings: list[str],
    ) -> dict:
        return {
            "ok": ok,
            "ready": ready,
            "status": status,
            "message": message,
            "provider": provider,
            "resolved_paths": resolved_paths,
            "warnings": warnings,
        }
