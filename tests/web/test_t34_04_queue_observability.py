from __future__ import annotations

import importlib
from pathlib import Path

from fastapi.testclient import TestClient


def test_t34_04_queue_runtime_endpoint_and_readyz_headers(monkeypatch, tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv('GENOMEAI_PROJECT_ROOT', str(repo_root))
    monkeypatch.setenv('GENOMEAI_WEB_STORAGE', str(tmp_path / 'web_storage'))
    monkeypatch.setenv('GENOMEAI_ARTIFACTS_ROOT', str(tmp_path / 'artifacts'))
    monkeypatch.setenv('GENOMEAI_WEB_SECRET', 'test-secret-queue')
    monkeypatch.setenv('GENOMEAI_WEB_DISABLE_WORKER', '1')
    monkeypatch.setenv('GENOMEAI_DEPLOY_PROFILE', 'dev')
    monkeypatch.setenv('GENOMEAI_RUNTIME_STORAGE_BACKEND', 'sqlite')
    monkeypatch.setenv('GENOMEAI_JOB_QUEUE_BACKEND', 'redis')
    monkeypatch.setenv('GENOMEAI_REDIS_DSN', 'redis://localhost:6379/0')

    from core.infra import queue_runtime as qr

    class _FakeBroker:
        backend = 'redis'
        def ping(self):
            return True
        def queue_metrics(self, queue_name: str):
            return {
                'queue_name': queue_name,
                'pending_jobs': 2,
                'inflight_jobs': 1,
                'deadletter_jobs': 1,
                'inflight': [{'public_job_id': 'job_1', 'worker_id': 'worker-a'}],
                'stuck_jobs': [],
                'stats': {'enqueued_total': 3, 'claimed_total': 1, 'failed_total': 1},
                'worker_ids': ['worker-a'],
            }

    qr.set_queue_broker_factory(lambda: _FakeBroker())
    try:
        import web_cabinet.app as appmod
        appmod = importlib.reload(appmod)
        with TestClient(appmod.app) as client:
            ready = client.get('/readyz')
            assert ready.status_code == 200
            assert ready.headers['X-GenomeAI-Queue-Backend'] == 'redis'
            login = client.post('/login', data={'username': 'admin', 'password': 'admin'})
            assert login.status_code in (200, 303)
            obs = client.get('/api/queue-runtime')
            assert obs.status_code == 200
            payload = obs.json()
            assert payload['backend'] == 'redis'
            assert payload['queues'][0]['pending_jobs'] == 2
            assert payload['queues'][0]['worker_ids'] == ['worker-a']
    finally:
        qr.set_queue_broker_factory(None)
