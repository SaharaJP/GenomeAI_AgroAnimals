from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

from core.interoperability import load_farm_connector_catalog
from genomeai.connectors_v1 import save_connector_state
from streamlit_app.auth_bridge import connect_web_db
from streamlit_app.platform_pages import list_connectors_view
from streamlit_app.farm_connector_catalog import load_connector_catalog_templates
from web_cabinet.auth import hash_password
from web_cabinet.connectors_v1 import finish_connector_run, start_connector_run

ROOT = Path(__file__).resolve().parents[1]


def _ctx(tmp_path: Path):
    return SimpleNamespace(web_storage_dir=tmp_path / 'web', artifacts_dir=tmp_path / 'artifacts')



def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()



def test_t26_04_load_farm_connector_catalog_blueprints() -> None:
    rows = load_farm_connector_catalog(ROOT / 'configs' / 'connector_catalog', project_root=ROOT)
    adapter_ids = {str(row.get('adapter_id') or '') for row in rows}
    assert {'dairycomp_305_batch', 'selex_batch', 'onec_livestock_batch'}.issubset(adapter_ids)
    dc = next(row for row in rows if str(row.get('adapter_id') or '') == 'dairycomp_305_batch')
    assert 'dm_lactations' in set(dc.get('data_contracts') or [])
    assert any(str(p).endswith('configs/connector_catalog/examples/dairycomp_305_batch.yaml') for p in [dc.get('representative_config_path')])
    assert len(dc.get('reusable_mapping_templates') or []) >= 3



def test_t26_04_platform_view_exposes_source_status_and_last_pull(tmp_path: Path, monkeypatch) -> None:
    ctx = _ctx(tmp_path)
    monkeypatch.setenv('GENOMEAI_WEB_STORAGE', str(ctx.web_storage_dir))
    connect_web_db(ctx, hash_password_fn=hash_password).close()

    external = ROOT / 'data' / 'examples' / 'external'
    selected = []
    state_datasets = {}
    for dataset_key, filename, mapping in [
        ('farms', 'farms_ext.csv', 'configs/mappings/farms_example.yaml'),
        ('animals', 'animals_ext.csv', 'configs/mappings/animals_example.yaml'),
        ('lactations', 'lactations_ext.csv', 'configs/mappings/lactations_example.yaml'),
    ]:
        file_path = external / filename
        stat = file_path.stat()
        modified_at = __import__('datetime').datetime.fromtimestamp(stat.st_mtime, tz=__import__('datetime').timezone.utc).replace(microsecond=0).isoformat()
        sha = _sha256_file(file_path)
        selected.append({
            'dataset_key': dataset_key,
            'file_path': str(file_path),
            'mapping_path': str((ROOT / mapping).resolve()),
            'sha256': sha,
            'modified_at': modified_at,
        })
        state_datasets[dataset_key] = {
            'file_path': str(file_path),
            'sha256': sha,
            'modified_at': modified_at,
        }

    save_connector_state(
        project_root=ROOT,
        connector_id='demo_file_pull',
        state={
            'connector_id': 'demo_file_pull',
            'datasets': state_datasets,
            'last_data_version': 'dv_demo_sync',
            'last_connector_run_id': 'connrun_demo_sync',
        },
    )

    conn = connect_web_db(ctx, hash_password_fn=hash_password)
    try:
        start_connector_run(
            conn,
            tenant_id='default',
            connector_run_id='connrun_demo_sync',
            connector_id='demo_file_pull',
            kind='file',
            trigger_type='manual',
            schedule_slot=None,
            config_path=str((ROOT / 'configs' / 'connectors' / 'file_demo.yaml').resolve()),
        )
        finish_connector_run(
            conn,
            tenant_id='default',
            connector_run_id='connrun_demo_sync',
            status='success',
            data_version='dv_demo_sync',
            message='ok',
            outputs={'connector_run_id': 'connrun_demo_sync'},
            selected_files=selected,
            ingest_summaries=[],
        )
    finally:
        conn.close()

    view = list_connectors_view(ctx, tenant_id='default')
    row = next(row for row in (view.get('catalog') or []) if str(row.get('connector_id') or '') == 'demo_file_pull')
    assert str(row.get('source_system') or '') == 'Generic farm file export'
    assert str(row.get('source_status') or '') in {'in_sync', 'stale_batch'}
    assert str(row.get('last_pull_status') or '') == 'success'
    assert str(row.get('last_pull_at') or '')
    assert row.get('sync_lag_minutes') is not None
    assert 'dm_animals' in set(row.get('supported_contracts') or [])
    assert str(row.get('action_hint') or '')



def test_t26_04_list_connectors_view_includes_catalog_templates_summary(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    connect_web_db(ctx, hash_password_fn=hash_password).close()
    view = list_connectors_view(ctx, tenant_id='default')
    templates = list(view.get('catalog_templates') or [])
    summary = dict(view.get('catalog_templates_summary') or {})
    assert len(templates) >= 3
    assert int(summary.get('total') or 0) >= 3
    assert int(summary.get('datasets_supported') or 0) >= 4
    payload = load_connector_catalog_templates()
    assert len(payload.get('rows') or []) >= 3
