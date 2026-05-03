from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo_root = Path(__file__).resolve().parents[2]
    storage = tmp_path / "web_storage"
    artifacts = tmp_path / "artifacts"
    monkeypatch.setenv("GENOMEAI_PROJECT_ROOT", str(repo_root))
    monkeypatch.setenv("GENOMEAI_WEB_STORAGE", str(storage))
    monkeypatch.setenv("GENOMEAI_ARTIFACTS_ROOT", str(artifacts))
    monkeypatch.setenv("GENOMEAI_WEB_DISABLE_WORKER", "1")
    monkeypatch.setenv("GENOMEAI_WEB_SECRET", "test-secret-123")
    monkeypatch.setenv("GENOMEAI_DEPLOY_PROFILE", "dev")
    monkeypatch.delenv("GENOMEAI_WEB_SECRET_FILE", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY_FILE", raising=False)

    import web_cabinet.app as appmod
    importlib.reload(appmod)

    with TestClient(appmod.app) as c:
        yield c


def _login(c: TestClient, username: str, password: str) -> None:
    r = c.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert r.status_code in (302, 303)


def test_security_action_groups_are_enforced(client: TestClient):
    # upload + run denied for Director
    _login(client, "director", "director")
    r_upload = client.post(
        "/upload/ingest-all",
        data={
            "data_version": "dv_sec",
            "farms_mapping_path": "configs/mappings/farms_example.yaml",
            "animals_mapping_path": "configs/mappings/animals_example.yaml",
            "lactations_mapping_path": "configs/mappings/lactations_example.yaml",
        },
    )
    assert r_upload.status_code == 403
    assert "upload.create" in r_upload.text
    assert "pipeline.run" in r_upload.text

    r_run = client.get("/connectors")
    assert r_run.status_code == 403
    assert "pipeline.run" in r_run.text

    client.get("/logout")
    _login(client, "operator", "operator")
    r_cfg = client.get("/configs")
    assert r_cfg.status_code == 403
    assert "configs.manage" in r_cfg.text

    client.get("/logout")
    _login(client, "zootech", "zootech")
    r_create = client.post(
        "/api/whatif_scenarios_v1",
        json={
            "name": "sec-approve",
            "base_report_version": "rv_sec",
            "changes": {"milk_price_per_kg": 35.0},
        },
    )
    assert r_create.status_code == 200
    scenario_id = r_create.json()["scenario_id"]

    r_approve = client.post(f"/api/whatif_scenarios_v1/{scenario_id}/approve", json={"comment": "nope"})
    assert r_approve.status_code == 403
    assert "whatif.scenarios.approve" in r_approve.text


def test_download_requires_export_permission_override(client: TestClient):
    _login(client, "viewer", "viewer")

    from web_cabinet.db import connect, get_settings

    settings = get_settings()
    conn = connect(settings.db_path)
    try:
        conn.execute("DELETE FROM role_permissions WHERE role=? AND permission=?", ("Viewer", "export.download"))
        conn.commit()
    finally:
        conn.close()

    r = client.get("/download", params={"path": "project/README.md"})
    assert r.status_code == 403
    assert "export.download" in r.text


def test_prod_startup_blocks_default_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo_root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("GENOMEAI_PROJECT_ROOT", str(repo_root))
    monkeypatch.setenv("GENOMEAI_WEB_STORAGE", str(tmp_path / "web_storage"))
    monkeypatch.setenv("GENOMEAI_ARTIFACTS_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("GENOMEAI_WEB_DISABLE_WORKER", "1")
    monkeypatch.setenv("GENOMEAI_DEPLOY_PROFILE", "prod")
    monkeypatch.setenv("GENOMEAI_WEB_SECRET", "dev-secret-change-me")
    monkeypatch.delenv("GENOMEAI_WEB_SECRET_FILE", raising=False)

    import web_cabinet.app as appmod
    importlib.reload(appmod)

    with pytest.raises(RuntimeError, match="startup_config_invalid: .*prod.*секрет"):
        with TestClient(appmod.app):
            pass


def test_prod_startup_accepts_secret_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo_root = Path(__file__).resolve().parents[2]
    secret_file = tmp_path / "session.secret"
    secret_file.write_text("prod-secret-long-enough", encoding="utf-8")
    monkeypatch.setenv("GENOMEAI_PROJECT_ROOT", str(repo_root))
    monkeypatch.setenv("GENOMEAI_WEB_STORAGE", str(tmp_path / "web_storage"))
    monkeypatch.setenv("GENOMEAI_ARTIFACTS_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("GENOMEAI_WEB_DISABLE_WORKER", "1")
    monkeypatch.setenv("GENOMEAI_DEPLOY_PROFILE", "prod")
    monkeypatch.setenv("GENOMEAI_WEB_SECRET", "")
    monkeypatch.setenv("GENOMEAI_WEB_SECRET_FILE", str(secret_file))

    import web_cabinet.app as appmod
    importlib.reload(appmod)

    with TestClient(appmod.app) as c:
        r = c.get("/healthz")
        assert r.status_code == 200
        assert r.text.strip() == "ok"


def test_compose_profiles_and_healthcheck_are_present():
    compose_path = Path(__file__).resolve().parents[2] / "deploy" / "docker-compose.yml"
    payload = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    services = payload["services"]
    assert set(services) >= {"web-dev", "web-prod"}
    assert services["web-dev"]["profiles"] == ["dev"]
    assert services["web-prod"]["profiles"] == ["prod"]
    health = services["web-prod"]["healthcheck"]
    assert "/readyz" in str(health["test"])
    assert services["web-prod"]["read_only"] is True
    assert "no-new-privileges:true" in services["web-prod"]["security_opt"]
