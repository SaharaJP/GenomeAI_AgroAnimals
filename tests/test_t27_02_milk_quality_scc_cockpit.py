from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

from core.economics import build_milk_quality_scc_snapshot, create_milk_quality_followup_worklist_use_case, describe_milk_quality_inputs_version
from core.infra.web_db import init_db



def _seed_input_dir(tmp_path: Path) -> Path:
    input_dir = tmp_path / 'input'
    input_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {'tenant_id': 'default', 'animal_id': 'A1001', 'farm_id': 'F1', 'site_id': 'S1', 'current_pen_id': 'P1', 'current_pen_name': 'Fresh', 'status': 'active', 'breed': 'Holstein', 'sex': 'F', 'birth_date': '2022-01-01'},
        {'tenant_id': 'default', 'animal_id': 'A1002', 'farm_id': 'F1', 'site_id': 'S1', 'current_pen_id': 'P2', 'current_pen_name': 'Hospital', 'status': 'active', 'breed': 'Holstein', 'sex': 'F', 'birth_date': '2021-01-01'},
        {'tenant_id': 'default', 'animal_id': 'A1003', 'farm_id': 'F1', 'site_id': 'S1', 'current_pen_id': 'P1', 'current_pen_name': 'Fresh', 'status': 'active', 'breed': 'Holstein', 'sex': 'F', 'birth_date': '2023-01-01'},
    ]).to_csv(input_dir / 'dm_animals.csv', index=False)
    pd.DataFrame([
        {'tenant_id': 'default', 'animal_id': 'A1001', 'date': '2026-04-03', 'milk_kg': 31.0, 'scc_cells_ml': 120000},
        {'tenant_id': 'default', 'animal_id': 'A1002', 'date': '2026-04-03', 'milk_kg': 23.0, 'scc_cells_ml': 420000},
        {'tenant_id': 'default', 'animal_id': 'A1003', 'date': '2026-04-03', 'milk_kg': 28.0, 'scc_cells_ml': 180000},
        {'tenant_id': 'default', 'animal_id': 'A1003', 'date': '2026-04-02', 'milk_kg': 27.0, 'scc_cells_ml': 170000},
        {'tenant_id': 'default', 'animal_id': 'A9999', 'date': '2026-04-03', 'milk_kg': 10.0, 'scc_cells_ml': None},
    ]).to_csv(input_dir / 'dm_milkings_daily.csv', index=False)
    pd.DataFrame([
        {'tenant_id': 'default', 'event_id': 'HE1', 'animal_id': 'A1002', 'event_date': '2026-03-20', 'event_type': 'mastitis', 'severity': 'high'},
    ]).to_csv(input_dir / 'dm_health_events.csv', index=False)
    pd.DataFrame([
        {'tenant_id': 'default', 'treatment_id': 'TR1', 'animal_id': 'A1002', 'start_date': '2026-03-21', 'end_date': '2026-04-10', 'treatment_type': 'antibiotic'},
    ]).to_csv(input_dir / 'dm_treatments.csv', index=False)
    return input_dir



def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn



def test_t27_02_builds_reproducible_scc_snapshot_with_contributions_and_caveats(tmp_path: Path) -> None:
    input_dir = _seed_input_dir(tmp_path)
    snap = build_milk_quality_scc_snapshot(input_dir=input_dir, asof_date=date(2026, 4, 3), project_root=Path(__file__).resolve().parents[1], data_version='dv_t27_02')
    assert snap['schema'] == 'genomeai.milk_quality_scc_cockpit.v1'
    assert snap['economics_inputs_version']
    assert snap['bulk_tank']['estimated_bulk_tank_scc'] is not None
    assert snap['bulk_tank']['economic_adjustment']['label']
    assert snap['animal_contributions'] and snap['group_contributions']
    a2 = next(r for r in snap['animal_contributions'] if r['animal_id'] == 'A1002')
    assert a2['suggested_action'] in {'inspect_and_sample', 'review_withdrawal_and_treatment'}
    assert a2['attributed_economic_adjustment_rub'] <= 0
    assert snap['action_lists']['animals']
    assert snap['formula_rows'] and snap['source_links']
    assert any('исключены из bulk tank estimation' in str(x).lower() for x in snap['quality_caveats'])



def test_t27_02_followup_worklist_is_created_and_audited(tmp_path: Path) -> None:
    input_dir = _seed_input_dir(tmp_path)
    snap = build_milk_quality_scc_snapshot(input_dir=input_dir, asof_date=date(2026, 4, 3), project_root=Path(__file__).resolve().parents[1], data_version='dv_t27_02')
    conn = _conn()
    res = create_milk_quality_followup_worklist_use_case(
        conn=conn,
        tenant_id='default',
        user_id=7,
        username='vet',
        role='Vet',
        snapshot=snap,
        target_level='animal',
        target_id='A1002',
        request_id='req-milk-quality',
    )
    assert res['worklist_id']
    assert res['worklist']['worklist_type'] == 'milk_quality'
    assert res['worklist']['object_type'] == 'animal'
    assert res['worklist']['why']['engine'] == 'milk_quality_scc_cockpit_v1'
    actions = [r[0] for r in conn.execute('SELECT action FROM audit_log ORDER BY id ASC').fetchall()]
    assert 'worklist.create' in actions
    assert 'milk_quality.worklist.create' in actions



def test_t27_02_page_profile_report_and_docs_contracts_present() -> None:
    page = Path('streamlit_app/pages/64_Milk_Quality_SCC_Cockpit.py').read_text(encoding='utf-8')
    animal_page = Path('streamlit_app/pages/15_Animal_Profile.py').read_text(encoding='utf-8')
    group_page = Path('streamlit_app/pages/14_Group_Profile.py').read_text(encoding='utf-8')
    report_page = Path('streamlit_app/pages/55_Operational_Report_Builder.py').read_text(encoding='utf-8')
    worklist_page = Path('streamlit_app/pages/43_Daily_Worklists_By_Role.py').read_text(encoding='utf-8')
    mobile_page = Path('streamlit_app/pages/58_Mobile_Worklists.py').read_text(encoding='utf-8')
    docs = Path('docs/milk_quality_scc_cockpit.md').read_text(encoding='utf-8')
    smoke = Path('scripts/smoke_t27_02_milk_quality_scc_cockpit.py').read_text(encoding='utf-8')
    ia = Path('configs/ui/ia_v3.yaml').read_text(encoding='utf-8')
    assert 'Milk quality / SCC cockpit' in page
    assert 'animal.summary.open.milk_quality' in animal_page
    assert 'pages/64_Milk_Quality_SCC_Cockpit.py' in group_page
    assert 'milk_quality_watchlist' in report_page and '64_Milk_Quality_SCC_Cockpit.py' in report_page
    assert '64_Milk_Quality_SCC_Cockpit.py' in worklist_page
    assert '64_Milk_Quality_SCC_Cockpit.py' in mobile_page
    assert 'bulk tank SCC' in docs
    assert 'milk quality / SCC cockpit smoke passed' in smoke
    assert 'pages/64_Milk_Quality_SCC_Cockpit.py' in ia
