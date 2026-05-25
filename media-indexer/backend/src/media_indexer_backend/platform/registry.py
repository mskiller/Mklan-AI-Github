from __future__ import annotations

from pathlib import Path
import tomllib

from media_indexer_backend.platform.manifest import ModuleManifest, ModuleSettingField


MANIFEST_DIR = Path(__file__).resolve().parent / "manifests"


def find_repo_root(start: Path | None = None) -> Path:
    current = (start or Path(__file__).resolve()).parent
    for candidate in [current, *current.parents]:
        if (candidate / "infra" / "docker-compose.yml").exists() and (candidate / "backend").exists():
            return candidate
    return Path.cwd()


def _normalize_manifest(
    payload: dict,
    *,
    kind: str,
    source_ref: str | None,
    manifest_path: Path,
) -> ModuleManifest:
    contributions = payload.get("contributions", {}) if isinstance(payload.get("contributions"), dict) else {}
    entrypoints = payload.get("entrypoints", {}) if isinstance(payload.get("entrypoints"), dict) else {}
    settings = payload.get("settings", {}) if isinstance(payload.get("settings"), dict) else {}
    fields_payload = settings.get("fields", [])
    fields = [ModuleSettingField.model_validate(item) for item in fields_payload if isinstance(item, dict)]
    return ModuleManifest(
        id=str(payload.get("id", "")).strip(),
        name=str(payload.get("name") or payload.get("id") or manifest_path.stem),
        version=str(payload.get("version", "0.0.0")),
        description=str(payload.get("description")).strip() if payload.get("description") else None,
        platform_api_version=str(payload.get("platform_api_version", "1")),
        kind="builtin" if kind == "builtin" else "addon",
        source_ref=source_ref,
        enabled_by_default=bool(payload.get("enabled_by_default", True)),
        permissions=[str(item) for item in payload.get("permissions", []) if str(item).strip()],
        dependencies=[str(item) for item in payload.get("dependencies", []) if str(item).strip()],
        backend_entrypoint=str(entrypoints.get("backend")).strip() if entrypoints.get("backend") else None,
        worker_entrypoint=str(entrypoints.get("worker")).strip() if entrypoints.get("worker") else None,
        frontend_entrypoint=str(entrypoints.get("frontend")).strip() if entrypoints.get("frontend") else None,
        backend_migrations=str(entrypoints.get("migrations")).strip() if entrypoints.get("migrations") else None,
        backend_router=str(contributions.get("backend_router")).strip() if contributions.get("backend_router") else None,
        api_mount=str(contributions.get("api_mount")).strip() if contributions.get("api_mount") else None,
        user_mount=str(contributions.get("user_mount")).strip() if contributions.get("user_mount") else None,
        admin_mount=str(contributions.get("admin_mount")).strip() if contributions.get("admin_mount") else None,
        nav_label=str(contributions.get("nav_label")).strip() if contributions.get("nav_label") else None,
        nav_href=str(contributions.get("nav_href")).strip() if contributions.get("nav_href") else None,
        nav_order=int(contributions.get("nav_order", 100)),
        admin_nav_label=str(contributions.get("admin_nav_label")).strip() if contributions.get("admin_nav_label") else None,
        admin_nav_href=str(contributions.get("admin_nav_href")).strip() if contributions.get("admin_nav_href") else None,
        admin_nav_order=int(contributions.get("admin_nav_order", 100)),
        user_visible=bool(contributions.get("user_visible", False)),
        admin_visible=bool(contributions.get("admin_visible", False)),
        settings_fields=fields,
        manifest_path=str(manifest_path),
    )


def _error_manifest(
    *,
    module_id: str,
    version: str,
    source_ref: str | None,
    manifest_path: Path,
    error: str,
) -> ModuleManifest:
    return ModuleManifest(
        id=module_id,
        name=module_id,
        version=version,
        kind="addon",
        source_ref=source_ref,
        enabled_by_default=False,
        manifest_path=str(manifest_path),
        error=error,
    )


def _load_manifest_file(path: Path, *, kind: str, source_ref: str | None) -> ModuleManifest:
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    return _normalize_manifest(payload, kind=kind, source_ref=source_ref, manifest_path=path)


def discover_module_manifests(repo_root: Path | None = None) -> list[ModuleManifest]:
    resolved_root = repo_root or find_repo_root()
    manifests: list[ModuleManifest] = []

    for manifest_path in sorted(MANIFEST_DIR.glob("*.toml")):
        manifests.append(_load_manifest_file(manifest_path, kind="builtin", source_ref=None))

    addons_manifest_path = resolved_root / "addons.toml"
    if not addons_manifest_path.exists():
        return manifests

    payload = tomllib.loads(addons_manifest_path.read_text(encoding="utf-8"))
    for addon_entry in payload.get("addons", []):
        addon_id = str(addon_entry.get("id", "")).strip()
        version = str(addon_entry.get("version", "0.0.0"))
        source_ref = str(addon_entry.get("source_ref", "")).strip() or None
        manifest_ref = str(addon_entry.get("manifest_path", "")).strip()
        manifest_path = (resolved_root / manifest_ref).resolve(strict=False) if manifest_ref else resolved_root / "missing"
        if not addon_id:
            continue
        if not manifest_ref or not manifest_path.exists():
            manifests.append(
                _error_manifest(
                    module_id=addon_id,
                    version=version,
                    source_ref=source_ref,
                    manifest_path=manifest_path,
                    error="Addon manifest_path is missing or does not exist.",
                )
            )
            continue
        try:
            manifest = _load_manifest_file(manifest_path, kind="addon", source_ref=source_ref)
            if manifest.id != addon_id:
                manifest.error = f"Manifest id {manifest.id!r} does not match addons.toml id {addon_id!r}."
            manifests.append(manifest)
        except Exception as exc:  # noqa: BLE001
            manifests.append(
                _error_manifest(
                    module_id=addon_id,
                    version=version,
                    source_ref=source_ref,
                    manifest_path=manifest_path,
                    error=str(exc),
                )
            )

    deduped: dict[str, ModuleManifest] = {}
    for manifest in manifests:
        if manifest.id in deduped:
            duplicate = manifest.model_copy(update={"error": f"Duplicate module id {manifest.id!r} discovered."})
            deduped[manifest.id] = duplicate
            continue
        deduped[manifest.id] = manifest
    return list(deduped.values())


def discover_manifest_map(repo_root: Path | None = None) -> dict[str, ModuleManifest]:
    return {manifest.id: manifest for manifest in discover_module_manifests(repo_root=repo_root)}


def iter_backend_router_refs(repo_root: Path | None = None) -> list[str]:
    refs: list[str] = []
    for manifest in discover_module_manifests(repo_root=repo_root):
        if manifest.backend_router:
            refs.append(manifest.backend_router)
    return refs


def _iter_entrypoints(kind: str, repo_root: Path | None = None) -> list[str]:
    refs: list[str] = []
    for manifest in discover_module_manifests(repo_root=repo_root):
        ref = getattr(manifest, f"{kind}_entrypoint", None)
        if ref:
            refs.append(ref)
    return refs


def iter_backend_entrypoints(repo_root: Path | None = None) -> list[str]:
    return _iter_entrypoints("backend", repo_root=repo_root)


def iter_worker_entrypoints(repo_root: Path | None = None) -> list[str]:
    return _iter_entrypoints("worker", repo_root=repo_root)


def iter_backend_migration_locations(repo_root: Path | None = None) -> list[str]:
    locations: list[str] = []
    for manifest in discover_module_manifests(repo_root=repo_root):
        if not manifest.backend_migrations or not manifest.manifest_path:
            continue
        manifest_dir = Path(manifest.manifest_path).resolve(strict=False).parent
        candidate = Path(manifest.backend_migrations)
        resolved = candidate if candidate.is_absolute() else manifest_dir / candidate
        if resolved.exists():
            locations.append(str(resolved.resolve(strict=False)))
    return locations
