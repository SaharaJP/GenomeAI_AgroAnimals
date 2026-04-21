from __future__ import annotations

import yaml
from pathlib import Path

from streamlit_app.parity_smoke import build_streamlit_web_parity_report, render_streamlit_parity_markdown


def test_t18_09_parity_report_marks_matching_steps_and_outputs() -> None:
    web = {
        'ok': True,
        'workdir': '/tmp/web',
        'data_version': 'dv_demo',
        'qc_run': 'qc_1',
        'model_version': 'm_1',
        'scoring_run': 's_1',
        'report_version': 'r_1',
        'pack_zip': '/tmp/web/pack.zip',
        'timings': {step: 0.1 for step in ['ingest', 'qc', 'train', 'score', 'report', 'decisions', 'pack']},
        'artifacts': {'pack_zip_exists': True},
    }
    streamlit = {
        'ok': True,
        'workdir': '/tmp/streamlit',
        'data_version': 'dv_demo',
        'qc_run': 'qc_2',
        'model_version': 'm_2',
        'scoring_run': 's_2',
        'report_version': 'r_2',
        'pack_zip': 'artifacts:///pack.zip',
        'timings': {step: 0.2 for step in ['ingest', 'qc', 'train', 'score', 'report', 'decisions', 'pack']},
        'artifacts': {'pack_zip_exists': True},
    }

    report = build_streamlit_web_parity_report(web_result=web, streamlit_result=streamlit)

    assert report['summary']['ok'] is True
    assert report['summary']['failed_steps'] == []
    assert [row['step'] for row in report['steps']] == ['ingest', 'qc', 'train', 'score', 'report', 'decisions', 'pack']
    md = render_streamlit_parity_markdown(report)
    assert '# Streamlit parity report' in md
    assert '| ingest | yes | yes | yes |' in md
    assert '- web: /tmp/web' in md
    assert '- streamlit: /tmp/streamlit' in md


def test_t18_09_parity_report_surfaces_mismatch() -> None:
    web = {
        'ok': True,
        'data_version': 'dv_demo',
        'qc_run': 'qc_1',
        'model_version': 'm_1',
        'scoring_run': 's_1',
        'report_version': 'r_1',
        'pack_zip': '/tmp/web/pack.zip',
        'timings': {step: 0.1 for step in ['ingest', 'qc', 'train', 'score', 'report', 'decisions', 'pack']},
        'artifacts': {'pack_zip_exists': True},
    }
    streamlit = {
        'ok': True,
        'data_version': 'dv_demo',
        'qc_run': 'qc_2',
        'model_version': 'm_2',
        'scoring_run': 's_2',
        'report_version': 'r_2',
        'pack_zip': '',
        'timings': {step: 0.2 for step in ['ingest', 'qc', 'train', 'score', 'report', 'pack']},
        'artifacts': {'pack_zip_exists': False},
    }

    report = build_streamlit_web_parity_report(web_result=web, streamlit_result=streamlit)

    assert report['summary']['ok'] is False
    assert 'decisions' in report['summary']['failed_steps']
    assert any('missing parity key: pack_zip' in item for item in report['summary']['diagnostics'])
    assert any('artifact parity mismatch: pack_zip_exists' in item for item in report['summary']['diagnostics'])


def test_t18_09_ci_workflow_has_streamlit_parity_gate_and_artifacts() -> None:
    workflow = yaml.safe_load(Path('.github/workflows/verify_refactor.yml').read_text(encoding='utf-8'))
    job = workflow['jobs']['gates']
    steps = job['steps']
    names = [step.get('name', '') for step in steps]

    assert 'E2E smoke gate' in names
    assert 'Streamlit parity gate' in names

    web_step = next(step for step in steps if step.get('name') == 'E2E smoke gate')
    assert '--timing-json "$CI_ARTIFACTS_ROOT/web_smoke.json"' in str(web_step.get('run', ''))

    streamlit_step = next(step for step in steps if step.get('name') == 'Streamlit parity gate')
    assert 'bash scripts/run_streamlit_parity_gate.sh' in str(streamlit_step.get('run', ''))
    assert 'CI_WEB_SMOKE_JSON="$CI_ARTIFACTS_ROOT/web_smoke.json"' in str(streamlit_step.get('run', ''))

    upload_step = next(step for step in steps if step.get('name') == 'Upload CI artifacts on failure')
    upload_path = str(upload_step['with']['path'])
    assert '_tmp/ci_streamlit_smoke' in upload_path
    assert 'steps.streamlit_gate.outcome' in str(upload_step.get('if', ''))

    enforce_step = next(step for step in steps if step.get('name') == 'Enforce gates')
    assert 'steps.streamlit_gate.outcome' in str(enforce_step.get('run', ''))


def test_t18_09_gate_scripts_docs_and_pytest_gate_are_wired() -> None:
    entries = [
        line.strip()
        for line in Path('ci/pytest_gate.txt').read_text(encoding='utf-8').splitlines()
        if line.strip() and not line.lstrip().startswith('#')
    ]
    assert 'tests/test_t18_09_streamlit_parity_gates.py' in entries

    gate_script = Path('scripts/run_streamlit_parity_gate.sh').read_text(encoding='utf-8')
    assert 'scripts/smoke_t18_09_streamlit_parity.py' in gate_script
    assert 'scripts/smoke_t18_09_streamlit_roles.py' in gate_script
    assert 'streamlit_parity_report.json' in gate_script
    assert 'streamlit_role_smoke.json' in gate_script

    doc = Path('docs/streamlit_parity_gates.md').read_text(encoding='utf-8')
    ci_doc = Path('docs/ci_gates.md').read_text(encoding='utf-8')
    readme = Path('README.md').read_text(encoding='utf-8')
    project_map = Path('docs/project_map.md').read_text(encoding='utf-8')
    assert 'scripts/run_streamlit_parity_gate.sh' in doc
    assert 'streamlit_parity_report.md' in doc
    assert 'Streamlit parity gate' in ci_doc
    assert 'streamlit_role_smoke.json' in ci_doc
    assert 'docs/streamlit_parity_gates.md' in readme
    assert 'Streamlit parity smoke' in project_map
