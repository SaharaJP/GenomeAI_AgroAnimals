from __future__ import annotations

import importlib
import os
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[2]
    storage = tmp_path / "web_storage"
    artifacts = tmp_path / "artifacts"
    os.environ["GENOMEAI_PROJECT_ROOT"] = str(repo_root)
    os.environ["GENOMEAI_WEB_STORAGE"] = str(storage)
    os.environ["GENOMEAI_ARTIFACTS_ROOT"] = str(artifacts)
    os.environ["GENOMEAI_WEB_DISABLE_WORKER"] = "1"
    os.environ["GENOMEAI_WEB_SECRET"] = "test-secret"

    import web_cabinet.app as appmod
    importlib.reload(appmod)

    with TestClient(appmod.app) as c:
        yield c


def _login(c: TestClient, username: str, password: str) -> None:
    r = c.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert r.status_code in (302, 303)


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "web.db"))
    conn.row_factory = sqlite3.Row
    return conn


def test_admin_users_page_and_matrix_visible_for_admin_only(client: TestClient):
    _login(client, "admin", "admin")
    r = client.get("/admin/users")
    assert r.status_code == 200
    assert "Security / Users" in r.text
    assert "Матрица прав" in r.text
    assert "users.manage" in r.text

    r_api = client.get("/api/admin/permission-matrix")
    assert r_api.status_code == 200
    payload = r_api.json()
    approve = next(x for x in payload["actions"] if x["key"] == "approve")
    assert approve["roles"]["Admin"] is True
    assert approve["roles"]["Zootech"] is False

    client.get("/logout")
    _login(client, "director", "director")
    r_forbidden = client.get("/admin/users")
    assert r_forbidden.status_code == 403


def test_admin_can_create_update_reset_and_deactivate_user_with_audit(client: TestClient):
    _login(client, "admin", "admin")

    r_create = client.post(
        "/admin/users/create",
        data={"username": "qa.operator", "password": "start123", "role": "Viewer"},
        follow_redirects=False,
    )
    assert r_create.status_code in (302, 303)

    with _db() as conn:
        row = conn.execute(
            "SELECT id, username, role, is_active FROM users_v2 WHERE tenant_id='default' AND username='qa.operator'"
        ).fetchone()
        assert row is not None
        user_id = int(row["id"])
        assert row["role"] == "Viewer"
        assert int(row["is_active"]) == 1

    r_role = client.post(f"/admin/users/{user_id}/role", data={"role": "Operator"}, follow_redirects=False)
    assert r_role.status_code in (302, 303)

    r_reset = client.post(
        f"/admin/users/{user_id}/reset_password",
        data={"password": "newpass123"},
        follow_redirects=False,
    )
    assert r_reset.status_code in (302, 303)

    client.get("/logout")
    _login(client, "qa.operator", "newpass123")
    r_upload = client.get("/upload")
    assert r_upload.status_code == 200

    client.get("/logout")
    _login(client, "admin", "admin")
    r_disable = client.post(f"/admin/users/{user_id}/status", data={"is_active": 0}, follow_redirects=False)
    assert r_disable.status_code in (302, 303)

    with _db() as conn:
        row = conn.execute("SELECT role, is_active FROM users_v2 WHERE id=?", (user_id,)).fetchone()
        assert row is not None
        assert row["role"] == "Operator"
        assert int(row["is_active"]) == 0
        audits = [
            dict(r)
            for r in conn.execute(
                "SELECT action, object_id FROM audit_log WHERE action LIKE 'security.user.%' ORDER BY id ASC"
            ).fetchall()
        ]
    actions = [r["action"] for r in audits]
    assert "security.user.create" in actions
    assert "security.user.role_update" in actions
    assert "security.user.password_reset" in actions
    assert "security.user.status_update" in actions


def test_last_admin_protection_blocks_disable_and_role_downgrade(client: TestClient):
    _login(client, "admin", "admin")

    with _db() as conn:
        admin_row = conn.execute(
            "SELECT id FROM users_v2 WHERE tenant_id='default' AND username='admin'"
        ).fetchone()
        assert admin_row is not None
        admin_id = int(admin_row["id"])

    r_disable = client.post(f"/admin/users/{admin_id}/status", data={"is_active": 0}, follow_redirects=False)
    assert r_disable.status_code == 400
    assert "self_disable" in r_disable.text

    r_role = client.post(f"/admin/users/{admin_id}/role", data={"role": "Director"}, follow_redirects=False)
    assert r_role.status_code == 400
    assert "last_admin" in r_role.text
