from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from core.health import (
    build_vet_protocol_engine_snapshot,
    complete_vet_protocol_execution_use_case,
    get_vet_protocol_execution,
    record_vet_protocol_step_use_case,
    start_vet_protocol_execution_use_case,
)
from streamlit_app.vet_protocol_engine import (
    build_candidate_health_events_table,
    build_protocol_catalog_table,
    build_protocol_executions_table,
    build_protocol_steps_table,
    load_vet_protocol_engine_snapshot,
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


@pytest.fixture()
def protocol_input_dir(tmp_path: Path) -> Path:
    base = tmp_path / 'input'
    base.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {'tenant_id': 'default', 'farm_id': 'F1', 'site_id': 'S1', 'animal_id': 'A1', 'status': 'active', 'current_pen_id': 'P1'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'site_id': 'S1', 'animal_id': 'A2', 'status': 'active', 'current_pen_id': 'P1'},
        ]
    ).to_csv(base / 'dm_animals.csv', index=False)
    pd.DataFrame(
        [
            {'tenant_id': 'default', 'pen_id': 'P1', 'pen_name': 'Health pen'},
        ]
    ).to_csv(base / 'dm_pens.csv', index=False)
    pd.DataFrame(columns=['tenant_id', 'animal_id', 'to_pen_id', 'move_date']).to_csv(base / 'dm_pen_moves.csv', index=False)
    pd.DataFrame(
        [
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A1', 'event_id': 'HE1', 'event_type': 'mastitis', 'event_date': '2026-04-01', 'severity': 'high', 'notes': 'fresh case'},
            {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A2', 'event_id': 'HE2', 'event_type': 'lameness', 'event_date': '2026-04-02', 'severity': 'medium', 'notes': 'rear leg'},
        ]
    ).to_csv(base / 'dm_health_events.csv', index=False)
    return base


def test_t23_01_init_db_adds_vet_protocol_execution_storage(conn: sqlite3.Connection) -> None:
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert 'vet_protocol_executions_v1' in tables

    cols = {row[1] for row in conn.execute("PRAGMA table_info(vet_protocol_executions_v1)").fetchall()}
    assert {
        'execution_id', 'protocol_key', 'protocol_version', 'protocol_title', 'status',
        'animal_id', 'linked_alert_id', 'linked_health_event_id', 'linked_worklist_id',
        'steps_json', 'linked_treatments_json', 'linked_observations_json', 'source_versions_json', 'metrics_json',
    }.issubset(cols)

    conn.execute(
        "INSERT INTO vet_protocol_executions_v1(execution_id, tenant_id, created_at, updated_at, protocol_key, protocol_version, protocol_title, status, steps_json, linked_treatments_json, linked_observations_json, source_versions_json, metrics_json, metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ('vpe1', 'default', '2026-04-01T00:00:00+00:00', '2026-04-01T00:00:00+00:00', 'mastitis_follow_up', 1, 'Mastitis', 'open', '[]', '[]', '[]', '{}', '{}', '{}'),
    )
    conn.commit()
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("DELETE FROM vet_protocol_executions_v1 WHERE execution_id='vpe1'")


def test_t23_01_start_protocol_creates_linked_worklist_and_versioned_execution(conn: sqlite3.Connection, protocol_input_dir: Path) -> None:
    res = start_vet_protocol_execution_use_case(
        conn=conn,
        tenant_id='default',
        project_root=Path.cwd(),
        protocol_key='mastitis_follow_up',
        animal_id='A1',
        user_id=22,
        username='vet',
        role='Vet',
        start_date='2026-04-03',
        farm_id='F1',
        site_id='S1',
        linked_alert_id='AL-1',
        linked_health_event_id='HE1',
        create_worklist_if_missing=True,
        data_version='dv_t23_01',
        request_id='REQ-VET-START',
    )
    assert res['deduped'] is False
    execution_id = str(res['execution_id'])
    stored = get_vet_protocol_execution(conn, tenant_id='default', execution_id=execution_id)
    assert stored is not None
    assert stored['protocol_key'] == 'mastitis_follow_up'
    assert stored['catalog_version']
    assert stored['linked_alert_id'] == 'AL-1'
    assert stored['linked_health_event_id'] == 'HE1'
    assert stored['linked_worklist_id']
    assert stored['status'] == 'open'
    assert len(stored['steps']) == 4
    assert stored['steps'][0]['status'] == 'pending'
    assert stored['source_versions']['data_version'] == 'dv_t23_01'

    res2 = start_vet_protocol_execution_use_case(
        conn=conn,
        tenant_id='default',
        project_root=Path.cwd(),
        protocol_key='mastitis_follow_up',
        animal_id='A1',
        user_id=22,
        username='vet',
        role='Vet',
        start_date='2026-04-03',
        linked_health_event_id='HE1',
        create_worklist_if_missing=True,
    )
    assert res2['deduped'] is True
    assert str(res2['execution_id']) == execution_id


def test_t23_01_step_execution_is_role_aware_and_creates_observation_event(conn: sqlite3.Connection) -> None:
    res = start_vet_protocol_execution_use_case(
        conn=conn,
        tenant_id='default',
        project_root=Path.cwd(),
        protocol_key='mastitis_follow_up',
        animal_id='A1',
        user_id=22,
        username='vet',
        role='Vet',
        start_date='2026-04-03',
        create_worklist_if_missing=False,
        data_version='dv_t23_01',
    )
    execution_id = str(res['execution_id'])

    step1 = record_vet_protocol_step_use_case(
        conn=conn,
        tenant_id='default',
        execution_id=execution_id,
        step_key='udder_observation',
        user_id=11,
        username='operator',
        role='Operator',
        step_status='done',
        completed_at='2026-04-03T08:00:00+00:00',
        comment='Observation captured',
        create_observation_event=True,
        data_version='dv_t23_01',
        request_id='REQ-VET-STEP1',
    )
    assert step1['observation_event_id']
    after1 = step1['after']
    assert after1['status'] == 'in_progress'
    assert after1['linked_observations']

    with pytest.raises(Exception):
        record_vet_protocol_step_use_case(
            conn=conn,
            tenant_id='default',
            execution_id=execution_id,
            step_key='link_treatment',
            user_id=11,
            username='operator',
            role='Operator',
            step_status='done',
            linked_treatment_id='TR-1',
        )

    step2 = record_vet_protocol_step_use_case(
        conn=conn,
        tenant_id='default',
        execution_id=execution_id,
        step_key='link_treatment',
        user_id=22,
        username='vet',
        role='Vet',
        step_status='done',
        completed_at='2026-04-03T08:30:00+00:00',
        linked_treatment_id='TR-1',
    )
    assert 'TR-1' in step2['after']['linked_treatments']


def test_t23_01_complete_protocol_closes_linked_worklist_and_snapshot_helpers(conn: sqlite3.Connection, protocol_input_dir: Path) -> None:
    res = start_vet_protocol_execution_use_case(
        conn=conn,
        tenant_id='default',
        project_root=Path.cwd(),
        protocol_key='mastitis_follow_up',
        animal_id='A1',
        user_id=22,
        username='vet',
        role='Vet',
        start_date='2026-04-03',
        linked_health_event_id='HE1',
        create_worklist_if_missing=True,
        data_version='dv_t23_01',
    )
    execution_id = str(res['execution_id'])

    for step_key in ('udder_observation', 'withdrawal_check', 'recheck_milk'):
        record_vet_protocol_step_use_case(
            conn=conn,
            tenant_id='default',
            execution_id=execution_id,
            step_key=step_key,
            user_id=22,
            username='vet',
            role='Vet',
            step_status='done',
            completed_at='2026-04-04T08:00:00+00:00',
            comment=f'done:{step_key}',
            create_observation_event=(step_key == 'udder_observation'),
        )

    done = complete_vet_protocol_execution_use_case(
        conn=conn,
        tenant_id='default',
        execution_id=execution_id,
        user_id=22,
        username='vet',
        role='Vet',
        comment='Protocol complete',
        close_linked_worklist=True,
        request_id='REQ-VET-COMPLETE',
    )
    after = done['after']
    assert after['status'] == 'completed'
    assert after['completed_by_username'] == 'vet'
    assert done['auto'] is not None
    assert done['auto']['after']['latest_outcome_status'] == 'done'

    snapshot = build_vet_protocol_engine_snapshot(
        project_root=Path.cwd(),
        input_dir=protocol_input_dir,
        conn=conn,
        tenant_id='default',
        asof_date=date(2026, 4, 5),
        animal_id='A1',
        limit=50,
    )
    assert snapshot['summary']['total_executions'] >= 1
    assert snapshot['candidate_health_events']

    loaded = load_vet_protocol_engine_snapshot(
        project_root=Path.cwd(),
        input_dir=protocol_input_dir,
        conn=conn,
        tenant_id='default',
        asof_date=date(2026, 4, 5),
        animal_id='A1',
        limit=50,
    )
    assert loaded['summary']['candidate_health_events_n'] >= 1
    assert {'protocol_key', 'steps_n'}.issubset(set(build_protocol_catalog_table(loaded['catalog']['protocols']).columns))
    assert {'execution_id', 'status', 'required_done'}.issubset(set(build_protocol_executions_table(loaded['executions']).columns))
    selected = next(x for x in loaded['executions'] if str(x['execution_id']) == execution_id)
    assert {'step_key', 'status', 'linked_treatment_id'}.issubset(set(build_protocol_steps_table(selected['steps']).columns))
    assert {'event_id', 'animal_id', 'event_type'}.issubset(set(build_candidate_health_events_table(loaded['candidate_health_events']).columns))
