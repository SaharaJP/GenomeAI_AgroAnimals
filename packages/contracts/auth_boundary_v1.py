from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class AuthDeviceInfo(BaseModel):
    device_id: Optional[str] = None
    device_label: Optional[str] = None
    platform: Optional[str] = None
    app_version: Optional[str] = None


class AuthScope(BaseModel):
    tenant_id: str = 'default'
    allowed_farm_ids: list[str] = Field(default_factory=list)
    allowed_site_ids: list[str] = Field(default_factory=list)
    active_farm_id: Optional[str] = None
    active_site_id: Optional[str] = None


class AuthUserView(BaseModel):
    user_id: int
    username: str
    role: str
    permissions: list[str] = Field(default_factory=list)
    collaboration_mode: Optional[str] = None
    external_org: Optional[str] = None


class AuthSessionView(BaseModel):
    session_id: str
    client_kind: str
    auth_transport: str
    status: str
    created_at: str
    updated_at: str
    last_seen_at: Optional[str] = None
    expires_at: Optional[str] = None
    refresh_expires_at: Optional[str] = None
    device: AuthDeviceInfo = Field(default_factory=AuthDeviceInfo)
    scope: AuthScope
    current: bool = False


class AuthTokenBundle(BaseModel):
    token_type: str = 'Bearer'
    access_token: str
    refresh_token: str
    expires_in_sec: int
    refresh_expires_in_sec: int


class AuthLoginRequest(BaseModel):
    username: str
    password: str
    tenant_id: str = 'default'
    client_kind: str = 'web'
    issue_web_session_cookie: bool = False
    active_farm_id: Optional[str] = None
    active_site_id: Optional[str] = None
    device: AuthDeviceInfo = Field(default_factory=AuthDeviceInfo)


class AuthLoginResponse(BaseModel):
    schema: str = 'genomeai.api.auth.login.v1'
    user: AuthUserView
    session: AuthSessionView
    scope: AuthScope
    tokens: AuthTokenBundle


class AuthRefreshRequest(BaseModel):
    refresh_token: str
    device: AuthDeviceInfo = Field(default_factory=AuthDeviceInfo)


class AuthRefreshResponse(BaseModel):
    schema: str = 'genomeai.api.auth.refresh.v1'
    session: AuthSessionView
    scope: AuthScope
    tokens: AuthTokenBundle


class AuthMeResponse(BaseModel):
    schema: str = 'genomeai.api.auth.me.v1'
    user: AuthUserView
    session: AuthSessionView
    scope: AuthScope


class AuthLogoutRequest(BaseModel):
    all_devices: bool = False


class AuthLogoutResponse(BaseModel):
    schema: str = 'genomeai.api.auth.logout.v1'
    revoked_session_ids: list[str] = Field(default_factory=list)


class AuthSessionsListResponse(BaseModel):
    schema: str = 'genomeai.api.auth.sessions.list.v1'
    items: list[AuthSessionView] = Field(default_factory=list)


class AuthSessionRevokeResponse(BaseModel):
    schema: str = 'genomeai.api.auth.sessions.revoke.v1'
    revoked_session_id: str
