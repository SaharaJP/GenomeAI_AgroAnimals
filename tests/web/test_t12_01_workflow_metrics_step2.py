from __future__ import annotations

import importlib
import os
from datetime import datetime, timedelta, timezone
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


def test_tasks_metrics_endpoint_and_update_flow(client: TestClient):
    # create tasks as zootech (write)
    _login(client, "zootech", "zootech")

    now = datetime.now(timezone.utc).replace(microsecond=0)
    past = (now - timedelta(hours=2)).isoformat()
    future = (now + timedelta(hours=10)).isoformat()

    r1 = client.post(
        "/api/tasks_v1",
        json={"task_type": "mastitis_control", "title": "Overdue task", "domain": "health", "priority": 2, "due_at": past},
    )
    assert r1.status_code == 200
    t1 = r1.json()["task_id"]

    r2 = client.post(
        "/api/tasks_v1",
        json={"task_type": "qc_fix", "title": "Not overdue", "domain": "qc", "priority": 3, "due_at": future},
    )
    assert r2.status_code == 200
    t2 = r2.json()["task_id"]

    # update: move t2 to in_progress and change priority
    rupd = client.post(f"/api/tasks_v1/{t2}/update", json={"status": "in_progress", "priority": 1, "assignee_team": "team-qc"})
    assert rupd.status_code == 200

    rget = client.get(f"/api/tasks_v1/{t2}")
    assert rget.status_code == 200
    assert rget.json().get("status") == "in_progress"
    assert int(rget.json().get("priority") or 0) == 1

    # close one task to populate lead_time
    rtake = client.post(f"/api/tasks_v1/{t2}/take")
    assert rtake.status_code == 200
    rclose = client.post(f"/api/tasks_v1/{t2}/close", json={"status": "done", "reason": "done", "comment": "ok"})
    assert rclose.status_code == 200

    client.get("/logout")

    # director can view metrics
    _login(client, "director", "director")
    rm = client.get("/api/tasks_v1/metrics", params={"window_days": 30})
    assert rm.status_code == 200
    body = rm.json()
    assert body.get("run_id")
    m = body.get("metrics") or {}

    assert int(m.get("active_total") or 0) >= 1
    # at least one overdue active (t1)
    assert int(m.get("active_overdue") or 0) >= 1
    assert float(m.get("overdue_rate_active") or 0.0) > 0.0

    # lead time exists because we closed t2
    assert int(m.get("closed_window_total") or 0) >= 1
