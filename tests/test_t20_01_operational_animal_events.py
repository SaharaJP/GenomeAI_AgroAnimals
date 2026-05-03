from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.operational.animal_events import (
    append_animal_event,
    build_animal_event,
    get_animal_event,
    list_animal_events_for_animal,
    normalize_legacy_operational_event,
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


def test_t20_01_init_db_creates_append_only_animal_events_table(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(animal_events_v1)").fetchall()}
    assert {
        'event_id', 'tenant_id', 'animal_id', 'event_type', 'event_ts', 'event_date',
        'actor_type', 'source', 'reason_code', 'linked_decision_id', 'linked_task_id',
        'request_id', 'job_id', 'data_version', 'payload_json', 'schema_version',
    }.issubset(columns)

    trigger_names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='animal_events_v1'").fetchall()}
    assert {'trg_animal_events_v1_no_update', 'trg_animal_events_v1_no_delete'}.issubset(trigger_names)

    event_id = append_animal_event(
        conn,
        tenant_id='default',
        event={
            'animal_id': 'A-1',
            'event_type': 'manual_note',
            'event_ts': '2026-03-31T09:15:00+00:00',
            'actor_type': 'user',
            'actor_user_id': 7,
            'actor_username': 'operator',
            'source': 'manual_ui',
            'reason_code': 'MANUAL_NOTE_ADDED',
            'payload': {'text': 'daily note'},
            'request_id': 'REQ-AN-1',
        },
    )
    with pytest.raises(sqlite3.IntegrityError, match='append-only'):
        conn.execute("UPDATE animal_events_v1 SET source='system' WHERE event_id=?", (event_id,))
    with pytest.raises(sqlite3.IntegrityError, match='append-only'):
        conn.execute("DELETE FROM animal_events_v1 WHERE event_id=?", (event_id,))


def test_t20_01_append_and_list_preserve_linkage_versions_and_audit(conn: sqlite3.Connection) -> None:
    event_id = append_animal_event(
        conn,
        tenant_id='default',
        event={
            'animal_id': 'A-100',
            'farm_id': 'farm-1',
            'site_id': 'site-1',
            'lactation_id': 'L-100',
            'event_type': 'insemination',
            'event_ts': '2026-03-31T10:00:00+00:00',
            'actor_type': 'user',
            'actor_user_id': 11,
            'actor_username': 'repro',
            'source': 'manual_ui',
            'reason_code': 'INSEMINATION_PERFORMED',
            'linked_object_type': 'bull',
            'linked_object_id': 'BULL-7',
            'linked_decision_id': 'dec-1',
            'linked_task_id': 'task-1',
            'request_id': 'REQ-T20-1',
            'job_id': 'job-77',
            'data_version': 'dv_t20',
            'qc_run': 'qc_t20',
            'model_version': 'mdl_t20',
            'scoring_run': 'score_t20',
            'report_version': 'rp_t20',
            'payload': {'comment': 'first AI after heat'},
        },
        audit_role='Operator',
    )
    stored = get_animal_event(conn, tenant_id='default', event_id=event_id)
    assert stored is not None
    assert stored['animal_id'] == 'A-100'
    assert stored['linked_object_type'] == 'bull'
    assert stored['linked_object_id'] == 'BULL-7'
    assert stored['linked_task_id'] == 'task-1'
    assert stored['linked_decision_id'] == 'dec-1'
    assert stored['data_version'] == 'dv_t20'
    assert stored['qc_run'] == 'qc_t20'
    assert stored['model_version'] == 'mdl_t20'
    assert stored['scoring_run'] == 'score_t20'
    assert stored['report_version'] == 'rp_t20'
    assert stored['request_id'] == 'REQ-T20-1'
    assert stored['job_id'] == 'job-77'
    assert stored['payload']['comment'] == 'first AI after heat'

    listed = list_animal_events_for_animal(conn, tenant_id='default', animal_id='A-100', limit=10)
    assert listed['total'] == 1
    assert listed['events'][0]['event_id'] == event_id

    audit_row = conn.execute(
        "SELECT action, object_type, object_id, request_id, after_json FROM audit_log WHERE action='animal_event.append' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert audit_row is not None
    assert audit_row['object_type'] == 'animal_event'
    assert audit_row['object_id'] == event_id
    assert audit_row['request_id'] == 'REQ-T20-1'
    after = json.loads(audit_row['after_json'])
    assert after['linked_task_id'] == 'task-1'
    assert after['linked_decision_id'] == 'dec-1'
    assert after['data_version'] == 'dv_t20'


def test_t20_01_build_animal_event_validates_pairs_and_reason_codes() -> None:
    with pytest.raises(ValueError, match='linked_object_type and linked_object_id'):
        build_animal_event(
            {
                'animal_id': 'A-1',
                'event_type': 'pen_move',
                'event_ts': '2026-03-31T10:00:00+00:00',
                'source': 'manual_ui',
                'linked_object_type': 'pen',
            }
        )

    with pytest.raises(ValueError, match='unknown animal event reason_code'):
        build_animal_event(
            {
                'animal_id': 'A-1',
                'event_type': 'manual_note',
                'event_ts': '2026-03-31T10:00:00+00:00',
                'source': 'manual_ui',
                'reason_code': 'NOT_A_REAL_REASON',
            }
        )


@pytest.mark.parametrize(
    ('source_table', 'fixture_key', 'expected_type', 'linked_type', 'linked_id'),
    [
        ('dm_repro_events', 'repro', 'insemination', 'bull', 'BULL-77'),
        ('dm_treatments', 'treatment', 'treatment', 'health_event', 'HE_10'),
        ('dm_pen_moves', 'pen_move', 'pen_move', 'pen', 'PEN-2'),
    ],
)
def test_t20_01_normalizes_legacy_sources_without_breaking_existing_loaders(
    source_table: str,
    fixture_key: str,
    expected_type: str,
    linked_type: str,
    linked_id: str,
) -> None:
    fixture = json.loads(Path('tests/fixtures/animal_events_v1.json').read_text(encoding='utf-8'))
    evt = normalize_legacy_operational_event(source_table=source_table, row=fixture[fixture_key], tenant_id='default')
    assert evt.event_type == expected_type
    assert evt.animal_id == 'A-100'
    assert evt.linked_object_type == linked_type
    assert evt.linked_object_id == linked_id
    assert evt.source == 'migration'
