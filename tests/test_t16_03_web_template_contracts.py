from __future__ import annotations

import importlib
import os
import warnings
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request


@pytest.fixture()
def appmod(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo_root = Path(__file__).resolve().parents[1]
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

    import web_cabinet.app as app_module

    return importlib.reload(app_module)


@pytest.fixture()
def client(appmod):
    with TestClient(appmod.app) as c:
        yield c


def _login(c: TestClient, username: str, password: str) -> None:
    r = c.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert r.status_code in (302, 303)


def _template_contract_warnings(captured: list[warnings.WarningMessage]) -> list[str]:
    out: list[str] = []
    for item in captured:
        msg = str(item.message)
        if "TemplateResponse" in msg or "The `name` is not the first parameter anymore" in msg:
            out.append(msg)
    return out


def test_render_helper_uses_request_first_template_response_contract(appmod, monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, object] = {}

    def _spy_template_response(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return {"args": args, "kwargs": kwargs}

    monkeypatch.setattr(appmod.templates, "TemplateResponse", _spy_template_response)
    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/upload",
            "raw_path": b"/upload",
            "query_string": b"",
            "headers": [],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "root_path": "",
        }
    )

    result = appmod._render(request, "upload.html", user={"username": "operator"})

    assert result == {"args": captured["args"], "kwargs": captured["kwargs"]}
    args = captured["args"]
    assert len(args) == 3
    assert args[0] is request
    assert args[1] == "upload.html"
    context = args[2]
    assert context["request"] is request
    assert context["settings"] is appmod.settings
    assert context["user"] == {"username": "operator"}
    assert context["active"] == "upload"


def test_login_route_renders_without_template_contract_warning(client: TestClient):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        response = client.get("/login")
    assert response.status_code == 200
    assert "<html" in response.text.lower()
    assert not _template_contract_warnings(caught)


def test_key_html_routes_render_without_template_contract_warning(client: TestClient):
    _login(client, "operator", "operator")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        upload = client.get("/upload")
        jobs = client.get("/jobs")

    assert upload.status_code == 200
    assert jobs.status_code == 200
    assert "upload" in upload.text.lower()
    assert "jobs" in jobs.text.lower() or "task" in jobs.text.lower()
    assert not _template_contract_warnings(caught)
