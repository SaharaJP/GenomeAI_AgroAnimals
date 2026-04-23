from __future__ import annotations

from streamlit_app.glossary_v3 import load_glossary, index_terms


def test_glossary_contains_core_kpi_terms() -> None:
    cfg = load_glossary()
    idx = index_terms(cfg)

    # minimal set used across role Home/pages
    expected = {
        "milk_total_kg_1d",
        "milk_total_kg_7d",
        "milk_avg_kg_per_cow_1d",
        "fat_pct_avg_7d",
        "protein_pct_avg_7d",
        "scc_avg_7d",
        "mastitis_events_30d",
        "health_events_30d",
        "inseminations_30d",
        "pregnancy_positive_90d",
        "margin_rub_7d",
        "alerts_open_count",
    }

    missing = [k for k in sorted(expected) if k not in idx]
    assert not missing, f"missing glossary keys: {missing}"
