"""Seed-on-demand persistence for TL_-prefixed seeded timeline events.

Prior bug: PATCH/DELETE on seeded TL_001..TL_012 returned 404 because the rows
existed only in data/demo/investor_v1/timeline_events_seeded.json, never in the
timeline_events Postgres table. Fix materializes the seed row on first edit/delete
and uses soft-delete (source='deleted') as a tombstone so the JSON copy doesn't
reappear after deletion.
"""
from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient


_TEST_IDS = ("TL_001", "TL_002", "TL_DOES_NOT_EXIST")


def _db_dsn() -> str:
    return os.environ.get("GENOMEAI_TEST_DSN") or os.environ.get(
        "GENOMEAI_DB_DSN", "postgresql://localhost/genomeai_test"
    )


@pytest.fixture(scope="module")
def app_client():
    os.environ.setdefault("GENOMEAI_DB_DSN", _db_dsn())
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


@pytest.fixture
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(autouse=True)
def _hard_reset_seed_rows():
    """Hard-delete any prior tombstones/materialised seed rows before each test."""
    import psycopg
    with psycopg.connect(_db_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM timeline_events WHERE timeline_event_id = ANY(%s)",
                (list(_TEST_IDS),),
            )
        conn.commit()
    yield


def test_patch_seeded_event_materialises_into_db(app_client, auth_headers):
    event_id = "TL_001"

    resp = app_client.patch(
        f"/api/timeline/events/{event_id}",
        headers=auth_headers,
        json={"title": "Звёздочка — мастит (отредактировано)"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True, "event_id": event_id}

    listing = app_client.get("/api/timeline/events", headers=auth_headers).json()
    matches = [e for e in listing["events"] if e.get("timeline_event_id") == event_id]
    assert len(matches) == 1, f"expected 1 row for {event_id}, got {len(matches)}"
    assert matches[0]["title"] == "Звёздочка — мастит (отредактировано)"


def test_delete_seeded_event_returns_200_and_does_not_reappear(app_client, auth_headers):
    event_id = "TL_002"

    resp = app_client.delete(
        f"/api/timeline/events/{event_id}", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True, "deleted": event_id}

    listing = app_client.get("/api/timeline/events", headers=auth_headers).json()
    matches = [e for e in listing["events"] if e.get("timeline_event_id") == event_id]
    assert matches == [], f"deleted seed event resurfaced: {matches}"


def test_unknown_event_id_still_404(app_client, auth_headers):
    resp = app_client.patch(
        "/api/timeline/events/TL_DOES_NOT_EXIST",
        headers=auth_headers,
        json={"title": "x"},
    )
    assert resp.status_code == 404
