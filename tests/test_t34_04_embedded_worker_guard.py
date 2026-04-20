from __future__ import annotations

from pathlib import Path

import pytest


def test_t34_04_adult_embedded_worker_is_forbidden(monkeypatch, tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv('GENOMEAI_PROJECT_ROOT', str(repo_root))
    monkeypatch.setenv('GENOMEAI_WEB_STORAGE', str(tmp_path / 'web_storage'))
    monkeypatch.setenv('GENOMEAI_ARTIFACTS_ROOT', str(tmp_path / 'artifacts'))
    monkeypatch.setenv('GENOMEAI_DEPLOY_PROFILE', 'adult')
    monkeypatch.setenv('GENOMEAI_JOB_QUEUE_BACKEND', 'redis')
    monkeypatch.setenv('GENOMEAI_REDIS_DSN', 'redis://localhost:6379/0')

    from web_cabinet.worker import JobWorker

    worker = JobWorker(execution_model='embedded')
    with pytest.raises(RuntimeError, match='dedicated redis worker required'):
        worker.run_once()
