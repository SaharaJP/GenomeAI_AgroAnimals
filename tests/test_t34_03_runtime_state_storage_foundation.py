from __future__ import annotations

from pathlib import Path

import pytest

from core.infra.runtime_state_storage import RUNTIME_STATE_ENTITIES, runtime_state_storage_diagnostics
from core.infra.web_db import connect, init_db


def test_t34_03_doc_scripts_and_migration_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / 'docs' / 'postgres_runtime_state_cutover.md').exists()
    assert (root / 'scripts' / 'runtime_state_backfill_postgres.py').exists()
    assert (root / 'scripts' / 'runtime_state_verify_postgres_cutover.py').exists()
    assert (root / 'deploy' / 'adult' / 'ops' / 'diagnostic_sql' / 'runtime_state_checks.sql').exists()
    assert (root / 'src' / 'core' / 'migrations' / 'alembic' / 'versions' / '20260414_03_runtime_state_postgres_baseline.py').exists()


def test_t34_03_sqlite_compat_runtime_state_diagnostics(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv('GENOMEAI_PROJECT_ROOT', str(repo_root))
    monkeypatch.setenv('GENOMEAI_WEB_STORAGE', str(tmp_path / 'web_storage'))
    monkeypatch.setenv('GENOMEAI_ARTIFACTS_ROOT', str(tmp_path / 'artifacts'))
    monkeypatch.setenv('GENOMEAI_DEPLOY_PROFILE', 'test')
    monkeypatch.setenv('GENOMEAI_WEB_SECRET', 'test-secret-long-enough')
    monkeypatch.delenv('GENOMEAI_RUNTIME_STORAGE_BACKEND', raising=False)

    db_path = tmp_path / 'web_storage' / 'web.db'
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        init_db(conn)
    finally:
        conn.close()

    diag = runtime_state_storage_diagnostics().as_dict()
    assert diag['backend'] == 'sqlite'
    assert diag['primary_runtime_state_backend'] == 'sqlite'
    assert diag['support_bundle_legacy_web_db_default'] is True
    entity_names = {row['entity'] for row in diag['entities']}
    assert set(RUNTIME_STATE_ENTITIES).issubset(entity_names)
    assert all(row['legacy_sqlite_primary'] is True for row in diag['entities'])
