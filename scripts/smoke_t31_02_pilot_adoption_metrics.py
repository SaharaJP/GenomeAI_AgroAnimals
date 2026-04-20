from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.audit.events import write_audit
from core.infra.repositories import AnimalEventsRepo, CompletionOutcomesRepo, DecisionsRepo, ReportApprovalsRepo, TasksRepo
from core.infra.web_db import init_db
from core.pilot_adoption_metrics import build_pilot_adoption_metrics_summary, render_pilot_adoption_metrics_cli_lines, render_pilot_adoption_metrics_markdown


def _seed(conn) -> None:
    now = datetime(2026, 4, 6, 9, 0, tzinfo=timezone.utc)
    # logins
    for user_id, username, role in [
        (1, 'director', 'Director'),
        (2, 'operator', 'Operator'),
        (3, 'zootech', 'Zootech'),
        (4, 'vet', 'Vet'),
        (5, 'admin', 'Admin'),
    ]:
        write_audit(conn, tenant_id='default', user_id=user_id, username=username, role=role, action='auth.login.web', object_type='session', object_id=f'req-{username}', request_id=f'req-{username}')

    write_audit(conn, tenant_id='default', user_id=1, username='director', role='Director', action='assistant.contextual.answer', object_type='report', object_id='rv_demo', request_id='r1')
    write_audit(conn, tenant_id='default', user_id=2, username='operator', role='Operator', action='pipeline.run', object_type='job', object_id='job1', request_id='r2')
    write_audit(conn, tenant_id='default', user_id=3, username='zootech', role='Zootech', action='tasks.take', object_type='task', object_id='TASK1', request_id='r3')
    write_audit(conn, tenant_id='default', user_id=4, username='vet', role='Vet', action='vet_protocol.start', object_type='vet_protocol_execution', object_id='VP1', request_id='r4')
    write_audit(conn, tenant_id='default', user_id=5, username='admin', role='Admin', action='security.user.create', object_type='user', object_id='user-x', request_id='r5')
    write_audit(conn, tenant_id='default', user_id=1, username='director', role='Director', action='export.download', object_type='report', object_id='rv_demo', request_id='r6')

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
                 ('FB1','default',now.isoformat(),'R1','accepted','looks_good',None,None,None,None,'TASK1','assistant_answer','A1',None,None,'dv_demo',None,'rv_demo',None,'sr_demo','assistant_context.worklist','DEC1',json.dumps({'feedback_kind':'assistant_answer'})))
    conn.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description='Smoke runner for pilot adoption / ROI metrics')
    parser.add_argument('--project-root', default='.')
    parser.add_argument('--report-root', default='artifacts/_ci/pilot_adoption_v1')
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / 'web.db'
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        init_db(conn)
        _seed(conn)
        payload = build_pilot_adoption_metrics_summary(project_root=args.project_root, conn=conn, tenant_id='default', now_utc=datetime(2026, 4, 6, 9, 0, tzinfo=timezone.utc))
        conn.close()

    report_root = Path(args.report_root)
    report_root.mkdir(parents=True, exist_ok=True)
    (report_root / 'pilot_adoption_metrics_report.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    (report_root / 'pilot_adoption_metrics_report.md').write_text(render_pilot_adoption_metrics_markdown(payload), encoding='utf-8')
    for line in render_pilot_adoption_metrics_cli_lines(payload):
        print(line)
    print('PILOT_ADOPTION_METRICS_READY')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
