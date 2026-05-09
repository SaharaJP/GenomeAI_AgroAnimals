"""Acceptance: NPV cull/keep model per thesis §3.2.4 + composite health-score (P1-2b)."""
from __future__ import annotations
import pandas as pd
import pytest
from web_cabinet.ai.npv_cull import (
    DEFAULTS, compute_npv_keep, compute_npv_cull, recommend,
    _health_burden_signal,
)
from web_cabinet.ai.context_helpers.demo_loader import DemoDataStore


def test_defaults_present():
    """All economic constants required by formulas 3.18–3.20 must be defined."""
    required = {
        "milk_price_rub_per_kg",
        "meat_price_rub_per_kg_live",
        "heifer_replacement_cost_rub",
        "feed_cost_rub_per_kg_milk",
        "vet_cost_rub_per_year",
        "discount_rate_default",
        "horizon_years_default",
    }
    assert required.issubset(set(DEFAULTS.keys()))
    assert DEFAULTS["discount_rate_default"] > 0
    assert DEFAULTS["horizon_years_default"] >= 1


def test_recommend_shape_for_starlet(rich_store):
    """Звёздочка (4821, productive) — recommend() must return full schema."""
    result = recommend(animal_id="4821", store=rich_store)
    for key in ("animal_id", "decision", "npv_keep", "npv_cull",
                "rationale", "sensitivity_table", "narrative_md", "evidence_chips"):
        assert key in result, f"missing key: {key}"
    assert result["decision"] in ("keep", "cull")
    assert isinstance(result["sensitivity_table"], list)
    assert len(result["sensitivity_table"]) >= 9, "sensitivity ≥3×3=9 cells per brief"


def test_compute_npv_keep_positive_for_productive_cow(rich_store):
    """A high-yield young cow's NPV_keep must be a positive RUB amount."""
    npv = compute_npv_keep(animal_id="4821", store=rich_store, horizon_years=4, r=0.13)
    assert npv["npv_rub"] > 0
    assert npv["horizon_months"] == 4 * 12
    assert "monthly_breakdown" in npv


def test_compute_npv_cull_returns_negative_or_zero(rich_store):
    """NPV_cull = S_meat − R_heifer + Σ(heifer earnings); usually small or negative."""
    npv = compute_npv_cull(animal_id="4821", store=rich_store, horizon_years=4, r=0.13)
    assert "npv_rub" in npv
    assert "salvage_meat_rub" in npv
    assert "replacement_cost_rub" in npv
    assert npv["replacement_cost_rub"] == DEFAULTS["heifer_replacement_cost_rub"]


def test_starlet_4821_recommends_keep(rich_store):
    """Звёздочка — productive cow with positive NPV_keep margin."""
    r = recommend("4821", rich_store)
    assert r["decision"] == "keep", (
        f"NPV_keep {r['npv_keep']['npv_rub']} vs NPV_cull {r['npv_cull']['npv_rub']}"
    )


def test_malina_3891_recommends_cull(rich_store):
    """Малина — older cow tagged for culling; NPV_cull should win.

    Note: the rich_store fixture seeds cow 7001 (Малина) not 3891.
    The investor_v1 CSV dataset uses 3891 for Малина.
    Skip if 3891 is not in the store (covered in endpoint acceptance instead).
    """
    df = rich_store.animals()
    if df.empty or "3891" not in df["animal_id"].astype(str).tolist():
        pytest.skip(
            "rich_store does not seed cow 3891 (Малина); covered in endpoint acceptance instead"
        )
    r = recommend("3891", rich_store)
    assert r["decision"] == "cull", (
        f"NPV_keep {r['npv_keep']['npv_rub']} vs NPV_cull {r['npv_cull']['npv_rub']}"
    )


# ── P1-2b composite health-score component tests ──────────────────────────


def _store_with(animals=None, lactations=None, health=None, milk=None) -> DemoDataStore:
    """Build a minimal DemoDataStore from inline DataFrames."""
    frames = {}
    frames["dm_animals"] = pd.DataFrame(animals or [
        dict(tenant_id="default", animal_id="C1", farm_id="F", ear_tag="C1",
             breed="Holstein", sex="F", birth_date="2020-01-01",
             is_alive=True, status="active"),
    ])
    frames["dm_lactations"] = pd.DataFrame(lactations or [])
    frames["dm_health_events"] = pd.DataFrame(health or [])
    if milk is not None:
        frames["milk_yields"] = pd.DataFrame(milk)
    return DemoDataStore.from_dataframes(**frames)


def test_health_signal_clean_cow_returns_baseline_multipliers():
    s = _store_with(
        lactations=[dict(animal_id="C1", lactation_no=2, calving_date="2025-12-01",
                         dryoff_date="2026-09-01", days_in_milk=120,
                         milk_305d_kg=9000, fat_pct=3.8, protein_pct=3.2)],
    )
    signal = _health_burden_signal("C1", s)
    assert signal["components"]["total_score"] == 0.0
    assert signal["milk_factor"] == 1.0
    assert signal["vet_factor"] == 1.0
    assert signal["cull_prob_factor"] == 1.0


def test_health_signal_late_dim_alone_lowers_milk_factor():
    """A clean cow at DIM=300 should still pick up the late-DIM component."""
    s = _store_with(
        lactations=[dict(animal_id="C1", lactation_no=2, calving_date="2025-06-01",
                         dryoff_date="2026-05-01", days_in_milk=300,
                         milk_305d_kg=9000, fat_pct=3.8, protein_pct=3.2)],
    )
    signal = _health_burden_signal("C1", s)
    assert signal["components"]["late_dim_score"] == pytest.approx(2.0, abs=0.01)
    assert signal["components"]["mastitis_score"] == 0.0
    assert signal["milk_factor"] < 1.0


def test_health_signal_high_parity_alone():
    """Lactation_no=5 → parity_score = (5-3)*0.8 = 1.6."""
    s = _store_with(
        lactations=[dict(animal_id="C1", lactation_no=5, calving_date="2025-12-01",
                         dryoff_date="2026-09-01", days_in_milk=100,
                         milk_305d_kg=9000, fat_pct=3.8, protein_pct=3.2)],
    )
    signal = _health_burden_signal("C1", s)
    assert signal["components"]["parity_score"] == pytest.approx(1.6, abs=0.01)


def test_health_signal_two_high_mastitis_dominates():
    s = _store_with(
        health=[
            dict(tenant_id="default", event_id="E1", animal_id="C1",
                 event_date="2026-02-01", event_type="mastitis", severity="high", notes=""),
            dict(tenant_id="default", event_id="E2", animal_id="C1",
                 event_date="2026-03-01", event_type="mastitis", severity="high", notes=""),
        ],
        lactations=[dict(animal_id="C1", lactation_no=2, calving_date="2025-12-01",
                         dryoff_date="2026-09-01", days_in_milk=100,
                         milk_305d_kg=9000, fat_pct=3.8, protein_pct=3.2)],
    )
    signal = _health_burden_signal("C1", s)
    assert signal["components"]["mastitis_score"] == 3.0
    assert signal["recurrent"] is True
    assert signal["milk_factor"] < 0.85


def test_health_signal_components_compose_additively():
    """Multiple signals stack — total = sum(component scores)."""
    s = _store_with(
        health=[
            dict(tenant_id="default", event_id="E1", animal_id="C1",
                 event_date="2026-02-01", event_type="mastitis", severity="high", notes=""),
            dict(tenant_id="default", event_id="E2", animal_id="C1",
                 event_date="2026-03-01", event_type="mastitis", severity="high", notes=""),
            dict(tenant_id="default", event_id="E3", animal_id="C1",
                 event_date="2026-04-01", event_type="lameness", severity="medium", notes=""),
        ],
        lactations=[dict(animal_id="C1", lactation_no=4, calving_date="2025-06-01",
                         dryoff_date="2026-05-01", days_in_milk=290,
                         milk_305d_kg=8500, fat_pct=3.8, protein_pct=3.2)],
    )
    signal = _health_burden_signal("C1", s)
    cs = signal["components"]
    expected = cs["mastitis_score"] + cs["late_dim_score"] + cs["parity_score"] + cs["scc_score"] + cs["lameness_score"]
    assert cs["total_score"] == pytest.approx(expected, abs=0.01)
    # All four configured signals fire (mastitis 3.0, late_dim ~1.8, parity 0.8, lameness 1.0)
    assert cs["mastitis_score"] > 0
    assert cs["late_dim_score"] > 0
    assert cs["parity_score"] > 0
    assert cs["lameness_score"] > 0


def test_health_signal_single_high_mastitis_does_not_trigger_recurrent_flag():
    """Backward-compat: 'recurrent' flag remains binary (≥2 high)."""
    s = _store_with(
        health=[
            dict(tenant_id="default", event_id="E1", animal_id="C1",
                 event_date="2026-02-01", event_type="mastitis", severity="high", notes=""),
        ],
    )
    signal = _health_burden_signal("C1", s)
    assert signal["recurrent"] is False
    assert signal["components"]["mastitis_score"] == 1.5  # 1 × 1.5
