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


def test_stage_and_teams_validation_and_filter(client: TestClient):
    _login(client, "zootech", "zootech")

    # valid team + stage
    r = client.post(
        "/api/tasks_v1",
        json={
            "task_type": "qc_check",
            "title": "QC task",
            "domain": "qc",
            "priority": 3,
            "assignee_team": "team-qc",
            "stage": "plan",
        },
    )
    assert r.status_code == 200
    task_id = r.json()["task_id"]

    rget = client.get(f"/api/tasks_v1/{task_id}")
    assert rget.status_code == 200
    t = rget.json()
    assert t.get("assignee_team") == "team-qc"
    assert t.get("stage") == "plan"

    # update stage
    rup = client.post(f"/api/tasks_v1/{task_id}/update", json={"stage": "execute"})
    assert rup.status_code == 200
    rget2 = client.get(f"/api/tasks_v1/{task_id}")
    assert rget2.status_code == 200
    assert rget2.json().get("stage") == "execute"

    # filter by stage
    rlist = client.get("/api/tasks_v1", params={"stage": "execute"})
    assert rlist.status_code == 200
    ids = [x["task_id"] for x in rlist.json()["tasks"]]
    assert task_id in ids

    # invalid team should be rejected when teams catalog configured
    rbad = client.post(
        "/api/tasks_v1",
        json={
            "task_type": "health_visit",
            "title": "Bad team",
            "domain": "health",
            "assignee_team": "nonexistent-team",
        },
    )
    assert rbad.status_code == 400
    assert "invalid_assignee_team" in str(rbad.json())
