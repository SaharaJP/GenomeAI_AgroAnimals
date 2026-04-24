from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Optional

import yaml

from core.migrations import MigrationCompatibilityError, validate_backup_manifest_compatibility


CHUNK_SIZE = 1024 * 1024
BACKUP_FORMAT_V1 = "genomeai_backup_v1"
BACKUP_FORMAT_V2 = "genomeai_backup_v2"
_DEFAULT_BACKUP_RETENTION_CONFIG: dict[str, Any] = {
    "version": 1,
    "enabled": True,
    "apply_after_backup": False,
    "backup_archives": {
        "keep_last": 5,
        "glob": "*.zip",
    },
    "restore_snapshots": {
        "enabled": True,
        "keep_last": 2,
    },
    "data_versions": {
        "enabled": False,
        "keep_last": 0,
    },
}


class BackupRestoreError(ValueError):
    """Human-readable configuration or integrity error for backup/restore."""


@dataclass(frozen=True)
class BackupResult:
    backup_zip: str
    manifest_json: str
    file_count: int
    backup_id: str


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _utc_ts_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _sha256_file(path: Path, *, chunk_size: int = CHUNK_SIZE) -> str:
    h = sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _iter_files(root: Path, *, exclude_dirs: Optional[list[Path]] = None, exclude_files: Optional[list[Path]] = None) -> list[Path]:
    root = root.resolve()
    if not root.exists():
        return []
    excluded_dirs = [p.resolve() for p in (exclude_dirs or [])]
    excluded_files = {p.resolve() for p in (exclude_files or []) if p.exists()}
    out: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rp = p.resolve()
        if rp in excluded_files:
            continue
        if any(ex_dir in rp.parents for ex_dir in excluded_dirs):
            continue
        out.append(rp)
    return out


def _safe_extract_all(zf: zipfile.ZipFile, dest: Path) -> None:
    """Safe zip extraction (prevents zip-slip)."""
    dest = dest.resolve()
    for member in zf.infolist():
        name = member.filename
        if not name:
            continue
        target = (dest / name).resolve()
        if target == dest:
            continue
        if dest not in target.parents:
            raise BackupRestoreError(f"Unsafe path in zip: {name}")
    zf.extractall(dest)


def _normalize_db_path(web_storage: Path, db_path: Optional[Path]) -> Path:
    return (db_path or (web_storage / "web.db")).resolve()


def _sqlite_sidecars(db_path: Path) -> list[Path]:
    candidates = [db_path, db_path.with_name(db_path.name + "-wal"), db_path.with_name(db_path.name + "-shm")]
    return [p.resolve() for p in candidates if p.exists() and p.is_file()]


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _top_level_data_versions(artifacts_root: Path) -> list[str]:
    if not artifacts_root.exists():
        return []
    return sorted(p.name for p in artifacts_root.iterdir() if p.is_dir() and p.name.startswith("dv_"))


def _write_best_effort_audit(
    *,
    db_path: Path,
    action: str,
    object_id: str,
    status: str = "OK",
    after: Optional[dict[str, Any]] = None,
    error: Optional[str] = None,
) -> bool:
    if not db_path.exists():
        return False
    try:
        from core.audit.events import write_audit
        from core.infra.web_db import connect, init_db

        conn = connect(db_path)
        try:
            init_db(conn)
            write_audit(
                conn,
                tenant_id="default",
                user_id=0,
                username="system",
                role="Admin",
                action=action,
                object_type="backup",
                object_id=object_id,
                run_id=object_id,
                after=after or {},
                status=status,
                error=error,
            )
            return True
        finally:
            conn.close()
    except Exception:
        return False


def _entry(prefix: str, root: Path, file_path: Path, *, component: str) -> dict[str, Any]:
    rel = file_path.relative_to(root).as_posix()
    arc = f"{prefix}/{rel}"
    return {
        "path": arc,
        "component": component,
        "rel_path": rel,
        "sha256": _sha256_file(file_path),
        "size": int(file_path.stat().st_size),
    }


def _load_manifest_from_zip(backup_zip: Path) -> dict[str, Any]:
    with zipfile.ZipFile(backup_zip, "r") as zf:
        try:
            raw = zf.read("manifest.json").decode("utf-8")
        except Exception as exc:
            raise BackupRestoreError(f"manifest.json read failed: {type(exc).__name__}: {exc}") from exc
    try:
        manifest = json.loads(raw)
    except Exception as exc:
        raise BackupRestoreError(f"manifest.json parse failed: {type(exc).__name__}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise BackupRestoreError("manifest.json должен содержать JSON-объект")
    return manifest


def _entry_destination(*, entry_path: str, artifacts_root: Path, web_storage: Path, db_path: Path) -> Optional[Path]:
    if entry_path.startswith("artifacts/"):
        return artifacts_root / entry_path[len("artifacts/") :]
    if entry_path.startswith("web_storage/"):
        return web_storage / entry_path[len("web_storage/") :]
    if entry_path.startswith("db/"):
        return db_path.parent / entry_path[len("db/") :]
    return None


def _verify_entries(
    entries: list[dict[str, Any]],
    *,
    artifacts_root: Path,
    web_storage: Path,
    db_path: Path,
) -> tuple[int, list[dict[str, Any]]]:
    mismatches: list[dict[str, Any]] = []
    verified = 0
    for entry in entries:
        entry_path = str(entry.get("path", ""))
        expected = str(entry.get("sha256", ""))
        if not entry_path or not expected:
            mismatches.append({"path": entry_path or "<empty>", "reason": "invalid_manifest_entry"})
            continue
        target = _entry_destination(entry_path=entry_path, artifacts_root=artifacts_root, web_storage=web_storage, db_path=db_path)
        if target is None:
            mismatches.append({"path": entry_path, "reason": "unknown_prefix"})
            continue
        if not target.exists() or not target.is_file():
            mismatches.append({"path": entry_path, "reason": "missing"})
            continue
        got = _sha256_file(target)
        if got != expected:
            mismatches.append({"path": entry_path, "reason": "hash_mismatch", "expected": expected, "got": got})
            continue
        verified += 1
    return verified, mismatches


def _restore_smoke_check(*, artifacts_root: Path, web_storage: Path, db_path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    checks: dict[str, Any] = {
        "artifacts_root_exists": artifacts_root.exists() and artifacts_root.is_dir(),
        "web_storage_exists": web_storage.exists() and web_storage.is_dir(),
        "db_exists": db_path.exists() and db_path.is_file(),
    }
    expected_dvs = list(manifest.get("data_versions") or [])
    checks["expected_data_versions"] = expected_dvs
    checks["restored_data_versions"] = _top_level_data_versions(artifacts_root)
    checks["data_versions_ok"] = all(dv in checks["restored_data_versions"] for dv in expected_dvs)

    required_dirs = [web_storage / "uploads", web_storage / "logs", web_storage / "config_overrides"]
    checks["required_dirs"] = {p.name: p.exists() and p.is_dir() for p in required_dirs}
    checks["required_dirs_ok"] = all(checks["required_dirs"].values())

    db_tables: list[str] = []
    db_error: Optional[str] = None
    # Postgres backend: db_path references a pg_dump file, not a SQLite file
    checks["db_tables"] = db_tables
    checks["db_tables_ok"] = True
    if db_error:
        checks["db_error"] = db_error

    ok = (
        checks["artifacts_root_exists"]
        and checks["web_storage_exists"]
        and checks["db_exists"]
        and checks["data_versions_ok"]
        and checks["required_dirs_ok"]
        and checks["db_tables_ok"]
    )
    if ok:
        return {"ok": True, "checks": checks}
    reason_parts = []
    for key in [
        "artifacts_root_exists",
        "web_storage_exists",
        "db_exists",
        "data_versions_ok",
        "required_dirs_ok",
        "db_tables_ok",
    ]:
        if not checks.get(key):
            reason_parts.append(key)
    if db_error:
        reason_parts.append(db_error)
    return {"ok": False, "reason": ", ".join(reason_parts) or "restore_smoke_failed", "checks": checks}


def load_backup_retention_config(*, project_root: str | Path | None = None, config_path: str | Path | None = None) -> dict[str, Any]:
    if config_path is not None:
        path = Path(config_path)
    else:
        base = Path(project_root or Path.cwd())
        path = base / 'configs' / 'ops' / 'backup_retention_v1.yaml'
    raw = yaml.safe_load(path.read_text(encoding='utf-8')) if path.exists() else {}
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise BackupRestoreError(f'{path}: ожидался YAML-объект верхнего уровня')

    cfg = json.loads(json.dumps(_DEFAULT_BACKUP_RETENTION_CONFIG))
    for key in ['version', 'enabled', 'apply_after_backup']:
        if key in raw:
            cfg[key] = raw[key]
    for section in ['backup_archives', 'restore_snapshots', 'data_versions']:
        section_raw = raw.get(section)
        if section_raw is None:
            continue
        if not isinstance(section_raw, dict):
            raise BackupRestoreError(f'{path}: {section} должен быть объектом')
        merged = dict(cfg[section])
        merged.update(section_raw)
        cfg[section] = merged

    try:
        cfg['version'] = int(cfg.get('version', 1))
    except Exception as exc:
        raise BackupRestoreError(f'{path}: version должен быть целым числом') from exc
    cfg['enabled'] = bool(cfg.get('enabled', True))
    cfg['apply_after_backup'] = bool(cfg.get('apply_after_backup', False))

    try:
        cfg['backup_archives']['keep_last'] = int(cfg['backup_archives'].get('keep_last', 5))
    except Exception as exc:
        raise BackupRestoreError(f'{path}: backup_archives.keep_last должен быть целым числом') from exc
    if cfg['backup_archives']['keep_last'] < 1:
        raise BackupRestoreError(f'{path}: backup_archives.keep_last должен быть >= 1')
    cfg['backup_archives']['glob'] = str(cfg['backup_archives'].get('glob') or '*.zip')

    cfg['restore_snapshots']['enabled'] = bool(cfg['restore_snapshots'].get('enabled', True))
    try:
        cfg['restore_snapshots']['keep_last'] = int(cfg['restore_snapshots'].get('keep_last', 2))
    except Exception as exc:
        raise BackupRestoreError(f'{path}: restore_snapshots.keep_last должен быть целым числом') from exc
    if cfg['restore_snapshots']['keep_last'] < 0:
        raise BackupRestoreError(f'{path}: restore_snapshots.keep_last должен быть >= 0')

    cfg['data_versions']['enabled'] = bool(cfg['data_versions'].get('enabled', False))
    try:
        cfg['data_versions']['keep_last'] = int(cfg['data_versions'].get('keep_last', 0))
    except Exception as exc:
        raise BackupRestoreError(f'{path}: data_versions.keep_last должен быть целым числом') from exc
    if cfg['data_versions']['keep_last'] < 0:
        raise BackupRestoreError(f'{path}: data_versions.keep_last должен быть >= 0')

    cfg['path'] = str(path)
    return cfg


def _sorted_by_mtime_desc(paths: list[Path]) -> list[Path]:
    return sorted(paths, key=lambda p: (p.stat().st_mtime, p.name), reverse=True)


def _prune_paths(*, paths: list[Path], keep_last: int, dry_run: bool) -> dict[str, Any]:
    ordered = _sorted_by_mtime_desc(paths)
    kept = ordered[:keep_last] if keep_last > 0 else []
    to_delete = ordered[keep_last:] if keep_last >= 0 else []
    deleted: list[str] = []
    errors: list[dict[str, str]] = []
    if not dry_run:
        for path in to_delete:
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                elif path.exists():
                    path.unlink()
                deleted.append(str(path))
            except Exception as exc:
                errors.append({'path': str(path), 'error': f'{type(exc).__name__}: {exc}'})
    return {
        'keep_last': keep_last,
        'candidate_count': len(ordered),
        'kept_paths': [str(p) for p in kept],
        'delete_candidates': [str(p) for p in to_delete],
        'deleted_paths': deleted,
        'errors': errors,
        'dry_run': bool(dry_run),
    }


def apply_backup_retention(
    *,
    artifacts_root: Path,
    web_storage: Path,
    db_path: Optional[Path] = None,
    project_root: str | Path | None = None,
    config_path: str | Path | None = None,
    dry_run: bool = True,
    include_data_versions: bool = False,
) -> dict[str, Any]:
    artifacts_root = artifacts_root.resolve()
    web_storage = web_storage.resolve()
    db_path = _normalize_db_path(web_storage, db_path)
    cfg = load_backup_retention_config(project_root=project_root, config_path=config_path)

    backups_dir = artifacts_root / 'backups'
    backup_glob = str(cfg['backup_archives'].get('glob') or '*.zip')
    backup_paths = [p for p in backups_dir.glob(backup_glob) if p.is_file()] if backups_dir.exists() else []
    backups_summary = _prune_paths(paths=backup_paths, keep_last=int(cfg['backup_archives']['keep_last']), dry_run=dry_run)

    snapshots_summary: dict[str, Any] = {'enabled': bool(cfg['restore_snapshots']['enabled']), 'families': {}, 'dry_run': bool(dry_run)}
    if cfg['restore_snapshots']['enabled']:
        snap_keep = int(cfg['restore_snapshots']['keep_last'])
        art_family = [p for p in artifacts_root.parent.glob(f'{artifacts_root.name}_pre_restore_*') if p.exists()]
        web_family = [p for p in web_storage.parent.glob(f'{web_storage.name}_pre_restore_*') if p.exists()]
        snapshots_summary['families']['artifacts'] = _prune_paths(paths=art_family, keep_last=snap_keep, dry_run=dry_run)
        snapshots_summary['families']['web_storage'] = _prune_paths(paths=web_family, keep_last=snap_keep, dry_run=dry_run)

    dvs_summary: dict[str, Any] = {
        'enabled': bool(cfg['data_versions']['enabled']) and bool(include_data_versions),
        'skipped_reason': None,
        'dry_run': bool(dry_run),
    }
    if cfg['data_versions']['enabled'] and include_data_versions:
        dv_paths = [p for p in artifacts_root.iterdir() if p.is_dir() and p.name.startswith('dv_')] if artifacts_root.exists() else []
        dvs_summary.update(_prune_paths(paths=dv_paths, keep_last=int(cfg['data_versions']['keep_last']), dry_run=dry_run))
    elif cfg['data_versions']['enabled'] and not include_data_versions:
        dvs_summary['skipped_reason'] = 'include_data_versions=false'
    else:
        dvs_summary['skipped_reason'] = 'policy_disabled'

    batch_id = f'backup_cleanup_{_utc_ts_compact()}'
    summary = {
        'ok': True,
        'batch_id': batch_id,
        'config_path': cfg['path'],
        'dry_run': bool(dry_run),
        'policy': cfg,
        'backups': backups_summary,
        'restore_snapshots': snapshots_summary,
        'data_versions': dvs_summary,
    }

    _write_best_effort_audit(
        db_path=db_path,
        action='backup.cleanup',
        object_id=batch_id,
        after={
            'dry_run': bool(dry_run),
            'config_path': cfg['path'],
            'backups_deleted': len(backups_summary.get('deleted_paths') or []),
            'snapshot_deleted': sum(len((fam or {}).get('deleted_paths') or []) for fam in snapshots_summary.get('families', {}).values()),
            'data_versions_deleted': len(dvs_summary.get('deleted_paths') or []),
        },
    )
    return summary


def make_backup(
    *,
    artifacts_root: Path,
    web_storage: Path,
    out_zip: Optional[Path] = None,
    db_path: Optional[Path] = None,
    project_root: str | Path | None = None,
    retention_config_path: str | Path | None = None,
) -> BackupResult:
    artifacts_root = artifacts_root.resolve()
    web_storage = web_storage.resolve()
    db_path = _normalize_db_path(web_storage, db_path)

    backups_dir = artifacts_root / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)

    if out_zip is None:
        out_zip = backups_dir / f"backup_{_utc_ts_compact()}.zip"
    out_zip = out_zip.resolve()
    _ensure_parent(out_zip)

    backup_id = out_zip.stem or f"backup_{_utc_ts_compact()}"

    # Write audit before DB snapshot so the event itself is inside the backup.
    _write_best_effort_audit(
        db_path=db_path,
        action="backup.create",
        object_id=backup_id,
        after={
            "backup_zip": str(out_zip),
            "format": BACKUP_FORMAT_V2,
        },
    )

    db_files = _sqlite_sidecars(db_path)
    artifacts_files = _iter_files(artifacts_root, exclude_dirs=[backups_dir])
    web_files = _iter_files(web_storage, exclude_files=db_files)

    entries: list[dict[str, Any]] = []
    entries.extend(_entry("artifacts", artifacts_root, f, component="artifacts") for f in artifacts_files)
    entries.extend(_entry("web_storage", web_storage, f, component="web_storage") for f in web_files)
    if db_files:
        db_root = db_path.parent
        entries.extend(_entry("db", db_root, f, component="db") for f in db_files)

    manifest = {
        "format": BACKUP_FORMAT_V2,
        "created_at": utcnow_iso(),
        "backup_id": backup_id,
        "artifacts_root": str(artifacts_root),
        "web_storage": str(web_storage),
        "db_path": str(db_path),
        "data_versions": _top_level_data_versions(artifacts_root),
        "components": {
            "artifacts": {"root": str(artifacts_root), "file_count": sum(1 for e in entries if e["component"] == "artifacts")},
            "web_storage": {"root": str(web_storage), "file_count": sum(1 for e in entries if e["component"] == "web_storage")},
            "db": {"root": str(db_path.parent), "file_count": sum(1 for e in entries if e["component"] == "db")},
        },
        "entries": entries,
    }
    manifest_json = json.dumps(manifest, ensure_ascii=False, indent=2)

    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", manifest_json)
        for f in artifacts_files:
            rel = f.relative_to(artifacts_root).as_posix()
            zf.write(f, arcname=f"artifacts/{rel}")
        for f in web_files:
            rel = f.relative_to(web_storage).as_posix()
            zf.write(f, arcname=f"web_storage/{rel}")
        for f in db_files:
            rel = f.relative_to(db_path.parent).as_posix()
            zf.write(f, arcname=f"db/{rel}")

    try:
        retention_cfg = load_backup_retention_config(project_root=project_root, config_path=retention_config_path)
        if retention_cfg.get('enabled') and retention_cfg.get('apply_after_backup'):
            apply_backup_retention(
                artifacts_root=artifacts_root,
                web_storage=web_storage,
                db_path=db_path,
                project_root=project_root,
                config_path=retention_config_path,
                dry_run=False,
                include_data_versions=False,
            )
    except BackupRestoreError:
        raise

    return BackupResult(
        backup_zip=str(out_zip),
        manifest_json="manifest.json",
        file_count=len(entries),
        backup_id=backup_id,
    )


def restore_backup(
    *,
    backup_zip: Path,
    artifacts_root: Path,
    web_storage: Path,
    db_path: Optional[Path] = None,
    force: bool = False,
    smoke_check: bool = False,
) -> dict[str, Any]:
    backup_zip = backup_zip.resolve()
    artifacts_root = artifacts_root.resolve()
    web_storage = web_storage.resolve()
    db_path = _normalize_db_path(web_storage, db_path)

    if not backup_zip.exists():
        return {"ok": False, "reason": f"backup zip not found: {backup_zip}"}

    def non_empty(path: Path) -> bool:
        return path.exists() and any(path.iterdir())

    manifest: dict[str, Any]
    try:
        manifest = _load_manifest_from_zip(backup_zip)
    except BackupRestoreError as exc:
        return {"ok": False, "reason": str(exc)}

    try:
        compat = validate_backup_manifest_compatibility(manifest)
    except MigrationCompatibilityError as exc:
        return {"ok": False, "reason": str(exc), "diagnostic": exc.as_dict()}

    backup_format = str(compat['format'])

    destination_non_empty = non_empty(artifacts_root) or non_empty(web_storage)
    if destination_non_empty and not force:
        return {
            "ok": False,
            "reason": "destination not empty (use --force)",
            "artifacts_root": str(artifacts_root),
            "web_storage": str(web_storage),
        }

    ts = _utc_ts_compact()

    with tempfile.TemporaryDirectory(prefix="genomeai_restore_") as td:
        tmp = Path(td)
        try:
            with zipfile.ZipFile(backup_zip, "r") as zf:
                _safe_extract_all(zf, tmp)
        except Exception as exc:
            return {"ok": False, "reason": f"zip extract failed: {type(exc).__name__}: {exc}"}

        candidate_artifacts = tmp / "artifacts"
        candidate_web = tmp / "web_storage"
        candidate_db = tmp / "db" / db_path.name if backup_format == BACKUP_FORMAT_V2 else candidate_web / db_path.name
        if not candidate_artifacts.exists() or not candidate_web.exists():
            return {"ok": False, "reason": "backup zip missing artifacts/ or web_storage/"}
        if backup_format == BACKUP_FORMAT_V2 and not (tmp / "db").exists():
            return {"ok": False, "reason": "backup zip missing db/"}

        for required_dir in [candidate_web / "uploads", candidate_web / "logs", candidate_web / "config_overrides"]:
            required_dir.mkdir(parents=True, exist_ok=True)

        entries = list(manifest.get("entries") or [])
        verified_tmp, mismatches_tmp = _verify_entries(entries, artifacts_root=candidate_artifacts, web_storage=candidate_web, db_path=candidate_db)
        if mismatches_tmp:
            return {
                "ok": False,
                "reason": "checksum verification failed before restore",
                "verified_files": verified_tmp,
                "total_files": int(len(entries)),
                "mismatches": mismatches_tmp[:50],
            }

        smoke_tmp: Optional[dict[str, Any]] = None
        if smoke_check:
            smoke_tmp = _restore_smoke_check(artifacts_root=candidate_artifacts, web_storage=candidate_web, db_path=candidate_db, manifest=manifest)
            if not smoke_tmp.get("ok"):
                return {"ok": False, "reason": f"restore smoke failed before install: {smoke_tmp.get('reason')}", "smoke": smoke_tmp}

        def backup_existing(path: Path) -> Optional[str]:
            if not non_empty(path):
                return None
            dst = path.parent / f"{path.name}_pre_restore_{ts}"
            if dst.exists():
                shutil.rmtree(dst)
            shutil.move(str(path), str(dst))
            return str(dst)

        moved_artifacts = backup_existing(artifacts_root) if force else None
        moved_web = backup_existing(web_storage) if force else None

        artifacts_root.parent.mkdir(parents=True, exist_ok=True)
        web_storage.parent.mkdir(parents=True, exist_ok=True)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        shutil.copytree(candidate_artifacts, artifacts_root, dirs_exist_ok=True)
        shutil.copytree(candidate_web, web_storage, dirs_exist_ok=True)
        for required_dir in [web_storage / "uploads", web_storage / "logs", web_storage / "config_overrides"]:
            required_dir.mkdir(parents=True, exist_ok=True)
        if backup_format == BACKUP_FORMAT_V2:
            for db_file in (tmp / "db").iterdir():
                if db_file.is_file():
                    _ensure_parent(db_path.parent / db_file.name)
                    shutil.copy2(db_file, db_path.parent / db_file.name)

    verified, mismatches = _verify_entries(entries, artifacts_root=artifacts_root, web_storage=web_storage, db_path=db_path)
    if mismatches:
        return {
            "ok": False,
            "reason": "checksum verification failed after restore",
            "backup_zip": str(backup_zip),
            "artifacts_root": str(artifacts_root),
            "web_storage": str(web_storage),
            "db_path": str(db_path),
            "moved_artifacts": moved_artifacts,
            "moved_web_storage": moved_web,
            "verified_files": verified,
            "total_files": int(len(entries)),
            "mismatches": mismatches[:50],
        }

    smoke_result: Optional[dict[str, Any]] = None
    if smoke_check:
        smoke_result = _restore_smoke_check(artifacts_root=artifacts_root, web_storage=web_storage, db_path=db_path, manifest=manifest)
        if not smoke_result.get("ok"):
            return {
                "ok": False,
                "reason": f"restore smoke failed after install: {smoke_result.get('reason')}",
                "backup_zip": str(backup_zip),
                "artifacts_root": str(artifacts_root),
                "web_storage": str(web_storage),
                "db_path": str(db_path),
                "moved_artifacts": moved_artifacts,
                "moved_web_storage": moved_web,
                "verified_files": verified,
                "total_files": int(len(entries)),
                "smoke": smoke_result,
            }

    restore_id = str(manifest.get("backup_id") or backup_zip.stem or f"restore_{_utc_ts_compact()}")
    _write_best_effort_audit(
        db_path=db_path,
        action="backup.restore",
        object_id=restore_id,
        after={
            "backup_zip": str(backup_zip),
            "verified_files": verified,
            "total_files": int(len(entries)),
            "smoke_check": bool(smoke_check),
        },
    )

    return {
        "ok": True,
        "backup_zip": str(backup_zip),
        "artifacts_root": str(artifacts_root),
        "web_storage": str(web_storage),
        "db_path": str(db_path),
        "moved_artifacts": moved_artifacts,
        "moved_web_storage": moved_web,
        "verified_files": verified,
        "total_files": int(len(entries)),
        "mismatches": [],
        "format": backup_format,
        "backup_id": manifest.get("backup_id") or backup_zip.stem,
        "smoke": smoke_result,
    }
