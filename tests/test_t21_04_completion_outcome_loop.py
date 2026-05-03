from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.workflow import AlertCreate, create_alert
from core.workflow.outcomes import (
    aggregate_execution_quality_metrics,
    get_completion_outcome,
    list_completion_outcomes,
    record_completion_outcome_use_case,
)
from core.workflow.worklists import close_worklist_use_case, create_worklist_use_case, get_worklist
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


def _create_alert(conn: sqlite3.Connection, *, animal_id: str) -> str:
    return create_alert(
        conn,
        tenant_id='default',
        a=AlertCreate(
            alert_type='ML.HEALTH_RISK',
            title='Нужна проверка исхода лечения',
            source='ml',
            cause='treatment_follow_up',
            confidence=0.81,
            object_type='animal',
            object_id=animal_id,
            deadline='2026-04-02T10:00:00+00:00',
            owner_user_id=22,
            attachments=[],
            why={'expected_effect': 'Подтвердить клинический исход.'},
            what_to_do=[{'action': 'check'}],
            data_version='dv_t21_04',
            qc_run='qc_t21_04',
            model_version='mdl_t21_04',
            scoring_run='score_t21_04',
            report_version='report_t21_04',
            dedupe_key=f'alert:{animal_id}',
        ),
    )


def _create_worklist(conn: sqlite3.Connection, *, animal_id: str, alert_id: str | None = None) -> str:
    created = create_worklist_use_case(
        conn=conn,
        tenant_id='default',
        worklist_type='health_follow_up',
        title='Контроль исхода лечения',
        priority=2,
        due_at='2026-04-01T09:00:00+00:00',
        owner_user_id=22,
        assignee_team='team-health',
        confidence=0.78,
        object_type='animal',
        object_id=animal_id,
        related_alert=alert_id,
        linked_source_facts=[{'label': 'alert', 'text': alert_id or 'manual'}],
        data_version='dv_t21_04',
        qc_run='qc_t21_04',
        model_version='mdl_t21_04',
        scoring_run='score_t21_04',
        report_version='report_t21_04',
        user_id=22,
        username='vet',
        role='Vet',
        request_id=f'REQ-{animal_id}',
    )
    return str(created['worklist_id'])


def test_t21_04_init_db_adds_completion_outcome_storage_and_task_summary_fields(conn: sqlite3.Connection) -> None:
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert 'completion_outcomes_v1' in tables

    cols = {row[1] for row in conn.execute("PRAGMA table_info(tasks_v1)").fetchall()}
    assert {
        'latest_outcome_id',
        'latest_outcome_status',
        'latest_outcome_reason_code',
        'latest_outcome_at',
        'latest_outcome_by',
        'latest_outcome_comment',
        'outcome_metrics_json',
    }.issubset(cols)

    conn.execute("INSERT INTO completion_outcomes_v1(outcome_id, tenant_id, created_at, outcome_status, reason_code, metrics_json, auto_actions_json) VALUES (?,?,?,?,?,?,?)", ('o-1', 'default', '2026-04-01T00:00:00+00:00', 'done', 'COMPLETED', '{}', '{}'))
    conn.commit()
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("UPDATE completion_outcomes_v1 SET reason_code='X' WHERE outcome_id='o-1'")


def test_t21_04_close_worklist_records_formal_outcome_and_resolves_alert_safely(conn: sqlite3.Connection) -> None:
    alert_id = _create_alert(conn, animal_id='AN-401')
    worklist_id = _create_worklist(conn, animal_id='AN-401', alert_id=alert_id)

    closed = close_worklist_use_case(
        conn=conn,
        tenant_id='default',
        worklist_id=worklist_id,
        user_id=22,
        username='vet',
        role='Vet',
        status='done',
        reason='VERIFIED',
        comment='Исход подтверждён',
        resolve_related_alert=True,
        request_id='REQ-T21-04-CLOSE',
    )
    assert closed['after']['status'] == 'done'
    assert closed['after']['latest_outcome_status'] == 'done'
    assert closed['after']['latest_outcome_reason_code'] == 'VERIFIED'
    assert closed['after']['linked_decision_id']
    assert closed['auto_actions']['alert_resolved'] is True

    outcome_id = str(closed['outcome']['outcome_id'])
    stored = get_completion_outcome(conn, tenant_id='default', outcome_id=outcome_id)
    assert stored is not None
    assert stored['outcome_status'] == 'done'
    assert stored['reason_code'] == 'VERIFIED'
    assert stored['linked_decision_id'] == closed['after']['linked_decision_id']
    assert stored['auto_actions']['alert_resolved'] is True
    assert stored['metrics']['auto_alert_resolved'] is True

    alert_status = conn.execute("SELECT status FROM alerts_v2 WHERE alert_id=?", (alert_id,)).fetchone()['status']
    assert alert_status == 'resolved'

    worklist = get_worklist(conn, tenant_id='default', worklist_id=worklist_id)
    assert worklist is not None
    assert worklist['signal_chain']['outcome']['status'] == 'done'
    assert worklist['signal_chain']['outcome']['reason_code'] == 'VERIFIED'
    assert worklist['signal_chain']['outcome']['outcome_id'] == outcome_id

    actions = [
        row['action']
        for row in conn.execute(
            "SELECT action FROM audit_log WHERE action IN ('completion_outcome.record','worklist.close') ORDER BY id"
        ).fetchall()
    ]
    assert actions == ['completion_outcome.record', 'worklist.close']


def test_t21_04_deferred_no_effect_and_escalated_preserve_explainable_outcome(conn: sqlite3.Connection) -> None:
    worklist_id = _create_worklist(conn, animal_id='AN-402')

    deferred = record_completion_outcome_use_case(
        conn=conn,
        tenant_id='default',
        worklist_id=worklist_id,
        user_id=11,
        username='zootech',
        role='Zootech',
        outcome_status='deferred',
        reason_code='WAIT_FOR_WINDOW',
        comment='Переносим на окно завтра',
        due_at='2026-04-02T08:00:00+00:00',
        request_id='REQ-DEFER',
    )
    assert deferred['after']['status'] == 'open'
    assert deferred['after']['stage'] == 'plan'
    assert deferred['after']['latest_outcome_status'] == 'deferred'
    assert deferred['after']['linked_decision_id']
    assert deferred['auto_actions']['decision_auto_linked'] is True

    no_effect = record_completion_outcome_use_case(
        conn=conn,
        tenant_id='default',
        worklist_id=worklist_id,
        user_id=11,
        username='zootech',
        role='Zootech',
        outcome_status='no_effect',
        reason_code='NO_EFFECT_OBSERVED',
        comment='После проверки эффект не подтверждён',
        request_id='REQ-NO-EFFECT',
    )
    assert no_effect['after']['status'] == 'done'
    assert no_effect['after']['latest_outcome_status'] == 'no_effect'
    assert no_effect['auto_actions']['alert_resolved'] is False

    worklist_id2 = _create_worklist(conn, animal_id='AN-403')
    escalated = record_completion_outcome_use_case(
        conn=conn,
        tenant_id='default',
        worklist_id=worklist_id2,
        user_id=33,
        username='operator',
        role='Operator',
        outcome_status='escalated',
        reason_code='NEEDS_VET_REVIEW',
        comment='Требуется ветврач',
        assignee_team='team-health',
        priority=1,
        request_id='REQ-ESCALATE',
    )
    assert escalated['after']['status'] == 'open'
    assert escalated['after']['stage'] == 'review'
    assert escalated['after']['priority'] == 1
    assert escalated['after']['latest_outcome_status'] == 'escalated'
    assert escalated['after']['linked_decision_id']

    listed = list_completion_outcomes(conn, tenant_id='default', task_id=worklist_id, limit=10)
    assert listed['total'] == 2
    statuses = {row['outcome_status'] for row in listed['outcomes']}
    assert {'deferred', 'no_effect'}.issubset(statuses)


def test_t21_04_execution_quality_metrics_aggregate_from_outcomes(conn: sqlite3.Connection) -> None:
    alert_id = _create_alert(conn, animal_id='AN-404')
    worklist_a = _create_worklist(conn, animal_id='AN-404', alert_id=alert_id)
    worklist_b = _create_worklist(conn, animal_id='AN-405')

    close_worklist_use_case(
        conn=conn,
        tenant_id='default',
        worklist_id=worklist_a,
        user_id=22,
        username='vet',
        role='Vet',
        status='done',
        reason='COMPLETED',
        comment=None,
        resolve_related_alert=True,
        request_id='REQ-M1',
    )
    record_completion_outcome_use_case(
        conn=conn,
        tenant_id='default',
        worklist_id=worklist_b,
        user_id=11,
        username='zootech',
        role='Zootech',
        outcome_status='deferred',
        reason_code='BLOCKED_BY_DEPENDENCY',
        comment='Ждём подтверждения',
        due_at='2026-04-03T08:00:00+00:00',
        request_id='REQ-M2',
    )

    metrics = aggregate_execution_quality_metrics(conn, tenant_id='default')
    assert metrics['total'] == 2
    assert metrics['by_outcome_status']['done'] == 1
    assert metrics['by_outcome_status']['deferred'] == 1
    assert metrics['decision_link_rate'] == 1.0
    assert metrics['auto_alert_resolution_rate'] == 0.5
    assert metrics['bottlenecks']


def test_t21_04_docs_and_registry_contracts_present() -> None:
    docs = Path('docs/completion_outcome_loop.md').read_text(encoding='utf-8')
    assumptions = Path('docs/assumptions.md').read_text(encoding='utf-8')
    registry = Path('src/core/migrations/registry.py').read_text(encoding='utf-8')
    web_db = Path('src/core/infra/web_db.py').read_text(encoding='utf-8')
    outcomes = Path('src/core/workflow/outcomes.py').read_text(encoding='utf-8')
    reasons = Path('configs/workflow_v2/reason_codes.yaml').read_text(encoding='utf-8')

    assert '## Что сделано в T21-04' in docs
    assert 'done / cancelled / deferred / no_effect / escalated' in docs
    assert 'completion_outcomes_v1' in docs
    assert '## T21-04 — completion / outcome loop' in assumptions
    assert 'WEB_DB_SCHEMA_VERSION = 9' in registry
    assert 'web.db.completion_outcomes' in registry
    assert 'completion_outcomes_v1' in web_db
    assert 'record_completion_outcome_use_case' in outcomes
    assert 'aggregate_execution_quality_metrics' in outcomes
    assert 'completion_outcome:' in reasons
