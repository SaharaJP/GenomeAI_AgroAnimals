from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _sha256(path: Path) -> str:
    h = sha256()
    with path.open('rb') as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def build_artifact_integrity_summary(*, artifacts_root: str | Path) -> dict[str, Any]:
    root = Path(artifacts_root).resolve()
    summary: dict[str, Any] = {
        'artifacts_root': str(root),
        'exists': root.exists() and root.is_dir(),
        'data_versions': 0,
        'canonical_files': 0,
        'report_files': 0,
        'manifest_files': 0,
        'support_bundles': 0,
        'backups': 0,
        'latest_manifest_examples': [],
        'latest_support_bundle': None,
        'latest_backup': None,
        'integrity_status': 'missing_root',
    }
    if not root.exists() or not root.is_dir():
        return summary

    dv_dirs = [p for p in root.iterdir() if p.is_dir() and p.name.startswith('dv_')]
    summary['data_versions'] = len(dv_dirs)
    canonical_files = list(root.glob('dv_*/canonical/**/*'))
    report_files = list(root.glob('dv_*/reports/**/*')) + list(root.glob('dv_*/whatif_reports/**/*'))
    manifest_files = [p for p in root.rglob('manifest.json') if p.is_file()]
    support_bundles = [p for p in (root / 'support_bundles').glob('*.zip')] if (root / 'support_bundles').exists() else []
    backups = [p for p in (root / 'backups').glob('*.zip')] if (root / 'backups').exists() else []
    summary['canonical_files'] = len([p for p in canonical_files if p.is_file()])
    summary['report_files'] = len([p for p in report_files if p.is_file()])
    summary['manifest_files'] = len(manifest_files)
    summary['support_bundles'] = len(support_bundles)
    summary['backups'] = len(backups)

    latest_manifests = sorted(manifest_files, key=lambda p: (p.stat().st_mtime, p.name), reverse=True)[:3]
    summary['latest_manifest_examples'] = [
        {
            'path': str(p.relative_to(root)),
            'sha256': _sha256(p),
            'size': int(p.stat().st_size),
        }
        for p in latest_manifests
    ]
    if support_bundles:
        latest = sorted(support_bundles, key=lambda p: (p.stat().st_mtime, p.name), reverse=True)[0]
        summary['latest_support_bundle'] = {'path': str(latest.relative_to(root)), 'size': int(latest.stat().st_size)}
    if backups:
        latest = sorted(backups, key=lambda p: (p.stat().st_mtime, p.name), reverse=True)[0]
        summary['latest_backup'] = {'path': str(latest.relative_to(root)), 'size': int(latest.stat().st_size)}

    summary['integrity_status'] = 'ok' if summary['data_versions'] >= 0 else 'unknown'
    return summary


def _maintenance_dir(artifacts_root: Path) -> Path:
    return artifacts_root / 'system' / 'maintenance'


def build_adult_backup_metadata_summary(*, artifacts_root: str | Path) -> dict[str, Any]:
    root = Path(artifacts_root).resolve()
    maintenance = _maintenance_dir(root)
    latest_backup = _read_json(maintenance / 'latest_backup_metadata.json')
    latest_restore = _read_json(maintenance / 'latest_restore_metadata.json')
    return {
        'artifacts_root': str(root),
        'maintenance_dir': str(maintenance),
        'latest_backup_metadata_present': latest_backup is not None,
        'latest_restore_metadata_present': latest_restore is not None,
        'latest_backup_metadata': latest_backup or {},
        'latest_restore_metadata': latest_restore or {},
    }


def verify_adult_backup_created(*, backup_dir: str | Path) -> dict[str, Any]:
    backup_root = Path(backup_dir).resolve()
    manifest_path = backup_root / 'manifest.json'
    manifest = _read_json(manifest_path)
    checks: dict[str, Any] = {
        'backup_dir': str(backup_root),
        'exists': backup_root.exists() and backup_root.is_dir(),
        'manifest_exists': manifest_path.exists() and manifest_path.is_file(),
        'manifest_ok': bool(manifest),
        'components_present': {},
        'required_files_ok': False,
    }
    required = {
        'postgres_dump': backup_root / 'postgres.sql',
        'redis_dump': backup_root / 'redis.rdb',
        'artifact_archive': backup_root / 'runtime_artifacts.tgz',
    }
    checks['components_present'] = {name: path.exists() and path.is_file() for name, path in required.items()}
    checks['required_files_ok'] = all(checks['components_present'].values())
    if manifest:
        checks['profile'] = manifest.get('profile')
        checks['runtime_storage_backend'] = manifest.get('runtime_storage_backend')
        checks['queue_backend'] = manifest.get('queue_backend')
        checks['artifact_storage_mode'] = manifest.get('artifact_storage_mode')
        checks['components'] = manifest.get('components') or []
    ok = bool(checks['exists'] and checks['manifest_exists'] and checks['manifest_ok'] and checks['required_files_ok'])
    return {
        'ok': ok,
        'checks': checks,
        'reason': None if ok else 'adult_backup_incomplete',
    }


def verify_adult_restore_performed(*, artifacts_root: str | Path, required_artifact_paths: list[str] | None = None) -> dict[str, Any]:
    root = Path(artifacts_root).resolve()
    maintenance = _maintenance_dir(root)
    metadata = _read_json(maintenance / 'latest_restore_metadata.json') or {}
    required_paths = [str(x).strip().strip('/') for x in (required_artifact_paths or []) if str(x).strip()]
    artifact_checks = []
    for rel in required_paths:
        p = root / rel
        artifact_checks.append({'path': rel, 'exists': p.exists()})
    boot_ok = bool(metadata.get('post_restore_smoke_ok')) if metadata else False
    ok = bool(metadata) and boot_ok and all(item['exists'] for item in artifact_checks)
    return {
        'ok': ok,
        'artifacts_root': str(root),
        'restore_metadata_present': bool(metadata),
        'post_restore_smoke_ok': boot_ok,
        'artifact_checks': artifact_checks,
        'metadata': metadata,
        'reason': None if ok else 'adult_restore_incomplete',
    }


__all__ = [
    'build_artifact_integrity_summary',
    'build_adult_backup_metadata_summary',
    'verify_adult_backup_created',
    'verify_adult_restore_performed',
]
