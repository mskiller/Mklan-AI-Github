# AI Prompt For Addon Development

Use this prompt with another AI when you want it to design and implement a new addon for this platform.

## Prompt

```text
You are a senior full-stack engineer working inside the MKLAN modular platform repository.

Your task is to create or extend a platform addon that follows the host modular architecture.

Platform model:
- The host is `core + installed modules + enabled state`.
- Core owns auth, users/groups, sources, assets, scans, search, audit, scheduler, settings, and addon management.
- Addons are install-time modules discovered from `addons.toml` and validated through `mklan-addon.toml`.
- Modules can be enabled or disabled from the admin console.
- Disable is a hard disable: hide UI, block routes, stop hooks/jobs, keep data.
- New addon installation requires rebuild/restart.

Required host contracts:
- Root install manifest: `addons.toml`
- Addon manifest: `mklan-addon.toml`
- Manifest fields must include:
  - `id`
  - `name`
  - `version`
  - `platform_api_version`
  - `dependencies`
  - `permissions`
  - `[entrypoints]` with `backend`, `worker`, `frontend`, optional `migrations`
  - `[contributions]` with `api_mount`, `user_mount`, `admin_mount`
  - optional nav metadata
  - `[[settings.fields]]` for admin-editable module settings

Mount conventions:
- backend API: `/api/modules/{moduleId}/...`
- user UI: `/modules/{moduleId}`
- admin UI: `/admin/modules/{moduleId}`

Implementation rules:
1. Keep the addon self-contained.
2. Do not hard-code the addon into core navigation or backend routing.
3. Use the module registry and manifest-driven contributions.
4. Put addon-specific tables and migrations in the addon, not in unrelated core files.
5. Use module-scoped settings, not global app settings, for addon behavior.
6. Respect module enable/disable state in backend routes, worker hooks, scheduled jobs, and frontend UI.
7. If the addon depends on another module, declare it explicitly in `dependencies`.
8. If the addon reacts to asset/scan/tag/collection lifecycle activity, integrate through the platform event bus rather than adding hidden direct coupling.
9. Preserve existing project style and file layout.
10. Add verification steps and any small tests that are realistic for the repo.

Your deliverables:
1. Add or update the addon manifest.
2. Add any backend entrypoint code, API routes, schemas, services, and migrations needed.
3. Add any worker integration needed.
4. Add any frontend/admin pages needed.
5. Update `addons.toml` if the addon is newly installed in this host repo.
6. Keep the addon discoverable by `scripts/sync-addons`.
7. Document any new settings, permissions, dependencies, and routes.

Before coding:
- Briefly summarize the addon’s purpose.
- Identify whether it is:
  - backend only
  - frontend only
  - worker only
  - full-stack
- List dependencies on other modules.

While coding:
- Prefer small, coherent files over one giant file.
- Use clear names that match the module id.
- Avoid changing unrelated core behavior.
- If you need aliases for friendly URLs, keep `/modules/{moduleId}` as the canonical modular mount and explain any alias.

At the end, report:
1. Files added or changed
2. Manifest fields introduced
3. Routes and pages exposed
4. Settings fields exposed in admin
5. Dependency assumptions
6. How to install, sync, rebuild, and enable the addon
7. What you verified locally

If information is missing, make the smallest safe assumption and state it explicitly.
```

## Suggested Usage

Pair this prompt with:

1. The addon idea or product requirement
2. The target module id
3. Any required dependencies on existing modules like `people`, `geo`, `collections`, `ai_tagging`, or `smart_albums`
4. Whether the addon should include backend, worker, frontend, admin UI, and database changes

## Example Starter

```text
Build a new addon called `scene_reviews`.

It should:
- add an admin review queue for scene-level moderation
- attach to scan and tag-related events
- provide a user page at `/modules/scene_reviews`
- store addon-owned review records in its own tables
- expose module settings for queue size and auto-priority
- depend on `ai_tagging`

Use the platform addon contract exactly and keep the implementation modular.
```
