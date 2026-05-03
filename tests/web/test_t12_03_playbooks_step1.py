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


def _login(c: TestClient, username: str, password: str):
    r = c.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert r.status_code in (302, 303)


def test_t12_03_playbooks_seed_and_farm_override_and_audit(client: TestClient):
    # Viewer can read active playbook
    _login(client, "viewer", "viewer")
    r = client.get(
        "/api/playbooks_v1/active",
        params={"target_kind": "alert", "target_type": "ML.MASTITIS_RISK"},
    )
    assert r.status_code == 200
    pb = r.json().get("playbook")
    assert pb is not None
    assert pb["target_kind"] == "alert"
    assert pb["target_type"] == "ML.MASTITIS_RISK"
    assert pb.get("steps") and isinstance(pb.get("steps"), list)

    # Viewer cannot create
    r_forbidden = client.post(
        "/api/playbooks_v1",
        json={
            "target_kind": "alert",
            "target_type": "ML.MASTITIS_RISK",
            "farm_id": "F1",
            "name": "override",
            "steps": [{"key": "x", "title": "t"}],
        },
    )
    assert r_forbidden.status_code == 403
    client.get("/logout")

    # Zootech can create a farm-specific override
    _login(client, "zootech", "zootech")
    r_create = client.post(
        "/api/playbooks_v1",
        json={
            "target_kind": "alert",
            "target_type": "ML.MASTITIS_RISK",
            "farm_id": "F1",
            "name": "План действий: риск мастита (F1)",
            "steps": [
                {"key": "custom_1", "title": "Шаг 1", "required": True},
                {"key": "custom_2", "title": "Шаг 2", "required": False},
            ],
            "set_active": True,
        },
    )
    assert r_create.status_code == 200

    # For F1 should return override
    r_f1 = client.get(
        "/api/playbooks_v1/active",
        params={"target_kind": "alert", "target_type": "ML.MASTITIS_RISK", "farm_id": "F1"},
    )
    assert r_f1.status_code == 200
    pb_f1 = r_f1.json().get("playbook")
    assert pb_f1 is not None
    assert pb_f1.get("farm_id") == "F1"
    assert pb_f1.get("name") == "План действий: риск мастита (F1)"

    # For other farm should fall back to global
    r_f2 = client.get(
        "/api/playbooks_v1/active",
        params={"target_kind": "alert", "target_type": "ML.MASTITIS_RISK", "farm_id": "F2"},
    )
    assert r_f2.status_code == 200
    pb_f2 = r_f2.json().get("playbook")
    assert pb_f2 is not None
    assert pb_f2.get("farm_id") in ("", None)

    # List versions should include both global (seeded) and farm override
    r_list = client.get(
        "/api/playbooks_v1",
        params={"target_kind": "alert", "target_type": "ML.MASTITIS_RISK", "limit": 50},
    )
    assert r_list.status_code == 200
    versions = r_list.json().get("versions") or []
    assert len(versions) >= 2
    client.get("/logout")

    # Admin can see audit log entries
    _login(client, "admin", "admin")
    ra = client.get("/api/audit", params={"action": "playbooks_v1.create_version"})
    assert ra.status_code == 200
    rows = ra.json().get("rows") or []
    assert rows, "expected playbooks_v1.create_version audit row"
