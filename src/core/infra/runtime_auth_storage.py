from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from core.infra.runtime_storage import (
    RuntimeStorageConfigError,
    resolve_runtime_storage_settings,
)
from core.security import DEFAULT_ROLE_PERMISSIONS, map_legacy_role

try:  # pragma: no cover - optional dependency in dev container
    import psycopg  # type: ignore
    from psycopg.rows import dict_row  # type: ignore
except Exception:  # pragma: no cover - optional dependency in dev container
    psycopg = None
    dict_row = None


@dataclass(frozen=True)
class RuntimeAuthStorageDiagnostics:
    backend: str
    profile: str
    adult_mode: bool
    compat_mode: bool
    postgres_dsn_present: bool
    postgres_driver_available: bool
    legacy_cookie_fallback_allowed: bool
    session_diagnostics_backend: str
    forbidden_fallback_detected: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            'backend': self.backend,
            'profile': self.profile,
            'adult_mode': self.adult_mode,
            'compat_mode': self.compat_mode,
            'postgres_dsn_present': self.postgres_dsn_present,
            'postgres_driver_available': self.postgres_driver_available,
            'legacy_cookie_fallback_allowed': self.legacy_cookie_fallback_allowed,
            'session_diagnostics_backend': self.session_diagnostics_backend,
            'forbidden_fallback_detected': self.forbidden_fallback_detected,
        }


def _parse_scope_json(value: Any) -> list[str]:
    if value in (None, ''):
        return []
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip()]
    try:
        parsed = json.loads(value)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(x) for x in parsed if str(x).strip()]


def auth_storage_diagnostics(*, settings: Any | None = None) -> RuntimeAuthStorageDiagnostics:
    if settings is None:
        from core.infra.web_db import get_settings
        settings = get_settings()
    runtime = resolve_runtime_storage_settings(
        project_root=settings.project_root,
        storage_dir=settings.storage_dir,
        sqlite_db_path=getattr(settings, 'db_path', settings.storage_dir / 'web.db'),
    )
    legacy_cookie_allowed = runtime.backend == 'sqlite' and not runtime.adult_mode
    return RuntimeAuthStorageDiagnostics(
        backend=runtime.backend,
        profile=runtime.profile,
        adult_mode=runtime.adult_mode,
        compat_mode=runtime.compat_mode,
        postgres_dsn_present=bool(runtime.postgres_dsn),
        postgres_driver_available=bool(runtime.postgres_driver_available),
        legacy_cookie_fallback_allowed=legacy_cookie_allowed,
        session_diagnostics_backend=runtime.backend,
        forbidden_fallback_detected=bool(runtime.adult_mode and runtime.backend != 'postgres'),
    )


def legacy_cookie_fallback_allowed(*, settings: Any | None = None) -> bool:
    return bool(auth_storage_diagnostics(settings=settings).legacy_cookie_fallback_allowed)


class SqliteCompatAuthStorage:
    backend = 'sqlite'

    def __init__(self, conn):
        self.conn = conn

    def diagnostics(self, *, settings: Any | None = None) -> dict[str, Any]:
        return auth_storage_diagnostics(settings=settings).as_dict()

    def get_user_by_username(self, *, tenant_id: str, username: str) -> Optional[dict[str, Any]]:
        from core.infra.web_db import get_user_by_username
        user = get_user_by_username(self.conn, username=username, tenant_id=tenant_id)
        return dict(user) if user else None

    def get_user_by_id(self, *, tenant_id: str, user_id: int) -> Optional[dict[str, Any]]:
        from core.infra.web_db import get_user_by_id
        user = get_user_by_id(self.conn, user_id=user_id, tenant_id=tenant_id)
        return dict(user) if user else None

    def get_permissions_for_role(self, *, role: str) -> list[str]:
        from core.infra.web_db import get_permissions_for_role
        return list(get_permissions_for_role(self.conn, role=role))

    def create_session(self, **kwargs) -> dict[str, Any]:
        from core.infra.web_db import create_auth_session
        return create_auth_session(self.conn, **kwargs)

    def get_session_by_id(self, *, session_id: str) -> Optional[dict[str, Any]]:
        from core.infra.web_db import get_auth_session_by_id
        return get_auth_session_by_id(self.conn, session_id=session_id)

    def get_session_by_access_token(self, *, access_token: str) -> Optional[dict[str, Any]]:
        from core.infra.web_db import get_auth_session_by_access_token
        return get_auth_session_by_access_token(self.conn, access_token=access_token)

    def get_session_by_refresh_token(self, *, refresh_token: str) -> Optional[dict[str, Any]]:
        from core.infra.web_db import get_auth_session_by_refresh_token
        return get_auth_session_by_refresh_token(self.conn, refresh_token=refresh_token)

    def touch_session(self, **kwargs) -> Optional[dict[str, Any]]:
        from core.infra.web_db import touch_auth_session
        return touch_auth_session(self.conn, **kwargs)

    def rotate_session_tokens(self, **kwargs) -> Optional[dict[str, Any]]:
        from core.infra.web_db import rotate_auth_session_tokens
        return rotate_auth_session_tokens(self.conn, **kwargs)

    def revoke_session(self, *, session_id: str, reason: str = 'logout') -> None:
        from core.infra.web_db import revoke_auth_session
        revoke_auth_session(self.conn, session_id=session_id, reason=reason)

    def revoke_sessions_for_user(self, *, tenant_id: str, user_id: int, reason: str = 'logout_all') -> list[str]:
        from core.infra.web_db import revoke_auth_sessions_for_user
        return revoke_auth_sessions_for_user(self.conn, tenant_id=tenant_id, user_id=user_id, reason=reason)

    def list_sessions_for_user(self, *, tenant_id: str, user_id: int, include_revoked: bool = False) -> list[dict[str, Any]]:
        from core.infra.web_db import list_auth_sessions_for_user
        return list_auth_sessions_for_user(self.conn, tenant_id=tenant_id, user_id=user_id, include_revoked=include_revoked)

    def list_active_sessions(self, *, tenant_id: str, user_id: int | None = None, username: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM auth_sessions WHERE tenant_id=? AND status='active'"
        args: list[Any] = [tenant_id]
        if user_id is not None:
            sql += ' AND user_id=?'
            args.append(int(user_id))
        if username:
            sql += ' AND username=?'
            args.append(str(username))
        sql += ' ORDER BY updated_at DESC, created_at DESC'
        rows = self.conn.execute(sql, tuple(args)).fetchall()
        return [dict(r) for r in rows]

    def list_refresh_lineage(self, *, session_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM auth_session_refresh_lineage WHERE session_id=? ORDER BY rotated_at DESC, id DESC",
            (str(session_id),),
        ).fetchall()
        return [dict(r) for r in rows]

    def record_failed_auth(self, *, tenant_id: str, username: str, reason_code: str, ip: str | None, user_agent: str | None) -> None:
        from core.infra.web_db import record_auth_failed_attempt
        record_auth_failed_attempt(
            self.conn,
            tenant_id=tenant_id,
            username=username,
            reason_code=reason_code,
            ip=ip,
            user_agent=user_agent,
        )

    def list_failed_auth(self, *, tenant_id: str, username: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        from core.infra.web_db import list_auth_failed_attempts
        return list_auth_failed_attempts(self.conn, tenant_id=tenant_id, username=username, limit=limit)


class PostgresAuthStorage:
    backend = 'postgres'

    def __init__(self, *, dsn: str, connection_factory: Callable[[], Any] | None = None):
        self.dsn = str(dsn)
        self._connection_factory = connection_factory
        if not self.dsn:
            raise RuntimeStorageConfigError('postgres auth storage requires DSN')
        if self._connection_factory is None and psycopg is None:
            raise RuntimeStorageConfigError('postgres auth storage requires psycopg or injected connection factory')

    def _connect(self):
        if self._connection_factory is not None:
            return self._connection_factory()
        assert psycopg is not None and dict_row is not None
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def diagnostics(self, *, settings: Any | None = None) -> dict[str, Any]:
        return auth_storage_diagnostics(settings=settings).as_dict()

    def get_user_by_username(self, *, tenant_id: str, username: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT user_id AS id, tenant_id, username, password_hash, role, is_active, external_org, collaboration_mode, allowed_farm_ids_json, allowed_site_ids_json FROM auth_users WHERE tenant_id=%s AND username=%s AND is_active=TRUE",
                    (tenant_id, username),
                )
                row = cur.fetchone()
                return dict(row) if row else None

    def get_user_by_id(self, *, tenant_id: str, user_id: int) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT user_id AS id, tenant_id, username, password_hash, role, is_active, external_org, collaboration_mode, allowed_farm_ids_json, allowed_site_ids_json FROM auth_users WHERE tenant_id=%s AND user_id=%s AND is_active=TRUE",
                    (tenant_id, int(user_id)),
                )
                row = cur.fetchone()
                return dict(row) if row else None

    def get_permissions_for_role(self, *, role: str) -> list[str]:
        return list(DEFAULT_ROLE_PERMISSIONS.get(map_legacy_role(role), []))

    def create_session(self, **kwargs) -> dict[str, Any]:
        from core.infra.web_db import _new_session_id, _new_access_token, _new_refresh_token, _token_hash, utcnow_iso, _iso_after_seconds
        session_id = _new_session_id()
        access_token = _new_access_token()
        refresh_token = _new_refresh_token()
        created_at = utcnow_iso()
        access_ttl_sec = int(kwargs.get('access_ttl_sec', 900))
        refresh_ttl_sec = int(kwargs.get('refresh_ttl_sec', 60 * 60 * 24 * 30))
        expires_at = _iso_after_seconds(access_ttl_sec)
        refresh_expires_at = _iso_after_seconds(refresh_ttl_sec)
        allowed_farm_ids_json = json.dumps(list(kwargs.get('allowed_farm_ids') or []), ensure_ascii=False)
        allowed_site_ids_json = json.dumps(list(kwargs.get('allowed_site_ids') or []), ensure_ascii=False)
        metadata_json = json.dumps(dict(kwargs.get('metadata') or {}), ensure_ascii=False)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO auth_sessions(
                      session_id, tenant_id, user_id, username, role, user_source, client_kind, auth_transport,
                      status, created_at, updated_at, last_seen_at, expires_at, refresh_expires_at,
                      access_token_hash, refresh_token_hash, device_id, device_label, device_platform, device_app_version,
                      active_farm_id, active_site_id, allowed_farm_ids_json, allowed_site_ids_json, metadata_json,
                      last_ip, last_user_agent, revoked_at, revoke_reason
                    ) VALUES(
                      %s,%s,%s,%s,%s,%s,%s,%s,
                      %s,%s,%s,%s,%s,%s,
                      %s,%s,%s,%s,%s,%s,
                      %s,%s,%s,%s,%s,
                      %s,%s,%s,%s
                    )
                    """,
                    (
                        session_id,
                        kwargs.get('tenant_id', 'default'),
                        int(kwargs.get('user_id') or 0),
                        str(kwargs.get('username') or ''),
                        str(kwargs.get('role') or ''),
                        str(kwargs.get('user_source') or 'users_v2'),
                        str(kwargs.get('client_kind') or 'unknown'),
                        str(kwargs.get('auth_transport') or 'bearer'),
                        'active',
                        created_at,
                        created_at,
                        created_at,
                        expires_at,
                        refresh_expires_at,
                        _token_hash(access_token),
                        _token_hash(refresh_token),
                        kwargs.get('device_id'),
                        kwargs.get('device_label'),
                        kwargs.get('device_platform'),
                        kwargs.get('device_app_version'),
                        kwargs.get('active_farm_id'),
                        kwargs.get('active_site_id'),
                        allowed_farm_ids_json,
                        allowed_site_ids_json,
                        metadata_json,
                        kwargs.get('ip'),
                        kwargs.get('user_agent'),
                        None,
                        None,
                    ),
                )
                cur.execute(
                    "INSERT INTO auth_session_refresh_lineage(session_id, previous_refresh_token_hash, new_refresh_token_hash, rotated_at, device_app_version) VALUES(%s,%s,%s,%s,%s)",
                    (session_id, None, _token_hash(refresh_token), created_at, kwargs.get('device_app_version')),
                )
            conn.commit()
        row = self.get_session_by_id(session_id=session_id) or {}
        row['access_token'] = access_token
        row['refresh_token'] = refresh_token
        row['access_ttl_sec'] = access_ttl_sec
        row['refresh_ttl_sec'] = refresh_ttl_sec
        return row

    def _fetch_session(self, where_sql: str, params: tuple[Any, ...]) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT * FROM auth_sessions WHERE {where_sql}", params)
                row = cur.fetchone()
                return dict(row) if row else None

    def get_session_by_id(self, *, session_id: str) -> Optional[dict[str, Any]]:
        return self._fetch_session('session_id=%s', (str(session_id),))

    def get_session_by_access_token(self, *, access_token: str) -> Optional[dict[str, Any]]:
        from core.infra.web_db import _token_hash
        return self._fetch_session('access_token_hash=%s', (_token_hash(access_token),))

    def get_session_by_refresh_token(self, *, refresh_token: str) -> Optional[dict[str, Any]]:
        from core.infra.web_db import _token_hash
        return self._fetch_session('refresh_token_hash=%s', (_token_hash(refresh_token),))

    def touch_session(self, **kwargs) -> Optional[dict[str, Any]]:
        from core.infra.web_db import utcnow_iso
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE auth_sessions
                    SET updated_at=%s, last_seen_at=%s,
                        last_ip=COALESCE(%s, last_ip), last_user_agent=COALESCE(%s, last_user_agent),
                        active_farm_id=COALESCE(%s, active_farm_id), active_site_id=COALESCE(%s, active_site_id)
                    WHERE session_id=%s AND status='active'
                    """,
                    (utcnow_iso(), utcnow_iso(), kwargs.get('ip'), kwargs.get('user_agent'), kwargs.get('active_farm_id'), kwargs.get('active_site_id'), str(kwargs.get('session_id') or '')),
                )
            conn.commit()
        return self.get_session_by_id(session_id=str(kwargs.get('session_id') or ''))

    def rotate_session_tokens(self, **kwargs) -> Optional[dict[str, Any]]:
        from core.infra.web_db import _new_access_token, _new_refresh_token, _token_hash, utcnow_iso, _iso_after_seconds
        session_id = str(kwargs.get('session_id') or '')
        old = self.get_session_by_id(session_id=session_id)
        if not old or str(old.get('status') or '') != 'active':
            return None
        access_token = _new_access_token()
        refresh_token = _new_refresh_token()
        access_ttl_sec = int(kwargs.get('access_ttl_sec', 900))
        refresh_ttl_sec = int(kwargs.get('refresh_ttl_sec', 60 * 60 * 24 * 30))
        now = utcnow_iso()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE auth_sessions
                    SET updated_at=%s, last_seen_at=%s, expires_at=%s, refresh_expires_at=%s,
                        access_token_hash=%s, refresh_token_hash=%s,
                        last_ip=COALESCE(%s, last_ip), last_user_agent=COALESCE(%s, last_user_agent),
                        device_app_version=COALESCE(%s, device_app_version)
                    WHERE session_id=%s AND status='active'
                    """,
                    (now, now, _iso_after_seconds(access_ttl_sec), _iso_after_seconds(refresh_ttl_sec), _token_hash(access_token), _token_hash(refresh_token), kwargs.get('ip'), kwargs.get('user_agent'), kwargs.get('device_app_version'), session_id),
                )
                cur.execute(
                    "INSERT INTO auth_session_refresh_lineage(session_id, previous_refresh_token_hash, new_refresh_token_hash, rotated_at, device_app_version) VALUES(%s,%s,%s,%s,%s)",
                    (session_id, old.get('refresh_token_hash'), _token_hash(refresh_token), now, kwargs.get('device_app_version')),
                )
            conn.commit()
        row = self.get_session_by_id(session_id=session_id) or {}
        row['access_token'] = access_token
        row['refresh_token'] = refresh_token
        row['access_ttl_sec'] = access_ttl_sec
        row['refresh_ttl_sec'] = refresh_ttl_sec
        return row

    def revoke_session(self, *, session_id: str, reason: str = 'logout') -> None:
        from core.infra.web_db import utcnow_iso
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE auth_sessions SET status='revoked', updated_at=%s, revoked_at=%s, revoke_reason=%s, access_token_hash=NULL, refresh_token_hash=NULL WHERE session_id=%s AND status='active'",
                    (utcnow_iso(), utcnow_iso(), str(reason or 'logout'), str(session_id)),
                )
            conn.commit()

    def revoke_sessions_for_user(self, *, tenant_id: str, user_id: int, reason: str = 'logout_all') -> list[str]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT session_id FROM auth_sessions WHERE tenant_id=%s AND user_id=%s AND status='active'", (tenant_id, int(user_id)))
                rows = cur.fetchall() or []
                ids = [str(r['session_id']) for r in rows]
                if ids:
                    from core.infra.web_db import utcnow_iso
                    cur.execute(
                        "UPDATE auth_sessions SET status='revoked', updated_at=%s, revoked_at=%s, revoke_reason=%s, access_token_hash=NULL, refresh_token_hash=NULL WHERE tenant_id=%s AND user_id=%s AND status='active'",
                        (utcnow_iso(), utcnow_iso(), str(reason or 'logout_all'), tenant_id, int(user_id)),
                    )
            conn.commit()
        return ids

    def list_sessions_for_user(self, *, tenant_id: str, user_id: int, include_revoked: bool = False) -> list[dict[str, Any]]:
        sql = "SELECT * FROM auth_sessions WHERE tenant_id=%s AND user_id=%s"
        params: list[Any] = [tenant_id, int(user_id)]
        if not include_revoked:
            sql += " AND status='active'"
        sql += " ORDER BY updated_at DESC, created_at DESC"
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                return [dict(r) for r in (cur.fetchall() or [])]

    def list_active_sessions(self, *, tenant_id: str, user_id: int | None = None, username: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM auth_sessions WHERE tenant_id=%s AND status='active'"
        params: list[Any] = [tenant_id]
        if user_id is not None:
            sql += " AND user_id=%s"
            params.append(int(user_id))
        if username:
            sql += " AND username=%s"
            params.append(str(username))
        sql += ' ORDER BY updated_at DESC, created_at DESC'
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                return [dict(r) for r in (cur.fetchall() or [])]

    def list_refresh_lineage(self, *, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM auth_session_refresh_lineage WHERE session_id=%s ORDER BY rotated_at DESC, id DESC",
                    (str(session_id),),
                )
                return [dict(r) for r in (cur.fetchall() or [])]

    def record_failed_auth(self, *, tenant_id: str, username: str, reason_code: str, ip: str | None, user_agent: str | None) -> None:
        created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO auth_failed_attempts(tenant_id, username, reason_code, created_at, ip, user_agent) VALUES(%s,%s,%s,%s,%s,%s)",
                    (tenant_id, username, reason_code, created_at, ip, user_agent),
                )
            conn.commit()

    def list_failed_auth(self, *, tenant_id: str, username: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        sql = "SELECT * FROM auth_failed_attempts WHERE tenant_id=%s"
        params: list[Any] = [tenant_id]
        if username:
            sql += ' AND username=%s'
            params.append(str(username))
        sql += ' ORDER BY created_at DESC LIMIT %s'
        params.append(int(limit))
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                return [dict(r) for r in (cur.fetchall() or [])]


def resolve_runtime_auth_storage(*, conn=None, settings: Any | None = None, postgres_connection_factory: Callable[[], Any] | None = None):
    if settings is None:
        from core.infra.web_db import get_settings
        settings = get_settings()
    runtime = resolve_runtime_storage_settings(
        project_root=settings.project_root,
        storage_dir=settings.storage_dir,
        sqlite_db_path=getattr(settings, 'db_path', settings.storage_dir / 'web.db'),
    )
    if runtime.backend == 'sqlite':
        if conn is None:
            raise RuntimeStorageConfigError('sqlite auth storage requires live sqlite connection')
        return SqliteCompatAuthStorage(conn)
    if runtime.backend == 'postgres':
        return PostgresAuthStorage(dsn=runtime.postgres_dsn or '', connection_factory=postgres_connection_factory)
    raise RuntimeStorageConfigError(f'unsupported auth runtime backend: {runtime.backend}')
