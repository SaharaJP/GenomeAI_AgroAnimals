from __future__ import annotations

import importlib
import os
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


def _login(c: TestClient, username: str, password: str):
    r = c.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert r.status_code in (302, 303)


def test_assign_by_username_and_list_filter(client: TestClient):
    _login(client, "zootech", "zootech")

    # Users catalog for dropdowns
    r_users = client.get("/api/users_v2")
    assert r_users.status_code == 200
    users = r_users.json().get("users") or []
    assert any(u.get("username") == "vet" for u in users)

    # Create task
    r_create = client.post(
        "/api/tasks_v1",
        json={"task_type": "qc_followup", "title": "Check dataset drift", "priority": 2, "domain": "qc"},
    )
    assert r_create.status_code == 200
    task_id = r_create.json()["task_id"]

    # Assign by username
    r_assign = client.post(f"/api/tasks_v1/{task_id}/assign", json={"assignee_username": "vet"})
    assert r_assign.status_code == 200

    r_get = client.get(f"/api/tasks_v1/{task_id}")
    assert r_get.status_code == 200
    t = r_get.json()
    assert t.get("owner_username") == "vet"
    assert t.get("owner_user_id") is not None

    # List filter by owner_username
    r_list = client.get("/api/tasks_v1", params={"owner_username": "vet"})
    assert r_list.status_code == 200
    tasks = r_list.json().get("tasks") or []
    assert any(x.get("task_id") == task_id for x in tasks)
    assert any((x.get("owner_username") == "vet") for x in tasks)

    # Invalid username
    r_bad = client.post(f"/api/tasks_v1/{task_id}/assign", json={"assignee_username": "no_such_user"})
    assert r_bad.status_code == 400
    assert "invalid_assignee_username" in str(r_bad.json())

    # Audit row exists (check as admin)
    client.get("/logout")
    _login(client, "admin", "admin")
    r_a = client.get("/api/audit", params={"action": "tasks_v1.assign"})
    assert r_a.status_code == 200
    rows = r_a.json().get("rows") or []
    assert any((r.get("object_id") == task_id) for r in rows)
