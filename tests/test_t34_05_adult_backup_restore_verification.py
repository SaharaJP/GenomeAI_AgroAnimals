from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_t34_05_adult_backup_and_restore_verification_scripts(tmp_path: Path) -> None:
    project_root = tmp_path / 'project'
    backup_dir = project_root / 'runtime' / 'backups' / '20260414T000000Z'
    artifacts_root = project_root / 'runtime' / 'artifacts'
    maintenance = artifacts_root / 'system' / 'maintenance'
    required_artifact = artifacts_root / 'dv_demo_001' / 'canonical' / 'animals.csv'

    backup_dir.mkdir(parents=True, exist_ok=True)
    artifacts_root.mkdir(parents=True, exist_ok=True)
    maintenance.mkdir(parents=True, exist_ok=True)
    required_artifact.parent.mkdir(parents=True, exist_ok=True)
    required_artifact.write_text('animal_id\nA001\n', encoding='utf-8')

    (backup_dir / 'postgres.sql').write_text('-- pg_dump', encoding='utf-8')
    (backup_dir / 'redis.rdb').write_bytes(b'redis-rdb')
    (backup_dir / 'runtime_artifacts.tgz').write_bytes(b'tgz')
    (backup_dir / 'manifest.json').write_text(
        json.dumps(
            {
                'profile': 'prod',
                'runtime_storage_backend': 'postgres',
                'queue_backend': 'redis',
                'artifact_storage_mode': 'file_or_object_storage',
                'components': ['postgres_dump', 'redis_dump', 'artifact_archive'],
            },
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )
    (maintenance / 'latest_restore_metadata.json').write_text(
        json.dumps({'profile': 'prod', 'post_restore_smoke_ok': True}, ensure_ascii=False),
        encoding='utf-8',
    )

    repo_root = Path(__file__).resolve().parents[1]
    backup_proc = subprocess.run(
        [sys.executable, str(repo_root / 'scripts' / 'verify_adult_backup_set.py'), '--backup-dir', str(backup_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert backup_proc.returncode == 0, backup_proc.stdout + backup_proc.stderr
    assert 'ADULT_BACKUP_VERIFY_OK' in backup_proc.stdout

    restore_proc = subprocess.run(
        [
            sys.executable,
            str(repo_root / 'scripts' / 'verify_adult_restore_set.py'),
            '--artifacts-root',
            str(artifacts_root),
            '--require-artifact',
            'dv_demo_001/canonical/animals.csv',
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert restore_proc.returncode == 0, restore_proc.stdout + restore_proc.stderr
    assert 'ADULT_RESTORE_VERIFY_OK' in restore_proc.stdout
