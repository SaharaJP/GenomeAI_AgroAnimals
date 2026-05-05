from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from packages.contracts.auth_boundary_v1 import (
    AuthLoginRequest,
    AuthLoginResponse,
    AuthLogoutRequest,
    AuthLogoutResponse,
    AuthMeResponse,
    AuthRefreshRequest,
    AuthRefreshResponse,
    AuthScope,
    AuthSessionRevokeResponse,
    AuthSessionView,
    AuthSessionsListResponse,
    AuthTokenBundle,
    AuthUserView,
    AuthDeviceInfo,
)
from core.audit.events import write_audit
from core.security import ROLE_ADMIN, has_any_permission

from .auth import (
    authenticate,
    build_auth_session_scope,
    create_authenticated_session,
    get_current_user,
    get_db,
)
from core.infra.runtime_auth_storage import resolve_runtime_auth_storage
from web_cabinet.ai.config import get_ai_settings

router = APIRouter(prefix='/api/app/v1/auth', tags=['auth-boundary-v1'])


def _scope_model(user: dict[str, Any], session_row: dict[str, Any] | None = None) -> AuthScope:
    return AuthScope(**build_auth_session_scope(user, session_row))


def _device_model(session_row: dict[str, Any]) -> AuthDeviceInfo:
    return AuthDeviceInfo(
        device_id=session_row.get('device_id'),
        device_label=session_row.get('device_label'),
        platform=session_row.get('device_platform'),
        app_version=session_row.get('device_app_version'),
    )


def _session_model(user: dict[str, Any], session_row: dict[str, Any], *, current_session_id: str | None = None) -> AuthSessionView:
    scope = _scope_model(user, session_row)
    return AuthSessionView(
        session_id=str(session_row.get('session_id') or ''),
        client_kind=str(session_row.get('client_kind') or 'unknown'),
        auth_transport=str(session_row.get('auth_transport') or 'bearer'),
        status=str(session_row.get('status') or 'active'),
        created_at=str(session_row.get('created_at') or ''),
        updated_at=str(session_row.get('updated_at') or ''),
        last_seen_at=session_row.get('last_seen_at'),
        expires_at=session_row.get('expires_at'),
        refresh_expires_at=session_row.get('refresh_expires_at'),
        device=_device_model(session_row),
        scope=scope,
        current=bool(current_session_id and str(session_row.get('session_id')) == str(current_session_id)),
    )


def _user_model(user: dict[str, Any]) -> AuthUserView:
    return AuthUserView(
        user_id=int(user.get('id') or 0),
        username=str(user.get('username') or ''),
        role=str(user.get('role') or ''),
        permissions=[str(x) for x in list(user.get('permissions') or [])],
        collaboration_mode=user.get('collaboration_mode'),
        external_org=user.get('external_org'),
    )


def _token_bundle(session_row: dict[str, Any]) -> AuthTokenBundle:
    return AuthTokenBundle(
        access_token=str(session_row.get('access_token') or ''),
        refresh_token=str(session_row.get('refresh_token') or ''),
        expires_in_sec=int(session_row.get('access_ttl_sec') or 0),
        refresh_expires_in_sec=int(session_row.get('refresh_ttl_sec') or 0),
    )


@router.post('/login', response_model=AuthLoginResponse)
def auth_login(payload: AuthLoginRequest, request: Request, conn=Depends(get_db)):
    storage = resolve_runtime_auth_storage(conn=conn)
    user = authenticate(conn=conn, tenant_id=payload.tenant_id, username=payload.username, password=payload.password)
    ip = request.client.host if request.client else None
    ua = request.headers.get('user-agent')
    if not user:
        try:
            storage.record_failed_auth(tenant_id=payload.tenant_id, username=payload.username, reason_code='invalid_credentials', ip=ip, user_agent=ua)
        except Exception:
            pass
        write_audit(
            conn,
            tenant_id=payload.tenant_id,
            user_id=0,
            username=payload.username,
            role='anonymous',
            action='auth.token.login',
            status='FAIL',
            error='invalid_credentials',
            ip=ip,
            user_agent=ua,
            request_id=getattr(request.state, 'request_id', None),
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='auth.invalid_credentials')

    session_row = create_authenticated_session(
        request=request,
        conn=conn,
        user=user,
        client_kind=payload.client_kind,
        issue_web_session_cookie=bool(payload.issue_web_session_cookie),
        active_farm_id=payload.active_farm_id,
        active_site_id=payload.active_site_id,
        device_id=payload.device.device_id,
        device_label=payload.device.device_label,
        device_platform=payload.device.platform,
        device_app_version=payload.device.app_version,
    )
    user['permissions'] = list(user.get('permissions') or []) or []
    if not user['permissions']:
        user['permissions'] = storage.get_permissions_for_role(role=user['role'])
    user['active_farm_id'] = payload.active_farm_id
    user['active_site_id'] = payload.active_site_id

    write_audit(
        conn,
        tenant_id=str(user.get('tenant_id') or 'default'),
        user_id=int(user.get('id') or 0),
        username=str(user.get('username') or ''),
        role=str(user.get('role') or ''),
        action='auth.token.login',
        object_type='auth_session',
        object_id=str(session_row.get('session_id') or ''),
        after={'client_kind': payload.client_kind, 'device_id': payload.device.device_id, 'issue_web_session_cookie': bool(payload.issue_web_session_cookie)},
        status='OK',
        ip=ip,
        user_agent=ua,
        request_id=getattr(request.state, 'request_id', None),
    )
    session_view = _session_model(user, session_row, current_session_id=session_row.get('session_id'))
    return AuthLoginResponse(user=_user_model(user), session=session_view, scope=session_view.scope, tokens=_token_bundle(session_row))


@router.post('/refresh', response_model=AuthRefreshResponse)
def auth_refresh(payload: AuthRefreshRequest, request: Request, conn=Depends(get_db)):
    storage = resolve_runtime_auth_storage(conn=conn)
    session_row = storage.get_session_by_refresh_token(refresh_token=payload.refresh_token)
    if not session_row or str(session_row.get('status') or '') != 'active':
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='auth.invalid_refresh_token')
    rotated = storage.rotate_session_tokens(
        session_id=str(session_row['session_id']),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get('user-agent'),
        device_app_version=payload.device.app_version,
    )
    if not rotated:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='auth.refresh_failed')
    from .auth import resolve_request_auth_context
    user = resolve_request_auth_context(request, conn, allow_missing=True)
    if not user or str(user.get('auth_session_id') or '') != str(session_row.get('session_id') or ''):
        user = {
            'id': int(session_row.get('user_id') or 0),
            'username': str(session_row.get('username') or ''),
            'role': str(session_row.get('role') or ''),
            'tenant_id': str(session_row.get('tenant_id') or 'default'),
            'permissions': [],
            'active_farm_id': session_row.get('active_farm_id'),
            'active_site_id': session_row.get('active_site_id'),
            'allowed_farm_ids_json': session_row.get('allowed_farm_ids_json'),
            'allowed_site_ids_json': session_row.get('allowed_site_ids_json'),
        }
        user['permissions'] = storage.get_permissions_for_role(role=user['role'])
    if request.session.get('auth_session_id') == str(session_row.get('session_id') or ''):
        request.session['auth_session_id'] = str(session_row.get('session_id') or '')
    write_audit(
        conn,
        tenant_id=str(session_row.get('tenant_id') or 'default'),
        user_id=int(session_row.get('user_id') or 0),
        username=str(session_row.get('username') or ''),
        role=str(session_row.get('role') or ''),
        action='auth.token.refresh',
        object_type='auth_session',
        object_id=str(session_row.get('session_id') or ''),
        status='OK',
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get('user-agent'),
        request_id=getattr(request.state, 'request_id', None),
    )
    session_view = _session_model(user, rotated, current_session_id=str(rotated.get('session_id') or ''))
    return AuthRefreshResponse(session=session_view, scope=session_view.scope, tokens=_token_bundle(rotated))


@router.get('/me', response_model=AuthMeResponse)
def auth_me(request: Request, user=Depends(get_current_user), conn=Depends(get_db)):
    storage = resolve_runtime_auth_storage(conn=conn)
    session_id = str(user.get('auth_session_id') or '')
    session_row = storage.get_session_by_id(session_id=session_id) if session_id else None
    if not session_row:
        # legacy-compatible representation
        session_row = {
            'session_id': session_id or 'legacy-cookie-session',
            'client_kind': user.get('client_kind') or 'web',
            'auth_transport': user.get('auth_transport') or 'legacy_cookie_session',
            'status': 'active',
            'created_at': '',
            'updated_at': '',
            'last_seen_at': None,
            'expires_at': None,
            'refresh_expires_at': None,
            'device_id': None,
            'device_label': None,
            'device_platform': None,
            'device_app_version': None,
            'active_farm_id': user.get('active_farm_id'),
            'active_site_id': user.get('active_site_id'),
            'allowed_farm_ids_json': user.get('allowed_farm_ids') or [],
            'allowed_site_ids_json': user.get('allowed_site_ids') or [],
        }
    session_view = _session_model(user, session_row, current_session_id=session_id or None)
    demo_mode = get_ai_settings().GENOMEAI_AI_DEMO_MODE
    return AuthMeResponse(user=_user_model(user), session=session_view, scope=session_view.scope, demo_mode=demo_mode)


@router.get('/mobile/runtime-proof')
def auth_mobile_runtime_proof(request: Request, user=Depends(get_current_user), conn=Depends(get_db)):
    storage = resolve_runtime_auth_storage(conn=conn)
    session_id = str(user.get('auth_session_id') or '')
    row = storage.get_session_by_id(session_id=session_id) if session_id else None
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='auth.session_not_found')
    session_user = {
        'id': int(row.get('user_id') or user.get('id') or 0),
        'username': str(row.get('username') or user.get('username') or ''),
        'role': str(row.get('role') or user.get('role') or ''),
        'tenant_id': str(row.get('tenant_id') or user.get('tenant_id') or 'default'),
        'allowed_farm_ids_json': row.get('allowed_farm_ids_json'),
        'allowed_site_ids_json': row.get('allowed_site_ids_json'),
        'permissions': storage.get_permissions_for_role(role=str(row.get('role') or user.get('role') or '')),
    }
    session_view = _session_model(session_user, row, current_session_id=session_id)
    diagnostics = storage.diagnostics()
    return {
        'schema': 'genomeai.api.auth.mobile.runtime_proof.v1',
        'storage_backend': str(diagnostics.get('storage_backend') or diagnostics.get('backend') or 'unknown'),
        'auth_backend': str(diagnostics.get('backend') or 'unknown'),
        'request_auth_transport': str(user.get('auth_transport') or row.get('auth_transport') or 'bearer'),
        'refresh_lineage_count': len(storage.list_refresh_lineage(session_id=session_id)),
        'revoke_status': str(row.get('status') or 'active'),
        'session': session_view.model_dump(),
        'scope': session_view.scope.model_dump(),
    }


@router.post('/logout', response_model=AuthLogoutResponse)
def auth_logout(payload: AuthLogoutRequest, request: Request, user=Depends(get_current_user), conn=Depends(get_db)):
    storage = resolve_runtime_auth_storage(conn=conn)
    tenant_id = str(user.get('tenant_id') or 'default')
    user_id = int(user.get('id') or 0)
    if payload.all_devices:
        revoked_ids = storage.revoke_sessions_for_user(tenant_id=tenant_id, user_id=user_id, reason='logout_all')
    else:
        current_session_id = str(user.get('auth_session_id') or '')
        if current_session_id:
            storage.revoke_session(session_id=current_session_id, reason='logout')
            revoked_ids = [current_session_id]
        else:
            revoked_ids = []
    try:
        request.session.clear()
    except Exception:
        pass
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=user_id,
        username=str(user.get('username') or ''),
        role=str(user.get('role') or ''),
        action='auth.logout',
        object_type='auth_session',
        object_id=str(user.get('auth_session_id') or ''),
        after={'all_devices': bool(payload.all_devices), 'revoked_session_ids': revoked_ids},
        status='OK',
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get('user-agent'),
        request_id=getattr(request.state, 'request_id', None),
    )
    return AuthLogoutResponse(revoked_session_ids=revoked_ids)


@router.get('/sessions', response_model=AuthSessionsListResponse)
def auth_sessions(request: Request, user=Depends(get_current_user), conn=Depends(get_db)):
    storage = resolve_runtime_auth_storage(conn=conn)
    rows = storage.list_sessions_for_user(tenant_id=str(user.get('tenant_id') or 'default'), user_id=int(user.get('id') or 0), include_revoked=False)
    current_session_id = str(user.get('auth_session_id') or '') or None
    items = [_session_model(user, row, current_session_id=current_session_id) for row in rows]
    return AuthSessionsListResponse(items=items)


@router.post('/sessions/{session_id}/revoke', response_model=AuthSessionRevokeResponse)
def auth_revoke_session(session_id: str, request: Request, user=Depends(get_current_user), conn=Depends(get_db)):
    storage = resolve_runtime_auth_storage(conn=conn)
    row = storage.get_session_by_id(session_id=session_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='auth.session_not_found')
    is_admin = str(user.get('role') or '') == ROLE_ADMIN or has_any_permission(user.get('permissions') or [], 'users.manage')
    if not is_admin:
        if str(row.get('tenant_id') or '') != str(user.get('tenant_id') or '') or int(row.get('user_id') or 0) != int(user.get('id') or 0):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='auth.session_revoke_forbidden')
    storage.revoke_session(session_id=session_id, reason='user_revoke')
    if request.session.get('auth_session_id') == session_id:
        request.session.clear()
    write_audit(
        conn,
        tenant_id=str(user.get('tenant_id') or 'default'),
        user_id=int(user.get('id') or 0),
        username=str(user.get('username') or ''),
        role=str(user.get('role') or ''),
        action='auth.session.revoke',
        object_type='auth_session',
        object_id=session_id,
        status='OK',
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get('user-agent'),
        request_id=getattr(request.state, 'request_id', None),
    )
    return AuthSessionRevokeResponse(revoked_session_id=session_id)


@router.get('/admin/runtime-storage')
def auth_admin_runtime_storage(user=Depends(get_current_user), conn=Depends(get_db)):
    is_admin = str(user.get('role') or '') == ROLE_ADMIN or has_any_permission(user.get('permissions') or [], 'users.manage', 'audit.view')
    if not is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='auth.admin_forbidden')
    storage = resolve_runtime_auth_storage(conn=conn)
    return storage.diagnostics()


@router.get('/admin/sessions')
def auth_admin_sessions(user=Depends(get_current_user), conn=Depends(get_db), username: str | None = None):
    is_admin = str(user.get('role') or '') == ROLE_ADMIN or has_any_permission(user.get('permissions') or [], 'users.manage', 'audit.view')
    if not is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='auth.admin_forbidden')
    storage = resolve_runtime_auth_storage(conn=conn)
    tenant_id = str(user.get('tenant_id') or 'default')
    rows = storage.list_active_sessions(tenant_id=tenant_id, username=username)
    items = []
    for row in rows:
        session_user = {
            'id': int(row.get('user_id') or 0),
            'username': str(row.get('username') or ''),
            'role': str(row.get('role') or ''),
            'tenant_id': tenant_id,
            'allowed_farm_ids_json': row.get('allowed_farm_ids_json'),
            'allowed_site_ids_json': row.get('allowed_site_ids_json'),
            'permissions': storage.get_permissions_for_role(role=str(row.get('role') or '')),
        }
        items.append({
            'session': _session_model(session_user, row, current_session_id=None).model_dump(),
            'revoke_status': str(row.get('status') or 'active'),
            'refresh_lineage_count': len(storage.list_refresh_lineage(session_id=str(row.get('session_id') or ''))),
        })
    return {'backend': storage.diagnostics().get('backend'), 'items': items}


@router.get('/admin/sessions/{session_id}')
def auth_admin_session_detail(session_id: str, user=Depends(get_current_user), conn=Depends(get_db)):
    is_admin = str(user.get('role') or '') == ROLE_ADMIN or has_any_permission(user.get('permissions') or [], 'users.manage', 'audit.view')
    if not is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='auth.admin_forbidden')
    storage = resolve_runtime_auth_storage(conn=conn)
    row = storage.get_session_by_id(session_id=session_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='auth.session_not_found')
    session_user = {
        'id': int(row.get('user_id') or 0),
        'username': str(row.get('username') or ''),
        'role': str(row.get('role') or ''),
        'tenant_id': str(row.get('tenant_id') or user.get('tenant_id') or 'default'),
        'allowed_farm_ids_json': row.get('allowed_farm_ids_json'),
        'allowed_site_ids_json': row.get('allowed_site_ids_json'),
        'permissions': storage.get_permissions_for_role(role=str(row.get('role') or '')),
    }
    return {
        'backend': storage.diagnostics().get('backend'),
        'session': _session_model(session_user, row, current_session_id=None).model_dump(),
        'revoke_status': str(row.get('status') or 'active'),
        'refresh_lineage': storage.list_refresh_lineage(session_id=session_id),
    }


@router.get('/admin/failed-attempts')
def auth_admin_failed_attempts(user=Depends(get_current_user), conn=Depends(get_db), username: str | None = None):
    is_admin = str(user.get('role') or '') == ROLE_ADMIN or has_any_permission(user.get('permissions') or [], 'users.manage', 'audit.view')
    if not is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='auth.admin_forbidden')
    storage = resolve_runtime_auth_storage(conn=conn)
    tenant_id = str(user.get('tenant_id') or 'default')
    return {
        'backend': storage.diagnostics().get('backend'),
        'items': storage.list_failed_auth(tenant_id=tenant_id, username=username, limit=100),
    }
