from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from core.observability.operational_gates import (
    evaluate_operational_rollout_report,
    load_operational_rollout_gates_policy,
    run_operational_rollout_gates,
)
from streamlit_app.admin_console import operational_rollout_diagnostics


def test_t28_05_policy_loader_exposes_enterprise_profile_and_gate_groups() -> None:
    policy = load_operational_rollout_gates_policy(project_root='.', profile='enterprise_ci')
    assert policy['version'] == 1
    assert policy['profile_name'] == 'enterprise_ci'
    assert set(policy['profile']) >= {
        'compile_daily_pages',
        'role_scenarios',
        'mobile_views',
        'worklists_profiles_reports',
        'rollout_diagnostics',
    }
    assert 'streamlit_app/pages/58_Mobile_Worklists.py' in policy['profile']['mobile_views']['pages']



def test_t28_05_evaluate_report_flags_budget_and_gate_failures() -> None:
    policy = {
        'profile': {
            'mobile_views': {'budget_sec': 1.0},
        }
    }
    report = {
        'gates': [
            {
                'gate': 'mobile_views',
                'ok': False,
                'duration_sec': 2.0,
                'details': {'diagnostics': ['script_failed: scripts/smoke_t25_02_mobile_worklists.py']},
            }
        ]
    }
    evaluated = evaluate_operational_rollout_report(report, policy=policy)
    assert evaluated['summary']['ok'] is False
    assert evaluated['summary']['ready_for_rollout'] is False
    assert 'mobile_views' in evaluated['summary']['failed_gates']
    assert any('mobile_views: total 2.000s > budget 1.000s' in item for item in evaluated['summary']['diagnostics'])
    assert any('mobile_views: script_failed: scripts/smoke_t25_02_mobile_worklists.py' in item for item in evaluated['summary']['diagnostics'])



def test_t28_05_run_operational_rollout_gates_writes_report(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from core.observability import operational_gates as gates_mod

    monkeypatch.setattr(gates_mod, '_measure_compile_daily_pages', lambda **kwargs: {
        'gate': 'compile_daily_pages', 'ok': True, 'duration_sec': 1.0, 'steps': {}, 'details': {'diagnostics': []}
    })
    monkeypatch.setattr(gates_mod, '_measure_role_scenarios', lambda **kwargs: {
        'gate': 'role_scenarios', 'ok': True, 'duration_sec': 1.5, 'steps': {}, 'details': {'diagnostics': []}
    })
    monkeypatch.setattr(gates_mod, '_measure_script_bundle', lambda gate_name, **kwargs: {
        'gate': gate_name, 'ok': True, 'duration_sec': 1.2, 'steps': {}, 'details': {'diagnostics': []}
    })
    monkeypatch.setattr(gates_mod, '_measure_rollout_diagnostics', lambda **kwargs: {
        'gate': 'rollout_diagnostics', 'ok': True, 'duration_sec': 0.3, 'steps': {}, 'details': {'diagnostics': []}
    })

    report_root = tmp_path / 'rollout_report'
    report = run_operational_rollout_gates(project_root='.', artifacts_root='artifacts', report_root=report_root)
    assert report['summary']['ok'] is True
    assert report['summary']['ready_for_rollout'] is True
    assert [g['gate'] for g in report['gates']] == [
        'compile_daily_pages',
        'role_scenarios',
        'mobile_views',
        'worklists_profiles_reports',
        'rollout_diagnostics',
    ]
    json_path = Path(report['outputs']['json'])
    md_path = Path(report['outputs']['md'])
    assert json_path.exists() and md_path.exists()
    saved = json.loads(json_path.read_text(encoding='utf-8'))
    assert saved['schema'] == 'genomeai.operational_rollout_gates_report.v1'



def test_t28_05_admin_diagnostics_reads_latest_report(tmp_path: Path) -> None:
    artifacts = tmp_path / 'artifacts'
    report_dir = artifacts / '_ci' / 'operational_rollout_gates' / 'latest'
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / 'operational_rollout_gates_report.json'
    report_path.write_text(json.dumps({'summary': {'ok': True}}, ensure_ascii=False), encoding='utf-8')

    class Ctx:
        artifacts_dir = str(artifacts)
        web_storage_dir = str(tmp_path / 'web_storage')

    diag = operational_rollout_diagnostics(Ctx())
    assert diag['path'] == str(report_path)
    assert diag['payload']['summary']['ok'] is True
    assert diag['policy']['profile_name'] == 'enterprise_ci'



def test_t28_05_ci_wiring_scripts_docs_and_admin_surface_are_present() -> None:
    entries = [
        line.strip()
        for line in Path('ci/pytest_gate.txt').read_text(encoding='utf-8').splitlines()
        if line.strip() and not line.lstrip().startswith('#')
    ]
    assert 'tests/test_t28_05_operational_sla_and_gates.py' in entries

    gate_script = Path('scripts/run_operational_rollout_gate.sh').read_text(encoding='utf-8')
    assert 'scripts/smoke_t28_05_operational_rollout_gates.py' in gate_script
    assert 'operational_rollout_gate.log' in gate_script
    assert 'operational_rollout_gates' in gate_script

    smoke_script = Path('scripts/smoke_t28_05_operational_rollout_gates.py').read_text(encoding='utf-8')
    assert 'run_operational_rollout_gates' in smoke_script
    assert 'render_operational_rollout_cli_lines' in smoke_script

    workflow = yaml.safe_load(Path('.github/workflows/verify_refactor.yml').read_text(encoding='utf-8'))
    steps = workflow['jobs']['gates']['steps']
    rollout_step = next(step for step in steps if step.get('name') == 'Operational rollout gate')
    assert 'bash scripts/run_operational_rollout_gate.sh' in str(rollout_step.get('run', ''))

    upload_step = next(step for step in steps if step.get('name') == 'Upload CI artifacts on failure')
    upload_path = str(upload_step['with']['path'])
    assert 'operational_rollout_gates' in upload_path
    assert '_tmp/ci_operational_rollout' in upload_path

    enforce_step = next(step for step in steps if step.get('name') == 'Enforce gates')
    assert 'steps.rollout_gate.outcome' in str(enforce_step.get('run', ''))

    admin_page = Path('streamlit_app/pages/37_Admin_Observability_Release.py').read_text(encoding='utf-8')
    admin_console = Path('streamlit_app/admin_console.py').read_text(encoding='utf-8')
    assert 'operational_rollout_gates' in admin_page
    assert 'operational_rollout_diagnostics' in admin_console

    doc = Path('docs/operational_sla_and_gates.md').read_text(encoding='utf-8')
    ci_doc = Path('docs/ci_gates.md').read_text(encoding='utf-8')
    readme = Path('README.md').read_text(encoding='utf-8')
    project_map = Path('docs/project_map.md').read_text(encoding='utf-8')
    assert 'run_operational_rollout_gate.sh' in doc
    assert 'Operational rollout gate' in ci_doc
    assert 'docs/operational_sla_and_gates.md' in readme
    assert 'operational sla / rollout gates' in project_map.lower()
