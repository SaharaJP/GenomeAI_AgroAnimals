"""Redis-backed cache for LLM connectivity ping (P1-6b R1).

Storing every /admin/integrations open hitting OpenAI's API would be
expensive ($$$/min). Instead the manual-sync endpoint runs a real ping
(models.list) and writes the outcome to Redis with a 5-minute TTL.
The health provider reads from cache:
  - cache hit, ok=True   → status='ok' (with latency_ms)
  - cache hit, ok=False  → status='degraded' (last_error in note)
  - cache miss           → status='ok' if credentials configured, but
                            note='не проверено — нажмите Sync для real ping'

This gives operators an honest signal vs the pre-R1 behavior which
treated "API key configured" as "provider is healthy".
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

_CACHE_TTL_SEC = 5 * 60  # 5 minutes — manual sync refreshes


def _redis_dsn() -> Optional[str]:
    dsn = (os.environ.get('GENOMEAI_REDIS_DSN') or '').strip()
    if dsn:
        return dsn
    file_path = (os.environ.get('GENOMEAI_REDIS_DSN_FILE') or '').strip()
    if file_path and os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                value = f.read().strip()
                return value or None
        except OSError:
            return None
    return None


def _make_client():
    try:
        import redis  # type: ignore
    except Exception:
        return None
    dsn = _redis_dsn()
    try:
        if dsn:
            client = redis.Redis.from_url(dsn, decode_responses=True, socket_timeout=1.0)
        else:
            client = redis.Redis(host='127.0.0.1', port=6379, decode_responses=True, socket_timeout=1.0)
        client.ping()
        return client
    except Exception as exc:
        logger.debug('llm_ping_cache.redis_unavailable: %s', exc)
        return None


def _key(provider: str) -> str:
    return f'iam:llm_ping:{provider}'


def record_ping(*, provider: str, ok: bool, latency_ms: int, message: str, detail: Optional[str] = None) -> None:
    """Write a ping result to Redis (5min TTL)."""
    client = _make_client()
    if client is None:
        return
    payload = {
        'ok': bool(ok),
        'latency_ms': int(latency_ms),
        'message': str(message),
        'detail': str(detail) if detail else None,
        'checked_at': datetime.now(timezone.utc).isoformat(),
    }
    try:
        client.setex(_key(provider), _CACHE_TTL_SEC, json.dumps(payload))
    except Exception as exc:
        logger.warning('llm_ping_cache.set_failed provider=%s err=%s', provider, exc)


def read_ping(*, provider: str) -> Optional[dict[str, Any]]:
    """Return last ping payload or None if cache miss / Redis down."""
    client = _make_client()
    if client is None:
        return None
    try:
        raw = client.get(_key(provider))
    except Exception:
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


__all__ = ['read_ping', 'record_ping']
