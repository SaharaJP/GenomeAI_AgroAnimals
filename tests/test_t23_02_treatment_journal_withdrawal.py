from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from core.health import (
    build_treatment_journal_snapshot,
    complete_treatment_course_use_case,
    get_treatment_course,
    start_treatment_course_use_case,
)
from streamlit_app.treatment_journal_withdrawal import (
    build_active_withdrawals_table,
    build_treatment_journal_table,
    load_treatment_journal_snapshot,
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
def treatment_input_dir(tmp_path: Path) -> Path:
    base = tmp_path / 'input'
    base.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {'tenant_id': 'default', 'farm_id': 'F1', 'site_id': 'S1', 'animal_id': 'A1', 'status': 'active', 'current_pen_id': 'P1'},
        {'tenant_id': 'default', 'farm_id': 'F1', 'site_id': 'S1', 'animal_id': 'A2', 'status': 'active', 'current_pen_id': 'P1'},
        {'tenant_id': 'default', 'farm_id': 'F2', 'site_id': 'S2', 'animal_id': 'A3', 'status': 'active', 'current_pen_id': 'P2'},
    ]).to_csv(base / 'dm_animals.csv', index=False)
    pd.DataFrame([
        {'tenant_id': 'default', 'pen_id': 'P1', 'pen_name': 'Hospital-1'},
        {'tenant_id': 'default', 'pen_id': 'P2', 'pen_name': 'Hospital-2'},
    ]).to_csv(base / 'dm_pens.csv', index=False)
    pd.DataFrame(columns=['tenant_id', 'animal_id', 'to_pen_id', 'move_date']).to_csv(base / 'dm_pen_moves.csv', index=False)
    pd.DataFrame([
        {'tenant_id': 'default', 'treatment_id': 'TR-L1', 'animal_id': 'A1', 'start_date': '2026-03-28', 'end_date': '2026-03-30', 'treatment_type': 'antibiotic', 'drug_name': 'ABX', 'withdrawal_end_date': ''},
        {'tenant_id': 'default', 'treatment_id': 'TR-L2', 'animal_id': 'A3', 'start_date': '2026-03-20', 'end_date': '2026-03-21', 'treatment_type': 'vitamin', 'drug_name': 'VIT', 'withdrawal_end_date': ''},
    ]).to_csv(base / 'dm_treatments.csv', index=False)
    return base


def test_t23_02_init_db_adds_treatment_journal_storage(conn: sqlite3.Connection) -> None:
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert 'treatment_journal_v1' in tables
    cols = {row[1] for row in conn.execute("PRAGMA table_info(treatment_journal_v1)").fetchall()}
    assert {
        'course_id', 'course_status', 'animal_id', 'treatment_type', 'start_date',
        'follow_up_due_at', 'withdrawal_end_date_calc', 'withdrawal_end_date_effective',
        'linked_alert_id', 'linked_health_event_id', 'linked_protocol_execution_id', 'linked_worklist_id',
    }.issubset(cols)
    conn.execute(
        "INSERT INTO treatment_journal_v1(course_id, tenant_id, created_at, updated_at, course_status, animal_id, treatment_type, start_date, follow_up_status, source_versions_json, metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ('tc1', 'default', '2026-04-01T00:00:00+00:00', '2026-04-01T00:00:00+00:00', 'active', 'A1', 'antibiotic', '2026-04-01', 'none', '{}', '{}'),
    )
    conn.commit()
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("DELETE FROM treatment_journal_v1 WHERE course_id='tc1'")


def test_t23_02_start_and_complete_treatment_course_with_withdrawal(conn: sqlite3.Connection) -> None:
    started = start_treatment_course_use_case(
        conn=conn,
        tenant_id='default',
        user_id=10,
        username='vet',
        role='Vet',
        animal_id='A2',
        treatment_type='antibiotic',
        start_date='2026-04-01',
        drug_name='ABX-2',
        follow_up_due_at='2026-04-03',
        linked_alert_id='AL-1',
        data_version='dv_t23_02',
        request_id='REQ-TX-START',
    )
    assert started['course_status'] == 'active'
    assert started['withdrawal_rule_version'] == '1'
    assert started['withdrawal_end_date_calc'] == '2026-04-11'
    assert started['withdrawal_end_date_effective'] == '2026-04-11'
    assert started['follow_up_status'] == 'due'

    completed = complete_treatment_course_use_case(
        conn=conn,
        tenant_id='default',
        course_id=str(started['course_id']),
        user_id=10,
        username='vet',
        role='Vet',
        end_date='2026-04-02',
        follow_up_due_at='2026-04-05',
        follow_up_comment='check milk tank exclusion',
        data_version='dv_t23_02',
        request_id='REQ-TX-COMPLETE',
    )
    assert completed['course_status'] == 'completed'
    assert completed['end_date'] == '2026-04-02'
    assert completed['withdrawal_end_date_effective'] == '2026-04-12'
    stored = get_treatment_course(conn, tenant_id='default', course_id=str(started['course_id']))
    assert stored is not None
    assert stored['follow_up_due_at'] == '2026-04-05'


def test_t23_02_snapshot_merges_runtime_and_legacy_and_aggregates_withdrawal(conn: sqlite3.Connection, treatment_input_dir: Path) -> None:
    start_treatment_course_use_case(
        conn=conn,
        tenant_id='default',
        user_id=10,
        username='vet',
        role='Vet',
        animal_id='A2',
        treatment_type='antibiotic',
        start_date='2026-04-01',
        drug_name='ABX-2',
        follow_up_due_at='2026-04-03',
        data_version='dv_t23_02',
    )
    conn.execute(
        "INSERT INTO alerts_v2(alert_id, tenant_id, created_at, updated_at, alert_type, title, source, cause, confidence, object_type, object_id, status, attachments_json, why_json, what_to_do_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ('AL-WD-1', 'default', '2026-04-01T00:00:00+00:00', '2026-04-01T00:00:00+00:00', 'health.withdrawal_active', 'Withdrawal active', 'rules', 'wd', 0.9, 'animal', 'A1', 'new', '[]', '{}', '[]'),
    )
    conn.commit()

    snapshot = build_treatment_journal_snapshot(
        input_dir=treatment_input_dir,
        conn=conn,
        tenant_id='default',
        asof_date=date(2026, 4, 1),
        limit=50,
    )
    assert snapshot['summary']['runtime_n'] >= 1
    assert snapshot['summary']['legacy_n'] >= 2
    assert snapshot['summary']['active_withdrawals_n'] >= 2
    assert any(str(x.get('animal_id')) == 'A1' for x in snapshot['active_by_animal'])
    assert any(str(x.get('group')) == 'Hospital-1' for x in snapshot['active_by_group'])
    assert any(str(x.get('farm_id')) == 'F1' for x in snapshot['active_by_farm'])
    a1 = next(x for x in snapshot['items'] if str(x.get('animal_id')) == 'A1')
    assert 'AL-WD-1' in list(a1.get('alert_ids') or [])

    helper = load_treatment_journal_snapshot(
        input_dir=treatment_input_dir,
        conn=conn,
        tenant_id='default',
        asof_date=date(2026, 4, 1),
        limit=50,
    )
    assert helper['summary']['active_withdrawals_n'] == snapshot['summary']['active_withdrawals_n']
    assert {'course_id', 'withdrawal_until', 'withdrawal_active'}.issubset(set(build_treatment_journal_table(helper['items']).columns))
    assert {'animal_id', 'group', 'until'}.issubset(set(build_active_withdrawals_table(helper['active_by_animal']).columns))
