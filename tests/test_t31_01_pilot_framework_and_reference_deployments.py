from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys

from core.pilot_framework import (
    build_pilot_framework_summary,
    load_pilot_framework_config,
    load_pilot_records,
    render_pilot_framework_markdown,
)

ROOT = Path(__file__).resolve().parents[1]


def test_t31_01_summary_builds_and_preserves_traceability() -> None:
    summary = build_pilot_framework_summary(project_root='.')
    assert summary['schema'] == 'genomeai.pilot_framework_summary.v1'
    assert summary['pilot_count'] == 3
    assert summary['pilot_range_ok'] is True
    assert summary['open_support_cases'] >= 2
    assert summary['referenceable_count'] == 0
    assert summary['version_linkage_ok_count'] == 3
    assert 'versions, support cases and incidents' in summary['traceability_statement']
    assert any(row['status'] == 'active' for row in summary['pilot_rows'])


def test_t31_01_config_and_records_are_explicit_about_evidence_rules() -> None:
    cfg = load_pilot_framework_config()
    records = load_pilot_records(ROOT / 'data/pilots/pilot_framework_v1/pilot_records_v1.json')
    assert cfg['framework']['target_pilot_range'] == [2, 5]
    assert 'customer_signoff' in cfg['framework']['reference_deployment_rules']['required_manual_evidence']
    assert records['record_mode'] == 'starter_sample'
    assert 'not evidence of real customer rollout readiness' in records['synthetic_note']


def test_t31_01_markdown_contains_status_board_and_reference_records() -> None:
    md = render_pilot_framework_markdown(build_pilot_framework_summary(project_root='.'))
    assert '# Pilot framework and reference deployments' in md
    assert '## Pilot status board' in md
    assert '## Reference deployment records' in md
    assert 'pilot_alpha_north' in md


def test_t31_01_page_docs_and_wiring_are_present() -> None:
    page = (ROOT / 'streamlit_app/pages/74_Pilot_Framework_And_Reference_Deployments.py').read_text(encoding='utf-8')
    widget = (ROOT / 'streamlit_app/pilot_framework.py').read_text(encoding='utf-8')
    docs = (ROOT / 'docs/pilot_framework_and_reference_deployments.md').read_text(encoding='utf-8')
    ia = (ROOT / 'configs/ui/ia_v3.yaml').read_text(encoding='utf-8')
    assumptions = (ROOT / 'docs/assumptions.md').read_text(encoding='utf-8')
    readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    project_map = (ROOT / 'docs/project_map.md').read_text(encoding='utf-8')
    pytest_gate = (ROOT / 'ci/pytest_gate.txt').read_text(encoding='utf-8')
    demo_page = (ROOT / 'streamlit_app/pages/71_Demo_Farm_And_Benchmark_Demos.py').read_text(encoding='utf-8')
    packaging_page = (ROOT / 'streamlit_app/pages/72_Commercial_Packaging_And_Editions.py').read_text(encoding='utf-8')
    replacement_page = (ROOT / 'streamlit_app/pages/73_Replacement_Narratives_And_Win_Themes.py').read_text(encoding='utf-8')

    assert 'Pilot framework и reference deployments' in page
    assert 'render_pilot_framework_widget' in widget
    assert 'runnable pilot tracking contour' in docs.lower()
    assert 'pages/74_Pilot_Framework_And_Reference_Deployments.py' in ia
    assert 'pilot_framework_and_reference_deployments' in ia
    assert 'T31-01 — Pilot framework и reference deployments' in assumptions
    assert 'docs/pilot_framework_and_reference_deployments.md' in readme
    assert 'pilot framework' in project_map.lower()
    assert 'tests/test_t31_01_pilot_framework_and_reference_deployments.py' in pytest_gate
    assert 'pages/74_Pilot_Framework_And_Reference_Deployments.py' in demo_page
    assert 'pages/74_Pilot_Framework_And_Reference_Deployments.py' in packaging_page
    assert 'pages/74_Pilot_Framework_And_Reference_Deployments.py' in replacement_page


def test_t31_01_smoke_runner_writes_reports(tmp_path: Path) -> None:
    report_root = tmp_path / 'pilot_framework_report'
    cmd = [
        sys.executable,
        'scripts/smoke_t31_01_pilot_framework.py',
        '--project-root',
        '.',
        '--report-root',
        str(report_root),
    ]
    proc = subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True)
    assert 'PILOT_FRAMEWORK_READY' in proc.stdout
    payload = json.loads((report_root / 'pilot_framework_report.json').read_text(encoding='utf-8'))
    assert payload['pilot_count'] == 3
    assert (report_root / 'pilot_framework_report.md').exists()
