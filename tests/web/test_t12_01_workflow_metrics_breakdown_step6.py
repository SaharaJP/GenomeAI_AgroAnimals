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


def test_metrics_breakdowns_and_sla_adherence(client: TestClient):
    _login(client, "zootech", "zootech")

    now = datetime.now(timezone.utc).replace(microsecond=0)
    past = (now - timedelta(hours=3)).isoformat()
    future = (now + timedelta(hours=5)).isoformat()

    # Closed on-time (due in the future)
    r_on = client.post(
        "/api/tasks_v1",
        json={"task_type": "qc_fix", "title": "On-time", "domain": "qc", "priority": 2, "due_at": future, "stage": "review"},
    )
    assert r_on.status_code == 200
    t_on = r_on.json()["task_id"]

    client.post(f"/api/tasks_v1/{t_on}/take")
    r_close_on = client.post(f"/api/tasks_v1/{t_on}/close", json={"status": "done", "reason": "done", "comment": "ok"})
    assert r_close_on.status_code == 200

    # Closed late (due in the past)
    r_late = client.post(
        "/api/tasks_v1",
        json={"task_type": "mastitis_control", "title": "Late", "domain": "health", "priority": 1, "due_at": past, "stage": "execute"},
    )
    assert r_late.status_code == 200
    t_late = r_late.json()["task_id"]

    client.post(f"/api/tasks_v1/{t_late}/take")
    r_close_late = client.post(f"/api/tasks_v1/{t_late}/close", json={"status": "done", "reason": "done", "comment": "late"})
    assert r_close_late.status_code == 200

    # One active overdue to populate active breakdowns
    r_act = client.post(
        "/api/tasks_v1",
        json={"task_type": "econ_review", "title": "Active overdue", "domain": "econ", "priority": 3, "due_at": past, "stage": "plan"},
    )
    assert r_act.status_code == 200

    client.get("/logout")

    _login(client, "director", "director")
    rm = client.get("/api/tasks_v1/metrics", params={"window_days": 30})
    assert rm.status_code == 200
    m = (rm.json() or {}).get("metrics") or {}

    # New keys exist
    assert "by_stage" in m
    assert "by_priority" in m
    assert "sla_adherence" in m

    sla = m.get("sla_adherence") or {}
    assert int(sla.get("closed_with_due_window") or 0) >= 2
    assert int(sla.get("closed_on_time_window") or 0) >= 1
    assert int(sla.get("closed_late_window") or 0) >= 1

    # stage breakdown contains at least done and one active stage
    stages = {str(x.get("stage")) for x in (m.get("by_stage") or [])}
    assert "done" in stages

    # priority breakdown contains created priorities
    prs = {str(x.get("priority")) for x in (m.get("by_priority") or [])}
    assert "1" in prs and "2" in prs and "3" in prs
