from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

from core.economics import (
    build_operational_what_if_snapshot,
    create_operational_what_if_followup_worklist_use_case,
    record_operational_what_if_decision_use_case,
)
from core.infra.web_db import init_db


def _seed_input(tmp_path: Path) -> Path:
    input_dir = tmp_path / 'input'
    input_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {'animal_id':'A1001','farm_id':'F1','status':'active','breed':'Holstein','current_pen_id':'P1','current_pen_name':'Fresh pen'},
        {'animal_id':'A1002','farm_id':'F1','status':'active','breed':'Holstein','current_pen_id':'P2','current_pen_name':'Hospital pen'},
    ]).to_csv(input_dir/'dm_animals.csv', index=False)
    pd.DataFrame([
        {'animal_id':'A1001','lactation_id':'L1','parity':2,'calving_date':'2026-03-20','scc_cells_ml':180000},
        {'animal_id':'A1002','lactation_id':'L2','parity':3,'calving_date':'2026-02-10','scc_cells_ml':330000},
    ]).to_csv(input_dir/'dm_lactations.csv', index=False)
    pd.DataFrame([
        {'animal_id':'A1001','date':'2026-04-03','milk_kg':31.0,'scc_cells_ml':180000},
        {'animal_id':'A1002','date':'2026-04-03','milk_kg':20.0,'scc_cells_ml':330000},
    ]).to_csv(input_dir/'dm_milkings_daily.csv', index=False)
    pd.DataFrame([
        {'animal_id':'A1002','event_id':'HE1','event_date':'2026-04-01','event_type':'mastitis','severity':'high'},
    ]).to_csv(input_dir/'dm_health_events.csv', index=False)
    pd.DataFrame([
        {'animal_id':'A1002','treatment_id':'T1','start_date':'2026-04-02','end_date':'2026-04-06'},
    ]).to_csv(input_dir/'dm_treatments.csv', index=False)
    pd.DataFrame([
        {'animal_id':'A1001','event_date':'2026-04-03','event_type':'heat_observed','result':'candidate'},
    ]).to_csv(input_dir/'dm_repro_events.csv', index=False)
    return input_dir


def _conn(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / 'web.db')
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def test_t27_05_builds_explainable_operational_what_if_for_culling_and_treatment(tmp_path: Path) -> None:
    input_dir = _seed_input(tmp_path)
    snap_cull = build_operational_what_if_snapshot(input_dir=input_dir, asof_date=date(2026,4,3), object_type='animal', object_id='A1002', scenario_family='cull_keep', project_root=Path(__file__).resolve().parents[1], data_version='dv_t27_05')
    assert snap_cull['schema'] == 'genomeai.operational_what_if.v1'
    assert any(str(r.get('scenario_key')) == 'cull' for r in list(snap_cull.get('scenario_rows') or []))
    assert any(str(r.get('metric')) == 'expected_net_value_rub' for r in list(snap_cull.get('formula_rows') or []))

    worklist = {
        'worklist_id': 'WL-HEALTH-1', 'worklist_type': 'health_follow_up', 'title': 'Check mastitis', 'object_type': 'animal', 'object_id': 'A1002',
        'farm_id': 'F1', 'group_id': 'P2', 'pen_id': 'P2', 'status': 'open', 'due_bucket': 'today', 'data_version': 'dv_t27_05',
        'linked_source_facts': [{'source': 'dm_health_events', 'event_id': 'HE1'}],
    }
    snap_health = build_operational_what_if_snapshot(input_dir=input_dir, asof_date=date(2026,4,3), worklist=worklist, project_root=Path(__file__).resolve().parents[1])
    keys = {str(r.get('scenario_key')) for r in list(snap_health.get('scenario_rows') or [])}
    assert {'treat_now', 'change_protocol', 'no_treat'}.issubset(keys)
    assert snap_health['recommended_scenario_key']


def test_t27_05_records_decision_and_followup_worklist_with_traceable_metadata(tmp_path: Path) -> None:
    input_dir = _seed_input(tmp_path)
    snap = build_operational_what_if_snapshot(input_dir=input_dir, asof_date=date(2026,4,3), object_type='animal', object_id='A1002', scenario_family='cull_keep', project_root=Path(__file__).resolve().parents[1], data_version='dv_t27_05')
    conn = _conn(tmp_path)
    dec = record_operational_what_if_decision_use_case(conn=conn, tenant_id='default', user_id=7, username='hm', role='HerdManager', snapshot=snap, scenario_key=snap['recommended_scenario_key'], reason='what_if_review', comment='Need sign-off', request_id='req-whatif-decision')
    assert dec['decision_id']
    assert dec['metadata']['engine'] == 'operational_what_if_v1'
    wl = create_operational_what_if_followup_worklist_use_case(conn=conn, tenant_id='default', user_id=7, username='hm', role='HerdManager', snapshot=snap, scenario_key=snap['recommended_scenario_key'], request_id='req-whatif-worklist')
    assert wl['worklist_id']
    actions = [str(r[0]) for r in conn.execute('SELECT action FROM audit_log ORDER BY id').fetchall()]
    assert 'operational_what_if.decision.create' in actions
    assert 'operational_what_if.worklist.create' in actions


def test_t27_05_profile_worklist_and_report_links_are_present() -> None:
    animal_page = Path('streamlit_app/pages/15_Animal_Profile.py').read_text(encoding='utf-8')
    group_page = Path('streamlit_app/pages/14_Group_Profile.py').read_text(encoding='utf-8')
    worklist_page = Path('streamlit_app/pages/43_Daily_Worklists_By_Role.py').read_text(encoding='utf-8')
    mobile_page = Path('streamlit_app/pages/58_Mobile_Worklists.py').read_text(encoding='utf-8')
    report_page = Path('streamlit_app/pages/55_Operational_Report_Builder.py').read_text(encoding='utf-8')
    docs = Path('docs/operational_what_if.md').read_text(encoding='utf-8')
    assert 'Open explainable what-if' in animal_page
    assert 'Open group move what-if' in group_page
    assert 'Open explainable what-if' in worklist_page
    assert 'Open what-if' in mobile_page
    assert 'pages/67_Operational_What_If.py' in report_page
    assert 'Operational what-if' in docs
