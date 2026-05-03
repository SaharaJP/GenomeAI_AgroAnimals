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


@pytest.mark.parametrize(
    "target_kind,target_type",
    [
        ("alert", "QC.PK_DUPLICATE"),
        ("alert", "QC.CONTRACT_MISMATCH"),
        ("alert", "REPRO.LONG_DAYS_OPEN"),
        ("alert", "ML.DRIFT_SUSPECT"),
        ("task", "alert_followup"),
        ("task", "repro_check"),
    ],
)
def test_default_playbooks_exist(client: TestClient, target_kind: str, target_type: str):
    _login(client, "viewer", "viewer")
    r = client.get(
        "/api/playbooks_v1/active",
        params={"target_kind": target_kind, "target_type": target_type, "farm_id": ""},
    )
    assert r.status_code == 200
    pb = r.json().get("playbook")
    assert pb is not None
    assert pb.get("target_kind") == target_kind
    assert pb.get("target_type") == target_type
    assert isinstance(pb.get("steps") or [], list)


def test_ui_editor_table_creates_steps_and_slugifies_keys(client: TestClient):
    _login(client, "zootech", "zootech")

    # Create playbook via UI (table editor): two steps with same title -> keys should be unique
    data = {
        "target_kind": "task",
        "target_type": "alert_followup",
        "farm_id": "F1",
        "name": "Чек‑лист: обработка алерта (F1)",
        "description": "override",
        "comment": "ui table",
        "set_active": "1",
        "step_title": ["Проверить данные", "Проверить данные"],
        "step_details": ["Сверить объект/причину", "Повторная проверка"],
        "step_required": ["1", "2"],
    }
    r_create = client.post("/playbooks/create", data=data, follow_redirects=False)
    assert r_create.status_code in (302, 303)

    r_active = client.get(
        "/api/playbooks_v1/active",
        params={"target_kind": "task", "target_type": "alert_followup", "farm_id": "F1"},
    )
    assert r_active.status_code == 200
    pb = r_active.json().get("playbook")
    assert pb is not None
    steps = list(pb.get("steps") or [])
    assert len(steps) == 2
    keys = [s.get("key") for s in steps]
    assert keys[0]
    assert keys[1]
    assert keys[0] != keys[1]
    # keys should be slug-like (no spaces)
    assert " " not in str(keys[0])
    assert " " not in str(keys[1])
