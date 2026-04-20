from __future__ import annotations

from pathlib import Path

from core.ops.production_operability import build_production_operability_report, metrics_contract, validate_production_operability


def _base_env(monkeypatch, tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv('GENOMEAI_PROJECT_ROOT', str(repo_root))
    monkeypatch.setenv('GENOMEAI_WEB_STORAGE', str(tmp_path / 'web_storage'))
    monkeypatch.setenv('GENOMEAI_ARTIFACTS_ROOT', str(tmp_path / 'artifacts'))
    monkeypatch.setenv('GENOMEAI_WEB_SECRET', 'test-secret-operability')
    monkeypatch.setenv('GENOMEAI_WEB_DISABLE_WORKER', '1')


def test_t34_09_metrics_contract_contains_required_ids_and_labels(monkeypatch, tmp_path: Path) -> None:
    _base_env(monkeypatch, tmp_path)
    contract = metrics_contract()
    assert set(['request_id', 'job_id', 'run_id', 'user_id', 'tenant_id']).issubset(set(contract['required_correlation_ids']))
    assert set(['storage_backend', 'queue_backend', 'auth_backend', 'auth_mode']).issubset(set(contract['required_log_labels']))


def test_t34_09_production_operability_report_contains_release_support_and_diagnostics(monkeypatch, tmp_path: Path) -> None:
    _base_env(monkeypatch, tmp_path)
    monkeypatch.setenv('GENOMEAI_DEPLOY_PROFILE', 'dev')
    report = build_production_operability_report().as_dict()
    assert 'release_checklist' in report['release']
    assert 'rollback_checklist' in report['release']
    assert 'support_bundle_expected_sections' in report['supportability']
    assert 'runtime_storage' in report['diagnostics']
    assert 'metrics_contract' in report['observability']
    validate_production_operability()
