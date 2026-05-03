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


def _login(c: TestClient, username: str = "operator", password: str = "operator"):
    r = c.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert r.status_code in (302, 303)


def _seed_kpi_artifacts(artifacts_root: Path, dv: str = "dv_demo", run_id: str = "kpi_run_001") -> None:
    kpi_dir = artifacts_root / dv / "runs" / run_id / "kpi"
    kpi_dir.mkdir(parents=True, exist_ok=True)
    (kpi_dir / "kpi_summary.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "asof_date": "2026-03-09",
                "currency": "RUB",
                "kpi_count": 3,
                "alert_count": 1,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (kpi_dir / "kpi_wide.csv").write_text("farm_id,milk_kg\nfarm_1,123.4\n", encoding="utf-8")
    (kpi_dir / "kpi_alerts.csv").write_text("alert_id,severity\na1,high\n", encoding="utf-8")


def test_copilot_target_api_resolves_fact_and_artifacts(client: TestClient):
    artifacts_root = Path(os.environ["GENOMEAI_ARTIFACTS_ROOT"])
    _seed_kpi_artifacts(artifacts_root)
    _login(client)

    resp = client.get(
        "/api/copilot/fact",
        params={
            "data_version": "dv_demo",
            "section": "modules.kpi",
            "table": "kpi_summary",
            "metric": "kpi_count",
            "run_id": "kpi_run_001",
            "fact_id": "fact.modules_kpi.kpi_count",
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["schema"] == "genomeai.copilot.target_resolution.v1"
    assert payload["resolution"]["matched_kind"] == "fact"
    assert payload["resolution"]["fact"]["value"] == 3
    assert payload["artifact_links"]
    assert any("kpi_summary.json" in row["path"] for row in payload["artifact_links"])
    assert any(row["href"] == "/reports?dv=dv_demo" for row in payload["navigation_hints"])
    assert payload["web_target_href"].startswith("/copilot/fact?")


def test_copilot_target_page_shows_missing_data_request(client: TestClient):
    _login(client)
    resp = client.get(
        "/copilot/fact",
        params={
            "data_version": "dv_empty",
            "section": "modules.repro",
        },
    )
    assert resp.status_code == 200
    assert "Данных недостаточно" in resp.text
    assert "Как получить" in resp.text
    assert "modules.repro" in resp.text
