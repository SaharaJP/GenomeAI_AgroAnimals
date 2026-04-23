from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

from core.economics import build_fresh_cows_transition_snapshot, create_fresh_transition_followup_worklist_use_case
from core.infra.web_db import init_db


def _seed_input(tmp_path: Path) -> Path:
    input_dir = tmp_path / 'input'
    input_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {'animal_id':'A1001','farm_id':'F1','status':'active','breed':'Holstein','current_pen_id':'P1','current_pen_name':'Fresh pen'},
        {'animal_id':'A1002','farm_id':'F1','status':'active','breed':'Holstein','current_pen_id':'P1','current_pen_name':'Fresh pen'},
        {'animal_id':'A1003','farm_id':'F1','status':'active','breed':'Holstein','current_pen_id':'P2','current_pen_name':'Late pen'},
    ]).to_csv(input_dir/'dm_animals.csv', index=False)
    pd.DataFrame([
        {'animal_id':'A1001','lactation_id':'L1','parity':2,'calving_date':'2026-03-20','scc_cells_ml':150000},
        {'animal_id':'A1002','lactation_id':'L2','parity':3,'calving_date':'2026-03-10','scc_cells_ml':330000},
        {'animal_id':'A1003','lactation_id':'L3','parity':1,'calving_date':'2026-02-20','scc_cells_ml':120000},
    ]).to_csv(input_dir/'dm_lactations.csv', index=False)
    pd.DataFrame([
        {'animal_id':'A1001','date':'2026-04-03','milk_kg':31.0,'scc_cells_ml':150000},
        {'animal_id':'A1002','date':'2026-04-03','milk_kg':22.0,'scc_cells_ml':330000},
        {'animal_id':'A1003','date':'2026-04-03','milk_kg':20.0,'scc_cells_ml':120000},
    ]).to_csv(input_dir/'dm_milkings_daily.csv', index=False)
    pd.DataFrame([
        {'animal_id':'A1002','event_id':'HE1','event_date':'2026-03-28','event_type':'metritis','severity':'high'},
    ]).to_csv(input_dir/'dm_health_events.csv', index=False)
    pd.DataFrame([
        {'animal_id':'A1002','treatment_id':'T1','start_date':'2026-03-29','end_date':'2026-04-05'},
    ]).to_csv(input_dir/'dm_treatments.csv', index=False)
    pd.DataFrame(columns=['animal_id','repro_event_id','event_date','event_type','result']).to_csv(input_dir/'dm_repro_events.csv', index=False)
    pd.DataFrame(columns=['animal_id','test_date','scc_cells_ml']).to_csv(input_dir/'dm_testday.csv', index=False)
    return input_dir


def _conn(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / 'web.db')
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def test_t27_04_builds_transition_snapshot_with_weekly_monitoring_and_action_lists(tmp_path: Path) -> None:
    input_dir = _seed_input(tmp_path)
    snap = build_fresh_cows_transition_snapshot(input_dir=input_dir, asof_date=date(2026,4,3), project_root=Path(__file__).resolve().parents[1], data_version='dv_t27_04')
    assert snap['schema'] == 'genomeai.fresh_cows_transition_economics.v1'
    assert int((snap.get('summary_metrics') or {}).get('fresh_cows_n') or 0) == 2
    assert list(snap.get('weekly_monitoring') or [])
    assert list((snap.get('action_lists') or {}).get('vet') or [])
    assert any(str(r.get('workflow_lane')) == 'vet' for r in list(snap.get('animal_rows') or []))
    assert any('risk_score' == str(r.get('metric')) for r in list(snap.get('formula_rows') or []))


def test_t27_04_creates_followup_worklist_with_existing_workflow_types_and_audit(tmp_path: Path) -> None:
    input_dir = _seed_input(tmp_path)
    snap = build_fresh_cows_transition_snapshot(input_dir=input_dir, asof_date=date(2026,4,3), project_root=Path(__file__).resolve().parents[1], data_version='dv_t27_04')
    conn = _conn(tmp_path)
    res = create_fresh_transition_followup_worklist_use_case(conn=conn, tenant_id='default', user_id=7, username='vet', role='Vet', snapshot=snap, target_level='animal', target_id='A1002', request_id='req-fresh')
    assert res['worklist_id']
    assert res['worklist']['worklist_type'] in {'health_follow_up','reproduction','milk_quality','manager_review'}
    assert res['worklist']['why']['engine'] == 'fresh_cows_transition_economics_v1'
    actions = [str(r[0]) for r in conn.execute('SELECT action FROM audit_log ORDER BY id').fetchall()]
    assert 'worklist.create' in actions
    assert 'fresh_transition.worklist.create' in actions


def test_t27_04_profile_and_worklist_links_are_present() -> None:
    animal_page = Path('streamlit_app/pages/15_Animal_Profile.py').read_text(encoding='utf-8')
    group_page = Path('streamlit_app/pages/14_Group_Profile.py').read_text(encoding='utf-8')
    worklist_page = Path('streamlit_app/pages/43_Daily_Worklists_By_Role.py').read_text(encoding='utf-8')
    mobile_page = Path('streamlit_app/pages/58_Mobile_Worklists.py').read_text(encoding='utf-8')
    assert 'Open fresh cows / transition' in animal_page
    assert 'Open fresh cows / transition' in group_page
    assert 'fresh_cows_transition_economics_v1' in worklist_page
    assert 'pages/66_Fresh_Cows_Transition_Economics.py' in mobile_page
