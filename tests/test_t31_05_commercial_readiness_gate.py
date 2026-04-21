from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from core.commercial_readiness_gate import build_commercial_readiness_report, load_commercial_readiness_policy, render_commercial_readiness_markdown

ROOT = Path(__file__).resolve().parents[1]


def test_t31_05_builds_honest_readiness_report_from_existing_evidence() -> None:
    report = build_commercial_readiness_report(project_root='.', artifacts_root='artifacts')
    summary = report['summary']
    assert report['schema'] == 'genomeai.commercial_readiness_gate.v1'
    assert summary['product_ready'] in {'ready', 'partial', 'not_ready'}
    assert summary['pilot_ready'] in {'ready', 'partial', 'not_ready'}
    assert summary['commercially_ready'] in {'ready', 'partial', 'not_ready'}
    assert any(row['key'] == 'reference_deployments' for row in report['domain_rows'])
    assert report['evidence_pack']['required_sections'] >= 6
    assert 'missing field evidence is treated as not-ready' in summary['statement']


def test_t31_05_current_archive_does_not_overclaim_commercial_readiness() -> None:
    report = build_commercial_readiness_report(project_root='.', artifacts_root='artifacts')
    summary = report['summary']
    assert summary['commercially_ready'] == 'not_ready'
    assert any('reference deployment' in str(item['reason']).lower() or 'referenceable' in str(item['reason']).lower() for item in report['blockers'])


def test_t31_05_policy_and_markdown_are_explicit() -> None:
    policy = load_commercial_readiness_policy(project_root='.')
    md = render_commercial_readiness_markdown(build_commercial_readiness_report(project_root='.', artifacts_root='artifacts'))
    assert policy['thresholds']['commercially_ready']['min_referenceable_deployments'] == 1
    assert '# Commercial readiness gate' in md
    assert '## Market-launch checklist' in md
    assert '## Evidence pack' in md


def test_t31_05_page_docs_and_wiring_are_present() -> None:
    page = (ROOT / 'streamlit_app/pages/78_Commercial_Readiness_Gate.py').read_text(encoding='utf-8')
    widget = (ROOT / 'streamlit_app/commercial_readiness_gate.py').read_text(encoding='utf-8')
    docs = (ROOT / 'docs/commercial_readiness_gate.md').read_text(encoding='utf-8')
    ia = (ROOT / 'configs/ui/ia_v3.yaml').read_text(encoding='utf-8')
    assumptions = (ROOT / 'docs/assumptions.md').read_text(encoding='utf-8')
    readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    project_map = (ROOT / 'docs/project_map.md').read_text(encoding='utf-8')
    pytest_gate = (ROOT / 'ci/pytest_gate.txt').read_text(encoding='utf-8')
    page37 = (ROOT / 'streamlit_app/pages/37_Admin_Observability_Release.py').read_text(encoding='utf-8')
    admin_console = (ROOT / 'streamlit_app/admin_console.py').read_text(encoding='utf-8')

    assert 'Commercial readiness gate' in page
    assert 'render_commercial_readiness_widget' in widget
    assert 'evidence-backed final readiness gate' in docs.lower()
    assert 'pages/78_Commercial_Readiness_Gate.py' in ia
    assert 'commercial_readiness_gate' in ia
    assert 'T31-05 — Commercial readiness gate and market-launch checklist' in assumptions
    assert 'docs/commercial_readiness_gate.md' in readme
    assert 'commercial readiness gate' in project_map.lower()
    assert 'tests/test_t31_05_commercial_readiness_gate.py' in pytest_gate
    assert 'commercial_readiness' in page37
    assert 'commercial_readiness_diagnostics' in admin_console


def test_t31_05_smoke_runner_writes_reports(tmp_path: Path) -> None:
    report_root = tmp_path / 'commercial_readiness'
    cmd = [
        sys.executable,
        'scripts/smoke_t31_05_commercial_readiness_gate.py',
        '--project-root',
        '.',
        '--artifacts-root',
        'artifacts',
        '--report-root',
        str(report_root),
    ]
    proc = subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True)
    assert 'COMMERCIAL_READINESS_GATE_READY' in proc.stdout
    payload = json.loads((report_root / 'commercial_readiness_report.json').read_text(encoding='utf-8'))
    assert payload['summary']['commercially_ready'] == 'not_ready'
    assert (report_root / 'commercial_readiness_report.md').exists()
    assert (report_root / 'commercial_readiness_evidence_pack.json').exists()
