from __future__ import annotations

import hashlib
import io
import json
import subprocess
import zipfile
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from media_indexer_backend.core.config import get_settings
from media_indexer_backend.models.tables import Asset, Source


def _utcnow_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(tz=timezone.utc).isoformat()


def _cli_database_url() -> str:
    return get_settings().database_url.replace("postgresql+psycopg://", "postgresql://")


def _alembic_head() -> str:
    """Return the highest known revision by walking the down_revision chain."""
    versions_dir = Path(__file__).resolve().parents[3] / "alembic" / "versions"
    # Build {revision: down_revision} map from all version files
    revision_to_down: dict[str, str | None] = {}
    for path in versions_dir.glob("*.py"):
        rev = None
        down = None
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("revision = ") and rev is None:
                rev = line.split("=", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("down_revision = ") and down is None:
                raw = line.split("=", 1)[1].strip().strip('"').strip("'")
                down = None if raw in ("None", "") else raw
        if rev:
            revision_to_down[rev] = down
    if not revision_to_down:
        return "unknown"
    # The head is the revision that no other revision points to as down_revision
    all_revisions = set(revision_to_down.keys())
    down_revisions = {v for v in revision_to_down.values() if v is not None}
    heads = all_revisions - down_revisions
    return sorted(heads)[-1] if heads else sorted(all_revisions)[-1]


def _read_app_version() -> str:
    pyproject = Path(__file__).resolve().parents[3] / "pyproject.toml"
    try:
        for line in pyproject.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("version ="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:  # noqa: BLE001
        pass
    return "unknown"


def create_backup_archive(session: Session) -> tuple[str, io.BytesIO, dict]:
    try:
        dump = subprocess.run(
            ["pg_dump", "--clean", "--if-exists", "--no-owner", "--no-acl", _cli_database_url()],
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="ignore")[:800]
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"pg_dump failed: {stderr}",
        ) from exc
    dump_bytes = dump.stdout
    settings = get_settings()
    manifest = {
        "created_at": _utcnow_iso(),
        "app_version": _read_app_version(),
        "alembic_head": _alembic_head(),
        "asset_count": session.scalar(select(func.count()).select_from(Asset)),
        "source_count": session.scalar(select(func.count()).select_from(Source)),
    }
    manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
    env_keys = "\n".join(f"{key}=" for key in settings.model_fields.keys()).encode("utf-8")
    previews = [
        {"id": str(asset_id), "preview_path": preview_path}
        for asset_id, preview_path in session.execute(
            select(Asset.id, Asset.preview_path).where(Asset.preview_path.is_not(None))
        ).all()
    ]
    previews_bytes = json.dumps(previews, indent=2).encode("utf-8")

    files = {
        "db_dump.sql": dump_bytes,
        "backup_manifest.json": manifest_bytes,
        "env_template.txt": env_keys,
        "previews_index.json": previews_bytes,
    }
    checksums = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    files["checksums.sha256"] = "\n".join(f"{checksum}  {name}" for name, checksum in checksums.items()).encode("utf-8")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    buffer.seek(0)

    created_at = manifest["created_at"].replace(":", "").replace("-", "")
    filename = f"mklanlocal_backup_{created_at[:15]}.zip"
    return filename, buffer, manifest


def validate_backup_archive(content: bytes) -> tuple[dict, bytes]:
    buffer = io.BytesIO(content)
    try:
        with zipfile.ZipFile(buffer) as archive:
            names = set(archive.namelist())
            required = {"backup_manifest.json", "db_dump.sql", "checksums.sha256"}
            if not required.issubset(names):
                missing = sorted(required - names)
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Missing files: {missing}")

            manifest = json.loads(archive.read("backup_manifest.json"))
            sql_bytes = archive.read("db_dump.sql")
            stored_checksums: dict[str, str] = {}
            for line in archive.read("checksums.sha256").decode("utf-8").splitlines():
                if "  " in line:
                    checksum, name = line.split("  ", 1)
                    stored_checksums[name] = checksum
            actual_sql_hash = hashlib.sha256(sql_bytes).hexdigest()
            if stored_checksums.get("db_dump.sql") != actual_sql_hash:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Checksum mismatch for db_dump.sql.")
            return {
                "valid": True,
                "manifest": manifest,
                "sql_size_bytes": len(sql_bytes),
                "checksum_ok": True,
            }, sql_bytes
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Backup archive is not a valid ZIP file.") from exc


def restore_backup_sql(sql_bytes: bytes) -> None:
    # Dispose the connection pool so psql can acquire exclusive locks without
    # competing with live SQLAlchemy connections.
    from media_indexer_backend.db.session import engine
    engine.dispose()

    result = subprocess.run(
        ["psql", _cli_database_url()],
        input=sql_bytes,
        capture_output=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="ignore")[:1000]
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"psql restore failed: {stderr}")

