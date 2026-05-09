"""Fixtures for /api/animals/* endpoint tests."""
import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def app_client():
    os.environ.setdefault(
        "GENOMEAI_DB_DSN",
        os.environ.get("TEST_PG_DSN", "postgresql://localhost/genomeai_test"),
    )
    from web_cabinet.app import app
    return TestClient(app)


@pytest.fixture(scope="module")
def admin_token(app_client) -> str:
    resp = app_client.post(
        "/api/app/v1/auth/login",
        json={"username": "admin", "password": "admin", "tenant_id": "default"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["tokens"]["access_token"]
