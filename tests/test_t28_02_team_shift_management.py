from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from core.infra.web_db import init_db
from core.workflow import (
    build_handover_monitor,
    build_team_queue_balance,
    create_worklist_use_case,
    enrich_team_shift_rows,
    filter_team_shift_rows,
    get_worklist,
    handover_worklist_use_case,
)
from streamlit_app.saved_views_state import apply_saved_view_state, extract_saved_view_state


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
        confidence=0.77,
        object_type='animal',
        object_id=object_id,
        linked_source_facts=[{'label': 'Signal', 'text': f'{worklist_type}:{object_id}'}],
        why={'expected_effect': 'Keep queue explainable.'},
        what_to_do=[{'action': 'inspect'}],
        data_version='dv_t28_02',
        user_id=99,
        username='seed',
        role='Vet' if assignee_team == 'team-health' else 'Zootech',
        request_id=f'REQ-{object_id}',
    )
    return str(created['worklist_id'])


def test_t28_02_handover_is_traceable_and_can_clear_personal_owner(conn: sqlite3.Connection) -> None:
    worklist_id = _seed_worklist(
        conn,
        worklist_type='vet',
        object_id='AN-001',
        due_at='2026-04-04T08:00:00+00:00',
        priority=1,
        owner_user_id=22,
        assignee_team='team-health',
        title='Проверить клинический исход',
    )

    res = handover_worklist_use_case(
        conn=conn,
        tenant_id='default',
        worklist_id=worklist_id,
        user_id=22,
        username='vet_lead',
        role='Vet',
        to_shift_key='night',
        to_team='team-health',
        to_owner_user_id=None,
        reason_code='shift_end',
        note='Передаю ночной смене',
        request_id='REQ-HANDOVER',
    )

    after = enrich_team_shift_rows([res['after']])[0]
    assert after['assignee_team'] == 'team-health'
    assert after['owner_user_id'] is None
    assert after['shift_key'] == 'night'
    assert after['handover_count'] == 1
    assert after['last_handover_reason'] == 'shift_end'
    assert 'team-health · Night shift' in str(after['queue_owner_label'])

    stored = get_worklist(conn, tenant_id='default', worklist_id=worklist_id)
    assert stored is not None
    attachments = list(stored.get('attachments') or [])
    handovers = [x for x in attachments if isinstance(x, dict) and x.get('kind') == 'handover']
    assert len(handovers) == 1
    assert handovers[0]['reason_code'] == 'shift_end'
    assert handovers[0]['to_shift'] == 'night'

    actions = [
        row['action']
        for row in conn.execute("SELECT action FROM audit_log WHERE action='worklist.handover' ORDER BY id").fetchall()
    ]
    assert actions == ['worklist.handover']


def test_t28_02_role_boundaries_and_queue_balance_are_explainable(conn: sqlite3.Connection) -> None:
    w1 = _seed_worklist(
        conn,
        worklist_type='vet',
        object_id='AN-002',
        due_at='2026-04-03T08:00:00+00:00',
        priority=1,
        owner_user_id=None,
        assignee_team='team-health',
        title='Mastitis high-risk',
    )
    w2 = _seed_worklist(
        conn,
        worklist_type='reproduction',
        object_id='AN-003',
        due_at='2026-04-04T09:00:00+00:00',
        priority=2,
        owner_user_id=31,
        assignee_team='team-repro',
        title='Preg-check due',
    )

    with pytest.raises(PermissionError):
        handover_worklist_use_case(
            conn=conn,
            tenant_id='default',
            worklist_id=w1,
            user_id=41,
            username='operator_1',
            role='Operator',
            to_shift_key='day',
            to_team='team-health',
            to_owner_user_id=None,
            reason_code='team_reassignment',
            note='Недопустимо для Operator',
            request_id='REQ-DENY',
        )

    # add one traceable handover so shift-based balance is not all unassigned
    handover_worklist_use_case(
        conn=conn,
        tenant_id='default',
        worklist_id=w2,
        user_id=31,
        username='zootech_1',
        role='Zootech',
        to_shift_key='day',
        to_team='team-repro',
        to_owner_user_id=31,
        reason_code='backlog_rebalance',
        note='Оставляю в дневной смене',
        request_id='REQ-REPRO-SHIFT',
    )

    rows = [
        dict(get_worklist(conn, tenant_id='default', worklist_id=w1) or {}),
        dict(get_worklist(conn, tenant_id='default', worklist_id=w2) or {}),
        {
            'planner_item_id': 'manual:1',
            'title': 'Night vet backlog',
            'status': 'open',
            'priority': 2,
            'bucket': 'overdue',
            'assignee_team': 'team-health',
            'owner_user_id': None,
            'why': {'ownership': {'team_key': 'team-health', 'shift_key': 'night'}},
            'load_units': 1.5,
        },
    ]
    enriched = enrich_team_shift_rows(rows)
    night_only = filter_team_shift_rows(enriched, assignee_team='team-health', shift_key='night')
    assert len(night_only) == 1
    assert night_only[0]['queue_key'] == 'team-health:night'

    balance = build_team_queue_balance(enriched, level='team_shift')
    rec = balance[(balance['assignee_team'].astype(str) == 'team-health') & (balance['shift_key'].astype(str) == 'night')].iloc[0].to_dict()
    assert rec['items_total'] == 1
    assert rec['overdue'] == 1
    assert rec['team_unowned'] == 1
    assert 'team=team-health' in str(rec['explainability'])

    monitor = build_handover_monitor(enriched)
    assert int(monitor['candidates_total']) >= 2
    assert int(monitor['unowned_total']) >= 1


def test_t28_02_saved_views_and_docs_are_wired() -> None:
    sess = {
        'daily_worklists_by_role.day': date(2026, 4, 4),
        'daily_worklists_by_role.data_version': 'dv_t28_02',
        'daily_worklists_by_role.include_upcoming': True,
        'daily_worklists_by_role.q': 'mastitis',
        'daily_worklists_by_role.limit': 60,
        'daily_worklists_by_role.farm_id': 'F1',
        'daily_worklists_by_role.site_id': 'S1',
        'daily_worklists_by_role.group_id': 'G1',
        'daily_worklists_by_role.pen_id': 'P1',
        'daily_worklists_by_role.team': 'team-health',
        'daily_worklists_by_role.shift': 'night',
        'daily_worklists_by_role.selected_worklist_id': 'W1',
        'operational_planner.day': date(2026, 4, 4),
        'operational_planner.data_version': 'dv_t28_02',
        'operational_planner.view_mode': 'manager',
        'operational_planner.role': 'Vet',
        'operational_planner.owner': 'vet_1',
        'operational_planner.team': 'team-health',
        'operational_planner.shift': 'night',
        'operational_planner.sources': ['alerts', 'worklists'],
        'operational_planner.q': 'handover',
        'operational_planner.farm_id': 'F1',
        'operational_planner.site_id': 'S1',
        'operational_planner.group_id': 'G1',
        'operational_planner.pen_id': 'P1',
        'operational_planner.limit_per_bucket': 40,
        'operational_planner.selected_item_id': 'P1',
    }
    dw_state = extract_saved_view_state(page_key='daily_worklists_by_role', session_state=sess)
    planner_state = extract_saved_view_state(page_key='operational_planner', session_state=sess)
    assert dw_state['daily_worklists_by_role.shift'] == 'night'
    assert planner_state['operational_planner.shift'] == 'night'
    restored: dict[str, object] = {}
    apply_saved_view_state(page_key='daily_worklists_by_role', state=dw_state, session_state=restored)
    assert restored['daily_worklists_by_role.day'] == date(2026, 4, 4)
    assert restored['daily_worklists_by_role.team'] == 'team-health'

    root = Path(__file__).resolve().parents[1]
    page_dw = (root / 'streamlit_app' / 'pages' / '43_Daily_Worklists_By_Role.py').read_text(encoding='utf-8')
    page_planner = (root / 'streamlit_app' / 'pages' / '44_Operational_Planner.py').read_text(encoding='utf-8')
    helper = (root / 'src' / 'core' / 'workflow' / 'team_shift.py').read_text(encoding='utf-8')
    docs = (root / 'docs' / 'team_shift_management.md').read_text(encoding='utf-8')
    assumptions = (root / 'docs' / 'assumptions.md').read_text(encoding='utf-8')
    saved = (root / 'streamlit_app' / 'saved_views_state.py').read_text(encoding='utf-8')

    assert 'Handover between shifts' in page_dw
    assert 'Queue balance / Team-shift load' in page_dw
    assert 'Queue balance / Team-shift load' in page_planner
    assert 'handover_worklist_use_case' in helper and 'build_team_queue_balance' in helper
    assert 'handover' in docs.lower() and 'shift' in docs.lower() and 'traceable' in docs.lower()
    assert '## T28-02 — team / shift management' in assumptions
    assert 'daily_worklists_by_role.shift' in saved and 'operational_planner.shift' in saved
