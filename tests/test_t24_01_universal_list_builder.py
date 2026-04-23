from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path

import openpyxl
import pandas as pd

from core.list_builder import build_universal_list_snapshot, build_universal_list_table, export_universal_list
from streamlit_app.saved_views_state import apply_saved_view_state, extract_saved_view_state



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
        {'tenant_id': 'default', 'animal_id': 'A1001', 'lactation_id': 'L1', 'parity': 2, 'calving_date': '2026-01-10'},
        {'tenant_id': 'default', 'animal_id': 'A1002', 'lactation_id': 'L2', 'parity': 3, 'calving_date': '2025-12-11'},
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



def test_t24_01_builds_animals_groups_and_events_lists(tmp_path: Path) -> None:
    input_dir = _seed_input_dir(tmp_path)
    animals = build_universal_list_snapshot(
        input_dir=input_dir,
        asof_date=date(2026, 3, 16),
        role='Zootech',
        object_type='animals',
        filters={'farm_id': 'F1'},
        sort_by='animal_id',
        sort_dir='asc',
        selected_columns=['animal_id', 'pen_name', 'active_treatments'],
        limit=50,
    )
    assert animals['object_type'] == 'animals'
    assert animals['total_before_limit'] == 2
    assert animals['returned_rows'] == 2
    assert build_universal_list_table(animals).columns.tolist() == ['animal_id', 'pen_name', 'active_treatments']
    assert any(str(r.get('animal_id')) == 'A1002' and int(r.get('active_treatments') or 0) == 1 for r in animals['rows'])

    groups = build_universal_list_snapshot(
        input_dir=input_dir,
        asof_date=date(2026, 3, 16),
        role='Director',
        object_type='groups',
        filters={'site_id': 'S1'},
        sort_by='headcount',
        sort_dir='desc',
        selected_columns=['pen_name', 'headcount', 'utilization_pct'],
        limit=50,
    )
    assert groups['object_type'] == 'groups'
    assert groups['returned_rows'] == 2
    table = build_universal_list_table(groups)
    assert 'pen_name' in table.columns and 'headcount' in table.columns
    assert int(table.iloc[0]['headcount']) >= int(table.iloc[1]['headcount'])

    events = build_universal_list_snapshot(
        input_dir=input_dir,
        asof_date=date(2026, 3, 16),
        role='Vet',
        object_type='events',
        filters={'event_family': 'health', 'animal_id': 'A1002'},
        sort_by='event_date_ts',
        sort_dir='desc',
        selected_columns=['event_id', 'event_family', 'animal_id', 'notes'],
        limit=50,
    )
    assert events['object_type'] == 'events'
    assert events['returned_rows'] == 1
    row = events['rows'][0]
    assert row['event_id'] == 'HE1'
    assert row['event_family'] == 'health'
    assert row['animal_id'] == 'A1002'



def test_t24_01_role_visibility_and_exports_are_applied_to_same_snapshot(tmp_path: Path) -> None:
    input_dir = _seed_input_dir(tmp_path)
    viewer_snapshot = build_universal_list_snapshot(
        input_dir=input_dir,
        asof_date=date(2026, 3, 16),
        role='Viewer',
        object_type='events',
        filters={'event_family': 'health'},
        sort_by='event_date_ts',
        sort_dir='desc',
        selected_columns=['event_id', 'animal_id', 'notes', 'status'],
        limit=50,
    )
    assert 'notes' not in viewer_snapshot['selected_columns']

    csv_bytes = export_universal_list(viewer_snapshot, fmt='csv')
    csv_text = csv_bytes.decode('utf-8')
    assert 'notes' not in csv_text.splitlines()[0].lower()

    xlsx_bytes = export_universal_list(viewer_snapshot, fmt='xlsx')
    wb = openpyxl.load_workbook(BytesIO(xlsx_bytes))
    ws = wb['list']
    header = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
    assert 'notes' not in [str(x).lower() for x in header if x is not None]
    assert 'event_id' in header and 'animal_id' in header



def test_t24_01_saved_view_state_supports_universal_list_builder() -> None:
    sess = {
        'universal_list_builder.asof': date(2026, 4, 2),
        'universal_list_builder.data_version': 'dv_t24_01',
        'universal_list_builder.object_type': 'events',
        'universal_list_builder.q': 'mastitis',
        'universal_list_builder.farm_id': 'F1',
        'universal_list_builder.site_id': 'S1',
        'universal_list_builder.pen_id': 'P2',
        'universal_list_builder.animal_id': 'A1002',
        'universal_list_builder.status': 'active',
        'universal_list_builder.event_family': 'treatment',
        'universal_list_builder.sort_by': 'event_date',
        'universal_list_builder.sort_dir': 'desc',
        'universal_list_builder.selected_columns': ['event_id', 'animal_id', 7],
        'universal_list_builder.limit': 80,
        'universal_list_builder.selected_row_id': 'TR1',
    }
    state = extract_saved_view_state(page_key='universal_list_builder', session_state=sess)
    assert state['universal_list_builder.asof'] == '2026-04-02'
    assert state['universal_list_builder.selected_columns'] == ['event_id', 'animal_id', '7']
    restored: dict[str, object] = {}
    apply_saved_view_state(page_key='universal_list_builder', state=state, session_state=restored)
    assert restored['universal_list_builder.asof'] == date(2026, 4, 2)
    assert restored['universal_list_builder.selected_columns'] == ['event_id', 'animal_id', '7']
    assert restored['universal_list_builder.selected_row_id'] == 'TR1'



def test_t24_01_streamlit_contracts_and_docs_present() -> None:
    page = Path('streamlit_app/pages/54_Universal_List_Builder.py').read_text(encoding='utf-8')
    helper = Path('streamlit_app/universal_list_builder.py').read_text(encoding='utf-8')
    state = Path('streamlit_app/saved_views_state.py').read_text(encoding='utf-8')
    saved_views_page = Path('streamlit_app/pages/17_Saved_Views_And_Favorites.py').read_text(encoding='utf-8')
    config = Path('configs/ui/ia_v3.yaml').read_text(encoding='utf-8')
    docs = Path('docs/universal_list_builder.md').read_text(encoding='utf-8')
    assumptions = Path('docs/assumptions.md').read_text(encoding='utf-8')

    assert 'Universal list builder' in page
    assert 'Open animal' in page or 'Open group' in page or 'Open linked object' in page
    assert 'Export CSV' in page and 'Export XLSX' in page
    assert 'build_universal_list_snapshot' in helper
    assert 'universal_list_builder' in state
    assert 'universal_list_builder' in saved_views_page
    assert 'pages/54_Universal_List_Builder.py' in config
    assert 'saved views' in docs.lower() and 'export' in docs.lower() and 'role-aware' in docs.lower()
    assert '## T24-01 — universal list builder' in assumptions
