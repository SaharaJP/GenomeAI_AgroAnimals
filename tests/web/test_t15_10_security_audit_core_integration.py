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
    assert r.status_code in (302, 303), r.text


def _seed_rows() -> None:
    import web_cabinet.app as appmod
    from web_cabinet.audit import write_audit
    from web_cabinet.db import connect

    conn = connect(appmod.settings.db_path)
    try:
        write_audit(
            conn,
            tenant_id="default",
            user_id=1,
            username="director",
            role="Director",
            action="report.approve",
            object_type="report",
            object_id="rp_101",
            request_id="REQ-101",
            run_id="run_report_101",
            status="OK",
        )
        write_audit(
            conn,
            tenant_id="default",
            user_id=2,
            username="operator",
            role="Operator",
            action="report.generate",
            object_type="report",
            object_id="rp_102",
            request_id="REQ-102",
            run_id="run_report_102",
            status="OK",
        )
    finally:
        conn.close()


def test_t15_10_web_forbidden_detail_is_core_backed(client: TestClient) -> None:
    _login(client, "viewer", "viewer")
    r = client.post("/qc/run", data={"data_version": "dv_forbidden"}, follow_redirects=False)
    assert r.status_code == 403
    body = r.json()["detail"]
    assert body["error"] == "forbidden"
    assert body["missing_permissions"] == ["pipeline.run"]
    assert body["operation"] == "require_permissions"


def test_t15_10_api_audit_supports_role_request_id_object_ref_and_prefix_filters(client: TestClient) -> None:
    _login(client, "admin", "admin")
    _seed_rows()
    r = client.get(
        "/api/audit",
        params={
            "action_prefix": "report.",
            "role": "Director",
            "request_id": "REQ-101",
            "object_ref": "report:rp_101",
            "limit": 50,
        },
    )
    assert r.status_code == 200, r.text
    rows = r.json()["rows"]
    assert len(rows) == 1
    assert rows[0]["action"] == "report.approve"
    assert rows[0]["request_id"] == "REQ-101"
