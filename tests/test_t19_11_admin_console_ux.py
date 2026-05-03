from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

from streamlit_app.admin_console import (
    admin_console_snapshot,
    build_support_bundle_action,
    list_support_bundles,
    upload_config_override,
)
from streamlit_app.admin_console_ux import (
    build_admin_area_cards,
    build_admin_diagnostic_rows,
    build_audit_display_rows,
    filter_user_rows,
    status_label_from_payload,
)
from streamlit_app.auth_bridge import connect_web_db
from web_cabinet import rbac
from web_cabinet.auth import hash_password


def _ctx(tmp_path: Path):
    return SimpleNamespace(web_storage_dir=tmp_path / "web", artifacts_dir=tmp_path / "artifacts")



def _user(role: str) -> dict[str, object]:
    return {
        "id": 1,
        "username": role.lower(),
        "role": role,
        "tenant_id": "default",
        "permissions": list(rbac.ROLE_PERMISSIONS.get(role, [])),
        "request_id": "st_test_t19_11",
    }



def test_status_label_and_admin_cards_are_operator_readable() -> None:
    assert status_label_from_payload({"status": "ok"}) == "OK"
    assert status_label_from_payload({"summary": {"ok": False}}) == "NA"

    snap = {
        "users_total": 12,
        "audit_archivable_count": 3,
        "release": {"startup": {"ok": True}},
        "warning_governance": {"payload": {"status": "ok"}},
        "performance": {"payload": {"summary": {"ok": True}}},
        "restore": {"payload": {"summary": {"ok": False}}},
    }
    cards = build_admin_area_cards(snap)
    assert [card.key for card in cards] == ["users_roles", "configs_audit", "observability_release"]
    assert cards[1].status == "WARN"

    diag_rows = build_admin_diagnostic_rows(
        release={"metadata": {"version": "1.0.0", "release_channel": "dev"}, "stamp": "v1", "startup": {"ok": True}},
        warning={"payload": {"status": "ok"}, "path": "warning.json"},
        perf={"payload": {"summary": {"ok": True}}, "path": "perf.json"},
        restore={"payload": {"summary": {"ok": False}}, "path": "restore.json"},
        support_bundle_count=2,
        runtime_logs_count=5,
    )
    by_key = {row.key: row for row in diag_rows}
    assert by_key["release"].status == "OK"
    assert by_key["restore"].status == "FAIL"
    assert by_key["support_bundle"].detail == "bundles=2 · logs=5"



def test_filter_user_rows_and_audit_display_rows() -> None:
    users = [
        {"id": 1, "username": "admin", "role": "Admin", "is_active": 1, "_source": "users_v2"},
        {"id": 2, "username": "viewer1", "role": "Viewer", "is_active": 0, "_source": "users_v2"},
    ]
    filtered = filter_user_rows(users, query="view", role="all", active_only=False)
    assert len(filtered) == 1
    assert filtered[0]["username"] == "viewer1"

    rows = build_audit_display_rows([
        {"id": 10, "ts": "2026-01-01", "action": "x", "status": "OK", "username": "admin", "role": "Admin", "request_id": "req", "object": {"ref": "user:1"}}
    ])
    assert rows[0]["object_ref"] == "user:1"



def test_t19_11_support_bundle_action_and_snapshot(tmp_path: Path) -> None:
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

    logs_dir = Path(ctx.web_storage_dir) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "backend_uvicorn.log").write_text("backend ok\n", encoding="utf-8")

    result = build_support_bundle_action(ctx, user=_user(rbac.ROLE_ADMIN), bundle_name="bundle_test")
    assert result.ok is True
    bundles = list_support_bundles(ctx)
    assert bundles and bundles[0]["name"].endswith(".zip")

    snap = admin_console_snapshot(ctx, tenant_id="default")
    assert int(snap.get("support_bundles_total") or 0) >= 1
    assert int(snap.get("runtime_logs_total") or 0) >= 1

    conn = sqlite3.connect(str(Path(ctx.web_storage_dir) / "web.db"))
    conn.row_factory = sqlite3.Row
    try:
        actions = [str(r[0]) for r in conn.execute("select action from audit_log where action in ('artifact.support_bundle.streamlit', 'artifact.support_bundle') order by id asc").fetchall()]
    finally:
        conn.close()
    assert "artifact.support_bundle.streamlit" in actions
