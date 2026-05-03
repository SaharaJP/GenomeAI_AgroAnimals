from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from core.audit.events import write_audit
from streamlit_app.admin_console import (
    admin_console_snapshot,
    admin_create_user,
    admin_reset_password,
    admin_set_user_active,
    admin_set_user_role,
    archive_old_audit_action,
    list_audit_view,
    list_config_overrides,
    list_runtime_logs,
    list_users_security_view,
    performance_diagnostics,
    release_diagnostics,
    restore_diagnostics,
    upload_config_override,
    warning_governance_diagnostics,
)
from streamlit_app.auth_bridge import connect_web_db
from streamlit_app.unified_shell import build_shell_for_user, flatten_shell_sections, load_shell_config
from web_cabinet import rbac
from web_cabinet.auth import hash_password


ROOT = Path(__file__).resolve().parents[1]


def _ctx(tmp_path: Path):
    return SimpleNamespace(web_storage_dir=tmp_path / "web", artifacts_dir=tmp_path / "artifacts")


def _user(role: str) -> dict[str, object]:
    return {
        "id": 1,
        "username": role.lower(),
        "role": role,
        "tenant_id": "default",
        "permissions": list(rbac.ROLE_PERMISSIONS.get(role, [])),
        "request_id": "st_test_t18_07",
    }


def test_t18_07_shell_exposes_admin_console_only_for_admin() -> None:
    cfg = load_shell_config(Path("configs/ui/ia_v3.yaml"))
    admin_flat = flatten_shell_sections(build_shell_for_user(cfg=cfg, role=rbac.ROLE_ADMIN, permissions=set(rbac.ROLE_PERMISSIONS.get(rbac.ROLE_ADMIN, []))))
    for key in ("admin_console", "admin_users_security", "admin_configs_audit", "admin_observability_release"):
        assert key in admin_flat

    operator_flat = flatten_shell_sections(build_shell_for_user(cfg=cfg, role=rbac.ROLE_OPERATOR, permissions=set(rbac.ROLE_PERMISSIONS.get(rbac.ROLE_OPERATOR, []))))
    for key in ("admin_console", "admin_users_security", "admin_configs_audit", "admin_observability_release"):
        assert key not in operator_flat


def test_t18_07_users_security_actions_and_audit(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    connect_web_db(ctx, hash_password_fn=hash_password).close()

    create = admin_create_user(ctx, user=_user(rbac.ROLE_ADMIN), username="qa_user", password="secret1", role=rbac.ROLE_VIEWER)
    assert create.ok is True
    created_id = int((create.payload or {}).get("id") or 0)
    assert created_id > 0

    update_role = admin_set_user_role(ctx, user=_user(rbac.ROLE_ADMIN), user_id=created_id, role=rbac.ROLE_OPERATOR)
    assert update_role.ok is True

    reset = admin_reset_password(ctx, user=_user(rbac.ROLE_ADMIN), user_id=created_id, password="secret2")
    assert reset.ok is True

    disable = admin_set_user_active(ctx, user=_user(rbac.ROLE_ADMIN), user_id=created_id, is_active=False)
    assert disable.ok is True

    view = list_users_security_view(ctx, tenant_id="default")
    by_name = {str(row.get("username")): row for row in view.get("users") or []}
    assert by_name["qa_user"]["role"] == rbac.ROLE_OPERATOR
    assert int(by_name["qa_user"]["is_active"] or 0) == 0

    conn = sqlite3.connect(str(Path(ctx.web_storage_dir) / "web.db"))
    conn.row_factory = sqlite3.Row
    try:
        actions = [str(r[0]) for r in conn.execute("select action from audit_log where action like 'security.user.%streamlit' order by id asc").fetchall()]
    finally:
        conn.close()
    assert {
        "security.user.create.streamlit",
        "security.user.role_update.streamlit",
        "security.user.password_reset.streamlit",
        "security.user.status_update.streamlit",
    }.issubset(set(actions))


def test_t18_07_configs_audit_and_diagnostics(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    connect_web_db(ctx, hash_password_fn=hash_password).close()

    upload = upload_config_override(
        ctx,
        user=_user(rbac.ROLE_ADMIN),
        target_rel_path="security/local_override.yaml",
        filename="local_override.yaml",
        content=b"enabled: true\n",
    )
    assert upload.ok is True
    overrides = list_config_overrides(ctx)
    assert any(str(row.get("relative_path")) == "security/local_override.yaml" for row in overrides)

    audit = list_audit_view(ctx, tenant_id="default", filters={"q": "configs.upload.streamlit", "scope": "active", "limit": 20})
    assert any(str(row.get("action")) == "configs.upload.streamlit" for row in audit.get("rows") or [])

    dry_run = archive_old_audit_action(ctx, user=_user(rbac.ROLE_ADMIN), dry_run=True)
    assert dry_run.ok is True
    assert (dry_run.payload or {}).get("dry_run") is True

    # seed runtime log for diagnostics page helpers
    logs_dir = Path(ctx.web_storage_dir) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "backend_uvicorn.log").write_text("backend ok\n", encoding="utf-8")
    assert list_runtime_logs(ctx)

    warning = warning_governance_diagnostics(ctx)
    perf = performance_diagnostics(ctx)
    restore = restore_diagnostics(ctx)
    release = release_diagnostics(ctx)
    snap = admin_console_snapshot(ctx, tenant_id="default")

    assert "payload" in warning
    assert "payload" in perf
    assert "payload" in restore
    assert "metadata" in release
    assert "observability" in snap
    assert "release" in snap


def test_t18_07_archive_old_audit_applies_and_records_audit(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    conn = connect_web_db(ctx, hash_password_fn=hash_password)
    try:
        conn.execute(
            """
            INSERT INTO audit_log (
                ts, tenant_id, user_id, username, role, action, action_group, object_type, object_id, object_ref,
                data_version, run_id, before_json, after_json, ip, user_agent, status, error, request_id, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2000-01-01T00:00:00+00:00",
                "default",
                1,
                "admin",
                rbac.ROLE_ADMIN,
                "legacy.test",
                "other",
                "test",
                "old_row",
                "test:old_row",
                None,
                None,
                None,
                None,
                None,
                None,
                "OK",
                None,
                "old_req",
                2,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    result = archive_old_audit_action(ctx, user=_user(rbac.ROLE_ADMIN), dry_run=False, limit=100)
    assert result.ok is True
    assert int((((result.payload or {}).get("result") or {}).get("rows_archived") or 0)) >= 1

    conn = sqlite3.connect(str(Path(ctx.web_storage_dir) / "web.db"))
    conn.row_factory = sqlite3.Row
    try:
        archived = conn.execute("select archived_at from audit_log where object_id='old_row'").fetchone()
        actions = [str(r[0]) for r in conn.execute("select action from audit_log where action='config.audit_retention.apply.streamlit'").fetchall()]
    finally:
        conn.close()
    assert archived is not None and archived[0] is not None
    assert "config.audit_retention.apply.streamlit" in actions
