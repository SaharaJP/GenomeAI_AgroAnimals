from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

from core.economics import (
    build_cow_value_population_table,
    build_cow_value_snapshot,
    create_culling_review_worklist_use_case,
    describe_cow_value_inputs_version,
    record_cow_value_decision_use_case,
)
from core.infra.web_db import init_db
from core.operational_report_builder import REPORT_TYPES, build_operational_report_snapshot


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
        {'tenant_id': 'default', 'animal_id': 'A1001', 'date': '2026-04-01', 'milk_kg': 31.0},
        {'tenant_id': 'default', 'animal_id': 'A1001', 'date': '2026-04-02', 'milk_kg': 30.0},
        {'tenant_id': 'default', 'animal_id': 'A1002', 'date': '2026-04-01', 'milk_kg': 14.0},
        {'tenant_id': 'default', 'animal_id': 'A1002', 'date': '2026-04-02', 'milk_kg': 15.0},
    ]).to_csv(input_dir / 'dm_milkings_daily.csv', index=False)
    pd.DataFrame([
        {'tenant_id': 'default', 'event_id': 'HE1', 'animal_id': 'A1002', 'event_date': '2026-03-15', 'event_type': 'mastitis', 'severity': 'high'},
    ]).to_csv(input_dir / 'dm_health_events.csv', index=False)
    pd.DataFrame([
        {'tenant_id': 'default', 'treatment_id': 'TR1', 'animal_id': 'A1002', 'start_date': '2026-03-20', 'end_date': '2026-04-10', 'treatment_type': 'antibiotic'},
    ]).to_csv(input_dir / 'dm_treatments.csv', index=False)
    pd.DataFrame([
        {'tenant_id': 'default', 'repro_event_id': 'RE1', 'animal_id': 'A1001', 'event_date': '2026-03-10', 'event_type': 'preg_check', 'result': 'pregnant'},
        {'tenant_id': 'default', 'repro_event_id': 'RE2', 'animal_id': 'A1002', 'event_date': '2026-03-12', 'event_type': 'preg_check', 'result': 'open'},
    ]).to_csv(input_dir / 'dm_repro_events.csv', index=False)
    return input_dir


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def test_t27_01_engine_builds_explainable_snapshot_and_versioned_inputs(tmp_path: Path) -> None:
    input_dir = _seed_input_dir(tmp_path)
    snap = build_cow_value_snapshot(input_dir=input_dir, asof_date=date(2026, 4, 2), animal_id='A1002', project_root=Path(__file__).resolve().parents[1], data_version='dv_t27_01')
    assert snap['schema'] == 'genomeai.cow_value_culling.v1'
    assert snap['economics_inputs_version']
    assert {row['action'] for row in snap['scenarios']} == {'keep', 'breed', 'treat', 'cull', 'defer'}
    cull_row = next(row for row in snap['scenarios'] if row['action'] == 'cull')
    assert cull_row['requires_confirmation'] is True
    assert snap['replacement_comparison']['replacement_value_rub'] is not None
    assert snap['formula_rows'] and snap['linked_source_facts'] and snap['factors']
    assert snap['recommended_action'] in {'keep', 'breed', 'treat', 'cull', 'defer'}


def test_t27_01_decision_and_worklist_integration_are_audited(tmp_path: Path) -> None:
    input_dir = _seed_input_dir(tmp_path)
    snap = build_cow_value_snapshot(input_dir=input_dir, asof_date=date(2026, 4, 2), animal_id='A1002', project_root=Path(__file__).resolve().parents[1], data_version='dv_t27_01', report_version='report_t27_01')
    conn = _conn()
    dec = record_cow_value_decision_use_case(conn=conn, tenant_id='default', user_id=7, username='zootech', role='Zootech', snapshot=snap, action='defer', reason='manual_review', comment='Need manager sign-off', request_id='req-decision')
    wl = create_culling_review_worklist_use_case(conn=conn, tenant_id='default', user_id=7, username='zootech', role='Zootech', snapshot=snap, request_id='req-worklist')
    assert dec['decision_id']
    assert dec['decision']['object_type'] == 'animal'
    assert dec['decision']['metadata']['economics_inputs_version'] == snap['economics_inputs_version']
    assert wl['worklist_id']
    assert wl['worklist']['worklist_type'] == 'culling_review'
    assert wl['worklist']['why']['engine'] == 'cow_value_culling_v1'
    actions = [r[0] for r in conn.execute("SELECT action FROM audit_log ORDER BY id ASC").fetchall()]
    assert 'cow_value.decision.create' in actions
    assert 'cow_value.worklist.create' in actions


def test_t27_01_report_builder_profile_and_worklist_contracts_present(tmp_path: Path) -> None:
    input_dir = _seed_input_dir(tmp_path)
    population = build_cow_value_population_table(input_dir=input_dir, asof_date=date(2026, 4, 2), project_root=Path(__file__).resolve().parents[1], data_version='dv_t27_01')
    assert not population.empty
    assert {'animal_id', 'keep_value_rub', 'replacement_value_rub', 'delta_keep_vs_replace_rub', 'recommended_action'}.issubset(set(population.columns))
    assert 'cow_value_culling' in REPORT_TYPES
    snap = build_operational_report_snapshot(input_dir=input_dir, asof_date=date(2026, 4, 2), role='Director', report_type='cow_value_culling', limit=20)
    table = pd.DataFrame(list(snap.get('rows') or []))
    assert not table.empty
    assert 'recommended_action' in table.columns and 'replacement_value_rub' in table.columns
    page = Path('streamlit_app/pages/63_Cow_Value_And_Culling.py').read_text(encoding='utf-8')
    animal_page = Path('streamlit_app/pages/15_Animal_Profile.py').read_text(encoding='utf-8')
    report_page = Path('streamlit_app/pages/55_Operational_Report_Builder.py').read_text(encoding='utf-8')
    worklist_page = Path('streamlit_app/pages/43_Daily_Worklists_By_Role.py').read_text(encoding='utf-8')
    docs = Path('docs/cow_value_culling_engine.md').read_text(encoding='utf-8')
    smoke = Path('scripts/smoke_t27_01_cow_value_culling_engine.py').read_text(encoding='utf-8')
    ia = Path('configs/ui/ia_v3.yaml').read_text(encoding='utf-8')
    assert 'Cow value / culling engine' in page
    assert 'Cow value / culling' in animal_page
    assert 'cow_value_culling' in report_page
    assert '63_Cow_Value_And_Culling.py' in worklist_page
    assert 'keep / breed / treat / cull / defer' in docs
    assert 'cow value / culling engine smoke passed' in smoke
    assert 'pages/63_Cow_Value_And_Culling.py' in ia
