from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.workflow.worklists import (
    accept_worklist_use_case,
    close_worklist_use_case,
    create_worklist_use_case,
    escalate_worklist_use_case,
    get_worklist,
    list_worklists_for_role_today,
    postpone_worklist_use_case,
)
from core.infra.web_db import init_db


@pytest.fixture()
def conn() -> sqlite3.Connection:
    conn = sqlite3.connect(':memory:', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    try:
        yield conn
    finally:
        conn.close()


def _seed_worklist(
    conn: sqlite3.Connection,
    *,
    worklist_type: str,
    object_id: str,
    due_at: str,
    priority: int,
    owner_user_id: int | None,
    assignee_team: str | None,
    title: str,
    expected_effect: str,
    role: str,
) -> str:
    created = create_worklist_use_case(
        conn=conn,
        tenant_id='default',
        worklist_type=worklist_type,
        title=title,
        priority=priority,
        due_at=due_at,
        owner_user_id=owner_user_id,
        assignee_team=assignee_team,
        confidence=0.74,
        object_type='animal',
        object_id=object_id,
        linked_source_facts=[
            {'label': 'Сигнал', 'text': f'{worklist_type}:{object_id}'},
            {'effect_text': expected_effect},
        ],
        why={'expected_effect': expected_effect},
        what_to_do=[{'action': 'inspect', 'expected_effect': expected_effect}],
        data_version='dv_t21_02',
        scoring_run='score_t21_02',
        report_version='report_t21_02',
        user_id=99,
        username='seed',
        role=role,
        request_id=f'REQ-{worklist_type}-{object_id}',
    )
    return str(created['worklist_id'])


def test_t21_02_role_today_queue_filters_by_role_and_due_bucket(conn: sqlite3.Connection) -> None:
    zootech_id = _seed_worklist(
        conn,
        worklist_type='reproduction',
        object_id='AN-100',
        due_at='2026-03-31T08:00:00+00:00',
        priority=1,
        owner_user_id=11,
        assignee_team='team-repro',
        title='Проверить осеменение',
        expected_effect='Снижение пропуска окна осеменения.',
        role='Zootech',
    )
    vet_id = _seed_worklist(
        conn,
        worklist_type='vet',
        object_id='AN-200',
        due_at='2026-03-30T08:00:00+00:00',
        priority=2,
        owner_user_id=22,
        assignee_team='team-health',
        title='Проверить mastitis follow-up',
        expected_effect='Снижение риска ухудшения здоровья.',
        role='Vet',
    )
    _seed_worklist(
        conn,
        worklist_type='data_cleanup',
        object_id='AN-300',
        due_at='2026-04-02T08:00:00+00:00',
        priority=3,
        owner_user_id=None,
        assignee_team='team-data',
        title='Исправить пропуски DIM',
        expected_effect='Повышение качества данных.',
        role='Operator',
    )

    zootech = list_worklists_for_role_today(
        conn,
        tenant_id='default',
        role='Zootech',
        user_id=11,
        today_iso='2026-03-31',
        limit=20,
    )
    assert zootech['summary']['total'] == 1
    assert zootech['worklists'][0]['worklist_id'] == zootech_id
    assert zootech['worklists'][0]['due_bucket'] == 'today'
    assert zootech['worklists'][0]['expected_effect'] == 'Снижение пропуска окна осеменения.'
    assert 'Сигнал' in zootech['worklists'][0]['linked_facts_preview'][0]

    vet = list_worklists_for_role_today(
        conn,
        tenant_id='default',
        role='Vet',
        user_id=22,
        today_iso='2026-03-31',
        limit=20,
    )
    assert vet['summary']['total'] == 1
    assert vet['worklists'][0]['worklist_id'] == vet_id
    assert vet['worklists'][0]['due_bucket'] == 'overdue'

    operator = list_worklists_for_role_today(
        conn,
        tenant_id='default',
        role='Operator',
        user_id=33,
        today_iso='2026-03-31',
        include_upcoming=False,
        limit=20,
    )
    assert operator['summary']['total'] == 0

    operator_upcoming = list_worklists_for_role_today(
        conn,
        tenant_id='default',
        role='Operator',
        user_id=33,
        today_iso='2026-03-31',
        include_upcoming=True,
        limit=20,
    )
    assert operator_upcoming['summary']['total'] == 1
    assert operator_upcoming['worklists'][0]['worklist_type'] == 'data_cleanup'


def test_t21_02_accept_postpone_escalate_complete_write_audit(conn: sqlite3.Connection) -> None:
    worklist_id = _seed_worklist(
        conn,
        worklist_type='health_follow_up',
        object_id='AN-400',
        due_at='2026-03-31T09:00:00+00:00',
        priority=2,
        owner_user_id=None,
        assignee_team='team-health',
        title='Follow-up after treatment',
        expected_effect='Подтверждение клинического исхода.',
        role='Vet',
    )

    accepted = accept_worklist_use_case(
        conn=conn,
        tenant_id='default',
        worklist_id=worklist_id,
        user_id=22,
        username='vet_user',
        role='Vet',
        request_id='REQ-ACCEPT',
    )
    assert accepted['after']['status'] == 'in_progress'
    assert accepted['after']['stage'] == 'execute'
    assert accepted['after']['owner_user_id'] == 22

    postponed = postpone_worklist_use_case(
        conn=conn,
        tenant_id='default',
        worklist_id=worklist_id,
        user_id=22,
        username='vet_user',
        role='Vet',
        due_at='2026-04-02',
        request_id='REQ-POSTPONE',
    )
    assert postponed['after']['status'] == 'open'
    assert postponed['after']['stage'] == 'plan'
    assert str(postponed['after']['due_at']).startswith('2026-04-02')

    escalated = escalate_worklist_use_case(
        conn=conn,
        tenant_id='default',
        worklist_id=worklist_id,
        user_id=22,
        username='vet_user',
        role='Vet',
        assignee_team='team-econ',
        priority=1,
        request_id='REQ-ESCALATE',
    )
    assert escalated['after']['stage'] == 'review'
    assert escalated['after']['assignee_team'] == 'team-econ'
    assert escalated['after']['priority'] == 1

    closed = close_worklist_use_case(
        conn=conn,
        tenant_id='default',
        worklist_id=worklist_id,
        user_id=22,
        username='vet_user',
        role='Vet',
        status='done',
        reason='completed',
        comment=None,
        resolve_related_alert=False,
        request_id='REQ-CLOSE',
    )
    assert closed['after']['status'] == 'done'
    stored = get_worklist(conn, tenant_id='default', worklist_id=worklist_id)
    assert stored is not None
    assert stored['signal_chain']['outcome']['status'] == 'done'

    actions = [
        row['action']
        for row in conn.execute(
            "SELECT action FROM audit_log WHERE action LIKE 'worklist.%' ORDER BY id"
        ).fetchall()
    ]
    assert 'worklist.accept' in actions
    assert 'worklist.postpone' in actions
    assert 'worklist.escalate' in actions
    assert 'worklist.close' in actions


def test_t21_02_streamlit_contracts_and_docs_present() -> None:
    page = Path('streamlit_app/pages/43_Daily_Worklists_By_Role.py').read_text(encoding='utf-8')
    helper = Path('streamlit_app/daily_worklists_by_role.py').read_text(encoding='utf-8')
    home = Path('streamlit_app/home_v3.py').read_text(encoding='utf-8')
    ia_cfg = Path('configs/ui/ia_v3.yaml').read_text(encoding='utf-8')
    home_cfg = Path('configs/ui/home_pages_v1.yaml').read_text(encoding='utf-8')
    docs = Path('docs/daily_worklists_by_role.md').read_text(encoding='utf-8')
    assumptions = Path('docs/assumptions.md').read_text(encoding='utf-8')

    assert 'Что делать сегодня' in page
    assert 'Accept' in page
    assert 'Postpone' in page
    assert 'Complete' in page
    assert 'Escalate' in page
    assert 'render_daily_worklists_home_widget' in helper
    assert 'list_worklists_for_role_today' in helper
    assert 'render_daily_worklists_home_widget(ctx, user, data_version=active_dv, max_items=3)' in home
    assert 'key: daily_worklists_by_role' in ia_cfg
    assert '- daily_worklists_by_role' in home_cfg
    assert '## Что сделано в T21-02' in docs
    assert '## T21-02 — daily worklists by role' in assumptions
