from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.performance import evaluate_perf_report, load_performance_gates_policy, run_performance_gates
from genomeai import cli as cli_module


def test_t17_05_policy_loader_exposes_ci_profile_and_verify_scenarios() -> None:
    policy = load_performance_gates_policy(project_root='.', profile='ci')
    assert policy['version'] == 1
    assert policy['profile_name'] == 'ci'
    assert set(policy['profile']) >= {'startup', 'pipeline_smoke', 'web_smoke', 'verify_refactor'}
    assert policy['profile']['verify_refactor']['scenarios'] == ['standard', 'qc_issues']


def test_t17_05_evaluate_perf_report_flags_budget_violations() -> None:
    policy = {
        'profile': {
            'startup': {
                'budget_sec': 2.0,
                'steps': {'import_app': 1.0},
            }
        }
    }
    report = {
        'gates': [
            {
                'gate': 'startup',
                'ok': True,
                'duration_sec': 3.5,
                'steps': {'import_app': 1.5},
            }
        ]
    }
    evaluated = evaluate_perf_report(report, policy=policy)
    assert evaluated['summary']['ok'] is False
    assert evaluated['summary']['failed_gates'] == ['startup']
    assert any('startup: total 3.500s > budget 2.000s' in item for item in evaluated['summary']['diagnostics'])
    assert any('startup.import_app: 1.500s > budget 1.000s' in item for item in evaluated['summary']['diagnostics'])


def test_t17_05_run_performance_gates_writes_report_with_selected_fake_gates(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from core.performance import gates as perf_mod

    monkeypatch.setattr(perf_mod, '_measure_app_startup', lambda **kwargs: {
        'gate': 'startup',
        'ok': True,
        'duration_sec': 1.0,
        'steps': {'import_app': 0.4, 'startup': 0.3},
        'details': {'fake': True},
    })
    monkeypatch.setattr(perf_mod, '_measure_pipeline_smoke', lambda **kwargs: {
        'gate': 'pipeline_smoke',
        'ok': True,
        'duration_sec': 2.0,
        'steps': {'ingest_total': 0.5, 'qc': 0.2, 'train': 0.4, 'score': 0.2, 'report': 0.3, 'decision_log': 0.1, 'pack': 0.2},
        'details': {'fake': True},
    })
    monkeypatch.setattr(perf_mod, '_measure_web_smoke', lambda **kwargs: {
        'gate': 'web_smoke',
        'ok': True,
        'duration_sec': 3.0,
        'steps': {'rbac': 0.1, 'ingest_all': 0.7, 'qc': 0.3, 'train': 0.4, 'score': 0.2, 'report': 0.5, 'decisions': 0.4, 'pack': 0.3},
        'details': {'fake': True},
    })
    monkeypatch.setattr(perf_mod, '_measure_verify_refactor', lambda **kwargs: {
        'gate': 'verify_refactor',
        'ok': True,
        'duration_sec': 4.0,
        'steps': {'standard': 1.4, 'qc_issues': 1.6},
        'details': {'fake': True},
    })

    report_root = tmp_path / 'perf_report'
    report = run_performance_gates(project_root='.', artifacts_root='artifacts', golden_root='golden', report_root=report_root)
    assert report['summary']['ok'] is True
    assert [gate['gate'] for gate in report['gates']] == ['startup', 'pipeline_smoke', 'web_smoke', 'verify_refactor']
    json_path = Path(report['outputs']['json'])
    md_path = Path(report['outputs']['md'])
    assert json_path.exists() and md_path.exists()
    saved = json.loads(json_path.read_text(encoding='utf-8'))
    assert saved['schema'] == 'genomeai.performance_gates_report.v1'
    assert saved['summary']['ok'] is True


def test_t17_05_cli_perf_gates_respects_nonzero_on_budget_failure(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(cli_module, 'run_performance_gates', lambda **kwargs: {
        'summary': {'ok': False},
        'gates': [],
        'outputs': {'json': '/tmp/report.json', 'md': '/tmp/report.md'},
        'profile': 'ci',
    })
    monkeypatch.setattr(cli_module, 'render_performance_gate_cli_lines', lambda result: ['PERF_GATES_FAILED', 'profile=ci'])

    exit_code = cli_module.main(['perf-gates', '--project-root', '.', '--gate', 'startup'])

    assert exit_code == 2
    out = capsys.readouterr().out
    assert 'PERF_GATES_FAILED' in out
    assert 'profile=ci' in out
