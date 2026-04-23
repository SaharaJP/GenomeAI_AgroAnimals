from __future__ import annotations

import json
from pathlib import Path

import yaml

from core.observability.competitive_acceptance import (
    load_competitive_acceptance_policy,
    render_competitive_acceptance_cli_lines,
    run_competitive_acceptance_set,
)
from streamlit_app.admin_console import competitive_acceptance_diagnostics


def test_t30_01_policy_loads_legacy_replacement_profile() -> None:
    policy = load_competitive_acceptance_policy(project_root='.')
    assert policy['profile_name'] == 'legacy_replacement_ci'
    assert set(policy['profile']) == {
        'daily_operations',
        'reproduction',
        'vet',
        'reports_worklists',
        'mobile',
        'migration',
    }
    assert policy['artifact_aliases']['streamlit_acceptance'].endswith('streamlit_acceptance_report.json')



def test_t30_01_runner_marks_ready_for_manual_signoff_without_manual_evidence(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        'core.observability.competitive_acceptance._evaluate_artifact_checks',
        lambda **kwargs: {'ok': True, 'duration_sec': 0.0, 'diagnostics': [], 'checks': [{'kind': 'artifact_report', 'target': 'stub', 'ok': True}]},
    )
    monkeypatch.setattr(
        'core.observability.competitive_acceptance._run_pytest_bundle',
        lambda **kwargs: {'ok': True, 'duration_sec': 0.2, 'diagnostics': [], 'checks': [{'kind': 'pytest', 'target': 'stub', 'ok': True}]},
    )
    monkeypatch.setattr(
        'core.observability.competitive_acceptance._run_script_bundle',
        lambda **kwargs: {'ok': True, 'duration_sec': 0.1, 'diagnostics': [], 'checks': [{'kind': 'script', 'target': 'stub', 'ok': True}]},
    )
    monkeypatch.setattr(
        'core.observability.competitive_acceptance._evaluate_required_files',
        lambda **kwargs: {'ok': True, 'duration_sec': 0.0, 'diagnostics': [], 'checks': [{'kind': 'required_file', 'target': 'stub', 'ok': True}]},
    )

    report_root = tmp_path / 'report'
    report = run_competitive_acceptance_set(project_root='.', artifacts_root='artifacts', report_root=report_root, scenarios=['daily_operations'])
    assert report['summary']['ok'] is True
    assert report['summary']['ready_for_competitive_uat'] is True
    assert report['summary']['product_ready_count'] == 0
    row = report['scenarios'][0]
    assert row['scenario'] == 'daily_operations'
    assert row['overall_status'] == 'ready_for_manual_signoff'
    assert row['manual']['signed_off'] is False
    assert Path(report['outputs']['json']).exists()
    assert Path(report['outputs']['md']).exists()
    lines = render_competitive_acceptance_cli_lines(report)
    assert any('COMPETITIVE_ACCEPTANCE_READY_FOR_UAT=true' in line for line in lines)



def test_t30_01_runner_marks_product_ready_with_manual_signoff(monkeypatch, tmp_path: Path) -> None:
    cfg = tmp_path / 'policy.yaml'
    cfg.write_text(
        yaml.safe_dump(
            {
                'version': 1,
                'manual_signoff': {'path': str(tmp_path / 'manual_signoff.json')},
                'profiles': {
                    'legacy_replacement_ci': {
                        'migration': {
                            'enabled': True,
                            'title': 'Migration',
                            'budget_sec': 5.0,
                            'pytest': [],
                            'scripts': [],
                            'required_files': [],
                            'manual_checks': [{'id': 'CAS-X', 'actor': 'PM', 'area': 'Migration', 'step': 'review', 'expected': 'ok'}],
                            'pass_fail_criteria': ['evidence present'],
                        }
                    }
                },
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding='utf-8',
    )
    (tmp_path / 'manual_signoff.json').write_text(
        json.dumps(
            {
                'scenarios': {
                    'migration': {
                        'signed_off': True,
                        'signoff_by': 'qa_lead',
                        'signoff_at': '2026-04-05T12:00:00Z',
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )
    monkeypatch.setattr(
        'core.observability.competitive_acceptance._evaluate_artifact_checks',
        lambda **kwargs: {'ok': True, 'duration_sec': 0.0, 'diagnostics': [], 'checks': []},
    )
    monkeypatch.setattr(
        'core.observability.competitive_acceptance._run_pytest_bundle',
        lambda **kwargs: {'ok': True, 'duration_sec': 0.0, 'diagnostics': [], 'checks': []},
    )
    monkeypatch.setattr(
        'core.observability.competitive_acceptance._run_script_bundle',
        lambda **kwargs: {'ok': True, 'duration_sec': 0.0, 'diagnostics': [], 'checks': []},
    )
    monkeypatch.setattr(
        'core.observability.competitive_acceptance._evaluate_required_files',
        lambda **kwargs: {'ok': True, 'duration_sec': 0.0, 'diagnostics': [], 'checks': []},
    )
    report = run_competitive_acceptance_set(project_root='.', artifacts_root='artifacts', config_path=cfg, scenarios=['migration'], report_root=tmp_path / 'out')
    row = report['scenarios'][0]
    assert row['overall_status'] == 'product_ready'
    assert report['summary']['product_ready_count'] == 1



def test_t30_01_admin_diagnostics_reads_latest_report(tmp_path: Path) -> None:
    artifacts = tmp_path / 'artifacts'
    report_dir = artifacts / '_ci' / 'competitive_acceptance' / 'latest'
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / 'competitive_acceptance_report.json'
    report_path.write_text(json.dumps({'summary': {'ok': True, 'ready_for_competitive_uat': True}}, ensure_ascii=False), encoding='utf-8')

    class Ctx:
        artifacts_dir = str(artifacts)
        web_storage_dir = str(tmp_path / 'web_storage')

    diag = competitive_acceptance_diagnostics(Ctx())
    assert diag['path'] == str(report_path)
    assert diag['payload']['summary']['ready_for_competitive_uat'] is True
    assert diag['policy']['profile_name'] == 'legacy_replacement_ci'



def test_t30_01_ci_docs_scripts_and_admin_surface_are_present() -> None:
    entries = [
        line.strip()
        for line in Path('ci/pytest_gate.txt').read_text(encoding='utf-8').splitlines()
        if line.strip() and not line.lstrip().startswith('#')
    ]
    assert 'tests/test_t30_01_competitive_acceptance_set.py' in entries

    gate_script = Path('scripts/run_competitive_acceptance_gate.sh').read_text(encoding='utf-8')
    assert 'scripts/smoke_t30_01_competitive_acceptance_set.py' in gate_script
    assert 'competitive_acceptance_gate.log' in gate_script
    assert 'competitive_acceptance' in gate_script

    smoke_script = Path('scripts/smoke_t30_01_competitive_acceptance_set.py').read_text(encoding='utf-8')
    assert 'run_competitive_acceptance_set' in smoke_script
    assert 'render_competitive_acceptance_cli_lines' in smoke_script

    workflow = yaml.safe_load(Path('.github/workflows/verify_refactor.yml').read_text(encoding='utf-8'))
    steps = workflow['jobs']['gates']['steps']
    competitive_step = next(step for step in steps if step.get('name') == 'Competitive acceptance gate')
    assert 'bash scripts/run_competitive_acceptance_gate.sh' in str(competitive_step.get('run', ''))

    upload_step = next(step for step in steps if step.get('name') == 'Upload CI artifacts on failure')
    upload_path = str(upload_step['with']['path'])
    assert 'artifacts/_ci/competitive_acceptance' in upload_path

    enforce_step = next(step for step in steps if step.get('name') == 'Enforce gates')
    assert 'steps.competitive_gate.outcome' in str(enforce_step.get('run', ''))

    admin_page = Path('streamlit_app/pages/37_Admin_Observability_Release.py').read_text(encoding='utf-8')
    admin_console = Path('streamlit_app/admin_console.py').read_text(encoding='utf-8')
    assert 'competitive_acceptance' in admin_page
    assert 'competitive_acceptance_diagnostics' in admin_console

    doc = Path('docs/competitive_acceptance_set.md').read_text(encoding='utf-8')
    ci_doc = Path('docs/ci_gates.md').read_text(encoding='utf-8')
    readme = Path('README.md').read_text(encoding='utf-8')
    project_map = Path('docs/project_map.md').read_text(encoding='utf-8')
    assert 'run_competitive_acceptance_gate.sh' in doc
    assert 'Competitive acceptance gate' in ci_doc
    assert 'docs/competitive_acceptance_set.md' in readme
    assert 'competitive acceptance set' in project_map.lower()
