from __future__ import annotations

import json
import zipfile
from pathlib import Path

from core.artifacts import build_support_bundle


def test_t34_05_support_bundle_includes_adult_runtime_and_backup_diagnostics(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / 'project'
    artifacts_root = project_root / 'artifacts'
    web_storage = project_root / 'web_storage'
    maintenance = artifacts_root / 'system' / 'maintenance'
    (artifacts_root / 'dv_demo_001' / 'canonical').mkdir(parents=True, exist_ok=True)
    (artifacts_root / 'dv_demo_001' / 'canonical' / 'animals.csv').write_text('animal_id\nA001\n', encoding='utf-8')
    (artifacts_root / 'dv_demo_001' / 'reports').mkdir(parents=True, exist_ok=True)
    (artifacts_root / 'dv_demo_001' / 'reports' / 'manifest.json').write_text('{"run_id":"run_001"}', encoding='utf-8')
    (artifacts_root / 'support_bundles').mkdir(parents=True, exist_ok=True)
    (web_storage / 'logs').mkdir(parents=True, exist_ok=True)
    (web_storage / 'uploads').mkdir(parents=True, exist_ok=True)
    (web_storage / 'config_overrides').mkdir(parents=True, exist_ok=True)
    maintenance.mkdir(parents=True, exist_ok=True)
    (maintenance / 'latest_backup_metadata.json').write_text(json.dumps({'profile': 'prod', 'runtime_storage_backend': 'postgres'}), encoding='utf-8')
    (maintenance / 'latest_restore_metadata.json').write_text(json.dumps({'profile': 'prod', 'post_restore_smoke_ok': True}), encoding='utf-8')

    monkeypatch.setenv('GENOMEAI_PROJECT_ROOT', str(project_root))
    monkeypatch.setenv('GENOMEAI_ARTIFACTS_ROOT', str(artifacts_root))
    monkeypatch.setenv('GENOMEAI_WEB_STORAGE', str(web_storage))
    monkeypatch.setenv('GENOMEAI_DEPLOY_PROFILE', 'prod')
    monkeypatch.setenv('GENOMEAI_RUNTIME_STORAGE_BACKEND', 'postgres')
    monkeypatch.setenv('GENOMEAI_RUNTIME_POSTGRES_DSN', 'postgresql://genomeai:secret@postgres:5432/genomeai')
    monkeypatch.setenv('GENOMEAI_JOB_QUEUE_BACKEND', 'redis')
    monkeypatch.setenv('GENOMEAI_REDIS_DSN', 'redis://redis:6379/0')

    out = artifacts_root / 'support_bundles' / 'bundle_prod.zip'
    result = build_support_bundle(
        output_zip=out,
        project_root=project_root,
        artifacts_root=artifacts_root,
        web_storage=web_storage,
        tmp_root=project_root / '_tmp',
    )
    assert result['ok'] is True
    assert out.exists()

    with zipfile.ZipFile(out, 'r') as zf:
        names = set(zf.namelist())
        runtime = json.loads(zf.read('diagnostics/runtime_storage_summary.json').decode('utf-8'))
        auth = json.loads(zf.read('diagnostics/auth_diagnostics.json').decode('utf-8'))
        queue = json.loads(zf.read('diagnostics/queue_runtime_summary.json').decode('utf-8'))
        backup = json.loads(zf.read('diagnostics/backup_metadata.json').decode('utf-8'))
        integrity = json.loads(zf.read('diagnostics/artifact_integrity_summary.json').decode('utf-8'))

    assert 'diagnostics/runtime_storage_summary.json' in names
    assert 'diagnostics/runtime_state_summary.json' in names
    assert 'diagnostics/auth_diagnostics.json' in names
    assert 'diagnostics/queue_runtime_summary.json' in names
    assert 'diagnostics/backup_metadata.json' in names
    assert 'diagnostics/artifact_integrity_summary.json' in names
    assert 'maintenance/latest_backup_metadata.json' in names
    assert 'maintenance/latest_restore_metadata.json' in names
    assert 'diagnostics/web_db_summary.json' not in names

    assert runtime['backend'] == 'postgres'
    assert auth['backend'] == 'postgres'
    assert queue['backend'] == 'redis'
    assert backup['latest_backup_metadata_present'] is True
    assert backup['latest_restore_metadata_present'] is True
    assert integrity['data_versions'] == 1
