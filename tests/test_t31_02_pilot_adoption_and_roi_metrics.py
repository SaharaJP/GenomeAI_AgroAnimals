from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.audit.events import write_audit
from core.infra.repositories import AnimalEventsRepo, CompletionOutcomesRepo, DecisionsRepo, ReportApprovalsRepo, TasksRepo
from core.infra.web_db import init_db
from core.pilot_adoption_metrics import build_pilot_adoption_metrics_summary


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(':memory:', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def _seed(conn: sqlite3.Connection) -> datetime:
    now = datetime(2026, 4, 6, 9, 0, tzinfo=timezone.utc)
    for user_id, username, role in [
        (1, 'director', 'Director'),
        (2, 'operator', 'Operator'),
        (3, 'zootech', 'Zootech'),
        (4, 'vet', 'Vet'),
        (5, 'admin', 'Admin'),
    ]:
        write_audit(conn, tenant_id='default', user_id=user_id, username=username, role=role, action='auth.login.web', object_type='session', object_id=f'req-{username}', request_id=f'req-{username}')
    write_audit(conn, tenant_id='default', user_id=1, username='director', role='Director', action='assistant.contextual.answer', object_type='report', object_id='rv_demo')
    write_audit(conn, tenant_id='default', user_id=1, username='director', role='Director', action='export.download', object_type='report', object_id='rv_demo')
    write_audit(conn, tenant_id='default', user_id=2, username='operator', role='Operator', action='pipeline.run', object_type='job', object_id='job1')
    write_audit(conn, tenant_id='default', user_id=3, username='zootech', role='Zootech', action='tasks.take', object_type='task', object_id='TASK1')
    write_audit(conn, tenant_id='default', user_id=4, username='vet', role='Vet', action='vet_protocol.start', object_type='vet_protocol_execution', object_id='VP1')
    write_audit(conn, tenant_id='default', user_id=5, username='admin', role='Admin', action='security.user.create', object_type='user', object_id='user-x')

    tasks = TasksRepo(conn)
    tasks.insert(tenant_id='default', task_id='TASK1', created_at=(now - timedelta(days=1)).isoformat(), payload={
        'task_type': 'review', 'title': 'Review worklist', 'domain': 'operations', 'priority': 1,
        'status': 'done', 'due_at': (now - timedelta(hours=12)).isoformat(), 'worklist_type': 'reproduction', 'linked_decision_id': 'DEC1'
    })
    tasks.insert(tenant_id='default', task_id='TASK2', created_at=(now - timedelta(days=1)).isoformat(), payload={
        'task_type': 'follow_up', 'title': 'Follow-up', 'domain': 'vet', 'priority': 2,
        'status': 'open', 'due_at': (now - timedelta(hours=3)).isoformat(), 'worklist_type': 'vet_triage'
    })

    AnimalEventsRepo(conn).append(tenant_id='default', created_at=now.isoformat(), payload={
        'event_id': 'EV1', 'animal_id': 'A1', 'farm_id': 'F1', 'site_id': 'S1', 'event_type': 'insemination',
        'event_ts': (now - timedelta(hours=2)).isoformat(), 'event_date': (now - timedelta(hours=2)).date().isoformat(),
        'actor_type': 'user', 'actor_user_id': 3, 'actor_username': 'zootech', 'source': 'manual'
    })

    DecisionsRepo(conn).append(tenant_id='default', decision_id='DEC1', created_at=now.isoformat(), payload={
        'recommendation_id': 'R1', 'action': 'defer', 'user_id': 1, 'username': 'director', 'reason': 'economics review', 'comment': 'Need sign-off',
        'object_type': 'animal', 'object_id': 'A1', 'data_version': 'dv_demo', 'report_version': 'rv_demo', 'scoring_run': 'sr_demo',
        'metadata': {'economics_inputs_version': 'econ_v1', 'expected_net_value_rub': 1200.0, 'expected_roi': 1.4, 'recommended_action': 'execute_now', 'worklist_type': 'reproduction'}
    })
    CompletionOutcomesRepo(conn).append(tenant_id='default', outcome_id='OUT1', created_at=now.isoformat(), payload={
        'task_id': 'TASK1', 'linked_decision_id': 'DEC1', 'object_type': 'animal', 'object_id': 'A1', 'outcome_status': 'done', 'reason_code': 'completed', 'outcome_role': 'Zootech'
    })
    ReportApprovalsRepo(conn).ensure_row(tenant_id='default', data_version='dv_demo', report_version='rv_demo', now=now.isoformat())
    ReportApprovalsRepo(conn).approve(tenant_id='default', data_version='dv_demo', report_version='rv_demo', updated_at=now.isoformat(), user_id=1, username='director', comment='ok')
    conn.execute("INSERT INTO feedback_events_v1(feedback_id, tenant_id, created_at, recommendation_id, decision, reason_code, comment, recommendation_created_at, decision_seconds, related_alert, task_id, object_type, object_id, farm_id, group_id, data_version, model_version, report_version, qc_run, scoring_run, feedback_source, decision_id, metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 ('FB1','default',now.isoformat(),'R1','accepted','looks_good',None,None,None,None,'TASK1','assistant_answer','A1',None,None,'dv_demo',None,'rv_demo',None,'sr_demo','assistant_context.worklist','DEC1','{"feedback_kind":"assistant_answer"}'))
    conn.commit()
    return now


def test_t31_02_builds_actionable_pilot_adoption_metrics() -> None:
    conn = _conn()
    now = _seed(conn)
    payload = build_pilot_adoption_metrics_summary(project_root=Path('.'), conn=conn, tenant_id='default', now_utc=now)
    summary = payload['summary']
    assert summary['dau_total'] >= 5
    assert summary['report_usage_total'] >= 1
    assert summary['assistant_usage_total'] >= 1
    assert summary['approval_usage_total'] >= 1
    assert summary['completion_rate'] == 0.5
    assert summary['overdue_open_tasks'] == 1
    assert summary['median_event_entry_latency_hours'] == 2.0
    assert summary['assistant_feedback_total'] == 1
    assert summary['economics_linked_decisions'] == 1
    assert summary['evidence_ready_decisions'] == 1
    assert summary['roi_evidence_rate'] == 1.0
    assert payload['hardening_priorities']


def test_t31_02_onboarding_friction_uses_role_activation_signals() -> None:
    conn = _conn()
    now = datetime(2026, 4, 6, 9, 0, tzinfo=timezone.utc)
    write_audit(conn, tenant_id='default', user_id=10, username='dir_drop', role='Director', action='auth.login.web', object_type='session', object_id='req-dir-drop')
    payload = build_pilot_adoption_metrics_summary(project_root=Path('.'), conn=conn, tenant_id='default', now_utc=now)
    rows = {row['role']: row for row in payload['onboarding_friction_by_role']}
    assert rows['Director']['users_started'] == 1
    assert rows['Director']['users_activated'] == 0
    assert 'no_post_login_action' in rows['Director']['top_dropoff_points'][0]
    assert any(item['priority_key'] == 'onboarding_friction_Director' for item in payload['hardening_priorities'])


def test_t31_02_roi_gate_requires_outcome_linkage() -> None:
    conn = _conn()
    now = datetime(2026, 4, 6, 9, 0, tzinfo=timezone.utc)
    DecisionsRepo(conn).append(tenant_id='default', decision_id='DEC_NO_OUTCOME', created_at=now.isoformat(), payload={
        'recommendation_id': 'R2', 'action': 'defer', 'user_id': 1, 'username': 'director', 'reason': 'economics review',
        'object_type': 'animal', 'object_id': 'A2', 'data_version': 'dv_demo', 'report_version': 'rv_demo',
        'metadata': {'economics_inputs_version': 'econ_v1', 'expected_net_value_rub': 500.0, 'expected_roi': 1.1}
    })
    payload = build_pilot_adoption_metrics_summary(project_root=Path('.'), conn=conn, tenant_id='default', now_utc=now)
    rows = payload['roi_evidence_rows']
    assert rows[0]['evidence_ready'] is False
    assert payload['summary']['roi_evidence_rate'] == 0.0
