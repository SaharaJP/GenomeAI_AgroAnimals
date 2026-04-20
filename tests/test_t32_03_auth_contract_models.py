from __future__ import annotations

from packages.contracts.auth_boundary_v1 import (
    AuthDeviceInfo,
    AuthLoginRequest,
    AuthLoginResponse,
    AuthScope,
    AuthSessionView,
    AuthTokenBundle,
    AuthUserView,
)


def test_t32_03_auth_contract_models_validate() -> None:
    request = AuthLoginRequest(
        username='operator',
        password='secret',
        tenant_id='default',
        client_kind='android',
        active_farm_id='farm-1',
        device=AuthDeviceInfo(device_id='d1', device_label='Pixel', platform='android', app_version='1.0.0'),
    )
    assert request.client_kind == 'android'
    assert request.device.device_id == 'd1'

    user = AuthUserView(user_id=1, username='operator', role='Operator', permissions=['tasks.view'])
    scope = AuthScope(tenant_id='default', allowed_farm_ids=['farm-1'], active_farm_id='farm-1')
    session = AuthSessionView(
        session_id='sess_1',
        client_kind='android',
        auth_transport='bearer',
        status='active',
        created_at='2026-04-12T20:00:00+00:00',
        updated_at='2026-04-12T20:00:00+00:00',
        device=AuthDeviceInfo(device_id='d1', platform='android'),
        scope=scope,
        current=True,
    )
    tokens = AuthTokenBundle(
        access_token='ga_at_x',
        refresh_token='ga_rt_x',
        expires_in_sec=900,
        refresh_expires_in_sec=2592000,
    )
    response = AuthLoginResponse(user=user, session=session, scope=scope, tokens=tokens)
    assert response.schema == 'genomeai.api.auth.login.v1'
    assert response.session.current is True
    assert response.tokens.token_type == 'Bearer'
