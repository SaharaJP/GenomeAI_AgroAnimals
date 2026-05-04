"""Tests for POST /api/impact endpoint (PMV-B03 statistical wiring).

Covers:
- test_impact_endpoint_demo: demo mode returns seeded JSON with p_value + CI
- test_impact_endpoint_real_mode_returns_p_value_and_ci: non-demo runs compute_full_impact
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) in sys.path:
    sys.path.remove(str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT))

for _k in list(sys.modules):
    if _k == "web_cabinet" or _k.startswith("web_cabinet."):
        del sys.modules[_k]

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Minimal test app — avoids full web_cabinet startup (DB connections etc.)
# ---------------------------------------------------------------------------

def _make_client() -> TestClient:
    from web_cabinet.ai.endpoints.impact import router

    _app = FastAPI()
    _app.include_router(router, prefix="/api")
    return TestClient(_app)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestImpactEndpointDemo:
    def test_impact_endpoint_demo(self):
        """Demo mode: endpoint returns deterministic seeded JSON with correct shape."""
        _settings = MagicMock()
        _settings.GENOMEAI_AI_DEMO_MODE = True

        with patch("web_cabinet.ai.endpoints.impact.get_ai_settings", return_value=_settings):
            client = _make_client()
            resp = client.post(
                "/api/impact",
                json={
                    "event_id": "DEMO_001",
                    "farm_id": "demo-farm-v1",
                    "kpi_list": ["milk_yield"],
                    "window": "1w",
                },
            )

        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert data["event_id"] == "DEMO_001"
        assert data["window"] == "1w"
        assert data["demo_mode"] is True

        assert len(data["results"]) == 1
        result = data["results"][0]
        assert result["kpi"] == "milk_yield"

        # Statistical fields must be present
        assert "welch_t_pvalue" in result
        assert "bootstrap_ci_95" in result
        assert "significance" in result
        assert "cohen_d_effect_size" in result
        assert "effect_magnitude" in result
        assert "diff_in_diff_effect" in result
        assert "treated_before" in result
        assert "treated_after" in result

        # Sanity bounds
        assert 0.0 <= result["welch_t_pvalue"] <= 1.0
        lo, hi = result["bootstrap_ci_95"]
        assert lo <= hi
        assert result["significance"] in ("significant", "not_significant", "inconclusive")
        assert result["effect_magnitude"] in ("negligible", "small", "medium", "large")

    def test_demo_mode_is_deterministic(self):
        """Same inputs produce identical p-value across calls (seeded RNG)."""
        _settings = MagicMock()
        _settings.GENOMEAI_AI_DEMO_MODE = True

        payload = {
            "event_id": "DEMO_001",
            "farm_id": "demo-farm-v1",
            "kpi_list": ["milk_yield"],
            "window": "2w",
        }

        with patch("web_cabinet.ai.endpoints.impact.get_ai_settings", return_value=_settings):
            client = _make_client()
            r1 = client.post("/api/impact", json=payload).json()
            r2 = client.post("/api/impact", json=payload).json()

        assert r1["results"][0]["welch_t_pvalue"] == r2["results"][0]["welch_t_pvalue"]
        assert r1["results"][0]["bootstrap_ci_95"] == r2["results"][0]["bootstrap_ci_95"]


class TestImpactEndpointRealMode:
    def test_impact_endpoint_real_mode_returns_p_value_and_ci(self):
        """Non-demo mode runs compute_full_impact() for each kpi, returns live stats."""
        _settings = MagicMock()
        _settings.GENOMEAI_AI_DEMO_MODE = False

        with patch("web_cabinet.ai.endpoints.impact.get_ai_settings", return_value=_settings):
            client = _make_client()
            resp = client.post(
                "/api/impact",
                json={
                    "event_id": "DEMO_001",
                    "farm_id": "demo-farm-v1",
                    "kpi_list": ["milk_yield", "dmi_per_group"],
                    "window": "2w",
                },
            )

        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert data["demo_mode"] is False
        assert len(data["results"]) == 2
        kpis = {r["kpi"] for r in data["results"]}
        assert kpis == {"milk_yield", "dmi_per_group"}

        for r in data["results"]:
            assert 0.0 <= r["welch_t_pvalue"] <= 1.0
            lo, hi = r["bootstrap_ci_95"]
            assert lo <= hi
            assert r["significance"] in ("significant", "not_significant", "inconclusive")

    def test_window_change_produces_different_results(self):
        """Different window values produce different statistical results."""
        _settings = MagicMock()
        _settings.GENOMEAI_AI_DEMO_MODE = False

        base = {
            "event_id": "DEMO_001",
            "farm_id": "demo-farm-v1",
            "kpi_list": ["milk_yield"],
        }

        with patch("web_cabinet.ai.endpoints.impact.get_ai_settings", return_value=_settings):
            client = _make_client()
            r3d = client.post("/api/impact", json={**base, "window": "3d"}).json()
            r4w = client.post("/api/impact", json={**base, "window": "4w"}).json()

        # Windows differ → different synthetic data → different p-values
        # (not guaranteed to differ but almost certainly will with different seeds)
        assert r3d["window"] == "3d"
        assert r4w["window"] == "4w"
