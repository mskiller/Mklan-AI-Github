# Changelog

## 2026-05-25

- Added Training model inventory for SDXL base checkpoints in
  `data/models/images/Base` and VAE files in `data/models/images/VAE`.
- Replaced manual Base SDXL/VAE text fields with selectors backed by the local
  `.safetensors` inventory.
- Made max training steps editable in the Training UI while still displaying
  the calculated dataset step count.
- Polished the Training page responsive layout and desktop/mobile navigation
  overflow so the model settings view stays clean on desktop and mobile browser
  sizes.
- Changed the Docker default for `STUDIO_TRAINING_DRY_RUN` to `false` so real
  training runs execute when the GPU trainer stack is available.
- Added backend path normalization for Windows-like `data\...` and `/data/...`
  model paths so training commands resolve to mounted `/app/data/...` files.
- Verified a real one-step SDXL LoRA smoke training run on CUDA, producing
  `data/models/loras/codex-real-smoke-lora/codex-real-smoke-lora.safetensors`.
- Added selectable caption models in Training Caption Scan, including local BLIP
  discovery from `data/models/captioning`.
- Added a `clip_tagger` caption provider for CLIP/OpenCLIP tag scoring with
  selectable DanbooruCLIP, LAION CLIP, FashionCLIP, and OpenAI CLIP models.
- Added `scripts/download_caption_models.py` and a default CLIP tag vocabulary
  for preparing caption models under the Studio data folder.
- Added `open_clip_torch` to the GPU backend requirements for LAION OpenCLIP
  support.
- Fixed local BLIP loading for folders that only contain `pytorch_model.bin`
  weights by falling back to a direct local state-dict load when Transformers
  blocks `.bin` loading under torch versions below 2.6.
- Reworked Training caption scan to support explicit providers: `auto`,
  `local_blip`, `koboldcpp_vlm`, `clip_tagger`, and `filename_fallback`.
- Added KoboldCPP/vLLM vision captioning through an OpenAI-compatible
  `/chat/completions` endpoint with image input.
- Added caption source reporting so scan results show whether captions came from
  local BLIP, KoboldCPP/vLLM, skipped existing files, or filename fallback.
- Improved ready dataset ZIP import caption matching for nested folders and
  recorded archive context for future filename fallback.
- Added Training UI controls for caption provider selection and clearer fallback
  warnings.
- Updated `.env.example`, Docker Compose env passthrough, README, and full
  documentation for the caption provider workflow.
