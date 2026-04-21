from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.infra.web_db import init_db
from core.operational import (
    AnimalEventBatchEntryError,
    animal_event_batch_entry_catalog,
    commit_animal_event_batch_use_case,
    preview_animal_event_batch_use_case,
)
from core.operational.animal_events import list_animal_events_for_animal
from core.security.policy import PermissionDenied
from web_cabinet import rbac


@pytest.fixture()
def conn() -> sqlite3.Connection:
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def _rows() -> list[dict[str, str]]:
    return [
        {'animal_id': 'A-301', 'farm_id': 'farm-1', 'site_id': 'site-1', 'pen_id': 'pen-1', 'pen_name': 'Group 1'},
        {'animal_id': 'A-302', 'farm_id': 'farm-1', 'site_id': 'site-1', 'pen_id': 'pen-1', 'pen_name': 'Group 1'},
        {'animal_id': 'A-303', 'farm_id': 'farm-1', 'site_id': 'site-1', 'pen_id': 'pen-1', 'pen_name': 'Group 1'},
    ]



def test_t20_03_batch_preview_and_commit_apply_append_only_events_with_audit(conn: sqlite3.Connection) -> None:
    preview = preview_animal_event_batch_use_case(
        conn=conn,
        tenant_id='default',
        animal_rows=_rows()[:2],
        action='move_to_group',
        event_ts='2026-03-31T12:00:00+00:00',
        permissions=rbac.ROLE_PERMISSIONS[rbac.ROLE_ZOOTECH],
        params={'target_pen_id': 'pen-7', 'target_pen_name': 'Fresh cows', 'comment': 'Перевод после сортировки'},
        data_version='dv_demo',
        user_id=21,
        username='zootech',
        role=rbac.ROLE_ZOOTECH,
    )
    assert preview['ok'] is True
    assert preview['summary']['rows_valid'] == 2
    assert preview['summary']['rows_invalid'] == 0
    assert preview['preview_id'].startswith('batch_')

    committed = commit_animal_event_batch_use_case(
        conn=conn,
        tenant_id='default',
        preview=preview,
        permissions=rbac.ROLE_PERMISSIONS[rbac.ROLE_ZOOTECH],
        user_id=21,
        username='zootech',
        role=rbac.ROLE_ZOOTECH,
    )
    assert committed['ok'] is True
    assert committed['summary']['rows_applied'] == 2
    assert committed['summary']['rows_conflict'] == 0
    assert committed['summary']['rows_invalid'] == 0

    events_a301 = list_animal_events_for_animal(conn, tenant_id='default', animal_id='A-301', limit=10, offset=0)['events']
    assert len(events_a301) == 1
    payload = dict(events_a301[0]['payload'])
    assert events_a301[0]['event_type'] == 'pen_move'
    assert events_a301[0]['reason_code'] == 'PEN_PROTOCOL'
    assert payload['workflow_action'] == 'move_to_group'
    assert payload['to_pen_id'] == 'pen-7'
    assert payload['batch_preview_id'] == preview['preview_id']

    audit_actions = [
        row['action']
        for row in conn.execute(
            "SELECT action FROM audit_log WHERE action LIKE 'animal_event.batch_entry.%' ORDER BY id"
        ).fetchall()
    ]
    assert audit_actions == [
        'animal_event.batch_entry.preview',
        'animal_event.batch_entry.commit',
    ]



def test_t20_03_preview_shows_per_row_validation_and_commit_handles_partial_conflicts(conn: sqlite3.Connection) -> None:
    rows = _rows()
    preview = preview_animal_event_batch_use_case(
        conn=conn,
        tenant_id='default',
        animal_rows=[rows[0], rows[0], rows[1], rows[2]],
        action='schedule_follow_up',
        event_ts='2026-03-31T13:00:00+00:00',
        permissions=rbac.ROLE_PERMISSIONS[rbac.ROLE_OPERATOR],
        params={'due_date': '2026-04-02', 'assignee_role': rbac.ROLE_OPERATOR, 'follow_up_kind': 'preg_check_follow_up'},
        data_version='dv_demo',
        user_id=22,
        username='operator',
        role=rbac.ROLE_OPERATOR,
    )
    assert preview['summary']['rows_total'] == 4
    assert preview['summary']['rows_valid'] == 3
    assert preview['summary']['rows_invalid'] == 1
    invalid_rows = [row for row in preview['rows'] if row['status'] == 'invalid']
    assert len(invalid_rows) == 1
    assert 'продублировано' in invalid_rows[0]['message'].lower()

    # Simulate a conflict between preview and commit for A-302 by committing the same row first.
    preview_conflict = preview_animal_event_batch_use_case(
        conn=conn,
        tenant_id='default',
        animal_rows=[rows[1]],
        action='schedule_follow_up',
        event_ts='2026-03-31T13:00:00+00:00',
        permissions=rbac.ROLE_PERMISSIONS[rbac.ROLE_OPERATOR],
        params={'due_date': '2026-04-02', 'assignee_role': rbac.ROLE_OPERATOR, 'follow_up_kind': 'preg_check_follow_up'},
        data_version='dv_demo',
        user_id=22,
        username='operator',
        role=rbac.ROLE_OPERATOR,
    )
    commit_animal_event_batch_use_case(
        conn=conn,
        tenant_id='default',
        preview=preview_conflict,
        permissions=rbac.ROLE_PERMISSIONS[rbac.ROLE_OPERATOR],
        user_id=22,
        username='operator',
        role=rbac.ROLE_OPERATOR,
    )

    committed = commit_animal_event_batch_use_case(
        conn=conn,
        tenant_id='default',
        preview=preview,
        permissions=rbac.ROLE_PERMISSIONS[rbac.ROLE_OPERATOR],
        user_id=22,
        username='operator',
        role=rbac.ROLE_OPERATOR,
    )
    assert committed['summary']['rows_applied'] == 2
    assert committed['summary']['rows_conflict'] >= 1
    assert committed['summary']['rows_invalid'] == 1
    conflict_rows = [row for row in committed['results'] if row['status'] == 'conflict']
    assert conflict_rows
    assert 'уже записано' in conflict_rows[0]['message'].lower()



def test_t20_03_batch_requires_permissions_and_preview_digest(conn: sqlite3.Connection) -> None:
    with pytest.raises(PermissionDenied):
        preview_animal_event_batch_use_case(
            conn=conn,
            tenant_id='default',
            animal_rows=_rows()[:1],
            action='close_status',
            event_ts='2026-03-31T14:00:00+00:00',
            permissions=rbac.ROLE_PERMISSIONS[rbac.ROLE_VIEWER],
            params={'status_code': 'HEAT_OPEN'},
            user_id=23,
            username='viewer',
            role=rbac.ROLE_VIEWER,
        )

    preview = preview_animal_event_batch_use_case(
        conn=conn,
        tenant_id='default',
        animal_rows=_rows()[:1],
        action='close_status',
        event_ts='2026-03-31T14:00:00+00:00',
        permissions=rbac.ROLE_PERMISSIONS[rbac.ROLE_VET],
        params={'status_code': 'HEAT_OPEN'},
        user_id=24,
        username='vet',
        role=rbac.ROLE_VET,
    )
    broken = dict(preview)
    broken['digest'] = 'broken'
    with pytest.raises(AnimalEventBatchEntryError) as exc:
        commit_animal_event_batch_use_case(
            conn=conn,
            tenant_id='default',
            preview=broken,
            permissions=rbac.ROLE_PERMISSIONS[rbac.ROLE_VET],
            user_id=24,
            username='vet',
            role=rbac.ROLE_VET,
        )
    assert exc.value.code == 'preview_digest_mismatch'
    assert 'устарел' in exc.value.message.lower() or 'пересоберите' in exc.value.message.lower()



def test_t20_03_docs_page_and_policy_are_wired() -> None:
    doc = Path('docs/batch_entry_workflows.md').read_text(encoding='utf-8')
    page = Path('streamlit_app/pages/14_Group_Profile.py').read_text(encoding='utf-8')
    policy = Path('src/core/security/policy.py').read_text(encoding='utf-8')
    assumptions = Path('docs/assumptions.md').read_text(encoding='utf-8')
    catalog = animal_event_batch_entry_catalog()

    assert any(item['action'] == 'move_to_group' for item in catalog['actions'])
    assert 'dry-run preview' in doc.lower()
    assert 'preview_animal_event_batch_use_case' in page
    assert 'commit_animal_event_batch_use_case' in page
    assert 'Batch entry / dry-run preview' in page
    assert 'animal_events.close' in policy
    assert 'batch entry workflows' in assumptions.lower()
