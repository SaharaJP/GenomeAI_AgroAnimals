"""Integration tests for GET /api/animals/{id}/cull-recommendation."""
from __future__ import annotations
import pytest


def test_cull_endpoint_unauth_returns_401_or_403(app_client):
    resp = app_client.get("/api/animals/4821/cull-recommendation")
    assert resp.status_code in (401, 403)


def test_cull_endpoint_404_for_unknown_animal(app_client, admin_token):
    resp = app_client.get(
        "/api/animals/NONEXISTENT_999/cull-recommendation",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 404


def test_cull_endpoint_starlet_4821_full_schema(app_client, admin_token):
    """Звёздочка (4821) — endpoint returns full §3.2.4 schema."""
    resp = app_client.get(
        "/api/animals/4821/cull-recommendation",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["animal_id"] == "4821"
    assert body["decision"] in ("keep", "cull")
    for key in ("npv_keep", "npv_cull", "rationale", "sensitivity_table",
                "narrative_md", "evidence_chips"):
        assert key in body, f"missing key: {key}"
    assert isinstance(body["sensitivity_table"], list)
    assert len(body["sensitivity_table"]) >= 9, "brief requires >=9 sensitivity cells"
    # Each sensitivity row must have the expected columns
    for row in body["sensitivity_table"]:
        for col in ("discount_rate", "milk_price_rub_per_kg", "npv_keep_rub", "npv_cull_rub", "decision"):
            assert col in row


def test_cull_endpoint_starlet_recommends_keep(app_client, admin_token):
    """Brief acceptance: Звёздочка (4821) -> keep."""
    resp = app_client.get(
        "/api/animals/4821/cull-recommendation",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["decision"] == "keep"


def test_cull_endpoint_malina_recommends_cull(app_client, admin_token):
    """Brief acceptance: Малина (3891) -> cull.

    NB: this test may FAIL if Малина's projected milk under the default
    constants doesn't yield NPV_keep < NPV_cull. Phase 4 calibration
    will tune constants if needed.
    """
    resp = app_client.get(
        "/api/animals/3891/cull-recommendation",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    if body["decision"] != "cull":
        pytest.fail(
            f"Малина (3891) recommended {body['decision']!r}, expected 'cull'. "
            f"NPV_keep={body['npv_keep']['npv_rub']}, NPV_cull={body['npv_cull']['npv_rub']}. "
            f"Phase 4 needs to recalibrate constants."
        )
    assert body["decision"] == "cull"
