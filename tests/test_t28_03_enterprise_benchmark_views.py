from __future__ import annotations

from datetime import date
from pathlib import Path

from core.operational import build_benchmark_compare_view, build_enterprise_dashboard_snapshot, build_top_issue_matrix
from streamlit_app.enterprise_benchmark_views import build_benchmark_table


def _rows() -> list[dict[str, object]]:
    return [
        {
            'planner_item_id': 'I1', 'farm_id': 'F1', 'farm_name': 'North farm', 'site_id': 'S1', 'site_name': 'Main site',
            'group_id': 'G1', 'group_name': 'Fresh cows', 'priority': 1, 'bucket': 'overdue', 'object_type': 'animal',
            'object_id': 'A1', 'source_kind': 'worklist', 'worklist_type': 'vet',
        },
        {
            'planner_item_id': 'I2', 'farm_id': 'F1', 'farm_name': 'North farm', 'site_id': 'S1', 'site_name': 'Main site',
            'group_id': 'G1', 'group_name': 'Fresh cows', 'priority': 2, 'bucket': 'today', 'object_type': 'animal',
            'object_id': 'A2', 'source_kind': 'alert', 'worklist_type': 'vet',
        },
        {
            'planner_item_id': 'I3', 'farm_id': 'F1', 'farm_name': 'North farm', 'site_id': 'S2', 'site_name': 'Remote site',
            'group_id': 'G2', 'group_name': 'Breed queue', 'priority': 3, 'bucket': 'today', 'object_type': 'animal',
            'object_id': 'A3', 'source_kind': 'worklist', 'worklist_type': 'reproduction',
        },
        {
            'planner_item_id': 'I4', 'farm_id': 'F2', 'farm_name': 'South farm', 'site_id': 'S3', 'site_name': 'South-1',
            'group_id': 'G3', 'group_name': 'Hospital', 'priority': 1, 'bucket': 'overdue', 'object_type': 'animal',
            'object_id': 'A4', 'source_kind': 'worklist', 'worklist_type': 'vet',
        },
        {
            'planner_item_id': 'I5', 'farm_id': 'F2', 'farm_name': 'South farm', 'site_id': 'S3', 'site_name': 'South-1',
            'group_id': 'G4', 'group_name': 'Dry cows', 'priority': 4, 'bucket': 'this_week', 'object_type': 'group',
            'object_id': 'G4', 'source_kind': 'follow_up', 'worklist_type': 'manager_review',
        },
    ]


def test_t28_03_builds_enterprise_summary_and_site_compare() -> None:
    snapshot = build_enterprise_dashboard_snapshot(_rows())
    summary = dict(snapshot['summary'])
    assert summary['items_total'] == 5
    assert summary['farms_n'] == 2
    assert summary['sites_n'] == 3
    assert summary['groups_n'] == 4
    assert summary['overdue'] == 2
    assert summary['high_priority'] == 3

    site_rows = list(snapshot['by_site'])
    assert len(site_rows) == 3
    top = site_rows[0]
    assert 'benchmark_basis' in top
    assert 'visible sibling scopes' in str(top['benchmark_basis'])
    assert 'top_issue_hint' in top

    north_main = next(r for r in site_rows if str(r.get('site_id')) == 'S1')
    assert north_main['items_total'] == 2
    assert north_main['overdue'] == 1
    assert north_main['high_priority'] == 2
    assert float(north_main['overdue_rate']) > 0
    assert int(north_main['sibling_count']) >= 2


def test_t28_03_group_benchmark_and_top_issues_are_explainable() -> None:
    group_df = build_benchmark_compare_view(_rows(), level='group')
    assert not group_df.empty
    g1 = group_df[group_df['group_id'].astype(str) == 'G1'].iloc[0].to_dict()
    assert g1['items_total'] == 2
    assert g1['overdue'] == 1
    assert 'median of visible sibling scopes' in str(g1['benchmark_basis'])

    issues = build_top_issue_matrix(_rows(), level='site', limit=10)
    assert not issues.empty
    first = issues.iloc[0].to_dict()
    assert 'issue_key' in first and first['issue_key'] in {'vet', 'reproduction', 'manager_review'}
    assert 'Open planner/worklists' in str(first['action_hint'])

    table = build_benchmark_table(group_df.to_dict(orient='records'))
    assert 'scope' in table.columns
    assert 'deviation_score' in table.columns


def test_t28_03_docs_and_page_wiring_are_present() -> None:
    root = Path(__file__).resolve().parents[1]
    page = (root / 'streamlit_app' / 'pages' / '68_Enterprise_Benchmark_Views.py').read_text(encoding='utf-8')
    summary_page = (root / 'streamlit_app' / 'pages' / '1_Director_Summary.py').read_text(encoding='utf-8')
    helper = (root / 'src' / 'core' / 'operational' / 'enterprise_benchmark.py').read_text(encoding='utf-8')
    docs = (root / 'docs' / 'enterprise_benchmark_views.md').read_text(encoding='utf-8')
    assumptions = (root / 'docs' / 'assumptions.md').read_text(encoding='utf-8')

    assert 'Enterprise dashboards и benchmark views' in page
    assert 'Site comparison' in page and 'Group benchmark' in page
    assert 'Open operational planner' in page and 'Open daily worklists' in page
    assert '68_Enterprise_Benchmark_Views.py' in summary_page
    assert 'build_enterprise_dashboard_snapshot' in helper and 'build_benchmark_compare_view' in helper
    assert 'benchmark' in docs.lower() and 'sibling median' in docs.lower() and 'action surfaces' in docs.lower()
    assert '## T28-03 — enterprise dashboards и benchmark views' in assumptions
