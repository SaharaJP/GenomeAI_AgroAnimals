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



def test_feedback_api_filters_by_scoring_run_and_report_version(client) -> None:
    c, artifacts = client
    _login(c, "zootech", "zootech")

    for recommendation_id, scoring_run, report_version, object_id in [
        ("rec:assistant:sr_demo:animal:1001", "sr_demo", "rv_demo_1", "1001"),
        ("rec:assistant:sr_other:animal:1002", "sr_other", "rv_demo_2", "1002"),
    ]:
        r = c.post(
            "/api/feedback_v1",
            json={
                "recommendation_id": recommendation_id,
                "decision": "rejected",
                "reason_code": "LOW_CONFIDENCE",
                "comment": "weak",
                "object_type": "animal",
                "object_id": object_id,
                "data_version": "dv_demo",
                "model_version": "mv_demo",
                "scoring_run": scoring_run,
                "report_version": report_version,
                "recommendation_created_at": "2026-03-02T10:00:00Z",
                "feedback_source": "assistant",
                "metadata": {"source": "pytest"},
            },
        )
        assert r.status_code == 200

    c.get("/logout")
    _login(c, "director", "director")

    rm = c.get("/api/feedback_v1/metrics", params={"window_days": 60, "data_version": "dv_demo", "scoring_run": "sr_demo"})
    assert rm.status_code == 200
    metrics_body = rm.json()
    assert metrics_body["metrics"]["feedback_total"] == 1
    assert metrics_body["filters"]["scoring_run"] == "sr_demo"
    assert metrics_body["metrics"]["by_scoring_run"][0]["scoring_run"] == "sr_demo"

    rl = c.get("/api/feedback_v1", params={"report_version": "rv_demo_2"})
    assert rl.status_code == 200
    listed = rl.json()["items"]
    assert len(listed) == 1
    assert listed[0]["report_version"] == "rv_demo_2"

    rex = c.get("/api/feedback_v1/export.csv", params={"data_version": "dv_demo", "report_version": "rv_demo_2"})
    assert rex.status_code == 200
    assert "1002" in rex.text
    assert "1001" not in rex.text
    feedback_run = rex.headers["X-Run-Id"]
    manifest = json.loads((artifacts / "system" / "feedback" / feedback_run / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["report_version_filter"] == "rv_demo_2"
    assert manifest["rows"] == 1
