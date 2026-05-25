# Data Directory

This directory is runtime storage for Mklan Studio.

The public repository keeps only documentation, placeholder files, and a tiny
text-only starter wildcard set. Do not commit generated images, databases,
training datasets, model weights, Hugging Face caches, Postgres files, logs, or
personal prompt libraries.

## Layout

```text
data/
  cards/                  SillyTavern card creator database and project assets
  exports/                Wildcard and prompt exports
  generated/              Generated images and sidecar metadata
  integrations/comfyui/   Optional local ComfyUI custom nodes
  media_previews/         Media Indexer preview files
  models/                 Local model weights and captioning caches
  movie/                  Movie Script database and project assets
  postgres/               Media Indexer PostgreSQL data
  training/               Datasets, run configs, logs, and artifacts
  wildcards/              Wildcard source files and runtime database
```

Most folders are created lazily by the app. Keep machine-specific content local.
