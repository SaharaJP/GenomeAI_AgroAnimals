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


def _login(c: TestClient, username: str, password: str) -> None:
    r = c.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert r.status_code in (302, 303)


def test_feedback_api_create_metrics_export_and_decision_link(client: TestClient) -> None:
    _login(client, "zootech", "zootech")

    # task linked to recommendation outcome
    rt = client.post(
        "/api/tasks_v1",
        json={
            "task_type": "mastitis_control",
            "title": "Inspect cow 1001",
            "domain": "health",
            "object_type": "animal",
            "object_id": "1001",
            "related_alert": "alert-1",
            "data_version": "dv_demo",
            "scoring_run": "sr_demo",
        },
    )
    assert rt.status_code == 200
    task_id = rt.json()["task_id"]
    assert client.post(f"/api/tasks_v1/{task_id}/take").status_code == 200
    assert client.post(f"/api/tasks_v1/{task_id}/close", json={"status": "done", "reason": "done", "comment": "checked"}).status_code == 200

    r = client.post(
        "/api/feedback_v1",
        json={
            "recommendation_id": "rec:alert:sr_demo:alert-1:animal:1001",
            "decision": "accepted",
            "reason_code": "CONFIRMED_BY_SPECIALIST",
            "comment": "accepted by vet",
            "related_alert": "alert-1",
            "task_id": task_id,
            "object_type": "animal",
            "object_id": "1001",
            "data_version": "dv_demo",
            "model_version": "mv_demo",
            "scoring_run": "sr_demo",
            "recommendation_created_at": "2026-03-01T10:00:00Z",
            "feedback_source": "api_test",
            "metadata": {"source": "pytest"},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["decision"] == "accepted"
    assert body["reason_code"] == "CONFIRMED_BY_SPECIALIST"
    assert body["decision_id"]

    rlist = client.get("/api/feedback_v1", params={"recommendation_id": "rec:alert:sr_demo:alert-1:animal:1001"})
    assert rlist.status_code == 200
    items = rlist.json()["items"]
    assert len(items) == 1
    assert items[0]["decision_id"] == body["decision_id"]

    client.get("/logout")
    _login(client, "director", "director")

    rm = client.get("/api/feedback_v1/metrics", params={"window_days": 60, "data_version": "dv_demo"})
    assert rm.status_code == 200
    mb = rm.json()
    assert mb["run_id"]
    assert (mb["metrics"] or {})["accepted_total"] >= 1
    assert (mb["metrics"] or {}).get("task_outcomes", {}).get("done") == 1

    rex = client.get("/api/feedback_v1/export.csv", params={"data_version": "dv_demo"})
    assert rex.status_code == 200
    assert rex.headers.get("X-Run-Id")
    assert "feedback_dataset" in rex.headers.get("content-disposition", "")
    text = rex.text
    assert "recommendation_id" in text
    assert "CONFIRMED_BY_SPECIALIST" in text
