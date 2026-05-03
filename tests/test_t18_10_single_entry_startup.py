from __future__ import annotations

from pathlib import Path

import yaml


def test_t18_10_dockerfile_includes_streamlit_app() -> None:
    text = Path("deploy/Dockerfile").read_text(encoding="utf-8")
    assert "COPY streamlit_app /app/streamlit_app" in text


def test_t18_10_docker_compose_has_streamlit_primary_services() -> None:
    payload = yaml.safe_load(Path("deploy/docker-compose.yml").read_text(encoding="utf-8"))
    services = payload.get("services") or {}
    assert "streamlit-dev" in services
    assert "streamlit-prod" in services
    dev = services["streamlit-dev"]
    prod = services["streamlit-prod"]
    assert any("8501" in str(item) for item in (dev.get("ports") or []))
    assert any("streamlit_app/app.py" in str(part) for part in (dev.get("command") or []))
    assert dev.get("depends_on", {}).get("web-dev") is not None
    assert prod.get("depends_on", {}).get("web-prod") is not None


def test_t18_10_single_entry_docs_and_scripts_present() -> None:
    assert Path("docs/single_entry_streamlit.md").exists()
    assert Path("scripts/run_single_entry_local.sh").exists()
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "Single-entry запуск" in readme
    assert "Streamlit" in readme
    doc = Path("docs/single_entry_streamlit.md").read_text(encoding="utf-8")
    assert "hidden fallback" in doc
    assert "soft-deprecated" in doc


def test_t18_10_fastapi_fallback_templates_show_streamlit_primary_note() -> None:
    base = Path("web_cabinet/templates/base.html").read_text(encoding="utf-8")
    login = Path("web_cabinet/templates/login.html").read_text(encoding="utf-8")
    assert "hidden fallback/internal admin-debug surface" in base
    assert "streamlit_primary_url" in base
    assert "Основной пользовательский вход" in login


def test_t18_10_web_cabinet_doc_marks_fastapi_as_fallback() -> None:
    doc = Path("docs/web_cabinet.md").read_text(encoding="utf-8")
    assert "hidden fallback/internal admin-debug surface" in doc
    assert "soft-deprecated" in doc
