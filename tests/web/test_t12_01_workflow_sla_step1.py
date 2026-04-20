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


def test_task_create_without_due_sets_sla_due_and_domain(client: TestClient):
    _login(client, "zootech", "zootech")

    r = client.post(
        "/api/tasks_v1",
        json={
            "task_type": "mastitis_control",
            "title": "Manual task without due",
            "priority": 2,
            "domain": "health",
        },
    )
    assert r.status_code == 200
    task_id = r.json()["task_id"]

    rget = client.get(f"/api/tasks_v1/{task_id}")
    assert rget.status_code == 200
    t = rget.json()

    assert t.get("domain") == "health"
    assert t.get("due_at"), "due_at must be auto-set from SLA defaults"
    assert t.get("sla_hours") is not None
    assert (t.get("sla_source") or "").strip() in ("cfg.default", "user.due_at", "derived.from_due_at")
