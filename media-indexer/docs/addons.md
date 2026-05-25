# Addon Authoring Guide

This platform now supports `core + installed modules + enabled state`.

Admin users can only enable or disable addons that are already installed. Adding a new addon is a repo change driven by `addons.toml`, then finalized by `scripts/sync-addons`.

## Required addon files

Every addon repo must include:

1. `mklan-addon.toml`
2. A backend package entrypoint if the addon contributes API/runtime hooks
3. A worker package entrypoint if the addon contributes scan-time jobs or enrichers
4. A frontend package or route bundle if the addon contributes UI
5. An optional Alembic migrations folder when the addon owns database tables

See [example-addon manifest](../addons/example-addon/mklan-addon.toml) for a minimal template.
See [AI addon builder prompt](./addon-ai-prompt.md) for a ready-to-use prompt you can give another AI to implement addons against this platform.

## Manifest contract

`mklan-addon.toml` must declare:

1. Identity: `id`, `name`, `version`, `platform_api_version`
2. Install metadata: `dependencies`, `permissions`
3. Runtime entrypoints: `[entrypoints] backend`, `worker`, `frontend`, and optional `migrations`
4. Public mounts: `[contributions] api_mount`, `user_mount`, `admin_mount`
5. Navigation metadata: `nav_label`, `nav_href`, `admin_nav_label`, `admin_nav_href`
6. Module settings schema: `[[settings.fields]]`

## Add a new addon

1. Check out the addon repo somewhere inside this repository, for example `addons/my-addon/`.
2. Add an entry to [addons.toml](../addons.toml) with its locked `version`, `source_ref`, and local `manifest_path`.
3. Run `python scripts/sync-addons`.
4. Review the generated registry files in `backend/generated/` and `frontend/generated/`.
5. Rebuild and restart the app so backend, worker, and frontend load the new addon packages.
6. Open `/admin/modules` and enable the addon.

## Compatibility rules

1. `platform_api_version` must match the host platform version.
2. Module ids must be globally unique.
3. Dependencies must reference other installed modules by id.
4. Disabling a module must stop routes, hooks, and scheduled behavior without deleting addon data.

## Suggested addon layout

```text
my-addon/
  mklan-addon.toml
  pyproject.toml
  src/
    my_addon/
      backend.py
      worker.py
  frontend/
    package.json
    src/
  alembic/
    versions/
```

## Formatted install instruction

Share this with addon authors:

```text
1. Create a repo with mklan-addon.toml at the root.
2. Declare id, version, platform_api_version, dependencies, permissions, entrypoints, mounts, and settings fields.
3. Put the checked-out addon inside this host repo.
4. Add the addon to addons.toml with source_ref, version, and manifest_path.
5. Run python scripts/sync-addons.
6. Rebuild/restart the platform.
7. Enable the module from /admin/modules.
```
