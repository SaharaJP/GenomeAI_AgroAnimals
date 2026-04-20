from __future__ import annotations

from pathlib import Path

import pytest

from core.ops.production_lockdown import (
    ProductionLockdownError,
    internal_web_login_allowed,
    internal_web_login_mode,
    production_lockdown_report,
    validate_production_lockdown,
)


def _base_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv('GENOMEAI_PROJECT_ROOT', str(repo_root))
    monkeypatch.setenv('GENOMEAI_WEB_STORAGE', str(tmp_path / 'web_storage'))
    monkeypatch.setenv('GENOMEAI_ARTIFACTS_ROOT', str(tmp_path / 'artifacts'))


def test_t34_07_adult_lockdown_report_marks_forbidden_tails_disabled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _base_env(monkeypatch, tmp_path)
    monkeypatch.setenv('GENOMEAI_DEPLOY_PROFILE', 'adult')
    monkeypatch.setenv('GENOMEAI_RUNTIME_STORAGE_BACKEND', 'postgres')
    monkeypatch.setenv('GENOMEAI_RUNTIME_POSTGRES_DSN', 'postgresql://genomeai:secret@postgres:5432/genomeai')
    monkeypatch.setenv('GENOMEAI_JOB_QUEUE_BACKEND', 'redis')
    monkeypatch.setenv('GENOMEAI_REDIS_DSN', 'redis://redis:6379/0')
    monkeypatch.setenv('GENOMEAI_WEB_DISABLE_WORKER', '1')
    monkeypatch.setenv('GENOMEAI_INTERNAL_WEB_LOGIN_MODE', 'disabled')

    report = production_lockdown_report()
    assert report.adult_mode is True
    assert report.runtime_storage_backend == 'postgres'
    assert report.queue_backend == 'redis'
    assert report.internal_web_login_allowed is False
    assert report.forbidden_tails_status['legacy_storage_fallback_disabled'] is True
    assert report.forbidden_tails_status['queue_fallback_disabled'] is True
    assert report.forbidden_tails_status['legacy_cookie_session_bypass_disabled'] is True
    assert report.forbidden_tails_status['hidden_fallback_detected'] is True
    assert report.lockdown_active is False
    with pytest.raises(ProductionLockdownError):
        validate_production_lockdown()


def test_t34_07_adult_support_only_internal_login_requires_justification(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _base_env(monkeypatch, tmp_path)
    monkeypatch.setenv('GENOMEAI_DEPLOY_PROFILE', 'prod')
    monkeypatch.setenv('GENOMEAI_RUNTIME_STORAGE_BACKEND', 'postgres')
    monkeypatch.setenv('GENOMEAI_RUNTIME_POSTGRES_DSN', 'postgresql://genomeai:secret@postgres:5432/genomeai')
    monkeypatch.setenv('GENOMEAI_JOB_QUEUE_BACKEND', 'redis')
    monkeypatch.setenv('GENOMEAI_REDIS_DSN', 'redis://redis:6379/0')
    monkeypatch.setenv('GENOMEAI_WEB_DISABLE_WORKER', '1')
    monkeypatch.setenv('GENOMEAI_INTERNAL_WEB_LOGIN_MODE', 'support_only')
    monkeypatch.delenv('GENOMEAI_INTERNAL_WEB_LOGIN_JUSTIFICATION', raising=False)

    assert internal_web_login_mode() == 'support_only'
    assert internal_web_login_allowed() is False
    with pytest.raises(ProductionLockdownError, match='JUSTIFICATION'):
        validate_production_lockdown()


def test_t34_07_dev_profile_keeps_internal_login_as_explicit_compat_mode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _base_env(monkeypatch, tmp_path)
    monkeypatch.setenv('GENOMEAI_DEPLOY_PROFILE', 'dev')
    monkeypatch.delenv('GENOMEAI_INTERNAL_WEB_LOGIN_MODE', raising=False)
    report = production_lockdown_report()
    assert report.adult_mode is False
    assert report.internal_web_login_mode == 'enabled'
    assert report.compatibility_flags['runtime_storage_compat_mode'] is True
