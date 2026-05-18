"""Manual integration sync dispatcher (P1-6b slice 2).

Routes a sync request to the appropriate handler based on integration id.
Handlers are minimal MVP: LLM does a real `models.list()` ping to the
configured provider; other ids return `not_supported` until the corresponding
batch/connector trigger interface is added in later slices.

Each handler returns the dispatcher schema:
    {
      'ok': bool,
      'duration_ms': int,
      'message': str,            # short status code, e.g. 'pong', 'not_supported'
      'detail': str | None,      # human-readable explanation / error tail
    }
"""
from __future__ import annotations

import os
import time
from typing import Any


SyncResult = dict[str, Any]


def _read_openai_key() -> str | None:
    direct = (os.environ.get('OPENAI_API_KEY') or '').strip()
    if direct:
        return direct
    file_env = (os.environ.get('OPENAI_API_KEY_FILE') or '').strip()
    if file_env and os.path.exists(file_env):
        try:
            with open(file_env, 'r', encoding='utf-8') as f:
                return f.read().strip() or None
        except OSError:
            return None
    return None


def _sync_llm(*, integration_id: str) -> SyncResult:
    """Real ping to the LLM provider via SDK. Cheap: `models.list()` only."""
    provider = (os.environ.get('GENOMEAI_LLM_PROVIDER') or 'openai').strip().lower()
    if provider not in ('openai', ''):
        return {
            'ok': False,
            'duration_ms': 0,
            'message': 'not_supported',
            'detail': f'LLM ping for provider={provider!r} appears in P2-2 (Ollama).',
        }
    api_key = _read_openai_key()
    if not api_key:
        return {
            'ok': False,
            'duration_ms': 0,
            'message': 'not_configured',
            'detail': 'OPENAI_API_KEY/OPENAI_API_KEY_FILE is empty; nothing to ping.',
        }
    started = time.perf_counter()
    try:
        from openai import OpenAI  # type: ignore
    except Exception as exc:  # pragma: no cover
        return {
            'ok': False,
            'duration_ms': 0,
            'message': 'sdk_missing',
            'detail': f'openai SDK not installed: {exc}',
        }
    try:
        client = OpenAI(api_key=api_key)
        client.models.list()
        duration_ms = int((time.perf_counter() - started) * 1000)
        result: SyncResult = {
            'ok': True,
            'duration_ms': duration_ms,
            'message': 'pong',
            'detail': None,
        }
    except Exception as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        result = {
            'ok': False,
            'duration_ms': duration_ms,
            'message': 'ping_failed',
            'detail': str(exc)[:300],
        }
    # P1-6b R1: persist ping outcome in Redis so /integrations/health reads
    # real connectivity, not just "key configured".
    try:
        from core.interoperability.llm_ping_cache import record_ping
        record_ping(
            provider=provider,
            ok=bool(result['ok']),
            latency_ms=int(result['duration_ms']),
            message=str(result['message']),
            detail=result.get('detail'),
        )
    except Exception:
        pass
    return result


def _sync_batch_connector(*, conn: Any, integration_id: str, tenant_id: str) -> SyncResult:
    """Trigger a connector_v1 run synchronously (P1-6b slice 2b).

    Real Selex / 1С / Хэрриот connectors don't exist yet; current configs
    in `configs/connectors/*.yaml` are stubs that finish in milliseconds,
    so synchronous execution is acceptable. When real long-running
    connectors land, this dispatcher should be switched to enqueue via
    `core.application.job_runner.enqueue_pipeline_job` and return the
    job_id immediately.
    """
    connector_id = integration_id.removeprefix('batch.')
    if not connector_id:
        return {
            'ok': False,
            'duration_ms': 0,
            'message': 'invalid_id',
            'detail': f"integration_id {integration_id!r} is missing the batch.* connector_id suffix.",
        }
    started = time.perf_counter()
    try:
        from pathlib import Path
        from genomeai.connectors_v1 import load_connector_spec, run_connector_spec
    except Exception as exc:
        return {
            'ok': False,
            'duration_ms': 0,
            'message': 'sdk_missing',
            'detail': f'connectors_v1 import failed: {exc}',
        }

    # Resolve project_root from current working dir; runtime sets cwd to repo root.
    project_root = Path(os.environ.get('GENOMEAI_PROJECT_ROOT') or os.getcwd()).resolve()
    artifacts_root = Path(os.environ.get('GENOMEAI_ARTIFACTS_ROOT') or (project_root / 'artifacts')).resolve()
    config_path = project_root / 'configs' / 'connectors' / f'{connector_id}.yaml'
    if not config_path.exists():
        return {
            'ok': False,
            'duration_ms': int((time.perf_counter() - started) * 1000),
            'message': 'config_missing',
            'detail': f'configs/connectors/{connector_id}.yaml not found',
        }
    try:
        spec = load_connector_spec(config_path, project_root=project_root)
        result = run_connector_spec(
            spec,
            project_root=project_root,
            artifacts_root=artifacts_root,
            trigger_type='manual',
        )
    except Exception as exc:
        return {
            'ok': False,
            'duration_ms': int((time.perf_counter() - started) * 1000),
            'message': 'run_failed',
            'detail': str(exc)[:300],
        }
    duration_ms = int((time.perf_counter() - started) * 1000)
    return {
        'ok': bool(getattr(result, 'ok', False)),
        'duration_ms': duration_ms,
        'message': str(getattr(result, 'status', None) or ('ran' if getattr(result, 'ok', False) else 'failed')),
        'detail': str(getattr(result, 'message', None) or ''),
        'connector_run_id': getattr(result, 'connector_run_id', None),
        'data_version': getattr(result, 'data_version', None),
    }


_STUB_NAMESPACES = ('iot.', 'sensor.', 'external_system.')


def trigger_sync(conn: Any, *, integration_id: str, tenant_id: str = 'default') -> SyncResult:
    """Dispatch sync to the right handler. Returns SyncResult dict.

    Routing:
      - llm.*               → real OpenAI ping with Redis-cached result
      - batch.*             → run_connector_spec (sync; future: job_runner)
      - iot./sensor./external_system. → stub noop (ok=true, no-op message)
      - anything else       → not_supported
    """
    if integration_id.startswith('llm.'):
        return _sync_llm(integration_id=integration_id)
    if integration_id.startswith('batch.'):
        return _sync_batch_connector(
            conn=conn, integration_id=integration_id, tenant_id=tenant_id,
        )
    if any(integration_id.startswith(ns) for ns in _STUB_NAMESPACES):
        return {
            'ok': True,
            'duration_ms': 0,
            'message': 'stub_noop',
            'detail': f"Источник {integration_id!r} — stub-провайдер; реальный sync появится в соответствующем эпике (P2-3 IoT / P2-4 RU-системы).",
        }
    return {
        'ok': False,
        'duration_ms': 0,
        'message': 'not_supported',
        'detail': f"Manual sync for {integration_id!r} is not implemented yet.",
    }


__all__ = ['SyncResult', 'trigger_sync']
