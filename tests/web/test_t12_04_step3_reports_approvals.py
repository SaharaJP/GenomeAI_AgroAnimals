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

    # create a minimal report artifact
    dv = artifacts / "dv_demo" / "reports" / "report_001" / "exports"
    dv.mkdir(parents=True, exist_ok=True)
    (dv / "report.docx").write_bytes(b"demo")

    import web_cabinet.app as appmod

    importlib.reload(appmod)

    with TestClient(appmod.app) as c:
        yield c


def _login(c: TestClient, username: str, password: str):
    r = c.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert r.status_code in (302, 303)


def test_report_approval_flow_and_rbac(client: TestClient):
    _login(client, "viewer", "viewer")

    # viewer can see status (draft by default)
    r0 = client.get(
        "/api/reports_v1/approval",
        params={"data_version": "dv_demo", "report_version": "report_001"},
    )
    assert r0.status_code == 200
    assert (r0.json().get("approval") or {}).get("status") == "draft"

    # viewer cannot approve
    r_forb = client.post(
        "/api/reports_v1/report_001/approve",
        json={"data_version": "dv_demo", "comment": "ok"},
    )
    assert r_forb.status_code == 403

    client.get("/logout")
    _login(client, "director", "director")

    r_appr = client.post(
        "/api/reports_v1/report_001/approve",
        json={"data_version": "dv_demo", "comment": "Утверждаю"},
    )
    assert r_appr.status_code == 200
    approval = r_appr.json().get("approval") or {}
    assert approval.get("status") == "approved"
    assert approval.get("approved_by_username") == "director"
    assert approval.get("approval_comment") == "Утверждаю"
    assert approval.get("rejected_at") is None

    # reject keeps draft and sets metadata
    r_rej = client.post(
        "/api/reports_v1/report_001/reject",
        json={"data_version": "dv_demo", "comment": "Нужно добавить пояснения"},
    )
    assert r_rej.status_code == 200
    approval2 = r_rej.json().get("approval") or {}
    assert approval2.get("status") == "draft"
    assert approval2.get("rejected_by_username") == "director"
    assert approval2.get("rejection_comment") == "Нужно добавить пояснения"

    # approve clears rejection metadata
    r_appr2 = client.post(
        "/api/reports_v1/report_001/approve",
        json={"data_version": "dv_demo", "comment": "OK"},
    )
    assert r_appr2.status_code == 200
    approval3 = r_appr2.json().get("approval") or {}
    assert approval3.get("status") == "approved"
    assert approval3.get("rejected_at") is None
    assert approval3.get("rejection_comment") is None

    # archive
    r_arch = client.post(
        "/api/reports_v1/report_001/archive",
        json={"data_version": "dv_demo", "comment": "в архив"},
    )
    assert r_arch.status_code == 200
    approval4 = r_arch.json().get("approval") or {}
    assert approval4.get("status") == "archived"
    assert approval4.get("archived_by_username") == "director"

    # audit
    ra = client.get("/api/audit", params={"action": "report.approve"})
    assert ra.status_code == 200
    rows = ra.json().get("rows") or []
    assert any(r.get("run_id") == "report_001" for r in rows)
