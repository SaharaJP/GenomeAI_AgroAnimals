from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

from core.health import (
    batch_complete_vet_triage_worklists_use_case,
    build_vet_triage_snapshot,
    bulk_comment_vet_triage_animals_use_case,
    materialize_vet_triage_worklists_use_case,
)
from core.infra.web_db import init_db
from streamlit_app.vet_triage_queues import build_vet_triage_table, load_vet_triage_snapshot


def _wcsv(path: Path, rows: list[dict]) -> None:
    pd.DataFrame(rows).to_csv(path, index=False)


def triage_input_dir(tmp_path: Path) -> Path:
    input_dir = tmp_path / 'input'
    input_dir.mkdir(parents=True, exist_ok=True)
    _wcsv(input_dir / 'dm_animals.csv', [
        {'tenant_id': 'default', 'animal_id': 'A1', 'farm_id': 'F1', 'status': 'active'},
        {'tenant_id': 'default', 'animal_id': 'A2', 'farm_id': 'F1', 'status': 'active'},
        {'tenant_id': 'default', 'animal_id': 'A3', 'farm_id': 'F1', 'status': 'active'},
        {'tenant_id': 'default', 'animal_id': 'A4', 'farm_id': 'F1', 'status': 'active'},
    ])
    _wcsv(input_dir / 'dm_lactations.csv', [
        {'animal_id': 'A1', 'farm_id': 'F1', 'lactation_id': 'L1', 'calving_date': '2026-03-30', 'parity': 2},
        {'animal_id': 'A2', 'farm_id': 'F1', 'lactation_id': 'L2', 'calving_date': '2026-01-10', 'parity': 3},
    ])
    _wcsv(input_dir / 'dm_health_events.csv', [
        {'animal_id': 'A1', 'farm_id': 'F1', 'lactation_id': 'L1', 'event_id': 'HE1', 'event_date': '2026-04-01', 'event_type': 'mastitis', 'condition_code': 'mastitis', 'severity': 'high', 'notes': 'acute case'},
        {'animal_id': 'A2', 'farm_id': 'F1', 'lactation_id': 'L2', 'event_id': 'HE2', 'event_date': '2026-03-25', 'event_type': 'lameness', 'condition_code': 'lameness', 'severity': 'medium', 'notes': 'rear leg'},
        {'animal_id': 'A2', 'farm_id': 'F1', 'lactation_id': 'L2', 'event_id': 'HE3', 'event_date': '2026-03-10', 'event_type': 'lameness', 'condition_code': 'lameness', 'severity': 'medium', 'notes': 'repeat'},
        {'animal_id': 'A2', 'farm_id': 'F1', 'lactation_id': 'L2', 'event_id': 'HE4', 'event_date': '2026-02-15', 'event_type': 'ketosis', 'condition_code': 'ketosis', 'severity': 'low', 'notes': 'history'},
        {'animal_id': 'A3', 'farm_id': 'F1', 'lactation_id': 'L3', 'event_id': 'HE5', 'event_date': '2026-03-28', 'event_type': 'metritis', 'condition_code': 'metritis', 'severity': 'high', 'notes': 'post calving'},
    ])
    _wcsv(input_dir / 'dm_treatments.csv', [
        {'treatment_id': 'TR1', 'animal_id': 'A3', 'start_date': '2026-03-28', 'end_date': '', 'treatment_type': 'antibiotic', 'drug_name': 'ABX', 'follow_up_due_at': '2026-04-02'},
    ])
    # pen assignments via moves/pens
    _wcsv(input_dir / 'dm_pens.csv', [
        {'tenant_id': 'default', 'farm_id': 'F1', 'pen_id': 'P1', 'pen_name': 'Hospital pen', 'site_id': 'S1', 'site_name': 'Main'},
    ])
    _wcsv(input_dir / 'dm_pen_moves.csv', [
        {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A1', 'move_id': 'M1', 'move_date': '2026-03-30', 'to_pen_id': 'P1'},
        {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A2', 'move_id': 'M2', 'move_date': '2026-03-30', 'to_pen_id': 'P1'},
        {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A3', 'move_id': 'M3', 'move_date': '2026-03-30', 'to_pen_id': 'P1'},
        {'tenant_id': 'default', 'farm_id': 'F1', 'animal_id': 'A4', 'move_id': 'M4', 'move_date': '2026-03-30', 'to_pen_id': 'P1'},
    ])
    return input_dir


def test_t23_03_builds_prioritized_vet_triage_snapshot(tmp_path: Path) -> None:
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    init_db(conn)
    input_dir = triage_input_dir(tmp_path)
    conn.execute("INSERT INTO alerts_v2(alert_id, tenant_id, created_at, updated_at, alert_type, title, source, cause, confidence, object_type, object_id, status, attachments_json, why_json, what_to_do_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
        'AL1', 'default', '2026-04-02T00:00:00+00:00', '2026-04-02T00:00:00+00:00', 'health.mastitis_risk', 'Mastitis risk', 'rules', 'risk', 0.92, 'animal', 'A1', 'new', '[]', '{}', '[]'
    ))
    conn.commit()
    snap = build_vet_triage_snapshot(input_dir=input_dir, conn=conn, tenant_id='default', asof_date=date(2026, 4, 2), limit=50)
    qtypes = {row['queue_type'] for row in snap['items']}
    assert {'mastitis', 'lameness', 'metritis', 'fresh_cows', 'chronic_review'}.issubset(qtypes)
    mastitis = next(r for r in snap['items'] if r['queue_type'] == 'mastitis')
    assert mastitis['animal_id'] == 'A1'
    assert mastitis['related_alert'] == 'AL1'
    assert mastitis['priority'] == 1
    assert float(mastitis['confidence']) >= 0.9
    assert {'animal_id', 'queue', 'severity', 'next_action'}.issubset(set(build_vet_triage_table(snap['items']).columns))
    helper = load_vet_triage_snapshot(input_dir=input_dir, conn=conn, tenant_id='default', asof_date=date(2026, 4, 2), limit=50)
    assert helper['summary']['total'] == snap['summary']['total']


def test_t23_03_materialize_and_complete_and_bulk_comment(tmp_path: Path) -> None:
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    init_db(conn)
    input_dir = triage_input_dir(tmp_path)
    snap = build_vet_triage_snapshot(input_dir=input_dir, conn=conn, tenant_id='default', asof_date=date(2026, 4, 2), queue_types=['mastitis', 'fresh_cows'], limit=50)
    selected = snap['items'][:2]
    res = materialize_vet_triage_worklists_use_case(conn=conn, tenant_id='default', rows=selected, user_id=1, username='vet', role='Vet', data_version='dv1', request_id='rq1')
    assert res['summary']['created_n'] == 2
    res2 = materialize_vet_triage_worklists_use_case(conn=conn, tenant_id='default', rows=selected, user_id=1, username='vet', role='Vet', data_version='dv1', request_id='rq2')
    assert res2['summary']['existing_n'] == 2
    comp = batch_complete_vet_triage_worklists_use_case(conn=conn, tenant_id='default', worklist_ids=res['created_worklist_ids'], user_id=1, username='vet', role='Vet', outcome_status='done', reason_code='DONE_OTHER', comment='ok', request_id='rq3')
    assert comp['summary']['completed_n'] == 2
    notes = bulk_comment_vet_triage_animals_use_case(conn=conn, tenant_id='default', animal_ids=['A1', 'A2'], user_id=1, username='vet', role='Vet', comment='seen', data_version='dv1', request_id='rq4')
    assert notes['summary']['created_n'] == 2
