"""KPI computation helpers for build_farm_context."""
from __future__ import annotations

import datetime
from typing import Any

import pandas as pd

from web_cabinet.ai.context_helpers.demo_loader import DemoDataStore


def _to_ts(d: Any) -> pd.Timestamp:
    return pd.Timestamp(d)


def _farm_animal_ids(store: DemoDataStore, farm_id: str) -> list[str]:
    animals = store.animals()
    if animals.empty:
        return []
    # Match loosely: "demo-farm-v1" matches DEMO_FARM_* or any farm
    mask = animals["farm_id"].notna()
    if farm_id and farm_id.lower() not in ("all", ""):
        # Try exact match first, fall back to "all animals" for demo
        exact = animals[animals["farm_id"] == farm_id]
        if not exact.empty:
            return exact["animal_id"].tolist()
    return animals[mask]["animal_id"].tolist()


def compute_today_kpi(
    store: DemoDataStore,
    farm_id: str,
    as_of: datetime.date,
) -> dict:
    """Return today_kpi dict for build_farm_context."""
    as_ts = _to_ts(as_of)
    animal_ids = _farm_animal_ids(store, farm_id)

    # ---- milk yield avg ----
    milkings = store.milkings()
    avg_yield = 0.0
    scc_bulk_k = 0.0
    if not milkings.empty and "milk_kg" in milkings.columns:
        milkings = milkings.copy()
        milkings["date"] = pd.to_datetime(milkings["date"], errors="coerce")
        farm_mk = milkings[milkings["animal_id"].isin(animal_ids)]
        if not farm_mk.empty:
            latest_date = farm_mk["date"].max()
            latest = farm_mk[farm_mk["date"] == latest_date]
            avg_yield = float(latest["milk_kg"].mean())
            if "scc_cells_ml" in latest.columns:
                scc_bulk_k = float(latest["scc_cells_ml"].mean()) / 1000

    # ---- withdrawal count ----
    treatments = store.treatments()
    withdrawal_count = 0
    if not treatments.empty and "withdrawal_end_date" in treatments.columns:
        tr = treatments.copy()
        tr["withdrawal_end_date"] = pd.to_datetime(tr["withdrawal_end_date"], errors="coerce")
        active = tr[
            tr["animal_id"].isin(animal_ids)
            & (tr["withdrawal_end_date"] >= as_ts)
        ]
        withdrawal_count = len(active)

    # ---- fresh cows (calved in last 21 days) ----
    repro = store.repro_events()
    fresh_count = 0
    conception_rate = 0.0
    if not repro.empty:
        repro = repro.copy()
        repro["event_date"] = pd.to_datetime(repro["event_date"], errors="coerce")
        farm_repro = repro[repro["animal_id"].isin(animal_ids)]
        fresh_df = farm_repro[
            (farm_repro["event_type"] == "fresh")
            & (farm_repro["event_date"] >= as_ts - pd.Timedelta(days=21))
        ]
        fresh_count = len(fresh_df)

        ins = farm_repro[farm_repro["event_type"] == "insemination"]
        if not ins.empty and "result" in ins.columns:
            confirmed = ins[ins["result"].str.lower().isin(["confirmed", "pregnant", "pos"])]
            conception_rate = round(len(confirmed) / max(len(ins), 1) * 100, 1)

    # ---- health index ----
    he = store.health_events()
    health_index = 95
    if not he.empty:
        he = he.copy()
        he["event_date"] = pd.to_datetime(he["event_date"], errors="coerce")
        recent = he[
            he["animal_id"].isin(animal_ids)
            & (he["event_date"] >= as_ts - pd.Timedelta(days=7))
        ]
        sev_map = {"low": 2, "medium": 5, "high": 10, "critical": 15, "warn": 3}
        deduction = sum(sev_map.get(str(s).lower(), 3) for s in recent.get("severity", []))
        health_index = max(0, 100 - deduction)

    return {
        "milk_yield_avg_kg_per_cow": round(avg_yield, 2),
        "scc_bulk_k": round(scc_bulk_k, 1),
        "fresh_cows_count": int(fresh_count),
        "cows_in_withdrawal_count": int(withdrawal_count),
        "conception_rate_21d_pct": round(conception_rate, 1),
        "health_index_score": int(health_index),
    }


def compute_period_trends(
    store: DemoDataStore,
    farm_id: str,
    as_of: datetime.date,
    period_days: int,
) -> list[dict]:
    """
    Compare current period vs previous period for each KPI.
    Returns list of {kpi, value, prev_value, delta, direction}.
    """
    current_kpi = compute_today_kpi(store, farm_id, as_of)

    prev_date = as_of - datetime.timedelta(days=period_days)
    prev_kpi = compute_today_kpi(store, farm_id, prev_date)

    trends = []
    for key, value in current_kpi.items():
        prev = prev_kpi.get(key, value)
        try:
            delta = round(float(value) - float(prev), 2)
        except (TypeError, ValueError):
            delta = 0.0
        if abs(delta) < 0.01:
            direction = "→"
        elif delta > 0:
            # For SCC and withdrawal higher is worse
            direction = "↑" if key not in ("scc_bulk_k", "cows_in_withdrawal_count") else "↑"
        else:
            direction = "↓"
        trends.append({
            "kpi": key,
            "value": value,
            "prev_value": prev,
            "delta": delta,
            "direction": direction,
        })
    return trends
