from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

from core.economics import build_action_economics_snapshot, record_action_economics_decision_use_case
from core.economics.cow_value_culling import create_culling_review_worklist_use_case, build_cow_value_snapshot
from core.infra.web_db import init_db


def _seed_input_dir(tmp_path: Path) -> Path:
    input_dir = tmp_path / 'input'
    input_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {'tenant_id': 'default', 'animal_id': 'A1001', 'farm_id': 'F1', 'site_id': 'S1', 'current_pen_id': 'P1', 'current_pen_name': 'Fresh', 'status': 'active', 'breed': 'Holstein', 'sex': 'F', 'birth_date': '2022-01-01'},
        {'tenant_id': 'default', 'animal_id': 'A1002', 'farm_id': 'F1', 'site_id': 'S1', 'current_pen_id': 'P2', 'current_pen_name': 'Hospital', 'status': 'active', 'breed': 'Holstein', 'sex': 'F', 'birth_date': '2021-01-01'},
    ]).to_csv(input_dir / 'dm_animals.csv', index=False)
    pd.DataFrame([
        {'tenant_id': 'default', 'animal_id': 'A1001', 'lactation_id': 'L1', 'parity': 2, 'calving_date': '2025-12-01', 'scc_cells_ml': 120000},
        {'tenant_id': 'default', 'animal_id': 'A1002', 'lactation_id': 'L2', 'parity': 5, 'calving_date': '2025-11-01', 'scc_cells_ml': 360000},
    ]).to_csv(input_dir / 'dm_lactations.csv', index=False)
    pd.DataFrame([
        {'tenant_id': 'default', 'animal_id': 'A1001', 'date': '2026-04-01', 'milk_kg': 31.0, 'scc_cells_ml': 120000},
        {'tenant_id': 'default', 'animal_id': 'A1002', 'date': '2026-04-01', 'milk_kg': 14.0, 'scc_cells_ml': 420000},
        {'tenant_id': 'default', 'animal_id': 'A1002', 'date': '2026-04-02', 'milk_kg': 15.0, 'scc_cells_ml': 430000},
    ]).to_csv(input_dir / 'dm_milkings_daily.csv', index=False)
    pd.DataFrame([
        {'tenant_id': 'default', 'event_id': 'HE1', 'animal_id': 'A1002', 'event_date': '2026-03-15', 'event_type': 'mastitis', 'severity': 'high'},
    ]).to_csv(input_dir / 'dm_health_events.csv', index=False)
    pd.DataFrame([
        {'tenant_id': 'default', 'treatment_id': 'TR1', 'animal_id': 'A1002', 'start_date': '2026-03-20', 'end_date': '2026-04-10', 'treatment_type': 'antibiotic'},
    ]).to_csv(input_dir / 'dm_treatments.csv', index=False)
    pd.DataFrame([
        {'tenant_id': 'default', 'repro_event_id': 'RE2', 'animal_id': 'A1002', 'event_date': '2026-03-12', 'event_type': 'preg_check', 'result': 'open'},
    ]).to_csv(input_dir / 'dm_repro_events.csv', index=False)
    return input_dir


def main() -> None:
    tmp = Path('/tmp/t27_03_smoke')
    if tmp.exists():
        import shutil
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    input_dir = _seed_input_dir(tmp)
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    init_db(conn)
    cow = build_cow_value_snapshot(input_dir=input_dir, asof_date=date(2026, 4, 2), animal_id='A1002', project_root=Path.cwd(), data_version='dv_t27_03')
    wl = create_culling_review_worklist_use_case(conn=conn, tenant_id='default', user_id=7, username='zootech', role='Zootech', snapshot=cow, request_id='req-smoke')
    task = dict(wl.get('worklist') or {})
    snap = build_action_economics_snapshot(input_dir=input_dir, asof_date=date(2026, 4, 2), worklist=task, project_root=Path.cwd())
    assert snap['schema'] == 'genomeai.economics_per_action.v1'
    assert snap['summary_metrics']['expected_gain_rub'] >= 0
    dec = record_action_economics_decision_use_case(conn=conn, tenant_id='default', user_id=7, username='zootech', role='Zootech', snapshot=snap, action='defer', reason='economics_review', comment='Need sign-off', request_id='req-smoke-decision')
    assert dec['decision_id']
    print('OK: economics per action smoke passed')


if __name__ == '__main__':
    main()
