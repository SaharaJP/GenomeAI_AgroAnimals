from __future__ import annotations

import importlib
import json
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
        yield c, artifacts


def _login(c: TestClient, username: str, password: str) -> None:
    r = c.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert r.status_code in (302, 303)


def test_feedback_metrics_and_export_include_training_ready_fields(client) -> None:
    c, artifacts = client
    _login(c, "zootech", "zootech")

    rt = c.post(
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
    task_id = rt.json()["task_id"]
    assert c.post(f"/api/tasks_v1/{task_id}/take").status_code == 200
    assert c.post(f"/api/tasks_v1/{task_id}/close", json={"status": "done", "reason": "done", "comment": "checked"}).status_code == 200

    assert c.post(
        "/api/feedback_v1",
        json={
            "recommendation_id": "rec:assistant:sr_demo:animal:1001",
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
            "feedback_source": "assistant",
            "metadata": {"source": "pytest"},
        },
    ).status_code == 200

    assert c.post(
        "/api/feedback_v1",
        json={
            "recommendation_id": "rec:alert:sr_demo:alert-2:animal:1002",
            "decision": "rejected",
            "reason_code": "LOW_CONFIDENCE",
            "comment": "too weak",
            "related_alert": "alert-2",
            "object_type": "animal",
            "object_id": "1002",
            "data_version": "dv_demo",
            "model_version": "mv_demo",
            "scoring_run": "sr_demo",
            "recommendation_created_at": "2026-03-02T10:00:00Z",
            "feedback_source": "alert_center",
            "metadata": {"source": "pytest"},
        },
    ).status_code == 200

    c.get("/logout")
    _login(c, "director", "director")

    rm = c.get("/api/feedback_v1/metrics", params={"window_days": 60, "data_version": "dv_demo"})
    assert rm.status_code == 200
    body = rm.json()
    metrics = body["metrics"]
    assert metrics["task_linked_total"] == 1
    assert metrics["task_linked_rate"] == 0.5
    assert len(metrics["by_feedback_source"]) == 2
    assert len(metrics["decision_time_buckets"]) >= 1
    assert "feedback_target_label" in (body["preview"][0].keys())

    rex = c.get("/api/feedback_v1/export.csv", params={"data_version": "dv_demo"})
    assert rex.status_code == 200
    feedback_run = rex.headers["X-Run-Id"]
    assert "feedback_sample_weight" in rex.text
    manifest = json.loads((artifacts / "system" / "feedback" / feedback_run / "manifest.json").read_text(encoding="utf-8"))
    metrics_json = json.loads((artifacts / "system" / "feedback" / feedback_run / "metrics_summary.json").read_text(encoding="utf-8"))
    assert "feedback_target_label" in manifest["dataset_columns"]
    assert manifest["outputs"]["metrics_summary_json"]
    assert metrics_json["feedback_total"] == 2
