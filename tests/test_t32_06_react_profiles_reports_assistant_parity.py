from pathlib import Path


def test_t32_06_files_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    expected = [
        root / 'web_app' / 'app' / '(protected)' / 'profiles' / '[objectType]' / '[objectId]' / 'page.tsx',
        root / 'web_app' / 'app' / '(protected)' / 'reports' / '[dataVersion]' / '[reportVersion]' / 'page.tsx',
        root / 'web_app' / 'components' / 'profiles' / 'profile-surface.tsx',
        root / 'web_app' / 'components' / 'reports' / 'report-catalog-surface.tsx',
        root / 'web_app' / 'components' / 'reports' / 'report-view-surface.tsx',
        root / 'web_app' / 'components' / 'reports' / 'report-governance-panel.tsx',
        root / 'web_app' / 'components' / 'assistant' / 'assistant-entry-points.tsx',
        root / 'web_app' / 'components' / 'decision' / 'decision-intelligence-widgets.tsx',
        root / 'web_app' / 'components' / 'explainability' / 'fact-pack-guardrail-note.tsx',
        root / 'web_app' / 'components' / 'explainability' / 'source-linkage-panel.tsx',
        root / 'web_app' / 'components' / 'explainability' / 'object-explainability-panel.tsx',
        root / 'web_app' / 'lib' / 'api' / 'profiles-reports-assistant.ts',
        root / 'web_app' / 'app' / 'api' / 'report-governance' / '[dataVersion]' / '[reportVersion]' / 'route.ts',
        root / 'docs' / 'react_profiles_reports_assistant_parity.md',
    ]
    missing = [str(path.relative_to(root)) for path in expected if not path.exists()]
    assert not missing, f'Missing T32-06 artifacts: {missing}'


def test_t32_06_docs_keep_fact_pack_only_and_no_invented_explanations() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = (root / 'docs' / 'react_profiles_reports_assistant_parity.md').read_text(encoding='utf-8')
    assert 'fact-pack only' in doc
    assert 'invent factors/explanations' in doc
    assert 'source linkage' in doc
    assert 'Streamlit не нужен' in doc


def test_t32_06_reuses_shared_explainability_components() -> None:
    root = Path(__file__).resolve().parents[1]
    profile_surface = (root / 'web_app' / 'components' / 'profiles' / 'profile-surface.tsx').read_text(encoding='utf-8')
    report_surface = (root / 'web_app' / 'components' / 'reports' / 'report-view-surface.tsx').read_text(encoding='utf-8')
    assert 'ObjectExplainabilityPanel' in profile_surface
    assert 'SourceLinkagePanel' in profile_surface
    assert 'AssistantEntryPoints' in profile_surface
    assert 'DecisionIntelligenceWidgets' in profile_surface
    assert 'ObjectExplainabilityPanel' in report_surface
    assert 'SourceLinkagePanel' in report_surface
    assert 'AssistantEntryPoints' in report_surface
    assert 'ReportGovernancePanel' in report_surface


def test_t32_06_report_governance_bff_stays_server_side() -> None:
    root = Path(__file__).resolve().parents[1]
    route = (root / 'web_app' / 'app' / 'api' / 'report-governance' / '[dataVersion]' / '[reportVersion]' / 'route.ts').read_text(encoding='utf-8')
    assert '/api/reports_v1/approval' in route
    assert '/api/reports_v1/' in route
    assert 'backendFetch' in route
    assert 'approve' in route and 'reject' in route and 'archive' in route
