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
        yield c



def _login(c: TestClient, username: str, password: str) -> None:
    r = c.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert r.status_code in (302, 303), r.text



def _seed_artifacts(base_artifacts: Path) -> None:
    kpi_dir = base_artifacts / "dv_demo" / "runs" / "kpi_run_001" / "kpi"
    kpi_dir.mkdir(parents=True, exist_ok=True)
    (kpi_dir / "kpi_summary.json").write_text(
        json.dumps({"run_id": "kpi_run_001", "kpi_count": 3, "alert_count": 2}, ensure_ascii=False),
        encoding="utf-8",
    )
    (kpi_dir / "kpi_wide.csv").write_text("farm_id,milk_kg\nfarm_1,123.4\n", encoding="utf-8")
    (kpi_dir / "kpi_alerts.csv").write_text("alert_id,severity,farm_id\na1,high,farm_1\n", encoding="utf-8")

    mast_dir = base_artifacts / "dv_demo" / "mastitis" / "scoring" / "mast_run_001"
    mast_dir.mkdir(parents=True, exist_ok=True)
    (mast_dir / "scoring_summary.json").write_text(
        json.dumps({"scoring_run": "mast_run_001", "asof_date": "2026-03-09", "horizon_days": 7, "risk_threshold": 0.7}, ensure_ascii=False),
        encoding="utf-8",
    )
    (mast_dir / "mastitis_risk_scores.csv").write_text(
        "farm_id,animal_id,risk_score,severity\nfarm_1,1001,0.91,high\n",
        encoding="utf-8",
    )

    econ_dir = base_artifacts / "dv_demo" / "economics" / "econ_run_001"
    econ_dir.mkdir(parents=True, exist_ok=True)
    (econ_dir / "summary_farm.csv").write_text(
        "farm_id,revenue_milk,margin_total\nfarm_1,100000,42000\n",
        encoding="utf-8",
    )
    (econ_dir / "whatif_params.json").write_text(
        json.dumps({"economics_run": "econ_run_001", "scenario_name": "base"}, ensure_ascii=False),
        encoding="utf-8",
    )



def test_pending_approval_api_and_director_page(client: TestClient) -> None:
    artifacts_root = Path(os.environ["GENOMEAI_ARTIFACTS_ROOT"])
    _seed_artifacts(artifacts_root)

    _login(client, "zootech", "zootech")
    r_generate = client.post(
        "/api/weekly_plans_v1/generate",
        json={
            "week_start": "2026-03-09",
            "data_version": "dv_demo",
            "farm_id": "farm_1",
            "question": "Сформируй план на неделю",
        },
    )
    assert r_generate.status_code == 200, r_generate.text
    plan_id = r_generate.json()["plan_id"]

    r_request = client.post(f"/api/weekly_plans_v1/{plan_id}/request_approval", json={"comment": "Нужен директор"})
    assert r_request.status_code == 200, r_request.text

    client.get("/logout")
    _login(client, "director", "director")

    r_pending = client.get("/api/weekly_plans_v1/pending_approval")
    assert r_pending.status_code == 200, r_pending.text
    payload = r_pending.json()
    assert payload["total"] >= 1
    row = next(p for p in payload["weekly_plans"] if p["plan_id"] == plan_id)
    assert row["approval_requested_by_username"] == "zootech"
    assert row["item_count"] >= 5
    assert row["citation_count"] >= 5
    assert "mast_run_001" in row["source_run_ids"]

    r_page = client.get("/weekly_plans")
    assert r_page.status_code == 200, r_page.text
    assert "Планы на approval" in r_page.text
    assert plan_id in r_page.text

    r_approve = client.post(f"/api/weekly_plans_v1/{plan_id}/approve", json={"comment": "OK"})
    assert r_approve.status_code == 200, r_approve.text

    r_pending_after = client.get("/api/weekly_plans_v1/pending_approval")
    assert r_pending_after.status_code == 200, r_pending_after.text
    ids_after = {p["plan_id"] for p in (r_pending_after.json().get("weekly_plans") or [])}
    assert plan_id not in ids_after
