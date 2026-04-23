
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from core.health import (
    approve_drug_use_use_case,
    build_drug_use_compliance_snapshot,
    execute_drug_use_use_case,
    record_drug_prescription_use_case,
    start_treatment_course_use_case,
)
from streamlit_app.drug_use_compliance import (
    build_drug_use_aggregate_table,
    build_drug_use_course_table,
    build_drug_use_history_table,
    load_drug_use_compliance_snapshot,
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
def drug_input_dir(tmp_path: Path) -> Path:
    base = tmp_path / 'input'
    base.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {'tenant_id': 'default', 'animal_id': 'A1', 'farm_id': 'F1', 'site_id': 'S1', 'status': 'active', 'current_pen_id': 'P1'},
        {'tenant_id': 'default', 'animal_id': 'A2', 'farm_id': 'F1', 'site_id': 'S1', 'status': 'active', 'current_pen_id': 'P1'},
    ]).to_csv(base / 'dm_animals.csv', index=False)
    pd.DataFrame([
        {'tenant_id': 'default', 'farm_id': 'F1', 'site_id': 'S1', 'pen_id': 'P1', 'pen_name': 'Hospital pen'},
    ]).to_csv(base / 'dm_pens.csv', index=False)
    pd.DataFrame([
        {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A1', 'move_id': 'M1', 'move_date': '2026-04-01', 'to_pen_id': 'P1'},
        {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A2', 'move_id': 'M2', 'move_date': '2026-04-01', 'to_pen_id': 'P1'},
    ]).to_csv(base / 'dm_pen_moves.csv', index=False)
    return base


def test_t23_04_init_db_adds_append_only_drug_use_table(conn: sqlite3.Connection) -> None:
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert 'drug_use_compliance_v1' in tables
    cols = {row[1] for row in conn.execute("PRAGMA table_info(drug_use_compliance_v1)").fetchall()}
    assert {'entry_id', 'course_id', 'linked_object_type', 'linked_object_id', 'approval_state', 'prescribed_by_username', 'approved_by_username', 'executed_by_username'}.issubset(cols)
    conn.execute(
        "INSERT INTO drug_use_compliance_v1(entry_id, tenant_id, created_at, event_at, course_id, animal_id, action_type, approval_state, source_versions_json, metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
        ('D1', 'default', '2026-04-01T00:00:00+00:00', '2026-04-01T00:00:00+00:00', 'TC-1', 'A1', 'prescribed', 'pending', '{}', '{}'),
    )
    conn.commit()
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("UPDATE drug_use_compliance_v1 SET approval_state='approved' WHERE entry_id='D1'")
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("DELETE FROM drug_use_compliance_v1 WHERE entry_id='D1'")


def test_t23_04_prescribe_approve_execute_trail_and_snapshot(conn: sqlite3.Connection, drug_input_dir: Path) -> None:
    course = start_treatment_course_use_case(
        conn=conn,
        tenant_id='default',
        user_id=10,
        username='vet',
        role='Vet',
        animal_id='A1',
        treatment_type='antibiotic',
        start_date='2026-04-01',
        drug_name='ABX',
        dose_value=10,
        dose_unit='ml',
        route='IM',
        linked_worklist_id='WL-1',
        linked_protocol_execution_id='VP-1',
        data_version='dv1',
    )
    prescribed = record_drug_prescription_use_case(
        conn,
        tenant_id='default',
        course_id=str(course['course_id']),
        user_id=10,
        username='vet',
        role='Vet',
        administration_date='2026-04-01',
        approval_required=True,
        protocol_reference='VP-1',
        reason_code='PROTOCOL_STEP',
        comment='start course',
        data_version='dv1',
        request_id='rq-prescribe',
    )
    assert prescribed['approval_state'] == 'pending'
    with pytest.raises(Exception):
        execute_drug_use_use_case(
            conn,
            tenant_id='default',
            course_id=str(course['course_id']),
            user_id=11,
            username='op',
            role='Operator',
            administration_date='2026-04-01',
            data_version='dv1',
        )
    approved = approve_drug_use_use_case(
        conn,
        tenant_id='default',
        course_id=str(course['course_id']),
        user_id=12,
        username='director',
        role='Director',
        comment='approved',
        data_version='dv1',
        request_id='rq-approve',
    )
    assert approved['approval_state'] == 'approved'
    executed = execute_drug_use_use_case(
        conn,
        tenant_id='default',
        course_id=str(course['course_id']),
        user_id=11,
        username='op',
        role='Operator',
        administration_date='2026-04-02',
        comment='done',
        data_version='dv1',
        request_id='rq-exec',
    )
    assert executed['action_type'] == 'executed'
    snap = build_drug_use_compliance_snapshot(input_dir=drug_input_dir, conn=conn, tenant_id='default', asof_date=date(2026, 4, 2), limit=50)
    assert snap['summary']['courses_n'] == 1
    course_row = snap['courses'][0]
    assert course_row['current_stage'] == 'executed'
    assert course_row['approval_state'] == 'approved'
    assert course_row['prescribed_by'] == 'vet'
    assert course_row['approved_by'] == 'director'
    assert course_row['executed_by'] == 'op'
    assert course_row['protocol_reference'] == 'VP-1'
    assert course_row['linked_worklist_id'] == 'WL-1'
    assert course_row['withdrawal_active_asof'] is True


def test_t23_04_snapshot_aggregates_and_helper_tables(conn: sqlite3.Connection, drug_input_dir: Path) -> None:
    for idx, aid in enumerate(['A1', 'A2'], start=1):
        course = start_treatment_course_use_case(
            conn=conn,
            tenant_id='default',
            user_id=10,
            username='vet',
            role='Vet',
            animal_id=aid,
            treatment_type='antibiotic',
            start_date='2026-04-01',
            drug_name=f'ABX-{idx}',
            data_version='dv1',
        )
        record_drug_prescription_use_case(conn, tenant_id='default', course_id=str(course['course_id']), user_id=10, username='vet', role='Vet', administration_date='2026-04-01', approval_required=True, data_version='dv1')
        if aid == 'A1':
            approve_drug_use_use_case(conn, tenant_id='default', course_id=str(course['course_id']), user_id=12, username='director', role='Director', data_version='dv1')
            execute_drug_use_use_case(conn, tenant_id='default', course_id=str(course['course_id']), user_id=10, username='vet', role='Vet', administration_date='2026-04-02', data_version='dv1')
    helper = load_drug_use_compliance_snapshot(input_dir=drug_input_dir, conn=conn, tenant_id='default', asof_date=date(2026, 4, 2), limit=50)
    assert helper['summary']['courses_n'] == 2
    assert helper['summary']['pending_approvals_n'] == 1
    assert helper['summary']['executed_n'] == 1
    assert {'course_id', 'animal_id', 'stage', 'approval', 'protocol_reference'}.issubset(set(build_drug_use_course_table(helper['courses']).columns))
    assert {'event_at', 'entry_id', 'action', 'approval', 'linked_object'}.issubset(set(build_drug_use_history_table(helper['history']).columns))
    assert {'animal_id', 'events', 'pending_approvals'}.issubset(set(build_drug_use_aggregate_table(helper['history_by_animal'], label_key='animal_id').columns))
