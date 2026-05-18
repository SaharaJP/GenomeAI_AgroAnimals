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
        return {
            'ok': True,
            'duration_ms': duration_ms,
            'message': 'pong',
            'detail': None,
        }
    except Exception as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        return {
            'ok': False,
            'duration_ms': duration_ms,
            'message': 'ping_failed',
            'detail': str(exc)[:300],
        }


def trigger_sync(conn: Any, *, integration_id: str, tenant_id: str = 'default') -> SyncResult:
    """Dispatch sync to the right handler. Returns SyncResult dict.

    Future slices will register per-connector sync (batch.* → connector_runs
    insert, iot.* → device probe, etc.). For now anything outside the LLM
    namespace returns not_supported.
    """
    if integration_id.startswith('llm.'):
        return _sync_llm(integration_id=integration_id)
    return {
        'ok': False,
        'duration_ms': 0,
        'message': 'not_supported',
        'detail': f"Manual sync for {integration_id!r} is not implemented yet (P1-6b slice 2 covers LLM only).",
    }


__all__ = ['SyncResult', 'trigger_sync']
