from __future__ import annotations

import yaml
from pathlib import Path

from streamlit_app.parity_smoke import build_streamlit_acceptance_report, render_streamlit_acceptance_markdown



def test_t19_14_acceptance_report_is_ready_when_all_gates_pass() -> None:
    parity = {'schema': 'parity.v1', 'summary': {'ok': True, 'diagnostics': []}}
    role = {'schema': 'role.v1', 'ok': True, 'diagnostics': []}
    role_ux = {'schema': 'roleux.v1', 'ok': True, 'diagnostics': []}
    report_admin = {
        'schema': 'reportadmin.v1',
        'checks': {
            'report_artifact_present': True,
            'report_approve': True,
            'support_bundle': True,
            'support_bundle_count': True,
        },
        'diagnostics': [],
    }

    report = build_streamlit_acceptance_report(
        parity_report=parity,
        role_smoke=role,
        role_ux_smoke=role_ux,
        report_admin_smoke=report_admin,
    )

    assert report['summary']['ok'] is True
    assert report['summary']['ready_for_manual_uat'] is True
    assert [row['gate'] for row in report['gates']] == ['navigation', 'role_visibility', 'operational_flow', 'report_flow', 'admin_flow']
    md = render_streamlit_acceptance_markdown(report)
    assert '# Streamlit final parity + UX acceptance' in md
    assert '| navigation | yes | role shell visibility + hidden detail pages |' in md
    assert '| UAT-01 | Operator | Navigation |' in md



def test_t19_14_acceptance_report_surfaces_failed_gate() -> None:
    parity = {'schema': 'parity.v1', 'summary': {'ok': False, 'diagnostics': ['step mismatch']}}
    role = {'schema': 'role.v1', 'ok': True, 'diagnostics': []}
    role_ux = {'schema': 'roleux.v1', 'ok': False, 'diagnostics': ['Director: missing visible shell items']}
    report_admin = {
        'schema': 'reportadmin.v1',
        'checks': {
            'report_artifact_present': False,
            'report_approve': False,
            'support_bundle': True,
            'support_bundle_count': True,
        },
        'diagnostics': ['report_artifact_present', 'report_approve'],
    }

    report = build_streamlit_acceptance_report(
        parity_report=parity,
        role_smoke=role,
        role_ux_smoke=role_ux,
        report_admin_smoke=report_admin,
    )

    assert report['summary']['ok'] is False
    assert 'navigation failed' in report['summary']['diagnostics']
    assert 'operational_flow failed' in report['summary']['diagnostics']
    assert 'report_flow failed' in report['summary']['diagnostics']



def test_t19_14_gate_script_docs_and_ci_wiring_are_present() -> None:
    entries = [
        line.strip()
        for line in Path('ci/pytest_gate.txt').read_text(encoding='utf-8').splitlines()
        if line.strip() and not line.lstrip().startswith('#')
    ]
    assert 'tests/test_t19_14_streamlit_final_gates.py' in entries

    gate_script = Path('scripts/run_streamlit_parity_gate.sh').read_text(encoding='utf-8')
    assert 'scripts/smoke_t19_14_streamlit_final_gates.py' in gate_script
    assert 'streamlit_role_ux_smoke.json' in gate_script
    assert 'streamlit_acceptance_report.json' in gate_script
    assert 'streamlit_acceptance_report.md' in gate_script

    smoke_script = Path('scripts/smoke_t19_14_streamlit_final_gates.py').read_text(encoding='utf-8')
    assert 'run_streamlit_role_ux_smoke' in smoke_script
    assert 'build_streamlit_acceptance_report' in smoke_script

    workflow = yaml.safe_load(Path('.github/workflows/verify_refactor.yml').read_text(encoding='utf-8'))
    steps = workflow['jobs']['gates']['steps']
    streamlit_step = next(step for step in steps if step.get('name') == 'Streamlit parity gate')
    assert 'bash scripts/run_streamlit_parity_gate.sh' in str(streamlit_step.get('run', ''))

    upload_step = next(step for step in steps if step.get('name') == 'Upload CI artifacts on failure')
    upload_path = str(upload_step['with']['path'])
    assert 'artifacts/_ci' in upload_path
    assert '_tmp/ci_streamlit_smoke' in upload_path

    final_doc = Path('docs/streamlit_final_gates.md').read_text(encoding='utf-8')
    ci_doc = Path('docs/ci_gates.md').read_text(encoding='utf-8')
    parity_doc = Path('docs/streamlit_parity_gates.md').read_text(encoding='utf-8')
    readme = Path('README.md').read_text(encoding='utf-8')
    assert 'streamlit_acceptance_report.md' in final_doc
    assert 'Streamlit final parity gate' in ci_doc
    assert 'final Streamlit gates' in parity_doc
    assert 'docs/streamlit_final_gates.md' in readme
