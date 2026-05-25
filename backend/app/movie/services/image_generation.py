from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import inspect
from pathlib import Path
import random
import re
import textwrap
from typing import Any

from app.comfyui_client import ComfyUIClient, build_workflow_from_generation
from ..config import Settings


SUPPORTED_IMAGE_MODEL_EXTENSIONS = {".safetensors", ".ckpt", ".pt", ".pth", ".bin"}


def _utc_now_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


class ImageGenerationService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _torch_cuda_available(self) -> bool:
        try:
            import torch

            return bool(torch.cuda.is_available())
        except Exception:
            return False

    def _resolve_runtime_device(self, requested_device: str) -> tuple[str, bool]:
        normalized = str(requested_device or "auto").strip().lower() or "auto"
        cuda_available = self._torch_cuda_available()
        if normalized == "auto":
            return ("cuda" if cuda_available else "cpu"), cuda_available
        if normalized.startswith("cuda"):
            if not cuda_available:
                raise RuntimeError(
                    "CUDA is selected for image generation, but the backend container cannot access an NVIDIA driver. "
                    "Either start Docker with NVIDIA GPU passthrough or switch Image Generation device to `auto` or `cpu` in Settings."
                )
            return normalized, cuda_available
        return normalized, cuda_available

    def list_available_models(self, media_settings: dict) -> dict[str, Any]:
        config = media_settings["image"]
        root_path = self._resolve_inventory_root(config)
        default_model = self._resolve_default_model_value(config)
        models: list[dict[str, Any]] = []

        if root_path.exists():
            for child in sorted(root_path.iterdir(), key=lambda item: (item.is_file(), item.name.lower())):
                if child.name.startswith("."):
                    continue
                if child.is_file() and child.suffix.lower() in SUPPORTED_IMAGE_MODEL_EXTENSIONS:
                    models.append(self._model_option_from_path(root_path, child))
                    continue
                if child.is_dir() and self._is_model_directory(child):
                    models.append(self._model_option_from_path(root_path, child))

        configured_model_path = self._resolve_model_path(config, default_model or None)
        if default_model and configured_model_path.exists():
            if not any(option["value"] == default_model for option in models):
                models.append(self._model_option_from_path(root_path, configured_model_path))

        return {
            "root_path": root_path.as_posix(),
            "default_model": default_model,
            "models": sorted(models, key=lambda item: item["label"].lower()),
        }

    def save_uploaded_model(
        self,
        *,
        media_settings: dict,
        filename: str,
        content: bytes,
        destination_name: str = "",
    ) -> dict[str, Any]:
        root_path, target_path = self.reserve_uploaded_model_path(
            media_settings=media_settings,
            filename=filename,
            destination_name=destination_name,
        )
        target_path.write_bytes(content)
        return self.describe_uploaded_model(root_path=root_path, model_path=target_path)

    def reserve_uploaded_model_path(
        self,
        *,
        media_settings: dict,
        filename: str,
        destination_name: str = "",
    ) -> tuple[Path, Path]:
        if not filename:
            raise RuntimeError("A checkpoint filename is required.")
        source_name = Path(filename).name
        suffix = Path(source_name).suffix.lower()
        if suffix not in SUPPORTED_IMAGE_MODEL_EXTENSIONS:
            raise RuntimeError(
                "Unsupported checkpoint format. Upload a .safetensors, .ckpt, .pt, .pth, or .bin model file."
            )

        root_path = self._resolve_inventory_root(media_settings["image"])
        root_path.mkdir(parents=True, exist_ok=True)
        base_name = destination_name.strip() or Path(source_name).stem
        safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "-", base_name).strip("-") or Path(source_name).stem or "model"
        target_path = root_path / f"{safe_name}{suffix}"
        duplicate_index = 2
        while target_path.exists():
            target_path = root_path / f"{safe_name}-{duplicate_index}{suffix}"
            duplicate_index += 1
        return root_path, target_path

    def describe_uploaded_model(self, *, root_path: Path, model_path: Path) -> dict[str, Any]:
        return self._model_option_from_path(root_path, model_path)

    def _resolve_vae_source(self, config: dict) -> str:
        vae_path = str(config.get("vae_path") or "").strip()
        return vae_path if vae_path else "integrated_checkpoint"

    def _resolve_effective_dtype(self, *, config: dict, model_path: Path, device: str):
        import torch
        requested_dtype = str(config.get("dtype", "auto") or "auto").strip().lower()
        resolved = self._resolve_torch_dtype(requested_dtype, device)
        # Prevent full fp32 pipeline on CUDA as it causes bugs in SDXL from_single_file 
        # and wastes VRAM. The VAE is upcasted to fp32 separately.
        if device.startswith("cuda") and resolved == torch.float32:
            return torch.float16
        return resolved

    def _image_is_all_black(self, image: Any) -> bool:
        try:
            extrema = image.convert("RGB").getextrema()
        except Exception:
            return False
        return bool(extrema) and all(low == 0 and high == 0 for low, high in extrema)

    def test_settings(self, media_settings: dict, hardware_profile: dict) -> dict:
        config = media_settings["image"]
        provider = config["provider"]
        warnings: list[str] = []
        requested_device = str(config.get("device", "auto") or "auto")
        if not config.get("enabled", True):
            return self._result(
                ok=True,
                ready=False,
                status="disabled",
                message="Image generation is disabled in settings.",
                provider=provider,
                resolved_paths={},
                warnings=warnings,
            )
        if provider == "mock":
            return self._result(
                ok=True,
                ready=True,
                status="ready",
                message="Mock image generation is ready for Docker smoke tests.",
                provider=provider,
                resolved_paths={"checkpoint_root": config.get("checkpoint_root", "")},
                warnings=warnings,
            )
        if provider == "diffusers":
            try:
                import diffusers  # noqa: F401
            except Exception as exc:
                return self._result(
                    ok=False,
                    ready=False,
                    status="missing_dependency",
                    message=f"Diffusers is not installed: {exc}",
                    provider=provider,
                    resolved_paths={"checkpoint_root": self._resolve_model_path(config).as_posix()},
                    warnings=warnings,
                )
            model_path = self._resolve_model_path(config)
            if not model_path.exists():
                return self._result(
                    ok=False,
                    ready=False,
                    status="missing_model",
                    message=f"Image model path does not exist: {model_path}",
                    provider=provider,
                    resolved_paths={"checkpoint_root": model_path.as_posix()},
                    warnings=warnings,
                )
            cuda_available = self._torch_cuda_available()
            try:
                resolved_device, _ = self._resolve_runtime_device(requested_device)
            except RuntimeError as exc:
                return self._result(
                    ok=False,
                    ready=False,
                    status="missing_gpu",
                    message=str(exc),
                    provider=provider,
                    resolved_paths={
                        "checkpoint_root": model_path.as_posix(),
                        "requested_device": requested_device,
                        "resolved_device": "unavailable",
                    },
                    warnings=warnings,
                )
            effective_dtype = str(
                self._resolve_effective_dtype(config=config, model_path=model_path, device=resolved_device)
            ).replace("torch.", "")
            if requested_device == "auto" and not cuda_available:
                warnings.append(
                    "CUDA is not available inside the backend container, so diffusers image generation will run on CPU."
                )
            if resolved_device == "cpu" and str(config.get("dtype", "auto")).lower() in {"auto", "fp16", "float16"}:
                warnings.append("CPU image generation automatically uses float32 precision to avoid invalid SDXL decoding.")

            return self._result(
                ok=True,
                ready=True,
                status="ready" if resolved_device == "cuda" else "cpu_only",
                message=(
                    "Diffusers image generation is configured and the model path is available."
                    if resolved_device == "cuda"
                    else "Diffusers image generation is configured, but CUDA is not available inside Docker, so images will render on CPU."
                ),
                provider=provider,
                resolved_paths={
                    "checkpoint_root": model_path.as_posix(),
                    "vae_source": self._resolve_vae_source(config),
                    "requested_device": requested_device,
                    "resolved_device": resolved_device,
                    "effective_dtype": effective_dtype,
                },
                warnings=warnings,
            )
        if provider == "comfyui":
            try:
                result = ComfyUIClient(
                    str(config.get("comfy_endpoint") or ""),
                    timeout_s=int(config.get("comfy_timeout_s") or 300),
                ).test_connection()
                return self._result(
                    ok=True,
                    ready=True,
                    status="ready",
                    message=f"ComfyUI is reachable at {result['endpoint']}.",
                    provider=provider,
                    resolved_paths={
                        "comfy_endpoint": str(result["endpoint"]),
                        "checkpoint_count": str(len(result.get("models") or [])),
                    },
                    warnings=warnings,
                )
            except Exception as exc:
                return self._result(
                    ok=False,
                    ready=False,
                    status="connection_failed",
                    message=f"ComfyUI connection failed: {exc}",
                    provider=provider,
                    resolved_paths={"comfy_endpoint": str(config.get("comfy_endpoint") or "")},
                    warnings=warnings,
                )
        return self._result(
            ok=False,
            ready=False,
            status="unsupported_provider",
            message=f"Unsupported image generation provider: {provider}",
            provider=provider,
            resolved_paths={},
            warnings=warnings,
        )

    def generate_scene_images(
        self,
        *,
        project: dict,
        scene: dict,
        media_settings: dict,
        request: dict,
    ) -> list[dict[str, Any]]:
        base_config = media_settings["image"]
        config = {
            **base_config,
            **{
                key: value
                for key, value in request.items()
                if value is not None
                and key
                in {
                    "model_name",
                    "variant_count",
                    "steps",
                    "cfg_scale",
                    "sampler",
                    "scheduler",
                    "width",
                    "height",
                    "seed_mode",
                    "seed",
                }
            },
        }
        provider = config["provider"]
        resolved_model_name = str(config.get("model_name") or config.get("default_model") or "").strip()
        model_path = self._resolve_model_path(config, resolved_model_name or None)
        model_name = resolved_model_name or model_path.name
        variant_count = int(config.get("variant_count") or 1)
        prompt_text = scene.get("first_image_prompt_text", "").strip() or scene.get("narrative_text", "").strip()
        
        # Character Visual Continuity Guard Injections
        try:
            from app.continuity import ContinuityGuard
            guard = ContinuityGuard(self.settings.projects_root)
            characters_list = project.get("characters", [])
            continuity_result = guard.detect_and_inject_characters(
                prompt=prompt_text,
                characters=characters_list,
                project_id=project["id"]
            )
            prompt_text = continuity_result["modified_prompt"]
            if continuity_result["has_continuity"]:
                print(f"Continuity Guard: Detected characters {continuity_result['applied_characters']}. Injected reference modifiers.")
        except Exception as e:
            print(f"Continuity Guard injection warning: {e}")

        seeds = self._resolve_seeds(
            seed_mode=str(config.get("seed_mode") or "random"),
            seed=config.get("seed"),
            count=variant_count,
        )
        project_root = self.settings.projects_root / project["id"]
        output_dir = project_root / "scene-images" / "generated"
        output_dir.mkdir(parents=True, exist_ok=True)
        generated: list[dict[str, Any]] = []
        for index, seed in enumerate(seeds, start=1):
            filename = f"scene-{scene['order']:02d}-{_utc_now_stamp()}-{index:02d}.png"
            output_path = output_dir / filename
            if provider == "mock":
                self._generate_mock_image(prompt_text, output_path, config, seed, scene["order"], index)
            elif provider == "diffusers":
                self._generate_diffusers_image(prompt_text, output_path, config, resolved_model_name or None, seed)
            elif provider == "comfyui":
                self._generate_comfyui_image(prompt_text, output_path, config, resolved_model_name or model_name, seed)
            else:
                raise RuntimeError(f"Unsupported image generation provider: {provider}")
            generated.append(
                {
                    "relative_path": str(output_path.relative_to(project_root)).replace("\\", "/"),
                    "original_filename": filename,
                    "mime_type": "image/png",
                    "size_bytes": output_path.stat().st_size,
                    "provider": provider,
                    "model_name": model_name,
                    "seed": seed,
                    "prompt_text": prompt_text,
                }
            )
        return generated

    def generate_single_image(
        self,
        *,
        project: dict,
        prompt: str,
        media_settings: dict,
        output_group: str = "character",
        output_stem: str = "image",
        variant: str = "generated",
        negative_prompt: str | None = None,
    ) -> str:
        config = {**media_settings["image"]}
        if negative_prompt is not None:
            config["default_negative_prompt"] = negative_prompt
        provider = config["provider"]
        resolved_model_name = str(config.get("default_model") or "").strip()
        
        seed = random.randint(1, 2**31 - 1)
        project_root = self.settings.projects_root / project["id"]
        safe_group = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(output_group or "image")).strip("-").lower() or "image"
        safe_variant = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(variant or "generated")).strip("-").lower() or "generated"
        safe_stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(output_stem or "image")).strip("-").lower() or "image"
        output_dir = project_root / f"{safe_group}-images" / safe_variant
        output_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f"{safe_stem}-{safe_variant}-{_utc_now_stamp()}.png"
        output_path = output_dir / filename
        
        if provider == "mock":
            # Mock image generation expects scene and variant indices, using 0 here
            self._generate_mock_image(prompt, output_path, config, seed, 0, 0)
        elif provider == "diffusers":
            self._generate_diffusers_image(prompt, output_path, config, resolved_model_name or None, seed)
        elif provider == "comfyui":
            self._generate_comfyui_image(prompt, output_path, config, resolved_model_name, seed)
        else:
            raise RuntimeError(f"Unsupported image generation provider: {provider}")
            
        return str(output_path.relative_to(project_root)).replace("\\", "/")

    def _copy_to_unified_gallery(
        self,
        image_path: Path,
        prompt_text: str,
        config: dict,
        seed: int,
    ) -> None:
        try:
            import shutil
            import json
            import os
            _env_data = os.environ.get("STUDIO_DATA_ROOT") or os.environ.get("MOVIE_TOOL_DATA_ROOT")
            base_path = Path(__file__).resolve().parent.parent.parent.parent
            data_path = Path(_env_data) if _env_data else base_path / 'data'
            generated_dir = data_path / "generated"
            generated_dir.mkdir(parents=True, exist_ok=True)

            gallery_image_path = generated_dir / image_path.name
            shutil.copy2(image_path, gallery_image_path)

            meta = {
                "prompt": prompt_text,
                "negative_prompt": config.get("default_negative_prompt") or config.get("negative_prompt") or "",
                "width": int(config.get("width", 1024)),
                "height": int(config.get("height", 1024)),
                "steps": int(config.get("steps", 24)),
                "cfg_scale": float(config.get("cfg_scale", 6.5)),
                "sampler_name": str(config.get("sampler") or "res_multistep"),
                "scheduler": str(config.get("scheduler") or "simple"),
                "seed": seed
            }
            gallery_meta_path = generated_dir / f"{image_path.stem}.json"
            gallery_meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            print(f"Error copying to unified gallery: {e}")

    def _generate_mock_image(
        self,
        prompt_text: str,
        output_path: Path,
        config: dict,
        seed: int,
        scene_order: int,
        variant_index: int,
    ) -> None:
        from PIL import Image, ImageDraw

        width = int(config.get("width", 1024))
        height = int(config.get("height", 1024))
        tone = hashlib.sha256(f"{seed}:{prompt_text}".encode("utf-8")).hexdigest()
        color = tuple(int(tone[index:index + 2], 16) for index in (0, 2, 4))
        img = Image.new("RGB", (width, height), color=color)
        draw = ImageDraw.Draw(img)
        draw.rectangle((24, 24, width - 24, height - 24), outline=(255, 255, 255), width=4)
        wrapped = textwrap.fill(prompt_text[:240] or "Scene image prompt", width=34)
        draw.text((56, 56), f"Scene {scene_order:02d} • Variant {variant_index:02d}", fill=(255, 255, 255))
        draw.multiline_text((56, 128), wrapped, fill=(255, 255, 255), spacing=10)
        img.save(output_path, format="PNG")
        self._copy_to_unified_gallery(output_path, prompt_text, config, seed)

    def _generate_diffusers_image(
        self,
        prompt_text: str,
        output_path: Path,
        config: dict,
        model_name: str | None,
        seed: int,
    ) -> None:
        import torch
        from diffusers import AutoPipelineForText2Image
        from diffusers import StableDiffusionXLPipeline

        model_path = self._resolve_model_path(config, model_name)
        device, _ = self._resolve_runtime_device(str(config.get("device", "auto")))
        requested_dtype = str(config.get("dtype", "auto") or "auto").strip().lower()
        dtype = self._resolve_effective_dtype(config=config, model_path=model_path, device=device)
        load_kwargs: dict[str, Any] = {
            "torch_dtype": dtype,
            "local_files_only": True,
        }
        optional_vae = self._load_optional_vae(config, dtype)
        if optional_vae is not None:
            load_kwargs["vae"] = optional_vae
        if model_path.is_file():
            load_kwargs["use_safetensors"] = model_path.suffix.lower() == ".safetensors"
            pipe = StableDiffusionXLPipeline.from_single_file(str(model_path), **load_kwargs)
        else:
            load_kwargs["safety_checker"] = None
            pipe = AutoPipelineForText2Image.from_pretrained(str(model_path), **load_kwargs)
            
        if hasattr(pipe, "safety_checker"):
            pipe.safety_checker = None

        try:
            pipe = pipe.to(device)
        except RuntimeError as exc:
            raise RuntimeError(
                "Diffusers image generation could not initialize the requested runtime device. "
                f"Requested `{device}` for model `{model_path.name}`. Original error: {exc}"
            ) from exc

        # Forcibly use the integrated VAE and cast it completely to float32 to avoid SDXL NaNs
        # We also monkey-patch the `decode` method to cast incoming latents to float32. 
        # This completely bypasses diffusers' buggy `upcast_vae()` and guarantees no dtype mismatch crashes.
        if hasattr(pipe, "vae") and pipe.vae is not None and dtype == torch.float16:
            pipe.vae.to(dtype=torch.float32)
            original_decode = pipe.vae.decode
            def _patched_decode(z, *args, **kwargs):
                return original_decode(z.to(dtype=torch.float32), *args, **kwargs)
            pipe.vae.decode = _patched_decode

        pipe.scheduler = self._build_scheduler(
            current_scheduler=pipe.scheduler,
            sampler_name=str(config.get("sampler") or "res_multistep"),
            scheduler_name=str(config.get("scheduler") or "simple"),
        )
        # Obsolete and buggy in PyTorch 2.x for SDXL:
        # if hasattr(pipe, "enable_attention_slicing"):
        #     pipe.enable_attention_slicing()
        # VAE slicing/tiling is disabled as it conflicts with explicit VAE fp32 casting in diffusers
        generator = torch.Generator(device=device if device != "mps" else "cpu").manual_seed(seed)
        image = pipe(
            prompt=prompt_text,
            negative_prompt=config.get("default_negative_prompt", ""),
            num_inference_steps=int(config.get("steps", 24)),
            guidance_scale=float(config.get("cfg_scale", 6.5)),
            width=int(config.get("width", 1024)),
            height=int(config.get("height", 1024)),
            generator=generator,
        ).images[0]
        if self._image_is_all_black(image):
            raise RuntimeError(
                "The generated image decoded to an all-black frame. "
                f"Requested dtype `{requested_dtype}` resolved to `{str(dtype).replace('torch.', '')}` for "
                f"`{model_path.name}`. The U-Net or VAE produced NaNs. If using a distilled model, try lowering CFG scale or steps, or changing the scheduler."
            )
        image.save(output_path, format="PNG")
        self._copy_to_unified_gallery(output_path, prompt_text, config, seed)

    def _generate_comfyui_image(
        self,
        prompt_text: str,
        output_path: Path,
        config: dict,
        model_name: str | None,
        seed: int,
    ) -> None:
        workflow, resolved_seed = build_workflow_from_generation(
            workflow_json=config.get("comfy_workflow_json") or "",
            prompt=prompt_text,
            negative_prompt=str(config.get("default_negative_prompt") or ""),
            model=str(model_name or config.get("default_model") or ""),
            width=int(config.get("width", 1024)),
            height=int(config.get("height", 1024)),
            steps=int(config.get("steps", 24)),
            cfg_scale=float(config.get("cfg_scale", 6.5)),
            sampler_name=str(config.get("sampler") or "euler"),
            scheduler=str(config.get("scheduler") or "normal"),
            seed=seed,
        )
        result = ComfyUIClient(
            str(config.get("comfy_endpoint") or ""),
            timeout_s=int(config.get("comfy_timeout_s") or 300),
        ).render(workflow)
        output_path.write_bytes(result.image_bytes)
        self._copy_to_unified_gallery(output_path, prompt_text, config, resolved_seed)

    def _load_optional_vae(self, config: dict, dtype) -> Any | None:
        from diffusers import AutoencoderKL

        raw_vae_path = str(config.get("vae_path") or "").strip()
        if not raw_vae_path:
            return None
        vae_path = Path(raw_vae_path)
        if not vae_path.is_absolute():
            checkpoint_root = Path(config.get("checkpoint_root") or self.settings.default_image_model_root)
            if checkpoint_root.suffix:
                vae_path = checkpoint_root.parent / raw_vae_path
            else:
                vae_path = checkpoint_root / raw_vae_path
        vae_path = vae_path.resolve()
        if not vae_path.exists():
            raise RuntimeError(f"Configured VAE path does not exist: {vae_path}")
        load_kwargs: dict[str, Any] = {
            "torch_dtype": dtype,
            "local_files_only": True,
        }
        if vae_path.is_file():
            load_kwargs["use_safetensors"] = vae_path.suffix.lower() == ".safetensors"
            return AutoencoderKL.from_single_file(str(vae_path), **load_kwargs)
        return AutoencoderKL.from_pretrained(str(vae_path), **load_kwargs)

    def _build_scheduler(self, *, current_scheduler: Any, sampler_name: str, scheduler_name: str):
        from diffusers import DPMSolverMultistepScheduler, DPMSolverSDEScheduler, KDPM2AncestralDiscreteScheduler, LCMScheduler

        sampler_key = self._normalize_sampler_name(sampler_name)
        scheduler_key = self._normalize_scheduler_name(scheduler_name)
        scheduler_cls = {
            "lcm": LCMScheduler,
            "res_multistep": DPMSolverMultistepScheduler,
            "dpmpp_sde": DPMSolverSDEScheduler,
            "dpmpp_2s_ancestral": KDPM2AncestralDiscreteScheduler,
        }.get(sampler_key, current_scheduler.__class__)

        scheduler_kwargs: dict[str, Any] = {}
        if scheduler_key == "karras":
            scheduler_kwargs["use_karras_sigmas"] = True
        elif scheduler_key == "beta":
            scheduler_kwargs["use_beta_sigmas"] = True
        elif scheduler_key == "gits":
            scheduler_kwargs["use_exponential_sigmas"] = True
        elif scheduler_key == "kl_optimal":
            scheduler_kwargs["rescale_betas_zero_snr"] = True
            scheduler_kwargs["timestep_spacing"] = "trailing"

        supported_names = set(inspect.signature(scheduler_cls.__init__).parameters)
        filtered_kwargs = {key: value for key, value in scheduler_kwargs.items() if key in supported_names}
        try:
            return scheduler_cls.from_config(current_scheduler.config, **filtered_kwargs)
        except Exception:
            try:
                return scheduler_cls.from_config(current_scheduler.config)
            except Exception:
                return current_scheduler

    def _resolve_model_path(self, config: dict, model_name: str | None = None) -> Path:
        configured_root = Path(config.get("checkpoint_root") or self.settings.default_image_model_root)
        candidate_name = model_name or config.get("default_model") or ""
        candidate = Path(candidate_name)
        if candidate_name and candidate.is_absolute():
            return candidate
        if candidate_name:
            if configured_root.suffix:
                sibling = configured_root.parent / candidate_name
                if sibling.exists():
                    return sibling
            joined = configured_root / candidate_name
            if joined.exists():
                return joined
        return configured_root

    def _resolve_inventory_root(self, config: dict) -> Path:
        configured_root = Path(config.get("checkpoint_root") or self.settings.default_image_model_root)
        return configured_root.parent if configured_root.suffix else configured_root

    def _resolve_default_model_value(self, config: dict) -> str:
        configured_root = Path(config.get("checkpoint_root") or self.settings.default_image_model_root)
        explicit_model = str(config.get("default_model") or "").strip()
        if explicit_model:
            return explicit_model
        if configured_root.suffix:
            return configured_root.name
        return ""

    def _is_model_directory(self, candidate: Path) -> bool:
        if (candidate / "model_index.json").exists():
            return True
        for child in candidate.iterdir():
            if child.is_file() and child.suffix.lower() in SUPPORTED_IMAGE_MODEL_EXTENSIONS:
                return True
        return False

    def _model_option_from_path(self, root_path: Path, model_path: Path) -> dict[str, Any]:
        try:
            relative_value = model_path.relative_to(root_path).as_posix()
        except ValueError:
            relative_value = model_path.as_posix()
        label = model_path.name
        return {
            "label": label,
            "value": relative_value,
            "kind": "directory" if model_path.is_dir() else "file",
            "absolute_path": model_path.as_posix(),
            "size_bytes": model_path.stat().st_size if model_path.is_file() else None,
        }

    def _normalize_sampler_name(self, sampler_name: str) -> str:
        normalized = re.sub(r"[^a-z0-9]+", "_", sampler_name.strip().lower()).strip("_")
        aliases = {
            "lcm": "lcm",
            "res_multistep": "res_multistep",
            "restart_multistep": "res_multistep",
            "dpmpp_sde": "dpmpp_sde",
            "dpmpp_2s_ancestral": "dpmpp_2s_ancestral",
            "dpmpp_2s_ancestral_": "dpmpp_2s_ancestral",
        }
        return aliases.get(normalized, normalized)

    def _normalize_scheduler_name(self, scheduler_name: str) -> str:
        normalized = re.sub(r"[^a-z0-9]+", "_", scheduler_name.strip().lower()).strip("_")
        aliases = {
            "simple": "simple",
            "karras": "karras",
            "beta": "beta",
            "gits": "gits",
            "kl_optimal": "kl_optimal",
        }
        return aliases.get(normalized, normalized or "simple")

    def _resolve_torch_dtype(self, dtype_name: str, device: str = "auto"):
        import torch

        normalized_device = str(device or "auto").lower()
        normalized_dtype = str(dtype_name).lower()
        if normalized_device == "cpu" and normalized_dtype in {"auto", "fp16", "float16"}:
            return torch.float32

        mapping = {
            "auto": torch.float16,
            "fp16": torch.float16,
            "float16": torch.float16,
            "bf16": torch.bfloat16,
            "bfloat16": torch.bfloat16,
            "fp32": torch.float32,
            "float32": torch.float32,
        }
        return mapping.get(normalized_dtype, torch.float16)

    def _resolve_seeds(self, *, seed_mode: str, seed: int | None, count: int) -> list[int]:
        if seed_mode == "fixed" and seed is not None:
            return [int(seed) + index for index in range(count)]
        return [random.randint(1, 2**31 - 1) for _ in range(count)]

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
