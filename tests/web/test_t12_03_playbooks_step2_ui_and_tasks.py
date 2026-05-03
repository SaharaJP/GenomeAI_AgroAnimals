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


def test_t12_03_ui_pages_and_task_playbook_integration(client: TestClient):
    # Viewer can open UI pages
    _login(client, "viewer", "viewer")
    r_pb = client.get("/playbooks")
    assert r_pb.status_code == 200
    assert "Playbooks" in r_pb.text

    r_wf = client.get("/workflow")
    assert r_wf.status_code == 200
    assert "Workflow" in r_wf.text

    # Viewer cannot create playbook via UI
    r_forbid = client.post(
        "/playbooks/create",
        data={
            "target_kind": "task",
            "target_type": "mastitis_control",
            "farm_id": "",
            "name": "x",
            "description": "",
            "comment": "",
            "set_active": "1",
            "steps_json": "[]",
        },
        follow_redirects=False,
    )
    assert r_forbid.status_code == 403
    client.get("/logout")

    # Zootech creates a task and sees recommended playbook in API
    _login(client, "zootech", "zootech")
    r_create_task = client.post(
        "/api/tasks_v1",
        json={
            "task_type": "mastitis_control",
            "title": "Test mastitis control",
            "why": {"farm_id": "F1"},
        },
    )
    assert r_create_task.status_code == 200
    task_id = r_create_task.json().get("task_id")
    assert task_id

    r_get_task = client.get(f"/api/tasks_v1/{task_id}")
    assert r_get_task.status_code == 200
    t = r_get_task.json()
    assert t.get("playbook") is not None
    assert t["playbook"]["target_kind"] == "task"
    assert t["playbook"]["target_type"] == "mastitis_control"
    assert "контроль" in (t["playbook"].get("name") or "").lower()

    # Zootech can create playbook override via UI and it is activated
    r_create_pb_ui = client.post(
        "/playbooks/create",
        data={
            "target_kind": "task",
            "target_type": "mastitis_control",
            "farm_id": "F1",
            "name": "Чек‑лист: контроль мастита (F1)",
            "description": "override",
            "comment": "ui test",
            "set_active": "1",
            "steps_json": "[{\"key\":\"s1\",\"title\":\"Шаг\",\"required\":true}]",
        },
        follow_redirects=False,
    )
    assert r_create_pb_ui.status_code in (302, 303)

    # Active for farm F1 should be override
    r_active = client.get(
        "/api/playbooks_v1/active",
        params={"target_kind": "task", "target_type": "mastitis_control", "farm_id": "F1"},
    )
    assert r_active.status_code == 200
    pb = r_active.json().get("playbook")
    assert pb is not None
    assert pb.get("farm_id") == "F1"
    assert pb.get("name") == "Чек‑лист: контроль мастита (F1)"

    client.get("/logout")

    # Viewer sees task and playbook name on workflow page
    _login(client, "viewer", "viewer")
    r_wf2 = client.get("/workflow")
    assert r_wf2.status_code == 200
    assert "Чек" in r_wf2.text or "контроль" in r_wf2.text.lower()
