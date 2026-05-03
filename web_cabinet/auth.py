from __future__ import annotations

import hmac
import os
import secrets
import hashlib
from datetime import datetime, timezone
from typing import Any, Optional, Callable

from fastapi import Depends, HTTPException, Request, status

from core.infra.web_db import get_settings, mark_expired_auth_sessions
from core.infra.runtime_auth_storage import (
    legacy_cookie_fallback_allowed,
    resolve_runtime_auth_storage,
)
from core.security import map_legacy_role


# --- Password hashing (portable, no native extensions) ---
# We use passlib-compatible format so existing deployments hashed with passlib's
# pbkdf2_sha256 continue to work, but we do NOT depend on passlib.
# Format: $pbkdf2-sha256$<rounds>$<salt_crypt64>$<checksum_crypt64>

CRYPT64_ALPHABET = "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
CRYPT64_INDEX = {c: i for i, c in enumerate(CRYPT64_ALPHABET)}
DEFAULT_ACCESS_TTL_SEC = int(os.environ.get("GENOMEAI_AUTH_ACCESS_TTL_SEC", "900"))
DEFAULT_REFRESH_TTL_SEC = int(os.environ.get("GENOMEAI_AUTH_REFRESH_TTL_SEC", str(60 * 60 * 24 * 30)))


def _is_expired(value: Optional[str]) -> bool:
    if not value:
        return False
    try:
        ts = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except Exception:
        return False
    return ts <= datetime.now(timezone.utc)


def _crypt64_encode(raw: bytes) -> str:
    out = []
    buf = 0
    bits = 0
    for b in raw:
        buf |= b << bits
        bits += 8
        while bits >= 6:
            out.append(CRYPT64_ALPHABET[buf & 0x3F])
            buf >>= 6
            bits -= 6
    if bits:
        out.append(CRYPT64_ALPHABET[buf & 0x3F])
    return "".join(out)


def _crypt64_decode(s: str) -> bytes:
    buf = 0
    bits = 0
    out = bytearray()
    for ch in s:
        if ch not in CRYPT64_INDEX:
            raise ValueError("invalid crypt64")
        buf |= CRYPT64_INDEX[ch] << bits
        bits += 6
        if bits >= 8:
            out.append(buf & 0xFF)
            buf >>= 8
            bits -= 8
    return bytes(out)


def hash_password(password: str, *, rounds: int = 29000) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds, dklen=32)
    return f"$pbkdf2-sha256${rounds}${_crypt64_encode(salt)}${_crypt64_encode(dk)}"


def verify_password(password: str, password_hash: str) -> bool:
    ph = (password_hash or "").strip()

    if ph.startswith("$pbkdf2-sha256$"):
        parts = ph.split("$")
        # ['', 'pbkdf2-sha256', rounds, salt, chk]
        if len(parts) < 5:
            return False
        rounds_s, salt_s, chk_s = parts[2], parts[3], parts[4]
    elif ph.startswith("pbkdf2_sha256$"):
        parts = ph.split("$")
        if len(parts) < 4:
            return False
        rounds_s, salt_s, chk_s = parts[1], parts[2], parts[3]
    else:
        return False

    try:
        rounds = int(rounds_s)
        salt = _crypt64_decode(salt_s)
        chk = _crypt64_decode(chk_s)
    except Exception:
        return False

    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds, dklen=len(chk))
    return hmac.compare_digest(dk, chk)


def get_db():
    from core.infra.postgres_compat import connect_postgres_compat
    conn = connect_postgres_compat()
    try:
        yield conn
    finally:
        conn.close()


def authenticate(*, conn, tenant_id: str, username: str, password: str) -> Optional[dict]:
    storage = resolve_runtime_auth_storage(conn=conn)
    u = storage.get_user_by_username(tenant_id=tenant_id, username=username)
    if not u:
        return None
    if not verify_password(password, str(u.get('password_hash') or '')):
        return None

    u = dict(u)
    u['role'] = map_legacy_role(u.get('role'))
    u['tenant_id'] = u.get('tenant_id') or tenant_id
    u['_source'] = str(u.get('_source') or ('users_v2' if str(storage.backend) == 'sqlite' else 'auth_users'))
    return u


def _parse_scope_list(value: Any) -> list[str]:
    if value in (None, ''):
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    try:
        import json
        parsed = json.loads(value)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(x).strip() for x in parsed if str(x).strip()]


def _scope_allowed(requested: Optional[str], allowed: list[str]) -> bool:
    if not requested:
        return True
    if not allowed:
        return True
    return str(requested) in {str(x) for x in allowed}


def _extract_bearer_token(request: Request) -> Optional[str]:
    auth_header = str(request.headers.get('authorization') or '').strip()
    if not auth_header:
        return None
    parts = auth_header.split(None, 1)
    if len(parts) != 2:
        return None
    if parts[0].lower() != 'bearer':
        return None
    token = parts[1].strip()
    return token or None


def _active_scope_from_request(request: Request) -> tuple[Optional[str], Optional[str]]:
    farm_id = str(request.headers.get('x-farm-id') or request.headers.get('x-genomeai-farm-id') or '').strip() or None
    site_id = str(request.headers.get('x-site-id') or request.headers.get('x-genomeai-site-id') or '').strip() or None
    return farm_id, site_id


def _resolve_user_from_session_row(*, conn, session_row: dict, fallback_tenant_id: str) -> Optional[dict[str, Any]]:
    storage = resolve_runtime_auth_storage(conn=conn)
    user_id = int(session_row.get('user_id') or 0)
    tenant_id = str(session_row.get('tenant_id') or fallback_tenant_id or 'default')
    user = storage.get_user_by_id(tenant_id=tenant_id, user_id=user_id)
    if not user:
        return None
    user = dict(user)
    user['role'] = map_legacy_role(user.get('role'))
    user['tenant_id'] = user.get('tenant_id') or tenant_id
    return user


def create_authenticated_session(
    *,
    request: Request,
    conn,
    user: dict[str, Any],
    client_kind: str,
    issue_web_session_cookie: bool,
    active_farm_id: Optional[str] = None,
    active_site_id: Optional[str] = None,
    device_id: Optional[str] = None,
    device_label: Optional[str] = None,
    device_platform: Optional[str] = None,
    device_app_version: Optional[str] = None,
    access_ttl_sec: int = DEFAULT_ACCESS_TTL_SEC,
    refresh_ttl_sec: int = DEFAULT_REFRESH_TTL_SEC,
) -> dict[str, Any]:
    allowed_farm_ids = _parse_scope_list(user.get('allowed_farm_ids_json'))
    allowed_site_ids = _parse_scope_list(user.get('allowed_site_ids_json'))
    if active_farm_id and not _scope_allowed(active_farm_id, allowed_farm_ids):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='farm_scope_forbidden')
    if active_site_id and not _scope_allowed(active_site_id, allowed_site_ids):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='site_scope_forbidden')

    storage = resolve_runtime_auth_storage(conn=conn)
    session_row = storage.create_session(
        tenant_id=str(user.get('tenant_id') or 'default'),
        user_id=int(user['id']),
        username=str(user.get('username') or ''),
        role=str(user.get('role') or ''),
        user_source=str(user.get('_source') or 'users_v2'),
        client_kind=str(client_kind or 'web'),
        auth_transport='hybrid' if issue_web_session_cookie else 'bearer',
        device_id=device_id,
        device_label=device_label,
        device_platform=device_platform,
        device_app_version=device_app_version,
        active_farm_id=active_farm_id,
        active_site_id=active_site_id,
        allowed_farm_ids=allowed_farm_ids,
        allowed_site_ids=allowed_site_ids,
        metadata={'issued_for': 'web_and_mobile_unified_auth'},
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get('user-agent'),
        access_ttl_sec=int(access_ttl_sec),
        refresh_ttl_sec=int(refresh_ttl_sec),
    )
    if issue_web_session_cookie:
        request.session['user_id'] = int(user['id'])
        request.session['user_source'] = str(user.get('_source') or 'users_v2')
        request.session['tenant_id'] = str(user.get('tenant_id') or 'default')
        request.session['auth_session_id'] = str(session_row['session_id'])
        if active_farm_id:
            request.session['active_farm'] = str(active_farm_id)
        if active_site_id:
            request.session['active_site'] = str(active_site_id)
    return session_row


def build_auth_session_scope(user: dict[str, Any], session_row: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    allowed_farm_ids = _parse_scope_list((session_row or {}).get('allowed_farm_ids_json') if session_row else user.get('allowed_farm_ids_json'))
    allowed_site_ids = _parse_scope_list((session_row or {}).get('allowed_site_ids_json') if session_row else user.get('allowed_site_ids_json'))
    active_farm_id = (session_row or {}).get('active_farm_id') or user.get('active_farm_id')
    active_site_id = (session_row or {}).get('active_site_id') or user.get('active_site_id')
    return {
        'tenant_id': str(user.get('tenant_id') or 'default'),
        'allowed_farm_ids': allowed_farm_ids,
        'allowed_site_ids': allowed_site_ids,
        'active_farm_id': active_farm_id,
        'active_site_id': active_site_id,
    }


def resolve_request_auth_context(request: Request, conn, *, allow_missing: bool = False) -> Optional[dict[str, Any]]:
    cached = getattr(getattr(request, 'state', None), 'auth_context', None)
    if isinstance(cached, dict) and cached.get('id'):
        return cached

    storage = resolve_runtime_auth_storage(conn=conn)
    if conn is not None:
        mark_expired_auth_sessions(conn)
    tenant_hint = request.session.get('tenant_id', 'default') if hasattr(request, 'session') else 'default'
    bearer_token = _extract_bearer_token(request)
    auth_session_row: Optional[dict[str, Any]] = None
    auth_transport: Optional[str] = None

    if bearer_token:
        auth_session_row = storage.get_session_by_access_token(access_token=bearer_token)
        auth_transport = 'bearer'
        if not auth_session_row:
            if allow_missing:
                return None
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='auth.invalid_access_token')
        if str(auth_session_row.get('status') or '') != 'active':
            if allow_missing:
                return None
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='auth.session_inactive')
        expires_at = str(auth_session_row.get('expires_at') or '').strip()
        if _is_expired(expires_at):
            storage.revoke_session(session_id=str(auth_session_row['session_id']), reason='access_expired')
            if allow_missing:
                return None
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='auth.access_expired')
    else:
        auth_session_id = None
        try:
            auth_session_id = request.session.get('auth_session_id')
        except Exception:
            auth_session_id = None
        if auth_session_id:
            auth_session_row = storage.get_session_by_id(session_id=str(auth_session_id))
            auth_transport = 'cookie_session'
            if auth_session_row and str(auth_session_row.get('status') or '') != 'active':
                auth_session_row = None

    if auth_session_row:
        refresh_expires_at = str(auth_session_row.get('refresh_expires_at') or '').strip()
        if _is_expired(refresh_expires_at):
            storage.revoke_session(session_id=str(auth_session_row['session_id']), reason='refresh_expired')
            if allow_missing:
                return None
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='auth.refresh_expired')
        user = _resolve_user_from_session_row(conn=conn, session_row=auth_session_row, fallback_tenant_id=tenant_hint)
        if not user:
            if allow_missing:
                return None
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='auth.user_not_found')

        requested_farm_id, requested_site_id = _active_scope_from_request(request)
        requested_farm_id = requested_farm_id or (request.session.get('active_farm') if hasattr(request, 'session') else None)
        requested_site_id = requested_site_id or (request.session.get('active_site') if hasattr(request, 'session') else None)
        allowed_farm_ids = _parse_scope_list(auth_session_row.get('allowed_farm_ids_json') or user.get('allowed_farm_ids_json'))
        allowed_site_ids = _parse_scope_list(auth_session_row.get('allowed_site_ids_json') or user.get('allowed_site_ids_json'))
        if requested_farm_id and not _scope_allowed(requested_farm_id, allowed_farm_ids):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='auth.scope.farm_forbidden')
        if requested_site_id and not _scope_allowed(requested_site_id, allowed_site_ids):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='auth.scope.site_forbidden')

        storage.touch_session(
            session_id=str(auth_session_row['session_id']),
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get('user-agent'),
            active_farm_id=requested_farm_id,
            active_site_id=requested_site_id,
        )
        user['permissions'] = storage.get_permissions_for_role(role=user['role'])
        user['allowed_farm_ids'] = allowed_farm_ids
        user['allowed_site_ids'] = allowed_site_ids
        user['active_farm_id'] = requested_farm_id
        user['active_site_id'] = requested_site_id
        user['auth_session_id'] = str(auth_session_row['session_id'])
        user['auth_transport'] = auth_transport or str(auth_session_row.get('auth_transport') or 'bearer')
        user['client_kind'] = str(auth_session_row.get('client_kind') or 'unknown')
        user['_auth_session'] = auth_session_row
        request.state.auth_context = user
        request.state.auth_session_id = str(auth_session_row['session_id'])
        request.state.auth_transport = user['auth_transport']
        request.state.client_kind = user['client_kind']
        return user

    # legacy cookie-only fallback is compatibility-only and forbidden for adult postgres profile
    if not legacy_cookie_fallback_allowed(settings=get_settings()):
        if allow_missing:
            return None
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='auth.legacy_cookie_session_forbidden')

    try:
        user_id = request.session.get('user_id')
    except Exception:
        user_id = None
    if not user_id:
        if allow_missing:
            return None
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    tenant_id = request.session.get('tenant_id', 'default')
    u = storage.get_user_by_id(tenant_id=tenant_id, user_id=int(user_id))
    if not u:
        if allow_missing:
            return None
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    u = dict(u)
    u['role'] = map_legacy_role(u.get('role'))
    u['permissions'] = storage.get_permissions_for_role(role=u['role'])
    u['tenant_id'] = u.get('tenant_id') or tenant_id
    u['allowed_farm_ids'] = _parse_scope_list(u.get('allowed_farm_ids_json'))
    u['allowed_site_ids'] = _parse_scope_list(u.get('allowed_site_ids_json'))
    u['active_farm_id'] = request.session.get('active_farm')
    u['active_site_id'] = request.session.get('active_site')
    u['auth_transport'] = 'legacy_cookie_session'
    u['client_kind'] = 'web'
    request.state.auth_context = u
    request.state.auth_transport = 'legacy_cookie_session'
    request.state.client_kind = 'web'
    return u


def get_current_user(request: Request, conn=Depends(get_db)) -> dict:
    return resolve_request_auth_context(request, conn, allow_missing=False) or {}


def require_roles(*roles: str) -> Callable:
    def dep(user: dict = Depends(get_current_user)) -> dict:
        if user.get('role') not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
        return user

    return dep
