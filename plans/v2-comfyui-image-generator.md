# V2 ComfyUI Image Generator Status

Last updated: 2026-05-25

## Goal

Mklan Studio can use an external ComfyUI server as an image-generation backend.
Users configure a ComfyUI endpoint, store API-format workflow JSON, and the
backend injects runtime values before queueing the workflow.

This is the active image workflow direction for the Studio. The old visual
`ComfyNodes` React component still exists in the source tree, but the routed
product surface now uses Settings, Generation, Studio APIs, and `/api/workflows`.

## Implemented

- Shared backend ComfyUI client using ComfyUI HTTP endpoints:
  - `GET /system_stats` for connection tests.
  - `GET /models/checkpoints` for checkpoint inventory.
  - `POST /prompt` to queue API-format workflow JSON.
  - `GET /history/{prompt_id}` to poll completion.
  - `GET /view` to retrieve generated images.
- Placeholder substitution for API workflow JSON:
  - `%prompt%`
  - `%negative_prompt%`
  - `%width%`
  - `%height%`
  - `%steps%`
  - `%scale%`, `%cfg%`, `%cfg_scale%`
  - `%sampler%`, `%sampler_name%`
  - `%scheduler%`
  - `%seed%`
  - `%model%`
  - `%denoise%`
- Built-in txt2img fallback workflow when no custom workflow JSON is configured.
- Studio Settings support for:
  - Selecting ComfyUI as the image provider.
  - Testing the ComfyUI connection.
  - Configuring timeout.
  - Storing workflow JSON.
- `/api/studio/generate-image` integration for the Settings sandbox and
  Wildcards image sandbox.
- Generation page image jobs and generated image browsing.
- V2 workflow API:
  - `GET /api/workflows/presets`
  - `POST /api/workflows/validate`
  - `POST /api/workflows/render`
- Movie media-generation provider integration for scene and character image
  jobs.
- Shared job manager visibility through `/api/jobs/overview`.

## Current Entry Points

```text
GET  /api/studio/settings
POST /api/studio/settings
POST /api/studio/comfyui/test
GET  /api/studio/models
POST /api/studio/generate-image

GET  /api/workflows/presets
POST /api/workflows/validate
POST /api/workflows/render

GET  /api/jobs/overview
```

Frontend surfaces:

- `/settings`: configure provider, endpoint, model inventory, and sandbox test.
- `/generation`: queue image jobs and review generated images.
- `/wildcards`: prompt sandbox generation.
- `/movie`: image jobs for movie planning.

## Known Boundaries

- ComfyUI must run separately on the host or a reachable machine.
- The ComfyUI client can listen for websocket progress and falls back to
  history polling. The frontend currently sees this through Studio job polling,
  not a dedicated live ComfyUI event stream.
- Image-to-image and reference upload flows are not fully surfaced yet.
- Model inventory currently focuses on the model groups exposed by the backend
  and workflow validation path. Broader ComfyUI folder browsing can be expanded.
- Workflow authoring is JSON-first today. A routed visual node editor is future
  work.

## Next Upgrades

1. Add task-specific workflow presets for portraits, scene frames, wildcard
   sandbox runs, and training sample previews.
2. Add a workflow mapping UI for users who prefer assigning node ids instead of
   editing placeholders in JSON.
3. Expose richer ComfyUI progress events in shared jobs and frontend job panels.
4. Add image-to-image and reference-image upload before queueing workflows.
5. Expand model inventory browsing for LoRA, VAE, ControlNet, and custom model
   folders.
