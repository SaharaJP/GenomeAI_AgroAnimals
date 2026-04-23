from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from streamlit_app.auth_bridge import (
    AUTH_STATE_KEYS,
    authenticate_streamlit_user,
    build_fastapi_session_payload,
    build_role_context,
    clear_streamlit_session,
    connect_web_db,
    resolve_user_permissions,
    store_streamlit_session,
    sync_active_context,
)
from web_cabinet.auth import hash_password
from web_cabinet import rbac


def _ctx(tmp_path: Path):
    return SimpleNamespace(web_storage_dir=tmp_path / "web", artifacts_dir=tmp_path / "artifacts")


def test_t18_02_streamlit_auth_uses_demo_users_and_role_permissions(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    for username, role in [
        ("admin", rbac.ROLE_ADMIN),
        ("operator", rbac.ROLE_OPERATOR),
        ("viewer", rbac.ROLE_VIEWER),
        ("director", rbac.ROLE_DIRECTOR),
        ("zootech", rbac.ROLE_ZOOTECH),
        ("vet", rbac.ROLE_VET),
    ]:
        result = authenticate_streamlit_user(
            ctx,
            username=username,
            password=username,
            tenant_id="default",
            hash_password_fn=hash_password,
        )
        assert result.ok is True
        assert result.user is not None
        assert result.user["role"] == role
        assert set(result.user["permissions"]) == set(rbac.ROLE_PERMISSIONS.get(role, []))


def test_t18_02_invalid_credentials_use_unified_error_payload(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    result = authenticate_streamlit_user(
        ctx,
        username="viewer",
        password="wrong",
        tenant_id="default",
        hash_password_fn=hash_password,
    )
    assert result.ok is False
    assert result.error is not None
    assert result.error["error"] == "auth.invalid_credentials"
    assert "Неверный логин/пароль" in result.error["detail"]


def test_t18_02_store_session_keeps_fastapi_compatible_keys_and_active_context(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    result = authenticate_streamlit_user(
        ctx,
        username="director",
        password="director",
        tenant_id="default",
        hash_password_fn=hash_password,
    )
    user = result.user
    assert user is not None

    state: dict[str, object] = {}
    stored = store_streamlit_session(
        state,
        user=user,
        request_id="st_req_demo",
        active_farm="farm_01",
        active_site="site_a",
        active_data_version="dv_2026_03",
    )
    assert stored["role"] == rbac.ROLE_DIRECTOR
    assert state["user_id"] == stored["id"]
    assert state["tenant_id"] == "default"
    assert state["user_source"] == "users_v2"
    assert state["request_id"] == "st_req_demo"
    assert state["active_farm"] == "farm_01"
    assert state["active_site"] == "site_a"
    assert state["active_data_version"] == "dv_2026_03"

    fastapi_payload = build_fastapi_session_payload(stored)
    assert fastapi_payload == {
        "user_id": stored["id"],
        "tenant_id": "default",
        "user_source": "users_v2",
    }

    role_ctx = build_role_context(state, stored)
    assert role_ctx.user_id == stored["id"]
    assert role_ctx.role == rbac.ROLE_DIRECTOR
    assert role_ctx.active_farm == "farm_01"
    assert role_ctx.active_site == "site_a"
    assert role_ctx.active_data_version == "dv_2026_03"
    assert role_ctx.request_id == "st_req_demo"


def test_t18_02_sync_active_context_promotes_page_scoped_state() -> None:
    state: dict[str, object] = {
        "director_summary.farm_id": "farm_x",
        "director_summary.site_id": "site_7",
        "regular_reports.data_version": "dv_sync_01",
    }
    synced = sync_active_context(state)
    assert synced["active_farm"] == "farm_x"
    assert synced["active_site"] == "site_7"
    assert synced["active_data_version"] == "dv_sync_01"
    assert state["active_farm"] == "farm_x"
    assert state["active_site"] == "site_7"
    assert state["active_data_version"] == "dv_sync_01"


def test_t18_02_clear_streamlit_session_removes_auth_and_context_keys() -> None:
    state: dict[str, object] = {key: f"value_{idx}" for idx, key in enumerate(AUTH_STATE_KEYS, start=1)}
    clear_streamlit_session(state)
    for key in AUTH_STATE_KEYS:
        assert key not in state


def test_t18_02_rbac_consistency_between_db_and_core(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    conn = connect_web_db(ctx, hash_password_fn=hash_password)
    try:
        for role in [
            rbac.ROLE_ADMIN,
            rbac.ROLE_DIRECTOR,
            rbac.ROLE_ZOOTECH,
            rbac.ROLE_VET,
            rbac.ROLE_OPERATOR,
            rbac.ROLE_VIEWER,
        ]:
            perms = resolve_user_permissions(conn=conn, role=role)
            assert set(perms) == set(rbac.ROLE_PERMISSIONS.get(role, []))
    finally:
        conn.close()
