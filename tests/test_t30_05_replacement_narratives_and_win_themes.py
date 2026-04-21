from __future__ import annotations

from pathlib import Path

from core.commercial_packaging import load_runtime_packaging_context
from core.replacement_narratives import (
    build_replacement_narratives_summary,
    load_replacement_narratives_config,
    render_replacement_narratives_markdown,
)

ROOT = Path(__file__).resolve().parents[1]


def test_t30_05_summary_builds_from_actual_product_sources() -> None:
    summary = build_replacement_narratives_summary(project_root='.')
    assert summary['profile_name'] == 'legacy_replacement_ci'
    assert summary['runtime_packaging']['edition_key'] == 'enterprise'
    assert len(summary['themes']) >= 5
    assert 'actual pages, docs, tests, scripts' in summary['source_statement']
    pp = summary['proof_points']['pp_competitive_acceptance']
    assert 'migration' in pp['acceptance_scenarios']
    assert any(nav['key'] == 'admin_observability_release' for nav in pp['nav_refs'])
    assert summary['proof_points']['pp_demo_benchmark']['demo_scenarios']


def test_t30_05_foundation_packaging_disables_enterprise_replacement_proof_points() -> None:
    foundation = build_replacement_narratives_summary(
        project_root='.',
        env={'GENOMEAI_COMMERCIAL_PROFILE': 'foundation_default'},
    )
    assert foundation['runtime_packaging']['edition_key'] == 'foundation'
    assert foundation['proof_points']['pp_demo_benchmark']['enabled'] is False
    assert foundation['proof_points']['pp_migration_verification']['enabled'] is False
    assert foundation['proof_points']['pp_training_by_role']['enabled'] is True


def test_t30_05_markdown_and_config_contain_checklists_feature_maps_and_not_claimed() -> None:
    cfg = load_replacement_narratives_config()
    assert 'daily_operations_parity' in cfg['themes']
    assert 'pre_sales' in cfg['compare_checklists']
    assert 'parity_map' in cfg['feature_maps']

    summary = build_replacement_narratives_summary(project_root='.')
    md = render_replacement_narratives_markdown(summary)
    assert '# Replacement narratives and win themes' in md
    assert '## Win themes' in md
    assert '## Compare checklists' in md
    assert 'Daily operations parity' in md


def test_t30_05_page_docs_and_wiring_are_present() -> None:
    page = (ROOT / 'streamlit_app' / 'pages' / '73_Replacement_Narratives_And_Win_Themes.py').read_text(encoding='utf-8')
    widget = (ROOT / 'streamlit_app' / 'replacement_narratives.py').read_text(encoding='utf-8')
    docs = (ROOT / 'docs' / 'replacement_narratives_and_win_themes.md').read_text(encoding='utf-8')
    ia = (ROOT / 'configs' / 'ui' / 'ia_v3.yaml').read_text(encoding='utf-8')
    assumptions = (ROOT / 'docs' / 'assumptions.md').read_text(encoding='utf-8')
    readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    project_map = (ROOT / 'docs' / 'project_map.md').read_text(encoding='utf-8')
    pytest_gate = (ROOT / 'ci' / 'pytest_gate.txt').read_text(encoding='utf-8')
    demo_page = (ROOT / 'streamlit_app' / 'pages' / '71_Demo_Farm_And_Benchmark_Demos.py').read_text(encoding='utf-8')
    packaging_page = (ROOT / 'streamlit_app' / 'pages' / '72_Commercial_Packaging_And_Editions.py').read_text(encoding='utf-8')

    assert 'Replacement narratives и win themes' in page
    assert 'render_replacement_narratives_widget' in widget
    assert 'product-backed' in docs.lower()
    assert 'proof points' in docs.lower()
    assert 'pages/73_Replacement_Narratives_And_Win_Themes.py' in ia
    assert 'replacement_narratives_and_win_themes' in ia
    assert 'T30-05 — Win themes и replacement narratives' in assumptions
    assert 'docs/replacement_narratives_and_win_themes.md' in readme
    assert 'replacement narratives' in project_map.lower()
    assert 'tests/test_t30_05_replacement_narratives_and_win_themes.py' in pytest_gate
    assert 'pages/73_Replacement_Narratives_And_Win_Themes.py' in demo_page
    assert 'pages/73_Replacement_Narratives_And_Win_Themes.py' in packaging_page
