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


def test_weekly_plan_director_approve_creates_tasks_and_audit(client: TestClient):
    _login(client, "zootech", "zootech")

    r_create = client.post(
        "/api/weekly_plans_v1",
        json={
            "name": "План на неделю",
            "week_start": "2026-03-02",
            "summary": "Проверки и разбор отклонений",
            "data_version": "dv_demo",
            "action_items": [
                {"title": "Разобрать QC ошибки по milk.csv"},
                {"title": "Проверить группу сухостоя"},
                {"title": "Сверить осеменения за 7 дней"},
            ],
        },
    )
    assert r_create.status_code == 200
    plan_id = r_create.json()["plan_id"]

    # zootech cannot approve
    r_forbidden = client.post(f"/api/weekly_plans_v1/{plan_id}/approve", json={"comment": "ok"})
    assert r_forbidden.status_code == 403

    client.get("/logout")
    _login(client, "director", "director")

    r_approve = client.post(
        f"/api/weekly_plans_v1/{plan_id}/approve",
        json={"comment": "Утверждаю. Создать задачи и закрыть до пятницы."},
    )
    assert r_approve.status_code == 200
    payload = r_approve.json()
    assert payload.get("ok") is True
    tasks = payload.get("tasks") or {}
    assert len(tasks.get("tasks_created") or []) == 3

    p = client.get(f"/api/weekly_plans_v1/{plan_id}").json()
    assert p["status"] == "approved"
    assert p.get("approved_at")
    assert p.get("approved_by_username") == "director"
    assert p.get("tasks_created_run_id")
    assert p.get("rejected_at") is None

    # tasks exist (by type)
    r_tasks = client.get("/api/tasks_v1", params={"task_type": "weekly_plan.action", "limit": 50})
    assert r_tasks.status_code == 200
    items = r_tasks.json().get("tasks") or []
    titles = {t.get("title") for t in items}
    assert "Разобрать QC ошибки по milk.csv" in titles
    assert "Проверить группу сухостоя" in titles
    assert "Сверить осеменения за 7 дней" in titles

    ra = client.get("/api/audit", params={"action": "weekly_plan.approve"})
    assert ra.status_code == 200
    rows = ra.json().get("rows") or []
    assert any(r.get("object_id") == plan_id for r in rows)


def test_weekly_plan_reject_keeps_draft_and_clears_on_approve(client: TestClient):
    _login(client, "zootech", "zootech")
    r_create = client.post(
        "/api/weekly_plans_v1",
        json={
            "name": "План B",
            "week_start": "2026-03-02",
            "action_items": [{"title": "Пункт 1"}],
        },
    )
    plan_id = r_create.json()["plan_id"]

    client.get("/logout")
    _login(client, "director", "director")

    r_reject = client.post(f"/api/weekly_plans_v1/{plan_id}/reject", json={"comment": "Добавь конкретику"})
    assert r_reject.status_code == 200

    p = client.get(f"/api/weekly_plans_v1/{plan_id}").json()
    assert p["status"] == "draft"
    assert p.get("rejected_at")
    assert p.get("rejected_by_username") == "director"
    assert p.get("rejection_comment") == "Добавь конкретику"

    # approve clears rejection metadata
    r_approve = client.post(f"/api/weekly_plans_v1/{plan_id}/approve", json={"comment": "OK"})
    assert r_approve.status_code == 200
    p2 = client.get(f"/api/weekly_plans_v1/{plan_id}").json()
    assert p2["status"] == "approved"
    assert p2.get("rejected_at") is None
    assert p2.get("rejection_comment") is None
