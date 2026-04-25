"""Tests for POST /api/ai/morning-brief/{brief_id}/approve endpoint."""
from __future__ import annotations

from unittest.mock import patch


def _make_app():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from web_cabinet.ai.endpoints.morning_brief import router
    app = FastAPI()
    app.include_router(router, prefix="/api/ai")
    return TestClient(app)


def test_approve_returns_approved_and_count():
    client = _make_app()
    payload = {
        "farm_id": "demo-farm-v1",
        "actions": [
            {"action": "Осмотреть №847 на мастит", "priority": "high", "due": "10:00", "role": "vet"},
            {"action": "Проверить аппарат", "priority": "medium", "due": None, "role": "operator"},
        ],
    }

    with patch("web_cabinet.ai.endpoints.morning_brief._create_tasks_for_actions", return_value=2):
        resp = client.post("/api/ai/morning-brief/test-brief-id/approve", json=payload)

    assert resp.status_code == 200
    data = resp.json()
    assert data["approved"] is True
    assert data["tasks_created"] == 2


def test_approve_graceful_on_task_error():
    """Ошибка создания задач не блокирует approve."""
    client = _make_app()
    payload = {
        "farm_id": "demo-farm-v1",
        "actions": [
            {"action": "Осмотреть", "priority": "low", "due": None, "role": "vet"},
        ],
    }

    with patch("web_cabinet.ai.endpoints.morning_brief._create_tasks_for_actions", side_effect=Exception("db down")):
        resp = client.post("/api/ai/morning-brief/any-id/approve", json=payload)

    assert resp.status_code == 200
    data = resp.json()
    assert data["approved"] is True
    assert data["tasks_created"] == 0
