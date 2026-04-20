from __future__ import annotations

import importlib
from pathlib import Path

from fastapi.testclient import TestClient


def test_t17_06_release_endpoint_and_headers_are_exposed(monkeypatch, tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("GENOMEAI_PROJECT_ROOT", str(repo_root))
    monkeypatch.setenv("GENOMEAI_ARTIFACTS_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("GENOMEAI_WEB_STORAGE", str(tmp_path / "web_storage"))
    monkeypatch.setenv("GENOMEAI_WEB_DISABLE_WORKER", "1")
    app_module = importlib.import_module("web_cabinet.app")
    app_module = importlib.reload(app_module)
    with TestClient(app_module.app) as client:
        release = client.get("/api/release")
        assert release.status_code == 200
        payload = release.json()
        assert payload["version"] == "0.0.1"
        assert payload["stamp"].startswith("v0.0.1")
        health = client.get("/healthz")
        assert health.status_code == 200
        assert health.headers.get("X-GenomeAI-Version") == "0.0.1"
        assert health.headers.get("X-GenomeAI-Build-Stamp")
