from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

from core.economics import (
    build_action_economics_snapshot,
    build_cow_value_snapshot,
    build_milk_quality_scc_snapshot,
    create_culling_review_worklist_use_case,
    create_milk_quality_followup_worklist_use_case,
    describe_action_economics_inputs_version,
    record_action_economics_decision_use_case,
)
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
        {'tenant_id': 'default', 'animal_id': 'A1001', 'date': '2026-04-03', 'milk_kg': 31.0, 'scc_cells_ml': 120000},
        {'tenant_id': 'default', 'animal_id': 'A1002', 'date': '2026-04-03', 'milk_kg': 23.0, 'scc_cells_ml': 420000},
        {'tenant_id': 'default', 'animal_id': 'A1002', 'date': '2026-04-02', 'milk_kg': 15.0, 'scc_cells_ml': 430000},
    ]).to_csv(input_dir / 'dm_milkings_daily.csv', index=False)
    pd.DataFrame([
        {'tenant_id': 'default', 'event_id': 'HE1', 'animal_id': 'A1002', 'event_date': '2026-03-20', 'event_type': 'mastitis', 'severity': 'high'},
    ]).to_csv(input_dir / 'dm_health_events.csv', index=False)
    pd.DataFrame([
        {'tenant_id': 'default', 'treatment_id': 'TR1', 'animal_id': 'A1002', 'start_date': '2026-03-21', 'end_date': '2026-04-10', 'treatment_type': 'antibiotic'},
    ]).to_csv(input_dir / 'dm_treatments.csv', index=False)
    pd.DataFrame([
        {'tenant_id': 'default', 'repro_event_id': 'RE1', 'animal_id': 'A1002', 'event_date': '2026-03-12', 'event_type': 'preg_check', 'result': 'open'},
    ]).to_csv(input_dir / 'dm_repro_events.csv', index=False)
    return input_dir


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def test_t27_03_builds_explainable_action_economics_for_culling_and_milk_quality(tmp_path: Path) -> None:
    input_dir = _seed_input_dir(tmp_path)
    conn = _conn()
    cow = build_cow_value_snapshot(input_dir=input_dir, asof_date=date(2026, 4, 3), animal_id='A1002', project_root=Path(__file__).resolve().parents[1], data_version='dv_t27_03')
    cull_wl = create_culling_review_worklist_use_case(conn=conn, tenant_id='default', user_id=7, username='zootech', role='Zootech', snapshot=cow, request_id='req-cull')
    cull_snap = build_action_economics_snapshot(input_dir=input_dir, asof_date=date(2026, 4, 3), worklist=cull_wl['worklist'], project_root=Path(__file__).resolve().parents[1])
    assert cull_snap['schema'] == 'genomeai.economics_per_action.v1'
    assert cull_snap['engine'] == 'cow_value_culling_v1'
    assert cull_snap['economics_inputs_version']
    assert cull_snap['summary_metrics']['expected_gain_rub'] >= 0
    assert cull_snap['formula_rows'] and cull_snap['factors']

    milk = build_milk_quality_scc_snapshot(input_dir=input_dir, asof_date=date(2026, 4, 3), project_root=Path(__file__).resolve().parents[1], data_version='dv_t27_03')
    milk_wl = create_milk_quality_followup_worklist_use_case(conn=conn, tenant_id='default', user_id=8, username='vet', role='Vet', snapshot=milk, target_level='animal', target_id='A1002', request_id='req-milk')
    milk_snap = build_action_economics_snapshot(input_dir=input_dir, asof_date=date(2026, 4, 3), worklist=milk_wl['worklist'], project_root=Path(__file__).resolve().parents[1])
    assert milk_snap['engine'] == 'milk_quality_scc_cockpit_v1'
    assert milk_snap['summary_metrics']['cost_of_delay_per_day_rub'] >= 0
    assert 'quality_caveats' in milk_snap


def test_t27_03_decision_records_economics_context_and_audit(tmp_path: Path) -> None:
    input_dir = _seed_input_dir(tmp_path)
    conn = _conn()
    cow = build_cow_value_snapshot(input_dir=input_dir, asof_date=date(2026, 4, 3), animal_id='A1002', project_root=Path(__file__).resolve().parents[1], data_version='dv_t27_03', report_version='report_t27_03')
    cull_wl = create_culling_review_worklist_use_case(conn=conn, tenant_id='default', user_id=7, username='zootech', role='Zootech', snapshot=cow, request_id='req-cull')
    snap = build_action_economics_snapshot(input_dir=input_dir, asof_date=date(2026, 4, 3), worklist=cull_wl['worklist'], project_root=Path(__file__).resolve().parents[1])
    res = record_action_economics_decision_use_case(conn=conn, tenant_id='default', user_id=7, username='zootech', role='Zootech', snapshot=snap, action='defer', reason='economics_review', comment='Need manager sign-off', request_id='req-decision')
    assert res['decision_id']
    assert res['decision']['metadata']['economics_inputs_version'] == snap['economics_inputs_version']
    assert res['decision']['metadata']['worklist_id'] == snap['worklist_id']
    actions = [r[0] for r in conn.execute('SELECT action FROM audit_log ORDER BY id ASC').fetchall()]
    assert 'economics_per_action.decision.create' in actions


def test_t27_03_ui_docs_and_integration_contracts_present() -> None:
    page = Path('streamlit_app/pages/65_Economics_Per_Action.py').read_text(encoding='utf-8')
    worklist_page = Path('streamlit_app/pages/43_Daily_Worklists_By_Role.py').read_text(encoding='utf-8')
    mobile_page = Path('streamlit_app/pages/58_Mobile_Worklists.py').read_text(encoding='utf-8')
    decisions_page = Path('streamlit_app/pages/31_Decisions_Operations.py').read_text(encoding='utf-8')
    docs = Path('docs/economics_per_action.md').read_text(encoding='utf-8')
    smoke = Path('scripts/smoke_t27_03_economics_per_action.py').read_text(encoding='utf-8')
    ia = Path('configs/ui/ia_v3.yaml').read_text(encoding='utf-8')
    assert 'Economics per action' in page
    assert 'Open action economics' in worklist_page
    assert 'Open economics' in mobile_page
    assert 'Economics context / Экономический контекст' in decisions_page
    assert 'expected ROI' in docs
    assert 'economics per action smoke passed' in smoke
    assert 'pages/65_Economics_Per_Action.py' in ia
