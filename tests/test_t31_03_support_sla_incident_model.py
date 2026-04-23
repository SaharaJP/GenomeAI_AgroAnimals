from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys

from core.support_sla_incident import (
    append_incident,
    append_support_case,
    build_support_sla_incident_summary,
    load_support_operating_records,
    load_support_sla_incident_policy,
    render_support_sla_incident_markdown,
)

ROOT = Path(__file__).resolve().parents[1]


def test_t31_03_summary_builds_with_traceable_incidents_and_support_bundle_usage(tmp_path: Path) -> None:
    web_storage = tmp_path / 'web_storage'
    artifacts = tmp_path / 'artifacts'
    (artifacts / 'support_bundles').mkdir(parents=True, exist_ok=True)
    (artifacts / 'support_bundles' / 'bundle_demo.zip').write_bytes(b'PK\x05\x06' + b'\x00' * 18)
    report_dir = artifacts / '_ci' / 'ops'
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / 'performance_gates_report.json').write_text('{"summary":{"ok":true}}', encoding='utf-8')
    payload = build_support_sla_incident_summary(project_root='.', artifacts_dir=artifacts, web_storage_dir=web_storage)
    summary = payload['summary']
    assert payload['schema'] == 'genomeai.support_sla_incident_summary.v1'
    assert summary['open_support_cases'] >= 1
    assert summary['critical_open_incidents'] >= 1
    assert summary['support_bundle_count'] == 1
    assert 'diagnostics, support bundle usage and version context' in payload['traceability_statement']
    assert any(row['available'] is True for row in payload['diagnostics_reports'])


def test_t31_03_append_case_and_incident_write_runtime_records(tmp_path: Path) -> None:
    web_storage = tmp_path / 'web_storage'
    case = append_support_case(project_root='.', web_storage_dir=web_storage, customer_label='Demo Customer', severity='SEV2', title='Need support bundle', release_note_id='REL-2026.04.1')
    inc = append_incident(project_root='.', web_storage_dir=web_storage, customer_label='Demo Customer', severity='SEV1', title='Critical outage', diagnostics_ref='performance_gates', support_bundle_ref='support_bundle_demo.zip', release_note_id='REL-2026.04.1')
    payload = load_support_operating_records(project_root='.', web_storage_dir=web_storage)
    assert any(row['case_id'] == case['case_id'] for row in payload['support_cases'])
    assert any(row['incident_id'] == inc['incident_id'] for row in payload['incidents'])
    assert payload['_record_source_mode'] == 'runtime'


def test_t31_03_policy_and_markdown_are_explicit_about_supported_targets_only() -> None:
    cfg = load_support_sla_incident_policy()
    md = render_support_sla_incident_markdown(build_support_sla_incident_summary(project_root='.'))
    assert 'SEV1' in cfg['support_model']['severity_levels']
    assert 'Support / incident coordinator' in cfg['support_model']['escalation_paths']['SEV1'][0]
    assert '# Support / SLA / incident model' in md
    assert '## Support cases' in md
    assert '## Incidents' in md


def test_t31_03_page_docs_and_wiring_are_present() -> None:
    page = (ROOT / 'streamlit_app/pages/76_Support_SLA_Incident_Model.py').read_text(encoding='utf-8')
    widget = (ROOT / 'streamlit_app/support_sla_incident.py').read_text(encoding='utf-8')
    docs = (ROOT / 'docs/support_sla_incident_model.md').read_text(encoding='utf-8')
    ia = (ROOT / 'configs/ui/ia_v3.yaml').read_text(encoding='utf-8')
    assumptions = (ROOT / 'docs/assumptions.md').read_text(encoding='utf-8')
    readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    project_map = (ROOT / 'docs/project_map.md').read_text(encoding='utf-8')
    pytest_gate = (ROOT / 'ci/pytest_gate.txt').read_text(encoding='utf-8')
    page37 = (ROOT / 'streamlit_app/pages/37_Admin_Observability_Release.py').read_text(encoding='utf-8')
    page74 = (ROOT / 'streamlit_app/pages/74_Pilot_Framework_And_Reference_Deployments.py').read_text(encoding='utf-8')

    assert 'Support / SLA / incident model' in page
    assert 'render_support_sla_incident_widget' in widget
    assert 'runnable support operating contour' in docs.lower()
    assert 'pages/76_Support_SLA_Incident_Model.py' in ia
    assert 'support_sla_incident_model' in ia
    assert 'T31-03 — Support / SLA / incident operating model' in assumptions
    assert 'docs/support_sla_incident_model.md' in readme
    assert 'support / sla / incident' in project_map.lower()
    assert 'tests/test_t31_03_support_sla_incident_model.py' in pytest_gate
    assert 'support_sla_incidents' in page37
    assert 'pages/76_Support_SLA_Incident_Model.py' in page74


def test_t31_03_smoke_runner_writes_reports(tmp_path: Path) -> None:
    report_root = tmp_path / 'support_sla_report'
    cmd = [
        sys.executable,
        'scripts/smoke_t31_03_support_sla_incident_model.py',
        '--project-root',
        '.',
        '--artifacts-dir',
        str(tmp_path / 'artifacts'),
        '--web-storage-dir',
        str(tmp_path / 'web_storage'),
        '--report-root',
        str(report_root),
    ]
    proc = subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True)
    assert 'SUPPORT_SLA_INCIDENT_READY' in proc.stdout
    payload = json.loads((report_root / 'support_sla_incident_report.json').read_text(encoding='utf-8'))
    assert payload['summary']['open_support_cases'] >= 1
    assert (report_root / 'support_sla_incident_report.md').exists()
