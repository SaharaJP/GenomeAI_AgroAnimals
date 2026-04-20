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



def test_feedback_api_exports_history_dataset_and_revision_metrics(client) -> None:
    c, artifacts = client
    _login(c, "zootech", "zootech")

    payloads = [
        {
            "recommendation_id": "rec:assistant:sr_demo:animal:1001",
            "decision": "accepted",
            "reason_code": "CONFIRMED_BY_SPECIALIST",
            "comment": "ok",
            "object_type": "animal",
            "object_id": "1001",
            "data_version": "dv_demo",
            "model_version": "mv_demo",
            "scoring_run": "sr_demo",
            "report_version": "rv_demo_1",
            "recommendation_created_at": "2026-03-02T08:00:00Z",
            "feedback_source": "assistant",
            "metadata": {"source": "pytest"},
        },
        {
            "recommendation_id": "rec:assistant:sr_demo:animal:1001",
            "decision": "rejected",
            "reason_code": "LOW_CONFIDENCE",
            "comment": "revised",
            "object_type": "animal",
            "object_id": "1001",
            "data_version": "dv_demo",
            "model_version": "mv_demo",
            "scoring_run": "sr_demo",
            "report_version": "rv_demo_1",
            "recommendation_created_at": "2026-03-02T08:00:00Z",
            "feedback_source": "assistant",
            "metadata": {"source": "pytest"},
        },
        {
            "recommendation_id": "rec:assistant:sr_demo:animal:1002",
            "decision": "accepted",
            "reason_code": "ALREADY_ACTIONED",
            "comment": "done",
            "object_type": "animal",
            "object_id": "1002",
            "data_version": "dv_demo",
            "model_version": "mv_demo",
            "scoring_run": "sr_demo",
            "report_version": "rv_demo_2",
            "recommendation_created_at": "2026-03-03T08:00:00Z",
            "feedback_source": "assistant",
            "metadata": {"source": "pytest"},
        },
    ]
    for payload in payloads:
        r = c.post("/api/feedback_v1", json=payload)
        assert r.status_code == 200, r.text

    c.get("/logout")
    _login(c, "director", "director")

    rm = c.get("/api/feedback_v1/metrics", params={"window_days": 60, "data_version": "dv_demo", "scoring_run": "sr_demo"})
    assert rm.status_code == 200
    body = rm.json()
    assert body["metrics"]["feedback_total"] == 2
    assert body["metrics"]["feedback_events_total"] == 3
    assert body["metrics"]["multi_feedback_recommendations_total"] == 1
    assert body["metrics"]["decision_changed_total"] == 1
    assert body["history_rows"] == 3
    assert body["metrics"]["recommendation_history_preview"][0]["recommendation_id"] == "rec:assistant:sr_demo:animal:1001"

    rex = c.get("/api/feedback_v1/export.csv", params={"data_version": "dv_demo", "scoring_run": "sr_demo"})
    assert rex.status_code == 200
    feedback_run = rex.headers["X-Run-Id"]
    manifest = json.loads((artifacts / "system" / "feedback" / feedback_run / "manifest.json").read_text(encoding="utf-8"))
    history_csv = artifacts / "system" / "feedback" / feedback_run / "feedback_history.csv"
    assert history_csv.exists()
    assert manifest["rows"] == 2
    assert manifest["history_rows"] == 3
    assert manifest["outputs"]["feedback_history_csv"]
    assert "feedback_sequence_no" in manifest["history_dataset_columns"]
    history_text = history_csv.read_text(encoding="utf-8")
    assert "recommendation_has_conflict" in history_text
    assert "LOW_CONFIDENCE" in history_text
