from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from core.operational import (
    build_current_location_index,
    build_explainable_scope_aggregates,
    build_multi_site_reference,
    enrich_operational_items,
    filter_operational_items,
    format_operational_location,
)
from streamlit_app.saved_views_state import apply_saved_view_state, extract_saved_view_state



def _seed_input_dir(tmp_path: Path) -> Path:
    root = tmp_path / 'canonical'
    root.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {'tenant_id': 'default', 'farm_id': 'F1', 'farm_name': 'North farm'},
        {'tenant_id': 'default', 'farm_id': 'F2', 'farm_name': 'South farm'},
    ]).to_csv(root / 'dm_farms.csv', index=False)
    pd.DataFrame([
        {'tenant_id': 'default', 'site_id': 'S1', 'farm_id': 'F1', 'site_name': 'Main site'},
        {'tenant_id': 'default', 'site_id': 'S2', 'farm_id': 'F2', 'site_name': 'Remote site'},
    ]).to_csv(root / 'dm_sites.csv', index=False)
    pd.DataFrame([
        {'tenant_id': 'default', 'pen_id': 'P1', 'site_id': 'S1', 'pen_name': 'Fresh pen', 'pen_type': 'fresh', 'group_id': 'G-FRESH', 'group_name': 'Fresh cows'},
        {'tenant_id': 'default', 'pen_id': 'P2', 'site_id': 'S2', 'pen_name': 'Hospital pen', 'pen_type': 'hospital'},
    ]).to_csv(root / 'dm_pens.csv', index=False)
    pd.DataFrame([
        {'tenant_id': 'default', 'animal_id': 'A1', 'farm_id': 'F1', 'site_id': 'S1', 'current_pen_id': 'P1', 'status': 'active'},
        {'tenant_id': 'default', 'animal_id': 'A2', 'farm_id': 'F2', 'site_id': 'S2', 'current_pen_id': 'P2', 'status': 'active'},
    ]).to_csv(root / 'dm_animals.csv', index=False)
    pd.DataFrame([
        {'tenant_id': 'default', 'move_id': 'M1', 'animal_id': 'A1', 'from_pen_id': '', 'to_pen_id': 'P1', 'move_date': '2026-04-01', 'reason': 'fresh'},
        {'tenant_id': 'default', 'move_id': 'M2', 'animal_id': 'A2', 'from_pen_id': '', 'to_pen_id': 'P2', 'move_date': '2026-04-01', 'reason': 'hospital'},
    ]).to_csv(root / 'dm_pen_moves.csv', index=False)
    return root



def test_t28_01_builds_enterprise_reference_and_current_location(tmp_path: Path) -> None:
    input_dir = _seed_input_dir(tmp_path)
    ref = build_multi_site_reference(input_dir=input_dir)
    assert {'farm_id', 'site_id', 'group_id', 'pen_id', 'physical_location', 'organizational_location'} <= set(ref.columns)

    fresh = ref[ref['pen_id'].astype(str) == 'P1'].iloc[0].to_dict()
    assert fresh['group_id'] == 'G-FRESH'
    assert 'North farm' in str(fresh['physical_location'])
    assert 'Fresh cows' in str(fresh['organizational_location'])

    hospital = ref[ref['pen_id'].astype(str) == 'P2'].iloc[0].to_dict()
    assert hospital['group_id'] == 'P2'  # fallback group=pen keeps compatibility
    assert hospital['group_name'] == 'Hospital pen'

    loc = build_current_location_index(input_dir=input_dir, asof_date=date(2026, 4, 4))
    a1 = loc[loc['animal_id'].astype(str) == 'A1'].iloc[0].to_dict()
    assert a1['farm_id'] == 'F1'
    assert a1['site_id'] == 'S1'
    assert a1['group_id'] == 'G-FRESH'
    assert a1['pen_id'] == 'P1'
    assert 'farm:F1' in str(a1['lineage_path'])



def test_t28_01_enriches_filters_and_aggregates_items_explainably(tmp_path: Path) -> None:
    input_dir = _seed_input_dir(tmp_path)
    rows = [
        {
            'worklist_id': 'W1',
            'object_type': 'animal',
            'object_id': 'A1',
            'priority': 1,
            'due_bucket': 'today',
            'source_kind': 'worklist',
        },
        {
            'planner_item_id': 'P1',
            'object_type': 'group',
            'object_id': 'P2',
            'priority': 2,
            'bucket': 'overdue',
            'source_kind': 'alert',
        },
        {
            'planner_item_id': 'P2',
            'object_type': 'alert',
            'object_id': 'AL-1',
            'priority': 3,
            'bucket': 'today',
            'source_kind': 'alert',
            'why': {'farm_id': 'F1', 'site_id': 'S1', 'group_id': 'G-FRESH'},
        },
    ]
    enriched = enrich_operational_items(rows=rows, input_dir=input_dir, asof_date=date(2026, 4, 4))
    by_id = {str(r.get('object_id') or r.get('worklist_id') or r.get('planner_item_id')): r for r in enriched}

    assert by_id['A1']['farm_id'] == 'F1'
    assert by_id['A1']['site_id'] == 'S1'
    assert by_id['A1']['group_id'] == 'G-FRESH'
    assert 'Fresh cows' in str(by_id['A1']['organizational_location'])

    assert by_id['P2']['farm_id'] == 'F2'
    assert by_id['P2']['site_id'] == 'S2'
    assert by_id['P2']['group_id'] == 'P2'

    filtered = filter_operational_items(enriched, site_id='S1', allowed_farm_ids=['F1'])
    assert len(filtered) == 2
    assert all(str(r.get('farm_id')) == 'F1' for r in filtered)

    site_aggr = build_explainable_scope_aggregates(filtered, level='site')
    assert len(site_aggr) == 1
    rec = site_aggr.iloc[0].to_dict()
    assert rec['farm_id'] == 'F1'
    assert rec['site_id'] == 'S1'
    assert rec['items_total'] == 2
    assert rec['high_priority'] == 1
    assert 'worklist' in str(rec['explainability']) or 'alert' in str(rec['explainability'])



def test_t28_01_saved_views_and_docs_are_wired() -> None:
    sess = {
        'daily_worklists_by_role.day': date(2026, 4, 4),
        'daily_worklists_by_role.data_version': 'dv_t28_01',
        'daily_worklists_by_role.include_upcoming': True,
        'daily_worklists_by_role.q': 'fresh',
        'daily_worklists_by_role.limit': 60,
        'daily_worklists_by_role.farm_id': 'F1',
        'daily_worklists_by_role.site_id': 'S1',
        'daily_worklists_by_role.group_id': 'G-FRESH',
        'daily_worklists_by_role.pen_id': 'P1',
        'daily_worklists_by_role.selected_worklist_id': 'W1',
        'operational_planner.day': date(2026, 4, 4),
        'operational_planner.data_version': 'dv_t28_01',
        'operational_planner.view_mode': 'manager',
        'operational_planner.role': 'Zootech',
        'operational_planner.owner': 'zootech_1',
        'operational_planner.team': 'team-repro',
        'operational_planner.sources': ['alerts', 'worklists'],
        'operational_planner.q': 'preg',
        'operational_planner.farm_id': 'F1',
        'operational_planner.site_id': 'S1',
        'operational_planner.group_id': 'G-FRESH',
        'operational_planner.pen_id': 'P1',
        'operational_planner.limit_per_bucket': 40,
        'operational_planner.selected_item_id': 'P1',
    }
    dw_state = extract_saved_view_state(page_key='daily_worklists_by_role', session_state=sess)
    planner_state = extract_saved_view_state(page_key='operational_planner', session_state=sess)
    assert dw_state['daily_worklists_by_role.day'] == '2026-04-04'
    assert dw_state['daily_worklists_by_role.farm_id'] == 'F1'
    assert planner_state['operational_planner.site_id'] == 'S1'
    restored: dict[str, object] = {}
    apply_saved_view_state(page_key='operational_planner', state=planner_state, session_state=restored)
    assert restored['operational_planner.day'] == date(2026, 4, 4)
    assert restored['operational_planner.group_id'] == 'G-FRESH'

    root = Path(__file__).resolve().parents[1]
    page_dw = (root / 'streamlit_app' / 'pages' / '43_Daily_Worklists_By_Role.py').read_text(encoding='utf-8')
    page_planner = (root / 'streamlit_app' / 'pages' / '44_Operational_Planner.py').read_text(encoding='utf-8')
    helper = (root / 'src' / 'core' / 'operational' / 'multi_site.py').read_text(encoding='utf-8')
    docs = (root / 'docs' / 'multi_site_operational_model.md').read_text(encoding='utf-8')
    assumptions = (root / 'docs' / 'assumptions.md').read_text(encoding='utf-8')

    assert 'Consolidated scope / Enterprise view' in page_dw
    assert 'Consolidated scope / Enterprise view' in page_planner
    assert 'build_multi_site_reference' in helper and 'build_explainable_scope_aggregates' in helper
    assert 'single-farm' in docs.lower() and 'lineage' in docs.lower()
    assert '## T28-01 — multi-site operational model' in assumptions



def test_t28_01_format_operational_location_builds_readable_paths() -> None:
    formatted = format_operational_location(row={
        'farm_id': 'F1', 'farm_name': 'North farm',
        'site_id': 'S1', 'site_name': 'Main site',
        'group_id': 'G1', 'group_name': 'Fresh cows',
        'pen_id': 'P1', 'pen_name': 'Fresh pen',
    })
    assert 'North farm' in formatted['physical_location']
    assert 'Fresh cows' in formatted['organizational_location']
    assert 'group:G1' in formatted['lineage_path']
