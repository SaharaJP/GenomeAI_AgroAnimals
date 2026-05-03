from __future__ import annotations

import inspect
from pathlib import Path

from core.workflow import generate_alerts_and_tasks, generate_alerts_and_tasks_use_case


class _StubConn:
    pass


def test_t15_09_workflow_generation_use_case_centralizes_candidates_and_auto_tasking(tmp_path: Path) -> None:
    calls: dict[str, object] = {}

    def _generate_alert_candidates(*, artifacts_root: Path, data_version: str):
        calls['generator'] = {
            'artifacts_root': Path(artifacts_root),
            'data_version': data_version,
        }
        return [
            {
                'alert_type': 'QC.PK_DUPLICATE',
                'title': 'Duplicate animal_id',
                'source': 'qc2',
                'cause': 'pk_animals',
                'confidence': 1.0,
                'object_type': 'animal',
                'object_id': '1001',
                'why': {'severity': 'MAJOR'},
                'data_version': data_version,
                'qc_run': 'qc_demo',
                'dedupe_key': 'alert:1001:dup',
            }
        ]

    def _load_tasks_catalog(path: Path):
        calls['catalog_path'] = Path(path)
        return {'from_alerts': {'QC.PK_DUPLICATE': {'task_type': 'qc_followup'}}}

    def _upsert_generated_alerts(conn, *, tenant_id: str, alerts):
        alerts = list(alerts)
        calls['alerts'] = alerts
        calls['tenant_id'] = tenant_id
        return 1, 0

    def _auto_create_tasks_from_alerts(conn, *, tenant_id: str, catalog, data_version: str):
        calls['auto_tasking'] = {
            'tenant_id': tenant_id,
            'catalog': catalog,
            'data_version': data_version,
        }
        return {'eligible': 1, 'inserted': 1, 'skipped': 0, 'task_ids': ['t-1']}

    res = generate_alerts_and_tasks_use_case(
        conn=_StubConn(),
        tenant_id='default',
        data_version='dv_demo',
        artifacts_root=tmp_path / 'artifacts',
        catalog_path=tmp_path / 'configs' / 'tasks_v1' / 'catalog.yaml',
        generate_alert_candidates=_generate_alert_candidates,
        load_tasks_catalog=_load_tasks_catalog,
        upsert_generated_alerts=_upsert_generated_alerts,
        auto_create_tasks_from_alerts=_auto_create_tasks_from_alerts,
    )

    assert res == {
        'candidates': 1,
        'inserted': 1,
        'updated': 0,
        'auto_tasks': {'eligible': 1, 'inserted': 1, 'skipped': 0, 'task_ids': ['t-1']},
    }
    assert calls['tenant_id'] == 'default'
    assert calls['generator'] == {
        'artifacts_root': (tmp_path / 'artifacts').resolve(),
        'data_version': 'dv_demo',
    }
    assert calls['catalog_path'] == (tmp_path / 'configs' / 'tasks_v1' / 'catalog.yaml').resolve()
    alert = list(calls['alerts'])[0]
    assert alert.alert_type == 'QC.PK_DUPLICATE'
    assert alert.object_type == 'animal'
    assert alert.data_version == 'dv_demo'
    assert calls['auto_tasking'] == {
        'tenant_id': 'default',
        'catalog': {'from_alerts': {'QC.PK_DUPLICATE': {'task_type': 'qc_followup'}}},
        'data_version': 'dv_demo',
    }


def test_t15_09_first_party_workflow_adapters_import_core_entrypoints() -> None:
    import core.workflow.entrypoints as workflow_entrypoints
    import web_cabinet.app as appmod

    assert generate_alerts_and_tasks is workflow_entrypoints.generate_alerts_and_tasks
    app_src = inspect.getsource(appmod)
    assert 'from core.workflow import (' in app_src
    assert 'generate_alerts_and_tasks(' in app_src

    for rel in [
        'streamlit_app/pages/5_Alert_Center_v2.py',
        'streamlit_app/pages/6_Decision_Log_v2.py',
        'streamlit_app/pages/7_Worklist_v1.py',
        'streamlit_app/pages/8_Mating_Plan_v1.py',
        'streamlit_app/pages/1_Director_Summary.py',
    ]:
        src = Path(rel).read_text(encoding='utf-8')
        assert 'core.workflow' in src, rel
