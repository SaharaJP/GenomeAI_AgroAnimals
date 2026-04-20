from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

from core.artifacts import build_support_bundle
from tests.test_t17_04_artifact_lifecycle import _prepare_runtime_tree


def test_t34_03_support_bundle_includes_runtime_state_summary_and_skips_web_db_summary_for_postgres(tmp_path: Path) -> None:
    project_root, artifacts_root, web_storage = _prepare_runtime_tree(tmp_path)
    os.environ['GENOMEAI_PROJECT_ROOT'] = str(project_root)
    os.environ['GENOMEAI_WEB_STORAGE'] = str(web_storage)
    os.environ['GENOMEAI_ARTIFACTS_ROOT'] = str(artifacts_root)
    os.environ['GENOMEAI_DEPLOY_PROFILE'] = 'prod'
    os.environ['GENOMEAI_RUNTIME_STORAGE_BACKEND'] = 'postgres'
    os.environ['GENOMEAI_RUNTIME_POSTGRES_DSN'] = 'postgresql://genomeai:secret@postgres:5432/genomeai'

    out = artifacts_root / 'support_bundles' / 'bundle_postgres.zip'
    result = build_support_bundle(
        output_zip=out,
        project_root=project_root,
        artifacts_root=artifacts_root,
        web_storage=web_storage,
        db_path=None,
    )
    assert result['ok'] is True
    with zipfile.ZipFile(out, 'r') as zf:
        names = set(zf.namelist())
        summary = json.loads(zf.read('diagnostics/runtime_state_summary.json').decode('utf-8'))
        manifest = json.loads(zf.read('manifest.json').decode('utf-8'))
    assert 'diagnostics/runtime_state_summary.json' in names
    assert 'diagnostics/web_db_summary.json' not in names
    assert summary['backend'] == 'postgres'
    assert manifest['runtime_storage_backend'] == 'postgres'
