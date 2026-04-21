from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.infra.web_db import init_db
from core.mobile_sync import (
    build_mobile_action_key,
    detect_worklist_mobile_conflict,
    execute_mobile_sync_action,
    get_mobile_sync_action,
    list_mobile_sync_actions,
    summarize_mobile_sync_actions,
)
from core.workflow import close_worklist_use_case, create_worklist_use_case


@pytest.fixture()
def conn() -> sqlite3.Connection:
    conn = sqlite3.connect(':memory:', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    try:
        yield conn
    finally:
        conn.close()



def test_t25_05_saved_action_is_idempotent_and_audited(conn: sqlite3.Connection) -> None:
    payload = {'animal_id': 'A-100', 'data_version': 'dv_t25_05'}
    key = build_mobile_action_key(page_key='cowside_event_entry', action_kind='animal_event.cowside_entry', object_type='animal', object_id='A-100', nonce='nonce-1')
    calls = {'n': 0}

    def executor(_conn, data):
        calls['n'] += 1
        return {'event_id': 'ev-1', 'data_version': data['data_version'], 'notice': 'ok'}

    first = execute_mobile_sync_action(
        conn,
        tenant_id='default',
        user_id=7,
        username='mobile',
        role='Vet',
        page_key='cowside_event_entry',
        action_kind='animal_event.cowside_entry',
        action_key=key,
        object_type='animal',
        object_id='A-100',
        payload=payload,
        request_id='rq-1',
        executor=executor,
    )
    second = execute_mobile_sync_action(
        conn,
        tenant_id='default',
        user_id=7,
        username='mobile',
        role='Vet',
        page_key='cowside_event_entry',
        action_kind='animal_event.cowside_entry',
        action_key=key,
        object_type='animal',
        object_id='A-100',
        payload=payload,
        request_id='rq-1-retry',
        executor=executor,
    )

    assert first['state'] == 'saved'
    assert second['state'] == 'saved'
    assert second['reused'] is True
    assert calls['n'] == 1
    row = get_mobile_sync_action(conn, tenant_id='default', action_key=key)
    assert row['status'] == 'saved'
    assert row['linked_event_id'] == 'ev-1'
    actions = [r['action'] for r in conn.execute("SELECT action FROM audit_log ORDER BY id").fetchall()]
    assert actions.count('mobile.sync.saved') == 1



def test_t25_05_transient_error_becomes_pending_retry_then_saved(conn: sqlite3.Connection) -> None:
    payload = {'worklist_id': 'WL-1', 'data_version': 'dv_t25_05'}
    key = build_mobile_action_key(page_key='mobile_worklists', action_kind='worklist.comment', object_type='worklist', object_id='WL-1', nonce='nonce-2')
    calls = {'n': 0}

    def executor(_conn, _data):
        calls['n'] += 1
        if calls['n'] == 1:
            raise TimeoutError('temporary timeout')
        return {'after': {'task_id': 'WL-1'}, 'notice': 'saved'}

    first = execute_mobile_sync_action(
        conn,
        tenant_id='default',
        user_id=9,
        username='operator',
        role='Operator',
        page_key='mobile_worklists',
        action_kind='worklist.comment',
        action_key=key,
        object_type='worklist',
        object_id='WL-1',
        payload=payload,
        request_id='rq-timeout',
        executor=executor,
    )
    second = execute_mobile_sync_action(
        conn,
        tenant_id='default',
        user_id=9,
        username='operator',
        role='Operator',
        page_key='mobile_worklists',
        action_kind='worklist.comment',
        action_key=key,
        object_type='worklist',
        object_id='WL-1',
        payload=payload,
        request_id='rq-timeout-retry',
        executor=executor,
    )

    assert first['state'] == 'pending_retry'
    assert second['state'] == 'saved'
    row = get_mobile_sync_action(conn, tenant_id='default', action_key=key)
    assert row['status'] == 'saved'
    assert int(row['retry_count']) == 2
    actions = [r['action'] for r in conn.execute("SELECT action FROM audit_log ORDER BY id").fetchall()]
    assert 'mobile.sync.pending_retry' in actions
    assert 'mobile.sync.saved' in actions



def test_t25_05_worklist_conflict_is_bounded_and_explainable(conn: sqlite3.Connection) -> None:
    created = create_worklist_use_case(
        conn=conn,
        tenant_id='default',
        worklist_type='health_follow_up',
        title='Follow-up',
        priority=2,
        due_at='2026-04-02T08:00:00+00:00',
        assignee_team='team-health',
        object_type='animal',
        object_id='A-100',
        data_version='dv_t25_05',
        user_id=11,
        username='seed',
        role='Vet',
        request_id='seed-wl',
    )
    wid = str(created['worklist_id'])
    close_worklist_use_case(
        conn=conn,
        tenant_id='default',
        worklist_id=wid,
        user_id=12,
        username='other_user',
        role='Vet',
        status='done',
        reason='completed',
        request_id='close-wl',
    )
    payload = {
        'tenant_id': 'default',
        'worklist_id': wid,
        'snapshot_status': 'open',
        'action_kind': 'worklist.postpone',
        'due_at': '2026-04-03',
        'data_version': 'dv_t25_05',
    }

    def never(_conn, _data):
        raise AssertionError('executor should not be called when conflict is detected')

    res = execute_mobile_sync_action(
        conn,
        tenant_id='default',
        user_id=7,
        username='mobile',
        role='Vet',
        page_key='mobile_worklists',
        action_kind='worklist.postpone',
        action_key=build_mobile_action_key(page_key='mobile_worklists', action_kind='worklist.postpone', object_type='worklist', object_id=wid, nonce='nonce-3'),
        object_type='worklist',
        object_id=wid,
        payload=payload,
        request_id='rq-conflict',
        conflict_checker=lambda conn_, data: detect_worklist_mobile_conflict(conn_, tenant_id='default', worklist_id=str(data['worklist_id']), snapshot_status=str(data['snapshot_status']), action_kind=str(data['action_kind'])),
        executor=never,
    )
    assert res['state'] == 'conflict'
    assert res['conflict']['code'] in {'worklist_already_closed', 'worklist_state_changed'}
    row = res['sync']
    assert row['status'] == 'conflict'
    assert row['conflict']['current_status'] == 'done'
    actions = [r['action'] for r in conn.execute("SELECT action FROM audit_log ORDER BY id").fetchall()]
    assert 'mobile.sync.conflict' in actions



def test_t25_05_recent_rows_summary_and_docs_are_wired(conn: sqlite3.Connection) -> None:
    rows = [
        {'status': 'saved'},
        {'status': 'pending_retry'},
        {'status': 'conflict'},
    ]
    summary = summarize_mobile_sync_actions(rows)
    assert summary == {'total': 3, 'saved': 1, 'pending_retry': 1, 'conflict': 1}

    root = Path(__file__).resolve().parents[1]
    page_wl = (root / 'streamlit_app' / 'pages' / '58_Mobile_Worklists.py').read_text(encoding='utf-8')
    page_ce = (root / 'streamlit_app' / 'pages' / '59_Cowside_Event_Entry.py').read_text(encoding='utf-8')
    helper = (root / 'streamlit_app' / 'mobile_sync_conflict.py').read_text(encoding='utf-8')
    docs = (root / 'docs' / 'mobile_sync_conflict_audit.md').read_text(encoding='utf-8')
    assumptions = (root / 'docs' / 'assumptions.md').read_text(encoding='utf-8')
    smoke = (root / 'scripts' / 'smoke_t25_05_mobile_sync_conflict_audit.py').read_text(encoding='utf-8')

    assert 'Sync / retry / conflict' in page_wl
    assert 'Sync / retry / conflict' in page_ce
    assert 'build_mobile_action_token' in helper
    assert 'pending retry' in docs.lower()
    assert 'not true offline-first' in assumptions.lower()
    assert 'mobile sync / conflict / audit smoke passed' in smoke
