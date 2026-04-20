from __future__ import annotations

from pathlib import Path

import pytest

from core.infra.queue_runtime import (
    QueueEnvelope,
    QueueRuntimeConfigError,
    RedisQueueBroker,
    resolve_queue_runtime_settings,
    validate_queue_runtime_settings,
)
from core.infra.web_db import connect, create_job, get_job


class FakeRedisClient:
    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.kv: dict[str, str] = {}

    def execute(self, *parts):
        cmd = str(parts[0]).upper()
        if cmd == 'PING':
            return 'PONG'
        if cmd == 'SET':
            key = str(parts[1])
            value = str(parts[2])
            nx = 'NX' in [str(x).upper() for x in parts[3:]]
            if nx and key in self.kv:
                return None
            self.kv[key] = value
            return 'OK'
        if cmd == 'RPUSH':
            key = str(parts[1])
            self.lists.setdefault(key, []).append(str(parts[2]))
            return len(self.lists[key])
        if cmd == 'LPUSH':
            key = str(parts[1])
            self.lists.setdefault(key, []).insert(0, str(parts[2]))
            return len(self.lists[key])
        if cmd == 'BRPOPLPUSH':
            src = str(parts[1])
            dst = str(parts[2])
            items = self.lists.setdefault(src, [])
            if not items:
                return None
            value = items.pop()
            self.lists.setdefault(dst, []).insert(0, value)
            return value
        if cmd == 'LREM':
            key = str(parts[1])
            count = int(parts[2])
            value = str(parts[3])
            items = self.lists.setdefault(key, [])
            removed = 0
            out = []
            for item in items:
                if item == value and removed < count:
                    removed += 1
                    continue
                out.append(item)
            self.lists[key] = out
            return removed
        if cmd == 'LLEN':
            return len(self.lists.setdefault(str(parts[1]), []))
        if cmd == 'HSET':
            key = str(parts[1])
            field = str(parts[2])
            value = str(parts[3])
            self.hashes.setdefault(key, {})[field] = value
            return 1
        if cmd == 'HGET':
            return self.hashes.setdefault(str(parts[1]), {}).get(str(parts[2]))
        if cmd == 'HGETALL':
            raw = []
            for k, v in self.hashes.setdefault(str(parts[1]), {}).items():
                raw.extend([k, v])
            return raw
        if cmd == 'HDEL':
            key = str(parts[1])
            field = str(parts[2])
            self.hashes.setdefault(key, {}).pop(field, None)
            return 1
        if cmd == 'HINCRBY':
            key = str(parts[1])
            field = str(parts[2])
            delta = int(parts[3])
            store = self.hashes.setdefault(key, {})
            store[field] = str(int(store.get(field, '0')) + delta)
            return int(store[field])
        raise AssertionError(f'unsupported command: {parts}')


def test_t34_04_adult_profile_requires_redis_queue(monkeypatch):
    monkeypatch.setenv('GENOMEAI_DEPLOY_PROFILE', 'adult')
    monkeypatch.setenv('GENOMEAI_JOB_QUEUE_BACKEND', 'sqlite')
    with pytest.raises(QueueRuntimeConfigError):
        validate_queue_runtime_settings(resolve_queue_runtime_settings())


def test_t34_04_redis_broker_claim_ack_fail_metrics(monkeypatch):
    monkeypatch.setenv('GENOMEAI_DEPLOY_PROFILE', 'adult')
    monkeypatch.setenv('GENOMEAI_JOB_QUEUE_BACKEND', 'redis')
    monkeypatch.setenv('GENOMEAI_REDIS_DSN', 'redis://localhost:6379/0')
    settings = resolve_queue_runtime_settings()
    broker = RedisQueueBroker(settings=settings, client=FakeRedisClient())

    envelope = QueueEnvelope(
        job_id=101,
        public_job_id='job_public_101',
        queue_name='default',
        kind='qc',
        tenant_id='default',
        user_id=1,
        data_version='dv1',
        run_id='run1',
        attempt_no=0,
        max_attempts=2,
        enqueued_at='2026-04-14T00:00:00+00:00',
    )
    first = broker.enqueue(envelope)
    second = broker.enqueue(envelope)
    claimed = broker.claim(queue_name='default', worker_id='worker-1')
    assert first['enqueued'] is True
    assert second['enqueued'] is False
    assert claimed is not None and claimed.public_job_id == 'job_public_101'
    broker.heartbeat(claimed, worker_id='worker-1')
    broker.fail(claimed, worker_id='worker-1', reason='boom', final_status='failed')
    snap = broker.queue_metrics('default')
    assert snap['pending_jobs'] == 0
    assert snap['inflight_jobs'] == 0
    assert snap['deadletter_jobs'] == 1
    assert snap['stats']['enqueued_total'] == 1
    assert snap['stats']['claimed_total'] == 1
    assert snap['stats']['failed_total'] == 1


def test_t34_04_create_job_auto_enqueues_to_broker(monkeypatch, tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv('GENOMEAI_PROJECT_ROOT', str(repo_root))
    monkeypatch.setenv('GENOMEAI_WEB_STORAGE', str(tmp_path / 'web_storage'))
    monkeypatch.setenv('GENOMEAI_ARTIFACTS_ROOT', str(tmp_path / 'artifacts'))
    monkeypatch.setenv('GENOMEAI_DEPLOY_PROFILE', 'dev')
    monkeypatch.setenv('GENOMEAI_RUNTIME_STORAGE_BACKEND', 'sqlite')
    monkeypatch.setenv('GENOMEAI_JOB_QUEUE_BACKEND', 'redis')
    monkeypatch.setenv('GENOMEAI_REDIS_DSN', 'redis://localhost:6379/0')
    fake_client = FakeRedisClient()

    from core.infra import queue_runtime as qr
    qr.set_queue_broker_factory(lambda: RedisQueueBroker(settings=resolve_queue_runtime_settings(), client=fake_client))
    try:
        conn = connect(tmp_path / 'web_storage' / 'web.db')
        try:
            from core.infra.web_db import init_db
            init_db(conn)
            job_id = create_job(
                conn,
                kind='qc',
                tenant_id='default',
                user_id=1,
                user='tester',
                command='python -m genomeai',
                args={'argv': ['qc', '--data-version', 'dv1']},
                log_path=tmp_path / 'web_storage' / 'logs' / 'job.log',
            )
            row = get_job(conn, job_id)
            assert row is not None
            pending = fake_client.lists[f'{resolve_queue_runtime_settings().key_prefix}:default:pending']
            assert len(pending) == 1
            assert str(row['public_job_id']) in pending[0]
        finally:
            conn.close()
    finally:
        qr.set_queue_broker_factory(None)
