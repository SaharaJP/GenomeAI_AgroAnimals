"""IAM role-change invalidation via Redis (P1-5 force-logout).

Whenever an admin mutates `role_permissions_overrides_v1` (via PATCH
/api/admin/permission-matrix), we publish a timestamp to Redis under
`iam:role_changed_at:{role}`. Auth middleware compares this against the
session's `created_at`: if the session was created BEFORE the most recent
role change, the session is forcibly invalidated and the user is bounced
to login (HTTP 401 + auth.session.invalidated_by_iam).

Goal: catch the case of revoked permissions while the user still has a
valid access token. Without this, a compromised account remains usable
for up to the refresh TTL even after the admin revokes its role.

Redis unavailability is non-fatal — the helper logs and returns None,
leaving the existing per-request permission re-read as the safety net.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


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
    dsn = _redis_dsn()
    try:
        import redis  # type: ignore
    except Exception:
        return None
    try:
        if dsn:
            client = redis.Redis.from_url(dsn, decode_responses=True, socket_timeout=1.0)
        else:
            client = redis.Redis(host='127.0.0.1', port=6379, decode_responses=True, socket_timeout=1.0)
        # cheap noop to surface connection errors early
        client.ping()
        return client
    except Exception as exc:
        logger.debug('iam_invalidation.redis_unavailable: %s', exc)
        return None


def _key(role: str) -> str:
    return f'iam:role_changed_at:{role}'


def mark_role_changed(role: str) -> Optional[str]:
    """Publish current UTC timestamp under the role key. Returns the ISO
    timestamp written, or None when Redis is unavailable."""
    client = _make_client()
    if client is None:
        return None
    ts = datetime.now(timezone.utc).isoformat()
    try:
        # 60-day TTL — sessions older than that have certainly expired anyway
        client.setex(_key(role), 60 * 60 * 24 * 60, ts)
    except Exception as exc:
        logger.warning('iam_invalidation.set_failed role=%s err=%s', role, exc)
        return None
    return ts


def role_changed_at(role: str) -> Optional[str]:
    """Return ISO timestamp of last role change, or None when none/unavailable."""
    client = _make_client()
    if client is None:
        return None
    try:
        value = client.get(_key(role))
    except Exception as exc:
        logger.debug('iam_invalidation.get_failed role=%s err=%s', role, exc)
        return None
    return value if value else None


def session_invalidated_by_role_change(
    *,
    role: str,
    session_created_at: Optional[str],
) -> bool:
    """True iff a role mutation occurred AFTER session_created_at.

    `session_created_at` should be an ISO-8601 timestamp from `auth_sessions`
    table. Returns False if either side is missing or Redis is unreachable.
    """
    if not role or not session_created_at:
        return False
    invalidated_at = role_changed_at(role)
    if not invalidated_at:
        return False
    try:
        s_dt = datetime.fromisoformat(session_created_at.replace('Z', '+00:00'))
        i_dt = datetime.fromisoformat(invalidated_at.replace('Z', '+00:00'))
    except ValueError:
        return False
    if s_dt.tzinfo is None:
        s_dt = s_dt.replace(tzinfo=timezone.utc)
    if i_dt.tzinfo is None:
        i_dt = i_dt.replace(tzinfo=timezone.utc)
    return i_dt > s_dt


__all__ = [
    'mark_role_changed',
    'role_changed_at',
    'session_invalidated_by_role_change',
]
