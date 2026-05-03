from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.infra.web_db import init_db
from core.operational import (
    AnimalEventQuickEntryError,
    add_animal_event_comment_use_case,
    close_animal_event_episode_use_case,
    confirm_animal_event_use_case,
    create_animal_event_use_case,
    list_recent_animal_events_use_case,
)
import core.security as rbac


@pytest.fixture()
def conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def test_t20_02_create_confirm_close_comment_use_cases_append_history_and_audit(conn: sqlite3.Connection) -> None:
    created = create_animal_event_use_case(
        conn=conn,
        tenant_id='default',
        animal_id='A-200',
        farm_id='farm-1',
        site_id='site-1',
        event_type='heat',
        event_ts='2026-03-31T08:15:00+00:00',
        reason_code='HEAT_OBSERVED',
        comment='Замечена охота в группе 4',
        data_version='dv_demo',
        request_id='req-1',
        user_id=11,
        username='zootech',
        role=rbac.ROLE_ZOOTECH,
    )
    assert created['ok'] is True
    source_event_id = str(created['event_id'])

    confirmed = confirm_animal_event_use_case(
        conn=conn,
        tenant_id='default',
        target_event_id=source_event_id,
        event_ts='2026-03-31T09:00:00+00:00',
        comment='Подтверждено оператором секции',
        data_version='dv_demo',
        request_id='req-2',
        user_id=12,
        username='operator',
        role=rbac.ROLE_OPERATOR,
    )
    assert confirmed['ok'] is True
    assert confirmed['after']['linked_object_id'] == source_event_id
    assert confirmed['after']['payload']['workflow_action'] == 'confirm_event'

    closed = close_animal_event_episode_use_case(
        conn=conn,
        tenant_id='default',
        target_event_id=source_event_id,
        event_ts='2026-03-31T10:30:00+00:00',
        comment='Эпизод закрыт после осмотра',
        data_version='dv_demo',
        request_id='req-3',
        user_id=13,
        username='vet',
        role=rbac.ROLE_VET,
    )
    assert closed['ok'] is True
    assert closed['after']['payload']['workflow_action'] == 'close_episode'

    comment = add_animal_event_comment_use_case(
        conn=conn,
        tenant_id='default',
        animal_id='A-200',
        target_event_id=source_event_id,
        event_ts='2026-03-31T11:00:00+00:00',
        comment='Животное спокойно, дополнительных замечаний нет.',
        data_version='dv_demo',
        request_id='req-4',
        user_id=11,
        username='zootech',
        role=rbac.ROLE_ZOOTECH,
    )
    assert comment['ok'] is True

    rows = list_recent_animal_events_use_case(conn=conn, tenant_id='default', animal_id='A-200', limit=10)
    assert len(rows) == 4
    assert {row['event_id'] for row in rows} >= {source_event_id, confirmed['event_id'], closed['event_id'], comment['event_id']}

    actions = {
        row['action']
        for row in conn.execute(
            "SELECT action FROM audit_log WHERE action LIKE 'animal_event.quick_entry.%' ORDER BY id"
        ).fetchall()
    }
    assert actions == {
        'animal_event.quick_entry.create',
        'animal_event.quick_entry.confirm',
        'animal_event.quick_entry.close_episode',
        'animal_event.quick_entry.comment',
    }


def test_t20_02_use_cases_raise_human_readable_errors(conn: sqlite3.Connection) -> None:
    with pytest.raises(AnimalEventQuickEntryError) as exc:
        create_animal_event_use_case(
            conn=conn,
            tenant_id='default',
            animal_id='A-201',
            event_type='manual_note',
            event_ts='2026-03-31T08:15:00+00:00',
            comment='',
            user_id=1,
            username='operator',
            role=rbac.ROLE_OPERATOR,
        )
    assert exc.value.code == 'comment_required'
    assert 'обязателен' in exc.value.message.lower()

    created = create_animal_event_use_case(
        conn=conn,
        tenant_id='default',
        animal_id='A-201',
        event_type='heat',
        event_ts='2026-03-31T08:15:00+00:00',
        reason_code='HEAT_OBSERVED',
        user_id=1,
        username='operator',
        role=rbac.ROLE_OPERATOR,
    )
    confirm_animal_event_use_case(
        conn=conn,
        tenant_id='default',
        target_event_id=str(created['event_id']),
        event_ts='2026-03-31T08:30:00+00:00',
        user_id=1,
        username='operator',
        role=rbac.ROLE_OPERATOR,
    )
    with pytest.raises(AnimalEventQuickEntryError) as exc2:
        confirm_animal_event_use_case(
            conn=conn,
            tenant_id='default',
            target_event_id=str(created['event_id']),
            event_ts='2026-03-31T08:45:00+00:00',
            user_id=1,
            username='operator',
            role=rbac.ROLE_OPERATOR,
        )
    assert exc2.value.code == 'event_already_confirmed'
    assert 'уже подтверждено' in exc2.value.message.lower()



def test_t20_02_docs_rbac_and_streamlit_page_are_wired() -> None:
    doc = Path('docs/animal_event_quick_entry.md').read_text(encoding='utf-8')
    page = Path('streamlit_app/pages/15_Animal_Profile.py').read_text(encoding='utf-8')
    policy = Path('src/core/security/policy.py').read_text(encoding='utf-8')

    assert 'append-only follow-up record' in Path('docs/assumptions.md').read_text(encoding='utf-8')
    assert 'Quick event entry' in page
    assert 'confirm_animal_event_use_case' in page
    assert 'close_animal_event_episode_use_case' in page
    assert 'PERM_ANIMAL_EVENTS_WRITE' in policy
    assert 'animal_events.write' in policy
    assert 'быстрый ввод событий' in doc.lower()
