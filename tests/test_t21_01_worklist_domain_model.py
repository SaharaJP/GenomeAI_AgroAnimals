from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.workflow import (
    AlertCreate,
    create_alert,
)
from core.workflow.worklists import (
    close_worklist_use_case,
    create_worklist_use_case,
    get_worklist,
    link_worklist_decision_use_case,
    list_worklists,
    list_worklists_for_object,
    start_worklist_use_case,
    triage_worklist_use_case,
)
from web_cabinet.db import init_db


@pytest.fixture()
def conn() -> sqlite3.Connection:
    conn = sqlite3.connect(':memory:', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    try:
        yield conn
    finally:
        conn.close()


def _create_alert(conn: sqlite3.Connection, *, alert_id_hint: str = 'A-1') -> str:
    return create_alert(
        conn,
        tenant_id='default',
        a=AlertCreate(
            alert_type='ML.REPRO_RISK',
            title='Риск по воспроизводству',
            source='ml',
            cause='repeat_insemination_risk',
            confidence=0.72,
            object_type='animal',
            object_id=alert_id_hint,
            deadline='2026-04-02T09:00:00+00:00',
            owner_user_id=11,
            attachments=[],
            why={'top_factors': ['days_open_high']},
            what_to_do=[{'action': 'check'}],
            data_version='dv_t21',
            qc_run='qc_t21',
            model_version='mdl_t21',
            scoring_run='score_t21',
            report_version='report_t21',
            dedupe_key=f'alert:{alert_id_hint}',
        ),
    )


def test_t21_01_init_db_extends_tasks_v1_with_worklist_columns(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(tasks_v1)").fetchall()}
    assert {
        'worklist_type',
        'confidence',
        'linked_decision_id',
        'linked_task_id',
        'linked_source_facts_json',
    }.issubset(cols)

    indexes = {row[1] for row in conn.execute("PRAGMA index_list(tasks_v1)").fetchall()}
    assert 'idx_tasks_v1_worklist_type' in indexes
    assert 'idx_tasks_v1_linked_decision' in indexes
    assert 'idx_tasks_v1_linked_task' in indexes


def test_t21_01_create_and_list_worklist_preserve_links_and_signal_chain(conn: sqlite3.Connection) -> None:
    alert_id = _create_alert(conn, alert_id_hint='AN-101')

    created = create_worklist_use_case(
        conn=conn,
        tenant_id='default',
        worklist_type='reproduction',
        title='Проверить повторное осеменение',
        priority=2,
        due_at='2026-04-02T08:00:00+00:00',
        owner_user_id=11,
        assignee_team='team-repro',
        confidence=0.81,
        object_type='animal',
        object_id='AN-101',
        related_alert=alert_id,
        linked_task_id='parent-task-1',
        linked_source_facts=[
            {'kind': 'alert', 'ref': alert_id},
            {'kind': 'fact_pack', 'section': 'repro_risk_top'},
        ],
        data_version='dv_t21',
        qc_run='qc_t21',
        model_version='mdl_t21',
        scoring_run='score_t21',
        report_version='report_t21',
        user_id=7,
        username='zootech',
        role='Zootech',
        request_id='REQ-WL-1',
    )
    worklist_id = str(created['worklist_id'])
    stored = get_worklist(conn, tenant_id='default', worklist_id=worklist_id)
    assert stored is not None
    assert stored['worklist_id'] == worklist_id
    assert stored['task_id'] == worklist_id
    assert stored['worklist_type'] == 'reproduction'
    assert stored['confidence'] == pytest.approx(0.81)
    assert stored['linked_alert_id'] == alert_id
    assert stored['linked_task_id'] == 'parent-task-1'
    assert stored['linked_object'] == {'object_type': 'animal', 'object_id': 'AN-101'}
    assert len(stored['linked_source_facts']) == 2
    assert stored['signal_chain']['signal']['alert_id'] == alert_id
    assert stored['signal_chain']['triage']['status'] == 'open'
    assert stored['signal_chain']['task']['task_id'] == worklist_id
    assert stored['signal_chain']['outcome']['closed_at'] is None

    listed = list_worklists(conn, tenant_id='default', worklist_type='reproduction', limit=20)
    assert listed['total'] == 1
    assert listed['worklists'][0]['worklist_id'] == worklist_id

    listed_for_object = list_worklists_for_object(
        conn,
        tenant_id='default',
        object_type='animal',
        object_id='AN-101',
        worklist_type='reproduction',
    )
    assert listed_for_object['total'] == 1
    assert listed_for_object['worklists'][0]['linked_alert_id'] == alert_id

    audit_rows = [
        dict(r)
        for r in conn.execute(
            "SELECT action, object_type, object_id, request_id, after_json FROM audit_log WHERE action='worklist.create'"
        ).fetchall()
    ]
    assert len(audit_rows) == 1
    assert audit_rows[0]['object_type'] == 'worklist'
    assert audit_rows[0]['object_id'] == worklist_id
    assert audit_rows[0]['request_id'] == 'REQ-WL-1'
    after = json.loads(audit_rows[0]['after_json'])
    assert after['worklist_type'] == 'reproduction'
    assert after['linked_alert_id'] == alert_id


def test_t21_01_worklist_lifecycle_triage_start_link_decision_close(conn: sqlite3.Connection) -> None:
    alert_id = _create_alert(conn, alert_id_hint='AN-202')
    created = create_worklist_use_case(
        conn=conn,
        tenant_id='default',
        worklist_type='vet',
        title='Осмотр мастита',
        priority=1,
        confidence=0.67,
        object_type='animal',
        object_id='AN-202',
        related_alert=alert_id,
        linked_source_facts=[{'kind': 'alert', 'ref': alert_id}],
        data_version='dv_t21',
        user_id=9,
        username='vet',
        role='Vet',
        request_id='REQ-WL-2',
    )
    worklist_id = str(created['worklist_id'])

    triaged = triage_worklist_use_case(
        conn=conn,
        tenant_id='default',
        worklist_id=worklist_id,
        confidence=0.92,
        owner_user_id=9,
        assignee_team='team-health',
        linked_source_facts=[{'kind': 'qc', 'rule_id': 'SCC_HIGH'}],
        user_id=9,
        username='vet',
        role='Vet',
        request_id='REQ-WL-3',
    )
    assert triaged['after']['stage'] == 'triage'
    assert triaged['after']['status'] == 'open'
    assert triaged['after']['confidence'] == pytest.approx(0.92)
    assert triaged['after']['assignee_team'] == 'team-health'

    started = start_worklist_use_case(
        conn=conn,
        tenant_id='default',
        worklist_id=worklist_id,
        user_id=9,
        username='vet',
        role='Vet',
        request_id='REQ-WL-4',
    )
    assert started['after']['status'] == 'in_progress'
    assert started['after']['stage'] == 'execute'

    linked = link_worklist_decision_use_case(
        conn=conn,
        tenant_id='default',
        worklist_id=worklist_id,
        linked_decision_id='dec-manual-1',
        user_id=9,
        username='vet',
        role='Vet',
        request_id='REQ-WL-5',
    )
    assert linked['after']['linked_decision_id'] == 'dec-manual-1'
    assert linked['after']['stage'] == 'review'

    closed = close_worklist_use_case(
        conn=conn,
        tenant_id='default',
        worklist_id=worklist_id,
        user_id=9,
        username='vet',
        role='Vet',
        status='done',
        reason='done',
        comment='Осмотр завершён',
        resolve_related_alert=True,
        request_id='REQ-WL-6',
    )
    assert closed['after']['status'] == 'done'
    assert closed['after']['closed_reason'] == 'done'
    assert closed['after']['linked_decision_id']
    assert closed['after']['signal_chain']['outcome']['closed_reason'] == 'done'

    alert_row = conn.execute("SELECT status FROM alerts_v2 WHERE alert_id=?", (alert_id,)).fetchone()
    assert alert_row is not None
    assert alert_row['status'] == 'resolved'

    actions = {
        row['action']
        for row in conn.execute(
            "SELECT action FROM audit_log WHERE action LIKE 'worklist.%' ORDER BY id"
        ).fetchall()
    }
    assert actions == {
        'worklist.create',
        'worklist.triage',
        'worklist.start',
        'worklist.link_decision',
        'worklist.close',
    }


def test_t21_01_legacy_task_rows_are_exposed_as_worklists_best_effort(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO tasks_v1(
          task_id, tenant_id, created_at, updated_at,
          task_type, title, priority, status,
          related_alert, object_type, object_id,
          linked_source_facts_json, attachments_json, why_json, what_to_do_json
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            'legacy-task-1',
            'default',
            '2026-03-31T09:00:00+00:00',
            '2026-03-31T09:00:00+00:00',
            'data_correction',
            'Разобрать QC проблемы',
            3,
            'open',
            None,
            'animal',
            'AN-303',
            '[]',
            '[]',
            '{}',
            '[]',
        ),
    )
    conn.commit()

    wl = get_worklist(conn, tenant_id='default', worklist_id='legacy-task-1')
    assert wl is not None
    assert wl['worklist_type'] == 'data_cleanup'
    assert wl['worklist_id'] == 'legacy-task-1'


def test_t21_01_docs_and_registry_notes_present() -> None:
    doc = Path('docs/worklist_domain_model.md').read_text(encoding='utf-8')
    assumptions = Path('docs/assumptions.md').read_text(encoding='utf-8')
    registry = Path('src/core/migrations/registry.py').read_text(encoding='utf-8')
    web_db = Path('src/core/infra/web_db.py').read_text(encoding='utf-8')
    module = Path('src/core/workflow/worklists.py').read_text(encoding='utf-8')

    assert 'first-class operational object' in doc
    assert 'tasks_v1' in doc
    assert 'signal → triage → decision → task → outcome' in doc
    assert '## T21-01 — worklist domain model' in assumptions
    assert 'WEB_DB_SCHEMA_VERSION = 9' in registry
    assert 'web.db.worklists' in web_db
    assert 'create_worklist_use_case' in module
    assert 'close_worklist_use_case' in module
