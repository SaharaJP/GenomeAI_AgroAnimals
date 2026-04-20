from __future__ import annotations

import os
from pathlib import Path

from genomeai.backup_restore import apply_backup_retention, make_backup
from web_cabinet.db import connect, init_db


def _prepare_source_tree(tmp_path: Path) -> tuple[Path, Path, Path]:
    artifacts = tmp_path / 'src' / 'artifacts'
    web_storage = tmp_path / 'src' / 'web_storage'
    db_path = web_storage / 'web.db'

    (artifacts / 'dv_demo_001' / 'canonical').mkdir(parents=True, exist_ok=True)
    (artifacts / 'dv_demo_001' / 'canonical' / 'animals.csv').write_text('animal_id\nA001\n', encoding='utf-8')
    (web_storage / 'uploads').mkdir(parents=True, exist_ok=True)
    (web_storage / 'logs').mkdir(parents=True, exist_ok=True)
    (web_storage / 'config_overrides').mkdir(parents=True, exist_ok=True)
    (web_storage / 'uploads' / 'sample.txt').write_text('upload', encoding='utf-8')

    conn = connect(db_path)
    try:
        init_db(conn)
        conn.commit()
    finally:
        conn.close()

    return artifacts, web_storage, db_path


def _write_policy(tmp_path: Path, body: str) -> Path:
    cfg = tmp_path / 'configs' / 'ops' / 'backup_retention_v1.yaml'
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(body, encoding='utf-8')
    return cfg


def _touch_with_mtime(path: Path, ts: int) -> None:
    if path.suffix:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(path.name, encoding='utf-8')
    else:
        path.mkdir(parents=True, exist_ok=True)
        (path / 'marker.txt').write_text(path.name, encoding='utf-8')
    os.utime(path, (ts, ts))


def test_t13_06_step2_cleanup_dry_run_and_apply_for_backups_and_restore_snapshots(tmp_path: Path):
    artifacts, web_storage, db_path = _prepare_source_tree(tmp_path)
    _write_policy(
        tmp_path,
        '''
version: 1
enabled: true
apply_after_backup: false
backup_archives:
  keep_last: 2
restore_snapshots:
  enabled: true
  keep_last: 1
data_versions:
  enabled: false
  keep_last: 0
''',
    )

    backups_dir = artifacts / 'backups'
    backups_dir.mkdir(parents=True, exist_ok=True)
    for idx, ts in enumerate([100, 200, 300], start=1):
        _touch_with_mtime(backups_dir / f'backup_{idx}.zip', ts)

    for idx, ts in enumerate([100, 200, 300], start=1):
        _touch_with_mtime(artifacts.parent / f'{artifacts.name}_pre_restore_{idx}', ts)
        _touch_with_mtime(web_storage.parent / f'{web_storage.name}_pre_restore_{idx}', ts)

    dry_run = apply_backup_retention(
        artifacts_root=artifacts,
        web_storage=web_storage,
        db_path=db_path,
        project_root=tmp_path,
        dry_run=True,
        include_data_versions=False,
    )
    assert len(dry_run['backups']['delete_candidates']) == 1
    assert len(dry_run['restore_snapshots']['families']['artifacts']['delete_candidates']) == 2
    assert len(dry_run['restore_snapshots']['families']['web_storage']['delete_candidates']) == 2
    assert (backups_dir / 'backup_1.zip').exists()
    assert (artifacts.parent / f'{artifacts.name}_pre_restore_1').exists()

    apply = apply_backup_retention(
        artifacts_root=artifacts,
        web_storage=web_storage,
        db_path=db_path,
        project_root=tmp_path,
        dry_run=False,
        include_data_versions=False,
    )
    assert len(apply['backups']['deleted_paths']) == 1
    assert not (backups_dir / 'backup_1.zip').exists()
    assert len(list(backups_dir.glob('*.zip'))) == 2
    assert len(list(artifacts.parent.glob(f'{artifacts.name}_pre_restore_*'))) == 1
    assert len(list(web_storage.parent.glob(f'{web_storage.name}_pre_restore_*'))) == 1

    conn = connect(db_path)
    try:
        rows = conn.execute("SELECT action FROM audit_log WHERE action='backup.cleanup' ORDER BY id DESC LIMIT 5").fetchall()
    finally:
        conn.close()
    assert rows, 'backup.cleanup must be written to audit log'


def test_t13_06_step2_make_backup_can_auto_apply_retention_and_cleanup_data_versions(tmp_path: Path):
    artifacts, web_storage, db_path = _prepare_source_tree(tmp_path)
    _write_policy(
        tmp_path,
        '''
version: 1
enabled: true
apply_after_backup: true
backup_archives:
  keep_last: 2
restore_snapshots:
  enabled: true
  keep_last: 2
data_versions:
  enabled: true
  keep_last: 1
''',
    )

    backups_dir = artifacts / 'backups'
    backups_dir.mkdir(parents=True, exist_ok=True)
    for idx, ts in enumerate([100, 200], start=1):
        _touch_with_mtime(backups_dir / f'old_{idx}.zip', ts)

    (artifacts / 'dv_demo_002' / 'canonical').mkdir(parents=True, exist_ok=True)
    (artifacts / 'dv_demo_002' / 'canonical' / 'animals.csv').write_text('animal_id\nA002\n', encoding='utf-8')
    os.utime(artifacts / 'dv_demo_001', (100, 100))
    os.utime(artifacts / 'dv_demo_002', (200, 200))

    out_zip = backups_dir / 'backup_new.zip'
    make_backup(
        artifacts_root=artifacts,
        web_storage=web_storage,
        db_path=db_path,
        out_zip=out_zip,
        project_root=tmp_path,
    )

    remaining_backups = sorted(p.name for p in backups_dir.glob('*.zip'))
    assert 'backup_new.zip' in remaining_backups
    assert len(remaining_backups) == 2, remaining_backups

    cleanup = apply_backup_retention(
        artifacts_root=artifacts,
        web_storage=web_storage,
        db_path=db_path,
        project_root=tmp_path,
        dry_run=False,
        include_data_versions=True,
    )
    assert cleanup['data_versions']['enabled'] is True
    assert len(cleanup['data_versions']['deleted_paths']) == 1
    remaining_dvs = sorted(p.name for p in artifacts.iterdir() if p.is_dir() and p.name.startswith('dv_'))
    assert remaining_dvs == ['dv_demo_002']
