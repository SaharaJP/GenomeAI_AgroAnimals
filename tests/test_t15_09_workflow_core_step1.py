from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path

from core.workflow import (
    AlertCreate,
    DecisionCreate,
    TaskCreate,
    append_decision,
    auto_create_tasks_from_alerts,
    create_alert,
    create_task,
    get_alert,
    get_task,
    load_tasks_catalog,
)
from web_cabinet.db import init_db


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def test_t15_09_web_workflow_modules_are_thin_core_shims() -> None:
    import core.workflow.alerts as core_alerts
    import core.workflow.decisions as core_decisions
    import core.workflow.entities as core_entities
    import core.workflow.tasks as core_tasks
    import web_cabinet.alerts_v2 as legacy_alerts
    import web_cabinet.decision_log_v2 as legacy_decisions
    import web_cabinet.entities as legacy_entities
    import web_cabinet.tasks_v1 as legacy_tasks

    assert legacy_tasks.create_task is core_tasks.create_task
    assert legacy_tasks.auto_create_tasks_from_alerts is core_tasks.auto_create_tasks_from_alerts
    assert legacy_alerts.create_alert is core_alerts.create_alert
    assert legacy_alerts.resolve_alert is core_alerts.resolve_alert
    assert legacy_decisions.append_decision is core_decisions.append_decision
    assert legacy_entities.normalize_object_type is core_entities.normalize_object_type

    assert 'core.workflow.tasks' in inspect.getsource(legacy_tasks)
    assert 'core.workflow.alerts' in inspect.getsource(legacy_alerts)
    assert 'core.workflow.decisions' in inspect.getsource(legacy_decisions)


def test_t15_09_core_workflow_preserves_sla_dedupe_and_linkage() -> None:
    conn = _conn()
    try:
        alert_id = create_alert(
            conn,
            tenant_id='default',
            a=AlertCreate(
                alert_type='QC.PK_DUPLICATE',
                title='Duplicate animal_id',
                source='qc2',
                cause='pk_animals',
                confidence=1.0,
                object_type='animal',
                object_id='1001',
                deadline=None,
                owner_user_id=None,
                attachments=[],
                why={'severity': 'MAJOR'},
                what_to_do=[{'step': 'inspect source'}],
                data_version='dv_demo',
                qc_run='qc2_demo',
                dedupe_key='alert:1001:pk_duplicate',
            ),
        )
        assert alert_id

        catalog = load_tasks_catalog(Path('configs/tasks_v1/catalog.yaml'))
        res1 = auto_create_tasks_from_alerts(conn, tenant_id='default', catalog=catalog, data_version='dv_demo')
        assert int(res1.get('eligible') or 0) == 1
        assert int(res1.get('inserted') or 0) == 1
        task_id = str((res1.get('task_ids') or [None])[0])
        assert task_id

        task = get_task(conn, tenant_id='default', task_id=task_id)
        assert task is not None
        assert task.get('related_alert') == alert_id
        assert task.get('qc_run') == 'qc2_demo'
        assert task.get('data_version') == 'dv_demo'
        assert int(task.get('priority') or 0) >= 1
        assert task.get('due_at')  # SLA/default deadline still materialized in core
        assert task.get('sla_source') in {'cfg.default', 'derived.from_due_at', 'user.due_at'}

        # Re-running must stay deduped for active tasks.
        res2 = auto_create_tasks_from_alerts(conn, tenant_id='default', catalog=catalog, data_version='dv_demo')
        assert int(res2.get('inserted') or 0) == 0
        assert int(res2.get('skipped') or 0) >= 1

        did = append_decision(
            conn,
            tenant_id='default',
            d=DecisionCreate(
                recommendation_id=None,
                action='recommendation.accepted',
                user_id=1,
                username='zootech',
                reason='CONFIRMED_BY_SPECIALIST',
                comment='ok',
                related_alert=alert_id,
                object_type='animal',
                object_id='1001',
                farm_id=None,
                group_id=None,
                data_version='dv_demo',
                model_version=None,
                report_version=None,
                qc_run='qc2_demo',
                scoring_run=None,
                metadata={'task_id': task_id},
            ),
        )
        assert did

        alert = get_alert(conn, tenant_id='default', alert_id=alert_id)
        assert alert is not None
        assert alert.get('alert_id') == alert_id
        assert alert.get('status') == 'new'
    finally:
        conn.close()
