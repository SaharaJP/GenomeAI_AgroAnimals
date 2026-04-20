from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest
from starlette.requests import Request

from web_cabinet.auth import hash_password
from core.infra.web_db import (
    connect,
    create_auth_session,
    create_user_v2,
    get_settings,
    init_db,
    list_auth_failed_attempts,
    list_auth_refresh_lineage,
    record_auth_failed_attempt,
    rotate_auth_session_tokens,
)


def _request_with_session(session: dict) -> Request:
    scope = {
        'type': 'http',
        'method': 'GET',
        'path': '/',
        'headers': [],
        'query_string': b'',
        'client': ('127.0.0.1', 5000),
        'server': ('testserver', 80),
        'scheme': 'http',
    }
    scope['session'] = dict(session)
    request = Request(scope)
    return request


def test_t34_02_refresh_lineage_and_failed_auth_sqlite_compat(tmp_path: Path) -> None:
    os.environ['GENOMEAI_PROJECT_ROOT'] = str(Path(__file__).resolve().parents[1])
    os.environ['GENOMEAI_WEB_STORAGE'] = str(tmp_path / 'web_storage')
    os.environ['GENOMEAI_ARTIFACTS_ROOT'] = str(tmp_path / 'artifacts')
    os.environ['GENOMEAI_DEPLOY_PROFILE'] = 'test'
    os.environ['GENOMEAI_RUNTIME_STORAGE_BACKEND'] = 'sqlite'

    settings = get_settings()
    conn = connect(settings.db_path)
    try:
        init_db(conn)
        row = create_auth_session(
            conn,
            tenant_id='default',
            user_id=1,
            username='admin',
            role='Admin',
            client_kind='android',
            auth_transport='bearer',
        )
        rotated = rotate_auth_session_tokens(conn, session_id=str(row['session_id']))
        assert rotated is not None
        lineage = list_auth_refresh_lineage(conn, session_id=str(row['session_id']))
        assert len(lineage) >= 2

        record_auth_failed_attempt(
            conn,
            tenant_id='default',
            username='bad_user',
            reason_code='invalid_credentials',
            ip='127.0.0.1',
            user_agent='pytest',
        )
        attempts = list_auth_failed_attempts(conn, tenant_id='default', username='bad_user')
        assert attempts
        assert attempts[0]['reason_code'] == 'invalid_credentials'
    finally:
        conn.close()


def test_t34_02_legacy_cookie_fallback_forbidden_for_adult(monkeypatch: pytest.MonkeyPatch) -> None:
    import web_cabinet.auth as authmod

    class _FakeStorage:
        backend = 'postgres'

        def get_session_by_access_token(self, *, access_token: str):
            return None

        def get_session_by_id(self, *, session_id: str):
            return None

        def get_user_by_id(self, *, tenant_id: str, user_id: int):
            return None

        def get_permissions_for_role(self, *, role: str):
            return []

    monkeypatch.setattr(authmod, 'resolve_runtime_auth_storage', lambda conn=None: _FakeStorage())
    monkeypatch.setattr(authmod, 'legacy_cookie_fallback_allowed', lambda settings=None: False)

    request = _request_with_session({'user_id': 1, 'tenant_id': 'default'})
    with pytest.raises(Exception) as exc:
        authmod.resolve_request_auth_context(request, conn=None, allow_missing=False)
    assert 'legacy_cookie_session_forbidden' in str(exc.value)
