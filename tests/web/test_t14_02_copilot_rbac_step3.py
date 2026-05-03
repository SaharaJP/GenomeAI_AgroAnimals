from __future__ import annotations

import importlib
import json
import os
import sqlite3
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


def _seed_economics_artifacts(artifacts_root: Path, dv: str = "dv_demo", run_id: str = "econ_run_001") -> None:
    econ_dir = artifacts_root / dv / "economics" / run_id
    econ_dir.mkdir(parents=True, exist_ok=True)
    (econ_dir / "summary_farm.csv").write_text(
        "farm_id,revenue_milk,margin_total\nfarm_1,100000,42000\n",
        encoding="utf-8",
    )
    (econ_dir / "whatif_params.json").write_text(
        json.dumps({"economics_run": run_id, "scenario_name": "base"}, ensure_ascii=False),
        encoding="utf-8",
    )


def _remove_role_permission(permission: str) -> None:
    db_path = Path(os.environ["GENOMEAI_WEB_STORAGE"]) / "web.db"
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM role_permissions WHERE role=? AND permission=?", ("Operator", permission))
    conn.commit()
    conn.close()


def test_copilot_target_api_denies_section_without_required_permission(client: TestClient):
    artifacts_root = Path(os.environ["GENOMEAI_ARTIFACTS_ROOT"])
    _seed_economics_artifacts(artifacts_root)
    _remove_role_permission("economics.view")
    _login(client)

    resp = client.get(
        "/api/copilot/fact",
        params={
            "data_version": "dv_demo",
            "section": "modules.economics",
            "table": "summary_farm_top",
            "metric": "economics_run",
            "run_id": "econ_run_001",
            "fact_id": "fact.modules_economics.economics_run",
        },
    )
    assert resp.status_code == 403
    payload = resp.json()
    assert payload["detail"]["error"] == "copilot_target_forbidden"
    assert payload["detail"]["required_permission"] == "economics.view"


def test_citation_action_cards_hide_reports_link_without_permission() -> None:
    from genomeai.copilot_ui_links import build_citation_action_cards

    cards = build_citation_action_cards(
        [
            {
                "label": "summary_farm.csv",
                "source": "artifacts/dv_demo/economics/econ_run_001/summary_farm.csv",
                "data_version": "dv_demo",
                "period": "daily",
                "asof_date": "2026-03-09",
                "run_id": "econ_run_001",
                "report_version": "NA",
                "section": "modules.economics",
                "table": "summary_farm_top",
                "metric": "revenue_milk",
                "fact_id": "fact.modules_economics.revenue_milk",
            }
        ],
        web_base_url="http://example.local",
        effective_permissions=["economics.view"],
    )
    assert cards
    assert cards[0]["resolver_url"].startswith("http://example.local/copilot/fact?")
    assert cards[0]["reports_url"] == ""
