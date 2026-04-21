from __future__ import annotations

from datetime import date
from pathlib import Path
import sqlite3

import pandas as pd

from core.audit import list_audit, write_audit
from core.fast_query_mode import execute_fast_query, parse_fast_query
from core.infra.web_db import init_db
from streamlit_app.fast_query_mode import build_fast_query_display_table, build_fast_query_history_table, load_fast_query_result
from streamlit_app.personalization import required_permission_for_favorite
from streamlit_app.saved_views_state import apply_saved_view_state, extract_saved_view_state
import core.security as rbac


def _seed_input_dir(tmp_path: Path) -> Path:
    input_dir = tmp_path / 'input'
    input_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {'tenant_id': 'default', 'animal_id': 'A1001', 'farm_id': 'F1', 'site_id': 'S1', 'current_pen_id': 'P1', 'current_pen_name': 'Fresh', 'sex': 'F', 'birth_date': '2022-01-01', 'breed': 'Holstein', 'status': 'active'},
        {'tenant_id': 'default', 'animal_id': 'A1002', 'farm_id': 'F1', 'site_id': 'S1', 'current_pen_id': 'P2', 'current_pen_name': 'Hospital', 'sex': 'F', 'birth_date': '2021-06-01', 'breed': 'Jersey', 'status': 'active'},
        {'tenant_id': 'default', 'animal_id': 'A1003', 'farm_id': 'F2', 'site_id': 'S2', 'current_pen_id': 'P3', 'current_pen_name': 'Dry', 'sex': 'F', 'birth_date': '2020-05-01', 'breed': 'Holstein', 'status': 'dry'},
    ]).to_csv(input_dir / 'dm_animals.csv', index=False)
    pd.DataFrame([
        {'tenant_id': 'default', 'pen_id': 'P1', 'site_id': 'S1', 'pen_name': 'Fresh', 'pen_type': 'fresh', 'capacity_head': 50},
        {'tenant_id': 'default', 'pen_id': 'P2', 'site_id': 'S1', 'pen_name': 'Hospital', 'pen_type': 'hospital', 'capacity_head': 20},
        {'tenant_id': 'default', 'pen_id': 'P3', 'site_id': 'S2', 'pen_name': 'Dry', 'pen_type': 'dry', 'capacity_head': 30},
    ]).to_csv(input_dir / 'dm_pens.csv', index=False)
    pd.DataFrame([
        {'tenant_id': 'default', 'move_id': 'PM1', 'animal_id': 'A1001', 'from_pen_id': '', 'to_pen_id': 'P1', 'move_date': '2026-03-01', 'reason': 'fresh'},
        {'tenant_id': 'default', 'move_id': 'PM2', 'animal_id': 'A1002', 'from_pen_id': '', 'to_pen_id': 'P2', 'move_date': '2026-03-02', 'reason': 'check'},
        {'tenant_id': 'default', 'move_id': 'PM3', 'animal_id': 'A1003', 'from_pen_id': '', 'to_pen_id': 'P3', 'move_date': '2026-03-03', 'reason': 'dry'},
    ]).to_csv(input_dir / 'dm_pen_moves.csv', index=False)
    pd.DataFrame([
        {'tenant_id': 'default', 'animal_id': 'A1001', 'lactation_id': 'L1', 'parity': 2, 'calving_date': '2026-01-10', 'scc_cells_ml': 110000},
        {'tenant_id': 'default', 'animal_id': 'A1002', 'lactation_id': 'L2', 'parity': 3, 'calving_date': '2025-12-11', 'scc_cells_ml': 320000},
    ]).to_csv(input_dir / 'dm_lactations.csv', index=False)
    pd.DataFrame([
        {'tenant_id': 'default', 'event_id': 'HE1', 'animal_id': 'A1002', 'event_date': '2026-03-12', 'event_type': 'mastitis', 'severity': 'high', 'notes': 'Detected by SCC rise'},
        {'tenant_id': 'default', 'event_id': 'HE2', 'animal_id': 'A1001', 'event_date': '2026-03-05', 'event_type': 'metritis', 'severity': 'medium', 'notes': 'Follow-up'},
    ]).to_csv(input_dir / 'dm_health_events.csv', index=False)
    pd.DataFrame([
        {'tenant_id': 'default', 'repro_event_id': 'RE1', 'animal_id': 'A1001', 'event_date': '2026-03-08', 'event_type': 'insemination', 'bull_id': 'B1', 'result': 'unknown', 'notes': 'AI'},
        {'tenant_id': 'default', 'repro_event_id': 'RE2', 'animal_id': 'A1003', 'event_date': '2026-02-01', 'event_type': 'preg_check', 'bull_id': '', 'result': 'pregnant', 'notes': 'Confirmed'},
    ]).to_csv(input_dir / 'dm_repro_events.csv', index=False)
    pd.DataFrame([
        {'tenant_id': 'default', 'treatment_id': 'TR1', 'animal_id': 'A1002', 'start_date': '2026-03-12', 'end_date': '2026-03-20', 'treatment_type': 'antibiotic', 'reason_event_id': 'HE1', 'withdrawal_end_date': '2026-03-20'},
    ]).to_csv(input_dir / 'dm_treatments.csv', index=False)
    return input_dir


def test_t24_03_parses_animals_query_and_routes_to_list(tmp_path: Path) -> None:
    input_dir = _seed_input_dir(tmp_path)
    parsed = parse_fast_query(query_text='animals breed:Holstein status:active sort:animal_id:asc cols:animal_id,pen_name limit:5')
    assert parsed.target_kind == 'list'
    assert parsed.object_type == 'animals'
    assert parsed.filters['breed'] == 'Holstein'
    assert parsed.sort_by == 'animal_id'
    assert parsed.sort_dir == 'asc'
    assert parsed.selected_columns == ('animal_id', 'pen_name')

    result = execute_fast_query(input_dir=input_dir, asof_date=date(2026, 3, 16), role='Zootech', query_text='animals breed:Holstein status:active sort:animal_id:asc cols:animal_id,pen_name limit:5')
    assert result.mode == 'list'
    table = build_fast_query_display_table({'mode': result.mode, 'payload': result.payload, 'parsed': {'explain_rows': [], 'selected_columns': list(parsed.selected_columns)}})
    assert table.columns.tolist() == ['animal_id', 'pen_name']
    assert table['animal_id'].tolist() == ['A1001']


def test_t24_03_parses_report_and_profile_targets(tmp_path: Path) -> None:
    input_dir = _seed_input_dir(tmp_path)
    report = load_fast_query_result(
        input_dir=input_dir,
        asof_date=date(2026, 3, 16),
        role='Vet',
        query_text='report:health animal:A1002 severity:high cols:event_date,animal_id,event_type limit:10',
    )
    assert report['mode'] == 'report'
    parsed = dict(report['parsed'])
    assert parsed['report_type'] == 'health_attention'
    table = build_fast_query_display_table(report)
    assert list(table.columns) == ['event_date', 'animal_id', 'event_type']
    assert set(table['animal_id']) == {'A1002'}

    profile = parse_fast_query(query_text='open:animal:A1002')
    assert profile.target_kind == 'profile'
    assert profile.open_target == {'kind': 'animal', 'object_id': 'A1002'}


def test_t24_03_rejects_unsafe_raw_query_patterns() -> None:
    try:
        parse_fast_query(query_text='animals status:active; drop table animals')
    except ValueError as exc:
        assert 'fast_query_unsafe' in str(exc)
    else:
        raise AssertionError('unsafe query must be rejected')


def test_t24_03_saved_view_state_history_and_permissions() -> None:
    sess = {
        'fast_query_mode.asof': date(2026, 4, 2),
        'fast_query_mode.data_version': 'dv_t24_03',
        'fast_query_mode.query_text': 'report:health animal:A1002 severity:high',
        'fast_query_mode.selected_result_id': 'HE1',
    }
    state = extract_saved_view_state(page_key='fast_query_mode', session_state=sess)
    assert state['fast_query_mode.asof'] == '2026-04-02'
    restored: dict[str, object] = {}
    apply_saved_view_state(page_key='fast_query_mode', state=state, session_state=restored)
    assert restored['fast_query_mode.asof'] == date(2026, 4, 2)
    assert restored['fast_query_mode.query_text'] == 'report:health animal:A1002 severity:high'

    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    init_db(conn)
    write_audit(
        conn,
        tenant_id='default',
        user_id=1,
        username='tester',
        role='Director',
        action='fast_query.run',
        object_type='fast_query',
        object_id='q1',
        after={'query_text': 'animals status:active', 'canonical_query': 'list:animals status:active limit:120', 'mode': 'list', 'target': 'animals', 'warnings': []},
    )
    rows = list_audit(conn, tenant_id='default', action='fast_query.run', limit=10)
    hist = build_fast_query_history_table(rows)
    assert hist.iloc[0]['query_text'] == 'animals status:active'
    assert required_permission_for_favorite('fast_query') == rbac.PERM_REPORTS_VIEW
    assert required_permission_for_favorite('pinned_fast_query') == rbac.PERM_REPORTS_VIEW


def test_t24_03_streamlit_contracts_docs_and_navigation_present() -> None:
    page = Path('streamlit_app/pages/56_Fast_Query_Mode.py').read_text(encoding='utf-8')
    helper = Path('streamlit_app/fast_query_mode.py').read_text(encoding='utf-8')
    core = Path('src/core/fast_query_mode.py').read_text(encoding='utf-8')
    state = Path('streamlit_app/saved_views_state.py').read_text(encoding='utf-8')
    saved_views_page = Path('streamlit_app/pages/17_Saved_Views_And_Favorites.py').read_text(encoding='utf-8')
    favorites = Path('streamlit_app/personalization.py').read_text(encoding='utf-8')
    config = Path('configs/ui/ia_v3.yaml').read_text(encoding='utf-8')
    docs = Path('docs/fast_query_mode.md').read_text(encoding='utf-8')
    assumptions = Path('docs/assumptions.md').read_text(encoding='utf-8')

    assert 'Fast query mode' in page
    assert 'History' in page and 'Favorite' in page and 'Pin query' in page
    assert 'Open target surface' in page and 'Open list builder' in page and 'Open report builder' in page
    assert 'parse_fast_query' in core and 'execute_fast_query' in core
    assert 'build_fast_query_history_table' in helper
    assert 'fast_query_mode' in state
    assert 'fast_query_mode' in saved_views_page
    assert 'fast_query' in favorites and 'pinned_fast_query' in favorites
    assert 'pages/56_Fast_Query_Mode.py' in config
    assert 'bounded' in docs.lower() and 'history' in docs.lower() and 'favorites' in docs.lower()
    assert '## T24-03 — fast query mode' in assumptions
