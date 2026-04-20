import json
from pathlib import Path


def test_t32_05_daily_operations_files_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    expected = [
        root / 'web_app' / 'app' / '(protected)' / 'daily-summary' / 'page.tsx',
        root / 'web_app' / 'app' / '(protected)' / 'alerts' / 'page.tsx',
        root / 'web_app' / 'app' / '(protected)' / 'worklists' / 'page.tsx',
        root / 'web_app' / 'app' / '(protected)' / 'planner' / 'page.tsx',
        root / 'web_app' / 'components' / 'operations' / 'daily-operations-dashboard.tsx',
        root / 'web_app' / 'components' / 'operations' / 'alerts-surface.tsx',
        root / 'web_app' / 'components' / 'operations' / 'worklists-surface.tsx',
        root / 'web_app' / 'components' / 'operations' / 'planner-surface.tsx',
        root / 'web_app' / 'components' / 'operations' / 'daily-brief-preview.tsx',
        root / 'web_app' / 'lib' / 'api' / 'daily-operations.ts',
        root / 'docs' / 'react_daily_operations_parity.md',
        root / 'configs' / 'parity' / 'react_daily_operations_parity_v1.json',
    ]
    missing = [str(path.relative_to(root)) for path in expected if not path.exists()]
    assert not missing, f'Missing T32-05 artifacts: {missing}'


def test_t32_05_doc_records_post_removal_status() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = (root / 'docs' / 'react_daily_operations_parity.md').read_text(encoding='utf-8')
    assert 'не' in doc.lower()
    assert 'formal cutover completed' in doc
    assert 'removed in T32-12' in doc


def test_t32_05_parity_map_references_real_legacy_and_react_surfaces() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = json.loads((root / 'configs' / 'parity' / 'react_daily_operations_parity_v1.json').read_text(encoding='utf-8'))
    assert payload['schema'] == 'genomeai.react.daily_operations.parity.v1'
    assert payload['formal_cutover_allowed'] is True
    for item in payload['legacy_surfaces']:
        react_route = item['react_route']
        assert react_route.startswith('/')
        assert item.get('legacy_status') == 'removed_after_t32_12'
    routes_doc = (root / 'web_app' / 'lib' / 'navigation.ts').read_text(encoding='utf-8')
    for route in ['/daily-summary', '/alerts', '/worklists', '/planner']:
        assert route in routes_doc


def test_t32_05_dashboard_declares_multi_site_and_hooks() -> None:
    root = Path(__file__).resolve().parents[1]
    dashboard = (root / 'web_app' / 'components' / 'operations' / 'daily-operations-dashboard.tsx').read_text(encoding='utf-8')
    assert 'multi-site' in dashboard
    assert 'Decision / feedback trail' in dashboard
    assert 'legacy Streamlit removed' in dashboard
