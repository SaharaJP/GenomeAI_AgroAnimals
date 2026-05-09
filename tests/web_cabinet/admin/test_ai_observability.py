"""Tests for /api/admin/ai/* endpoints."""
import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def app_client():
    os.environ.setdefault("GENOMEAI_DB_DSN", os.environ.get("TEST_PG_DSN", "postgresql://localhost/genomeai_test"))
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


def _seed_call(conn, **kwargs):
    defaults = dict(
        user_id="admin", endpoint="ask-farm", task_type="default",
        model="claude-sonnet-4-6",
        input_tokens=100, output_tokens=50,
        cache_creation_tokens=0, cache_read_tokens=0,
        cost_usd=0.001, latency_ms=850, error=None,
        prompt="тест", response="ответ",
        evidence_chips='[]', tools_used='[]',
    )
    defaults.update(kwargs)
    cols = ", ".join(defaults.keys())
    placeholders = ", ".join(["%s"] * len(defaults))
    with conn.cursor() as cur:
        cur.execute(
            f"INSERT INTO ai_call_log ({cols}) VALUES ({placeholders}) RETURNING id",
            tuple(defaults.values()),
        )
        row = cur.fetchone()
    conn.commit()
    # Handle either tuple or dict_row factories
    return row[0] if not isinstance(row, dict) else row["id"]


def test_stats_requires_auth(app_client):
    resp = app_client.get("/api/admin/ai/stats")
    assert resp.status_code in (401, 403)


def test_stats_happy_path(app_client, admin_token):
    from core.infra.postgres_compat import connect_postgres_compat
    conn = connect_postgres_compat()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM ai_call_log WHERE endpoint LIKE 'test_stats_%'")
    conn.commit()
    for i in range(5):
        _seed_call(conn, endpoint="test_stats_a", latency_ms=100 + i*100, cost_usd=0.01)
    conn.close()

    resp = app_client.get(
        "/api/admin/ai/stats?period_hours=24",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["count"] >= 5
    assert "p50_latency_ms" in data
    assert "p95_latency_ms" in data
    assert data["total_cost_usd"] >= 0.05
    assert data["error_count"] >= 0


def test_calls_list(app_client, admin_token):
    resp = app_client.get(
        "/api/admin/ai/calls?limit=10",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    if body:
        row = body[0]
        assert "prompt" not in row
        assert "response" not in row
        for key in ("id", "created_at", "endpoint", "model", "latency_ms", "total_tokens", "cost_usd", "has_error"):
            assert key in row, f"missing {key}"


def test_call_detail(app_client, admin_token):
    from core.infra.postgres_compat import connect_postgres_compat
    conn = connect_postgres_compat()
    call_id = _seed_call(conn, endpoint="test_detail", prompt="тест-prompt", response="тест-resp")
    conn.close()

    resp = app_client.get(
        f"/api/admin/ai/calls/{call_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == call_id
    assert data["prompt"] == "тест-prompt"
    assert data["response"] == "тест-resp"


def test_call_detail_404(app_client, admin_token):
    resp = app_client.get(
        "/api/admin/ai/calls/99999999",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 404


def test_grounding_rate(app_client, admin_token):
    from core.infra.postgres_compat import connect_postgres_compat
    conn = connect_postgres_compat()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM ai_call_log WHERE endpoint LIKE 'test_grounding_%'")
    conn.commit()
    _seed_call(conn, endpoint="test_grounding_with", evidence_chips='["chip1"]')
    _seed_call(conn, endpoint="test_grounding_with", evidence_chips='["chip1","chip2"]')
    _seed_call(conn, endpoint="test_grounding_without", evidence_chips='[]')
    conn.close()

    resp = app_client.get(
        "/api/admin/ai/grounding-rate?period_hours=1",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 3
    assert body["with_evidence"] >= 2
    assert body["without_evidence"] >= 1


def test_grounding_rate_counts_tool_use_as_grounded(app_client, admin_token):
    """P1-1d: a call with non-empty tools_used (and no evidence_chips) is grounded."""
    from core.infra.postgres_compat import connect_postgres_compat
    conn = connect_postgres_compat()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM ai_call_log WHERE endpoint LIKE 'test_grounding_tooluse_%'")
    conn.commit()
    # Tool-use only — no evidence_chips
    _seed_call(
        conn,
        endpoint="test_grounding_tooluse_with",
        evidence_chips='[]',
        tools_used='[{"name":"get_animal_profile","input":{"cow_id":"4821"}}]',
    )
    _seed_call(
        conn,
        endpoint="test_grounding_tooluse_with",
        evidence_chips='[]',
        tools_used='[{"name":"calculate_cull_npv","input":{"animal_id":"7001"}}]',
    )
    # Neither evidence_chips nor tools_used — counts as ungrounded
    _seed_call(
        conn,
        endpoint="test_grounding_tooluse_without",
        evidence_chips='[]',
        tools_used='[]',
    )
    conn.close()

    resp = app_client.get(
        "/api/admin/ai/grounding-rate?period_hours=1",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    # Must include both the 2 tool-use rows and the 1 ungrounded row introduced here
    assert body["with_evidence"] >= 2
    assert body["without_evidence"] >= 1
